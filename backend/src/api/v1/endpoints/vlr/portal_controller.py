"""
Vendor Portal API endpoints.
Thin controller — provides vendor-facing portal access via token-based authentication.
Does NOT use standard JWT auth; uses unique portal_token stored on ReconciliationCase.

Routes:
- GET    /api/v1/vlr/portal/auth/{token}   — Authenticate via portal token
- POST   /api/v1/vlr/portal/upload         — Upload vendor statement file
- GET    /api/v1/vlr/portal/statement      — Get reconciliation statement
- POST   /api/v1/vlr/portal/sign-off       — Record digital sign-off

Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8, 4.9, 4.10, 4.11
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Request, UploadFile, status
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.v1.schemas.vlr.portal_schemas import (
    PortalAuthResponse,
    PortalSignOffRequest,
    PortalSignOffResponse,
    PortalStatementResponse,
    PortalUploadResponse,
)
from src.domain.exceptions.vlr import (
    FileValidationException,
    TokenExpiredException,
    UploadLimitExceededException,
)
from src.domain.services.vlr.file_parser_service import FileParserService
from src.infrastructure.database.models.vlr.ledger_entry_model import LedgerEntryModel
from src.infrastructure.database.models.vlr.match_result_model import MatchResultModel
from src.infrastructure.database.models.vlr.portal_sign_off_model import PortalSignOffModel
from src.infrastructure.database.models.vlr.reconciliation_case_model import (
    ReconciliationCaseModel,
)
from src.infrastructure.database.models.vlr.reco_exception_model import RecoExceptionModel
from src.infrastructure.database.repositories.vlr.case_repository_impl import (
    CaseRepositoryImpl,
)
from src.infrastructure.database.repositories.vlr.ledger_entry_repository_impl import (
    LedgerEntryRepositoryImpl,
)
from src.infrastructure.database.session import get_db_session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/vlr/portal", tags=["VLR - Vendor Portal"])

# Maximum upload attempts allowed per case
MAX_UPLOAD_ATTEMPTS = 5


# ──────────────────────────────────────────────────────────────────────
# Dependencies
# ──────────────────────────────────────────────────────────────────────


async def _validate_portal_token(
    token: str,
    session: AsyncSession,
) -> ReconciliationCaseModel:
    """
    Validate a portal token and return the associated case.

    Raises:
        HTTPException 401: Token not found or case deleted.
        HTTPException 401: Token has expired.
    """
    case_repo = CaseRepositoryImpl(session)
    case = await case_repo.get_by_token(token)

    if case is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired portal token.",
        )

    # Check token expiry
    if case.token_expiry and case.token_expiry < datetime.now(timezone.utc):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Portal token has expired. Please contact the reconciliation team for a new invitation.",
        )

    return case


async def _get_case_from_header(
    request: Request,
    x_portal_token: str = Header(..., alias="X-Portal-Token"),
    session: AsyncSession = Depends(get_db_session),
) -> ReconciliationCaseModel:
    """
    FastAPI dependency: extract and validate portal token from X-Portal-Token header.
    Used by upload, statement, and sign-off endpoints.
    """
    return await _validate_portal_token(x_portal_token, session)


# ──────────────────────────────────────────────────────────────────────
# Endpoints
# ──────────────────────────────────────────────────────────────────────


@router.get(
    "/auth/{token}",
    response_model=PortalAuthResponse,
    summary="Authenticate via portal token",
)
async def authenticate_token(
    token: str,
    session: AsyncSession = Depends(get_db_session),
) -> PortalAuthResponse:
    """
    GET /api/v1/vlr/portal/auth/{token}

    Validates the portal token and returns case context for the vendor portal.
    No username/password required — the token itself is the credential.

    Requirement 4.1: Token-based access without username/password.
    Requirement 4.2: Token expiry validation.
    """
    case = await _validate_portal_token(token, session)

    return PortalAuthResponse(
        case_id=case.id,
        vendor_id=case.vendor_id,
        status=case.status,
        upload_count=case.upload_count,
        max_uploads=MAX_UPLOAD_ATTEMPTS,
        token_valid_until=case.token_expiry,
    )


@router.post(
    "/upload",
    response_model=PortalUploadResponse,
    summary="Upload vendor statement file",
)
async def upload_vendor_statement(
    file: UploadFile,
    request: Request,
    x_portal_token: str = Header(..., alias="X-Portal-Token"),
    session: AsyncSession = Depends(get_db_session),
) -> PortalUploadResponse:
    """
    POST /api/v1/vlr/portal/upload

    Uploads a vendor statement file (CSV or XLSX). Validates the file,
    parses entries, stores them, and triggers re-reconciliation if this
    is a subsequent upload.

    Requirement 4.3: File upload with validation.
    Requirement 4.4: 5-attempt upload limit enforcement.
    Requirement 4.5: Re-upload triggers re-reconciliation.
    Requirement 4.6: File format validation (CSV/XLSX).
    """
    # Validate token
    case = await _validate_portal_token(x_portal_token, session)

    # Enforce 5-upload limit (Requirement 4.4)
    if case.upload_count >= MAX_UPLOAD_ATTEMPTS:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Upload limit reached ({MAX_UPLOAD_ATTEMPTS} attempts). "
                "Please contact the reconciliation team."
            ),
        )

    # Read file content
    file_content = await file.read()
    if not file_content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty.",
        )

    # Validate and parse the file
    parser = FileParserService()
    try:
        result = parser.validate_and_parse(file_content, file.filename or "unknown.csv")
    except FileValidationException as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=exc.message,
        )

    if not result.is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File validation failed: {'; '.join(result.errors)}",
        )

    # Determine if this is a re-upload (subsequent upload triggers re-reconciliation)
    is_reupload = case.upload_count > 0

    # Delete existing vendor-side entries for this case (re-upload replaces previous data)
    ledger_repo = LedgerEntryRepositoryImpl(session)
    if is_reupload:
        # Clear all match data for re-reconciliation
        await ledger_repo.clear_match_data_by_case(case.id)
        # Delete existing vendor-side entries
        from sqlalchemy import delete as sql_delete

        del_stmt = sql_delete(LedgerEntryModel).where(
            and_(
                LedgerEntryModel.case_id == case.id,
                LedgerEntryModel.side == "vendor",
            )
        )
        await session.execute(del_stmt)
        await session.flush()

    # Create new vendor ledger entries from parsed data
    entries_data = [
        {
            "id": uuid4(),
            "case_id": case.id,
            "side": "vendor",
            "document_number": entry.document_number,
            "document_type": entry.document_type,
            "reference_number": entry.reference_number,
            "posting_date": entry.posting_date,
            "clearing_date": entry.clearing_date,
            "clearing_document": entry.clearing_document,
            "amount": float(entry.amount),
            "currency": entry.currency,
            "assignment_number": entry.assignment_number,
            "description": entry.description,
            "source": "portal_upload",
            "created_by": "vendor_portal",
            "modified_by": "vendor_portal",
        }
        for entry in result.entries
    ]

    await ledger_repo.bulk_create(entries_data)

    # Increment upload count
    case_repo = CaseRepositoryImpl(session)
    new_upload_count = await case_repo.increment_upload_count(case.id)

    # Transition case status to data_received
    await case_repo.update(
        case.id,
        {
            "status": "data_received",
            "modified_by": "vendor_portal",
            "modified_date": datetime.now(timezone.utc),
        },
    )

    # Trigger re-reconciliation if this is a subsequent upload (Requirement 4.5)
    task_id = None
    if is_reupload:
        try:
            from src.infrastructure.tasks.vlr.reconciliation_tasks import reconciliation_task

            idempotency_key = hashlib.sha256(
                f"{case.id}:{new_upload_count}:{datetime.now(timezone.utc).isoformat()}".encode()
            ).hexdigest()[:32]

            task = reconciliation_task.delay(
                case_id=str(case.id),
                idempotency_key=idempotency_key,
                triggered_by="vendor_portal",
            )
            task_id = task.id
        except (ImportError, Exception) as exc:
            logger.warning(
                "Failed to trigger re-reconciliation after re-upload: case_id=%s, error=%s",
                case.id,
                str(exc),
            )

    logger.info(
        "Portal upload successful: case_id=%s, upload_count=%d, entries=%d, is_reupload=%s",
        case.id,
        new_upload_count,
        len(result.entries),
        is_reupload,
    )

    return PortalUploadResponse(
        case_id=case.id,
        status="data_received",
        upload_count=new_upload_count,
        entries_parsed=len(result.entries),
        message=(
            f"Successfully uploaded {len(result.entries)} entries. "
            + ("Re-reconciliation triggered." if is_reupload else "Awaiting reconciliation.")
        ),
        task_id=task_id,
    )


@router.get(
    "/statement",
    response_model=PortalStatementResponse,
    summary="Get reconciliation statement",
)
async def get_statement(
    request: Request,
    x_portal_token: str = Header(..., alias="X-Portal-Token"),
    session: AsyncSession = Depends(get_db_session),
) -> PortalStatementResponse:
    """
    GET /api/v1/vlr/portal/statement

    Returns the full reconciliation statement for the vendor to review
    before sign-off. Includes company entries, vendor entries, match results,
    and exceptions.

    Requirement 4.7: Vendor can view reconciliation statement.
    Requirement 4.8: Statement includes both sides and match results.
    """
    # Validate token
    case = await _validate_portal_token(x_portal_token, session)

    # Fetch company entries
    company_stmt = select(LedgerEntryModel).where(
        and_(
            LedgerEntryModel.case_id == case.id,
            LedgerEntryModel.side == "company",
        )
    )
    company_result = await session.execute(company_stmt)
    company_entries = [
        {
            "id": str(e.id),
            "document_number": e.document_number,
            "document_type": e.document_type,
            "reference_number": e.reference_number,
            "posting_date": e.posting_date.isoformat() if e.posting_date else None,
            "amount": str(e.amount) if e.amount else None,
            "currency": e.currency,
            "match_id": str(e.match_id) if e.match_id else None,
            "pass_number": e.pass_number,
        }
        for e in company_result.scalars().all()
    ]

    # Fetch vendor entries
    vendor_stmt = select(LedgerEntryModel).where(
        and_(
            LedgerEntryModel.case_id == case.id,
            LedgerEntryModel.side == "vendor",
        )
    )
    vendor_result = await session.execute(vendor_stmt)
    vendor_entries = [
        {
            "id": str(e.id),
            "document_number": e.document_number,
            "document_type": e.document_type,
            "reference_number": e.reference_number,
            "posting_date": e.posting_date.isoformat() if e.posting_date else None,
            "amount": str(e.amount) if e.amount else None,
            "currency": e.currency,
            "match_id": str(e.match_id) if e.match_id else None,
            "pass_number": e.pass_number,
        }
        for e in vendor_result.scalars().all()
    ]

    # Fetch match results
    match_stmt = select(MatchResultModel).where(MatchResultModel.case_id == case.id)
    match_result = await session.execute(match_stmt)
    match_results = [
        {
            "id": str(m.id),
            "pass_number": m.pass_number,
            "match_type": m.match_type,
            "confidence_score": str(m.confidence_score) if m.confidence_score else None,
            "matched_amount": str(m.matched_amount) if m.matched_amount else None,
            "difference_amount": str(m.difference_amount) if m.difference_amount else None,
            "is_confirmed": m.is_confirmed,
        }
        for m in match_result.scalars().all()
    ]

    # Fetch exceptions
    exc_stmt = select(RecoExceptionModel).where(RecoExceptionModel.case_id == case.id)
    exc_result = await session.execute(exc_stmt)
    exceptions = [
        {
            "id": str(ex.id),
            "category": ex.category,
            "severity": ex.severity,
            "amount": str(ex.amount) if ex.amount else None,
            "status": ex.status,
        }
        for ex in exc_result.scalars().all()
    ]

    # Generate statement version (hash of case data for integrity tracking)
    version_input = f"{case.id}:{case.upload_count}:{case.modified_date.isoformat() if case.modified_date else ''}"
    statement_version = hashlib.sha256(version_input.encode()).hexdigest()[:16]

    return PortalStatementResponse(
        case_id=case.id,
        status=case.status,
        company_entries=company_entries,
        vendor_entries=vendor_entries,
        match_results=match_results,
        exceptions=exceptions,
        row_10_balance=case.row_10_balance,
        statement_version=statement_version,
    )


@router.post(
    "/sign-off",
    response_model=PortalSignOffResponse,
    summary="Record digital sign-off",
)
async def sign_off(
    body: PortalSignOffRequest,
    request: Request,
    x_portal_token: str = Header(..., alias="X-Portal-Token"),
    session: AsyncSession = Depends(get_db_session),
) -> PortalSignOffResponse:
    """
    POST /api/v1/vlr/portal/sign-off

    Records the vendor's digital sign-off on the reconciliation statement.
    Captures timestamp, IP address, and statement version for audit purposes.

    Requirement 4.9: Digital sign-off recording with timestamp and IP.
    Requirement 4.10: Statement version tracking for sign-off integrity.
    Requirement 4.11: Case transitions to signed_off status.
    """
    # Validate token
    case = await _validate_portal_token(x_portal_token, session)

    # Ensure the case is in a state that allows sign-off (must be matched or review)
    allowed_statuses = ("matched", "review")
    if case.status not in allowed_statuses:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Cannot sign off case in '{case.status}' status. "
                f"Case must be in one of: {', '.join(allowed_statuses)}."
            ),
        )

    # Extract client IP address
    client_ip = request.client.host if request.client else "unknown"
    # Check for forwarded IP (behind proxy)
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        client_ip = forwarded_for.split(",")[0].strip()

    signed_at = datetime.now(timezone.utc)

    # Create sign-off record
    sign_off_record = PortalSignOffModel(
        id=uuid4(),
        case_id=case.id,
        ip_address=client_ip,
        statement_version=body.statement_version,
        signed_at=signed_at,
        created_by="vendor_portal",
        modified_by="vendor_portal",
    )
    session.add(sign_off_record)

    # Transition case to signed_off status
    case_repo = CaseRepositoryImpl(session)
    await case_repo.update(
        case.id,
        {
            "status": "signed_off",
            "modified_by": "vendor_portal",
            "modified_date": signed_at,
        },
    )

    await session.flush()

    logger.info(
        "Portal sign-off recorded: case_id=%s, ip=%s, version=%s",
        case.id,
        client_ip,
        body.statement_version,
    )

    return PortalSignOffResponse(
        case_id=case.id,
        signed_at=signed_at,
        ip_address=client_ip,
        statement_version=body.statement_version,
        status="signed_off",
        message="Digital sign-off recorded successfully.",
    )
