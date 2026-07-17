"""
Vendor Portal API endpoints.
Thin controller — provides vendor-facing portal access via token-based authentication.
Does NOT use standard JWT auth; uses unique portal_token stored on ReconciliationCase.

Routes:
- GET    /api/v1/vlr/portal/auth/{token}          — Authenticate via portal token
- POST   /api/v1/vlr/portal/validate-token        — Validate token with 90-day expiry check
- POST   /api/v1/vlr/portal/upload                — Upload vendor statement file
- GET    /api/v1/vlr/portal/statement             — Get reconciliation statement (legacy)
- GET    /api/v1/vlr/portal/statement/{case_id}   — Get vendor-facing reconciliation results
- POST   /api/v1/vlr/portal/sign-off             — Record digital sign-off (legacy)
- POST   /api/v1/vlr/portal/sign-off/{case_id}   — Record vendor approval with confirmation

Requirements: 4.1–4.11, 24.1, 24.2, 24.3, 24.4, 33.1, 33.2
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Form, Header, HTTPException, Request, UploadFile, status
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.api.v1.schemas.vlr.portal_schemas import (
    PortalAuthResponse,
    PortalCaseSignOffRequest,
    PortalCaseSignOffResponse,
    PortalDisputeResponse,
    PortalReconciliationStatusResponse,
    PortalRequestNewLinkRequest,
    PortalRequestNewLinkResponse,
    PortalSignOffRequest,
    PortalSignOffResponse,
    PortalStatementResponse,
    PortalStatementResultResponse,
    PortalUploadResponse,
    PortalValidateTokenRequest,
    PortalValidateTokenResponse,
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
from src.infrastructure.database.models.vlr.reconciliation_request_model import (
    ReconciliationRequestModel,
)
from src.infrastructure.database.models.vlr.reco_exception_model import RecoExceptionModel
from src.infrastructure.database.models.vlr.vendor_model import VendorModel
from src.infrastructure.database.models.vlr.vendor_contact_model import VendorContactModel
from src.infrastructure.database.repositories.vlr.case_repository_impl import (
    CaseRepositoryImpl,
)
from src.infrastructure.database.repositories.vlr.ledger_entry_repository_impl import (
    LedgerEntryRepositoryImpl,
)
from src.infrastructure.database.session import get_db_session
from src.domain.services.vlr.audit_trail_service import (
    AuditEvent,
    AuditEventType,
    AuditTrailService,
)
from src.infrastructure.database.repositories.vlr.audit_trail_repository_impl import (
    AuditTrailRepositoryImpl,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/vlr/portal", tags=["VLR - Vendor Portal"])

# Maximum upload attempts allowed per case
MAX_UPLOAD_ATTEMPTS = 1


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

    # Block upload if a file has already been submitted for this case
    if case.upload_count >= 1:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="A statement has already been submitted for this request. No further uploads are allowed.",
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

    # ─── Run reconciliation engine directly ───────────────────────────────
    reco_status = "awaiting_reconciliation"
    reco_stats = None
    try:
        from src.infrastructure.database.repositories.vlr.ledger_entry_repository_impl import (
            LedgerEntryRepositoryImpl as LedgerRepoForReco,
        )
        from src.infrastructure.database.repositories.vlr.match_result_repository_impl import (
            MatchResultRepositoryImpl,
        )
        from src.infrastructure.database.repositories.vlr.exception_repository_impl import (
            ExceptionRepositoryImpl,
        )
        from src.domain.services.vlr.reconciliation_engine_service import (
            ReconciliationEngineService,
        )
        from decimal import Decimal as RDecimal

        ledger_repo_reco = LedgerRepoForReco(session)
        match_repo = MatchResultRepositoryImpl(session)
        exception_repo = ExceptionRepositoryImpl(session)

        engine = ReconciliationEngineService(
            ledger_entry_repository=ledger_repo_reco,
            match_result_repository=match_repo,
            case_repository=case_repo,
            exception_repository=exception_repo,
        )

        # Update status to matching
        await case_repo.update(case.id, {"status": "matching", "modified_by": "vendor_portal"})

        # Load reconciliation settings from the parent request
        from src.infrastructure.database.models.vlr.reconciliation_request_model import (
            ReconciliationRequestModel,
        )
        from sqlalchemy import select as sa_select
        req_stmt = sa_select(ReconciliationRequestModel).where(
            ReconciliationRequestModel.id == case.request_id
        )
        req_result_obj = await session.execute(req_stmt)
        parent_request = req_result_obj.scalar_one_or_none()

        # Extract settings (with fallback defaults)
        tolerance_pct = float(parent_request.tolerance_amount or 0) if parent_request else 0
        tds_pct = float(parent_request.tds_percentage or 0) if parent_request else 0
        gst_pct = float(parent_request.gst_percentage or 0) if parent_request else 0

        # Convert percentage tolerance to absolute value
        # For percentage-based tolerance, we pass it as a fraction (1% = 0.01)
        # The engine will use it as: amount * tolerance_fraction
        tolerance_fraction = RDecimal(str(tolerance_pct / 100)) if tolerance_pct > 0 else RDecimal("0")

        # Execute the 7-pass reconciliation engine with actual settings
        reco_result = await engine.execute(
            case_id=case.id,
            tolerance=tolerance_fraction,
            fuzzy_threshold=0.8,
            date_tolerance_days=15,  # Max from UI date range setting
            tds_percentage=RDecimal(str(tds_pct)),
            gst_percentage=RDecimal(str(gst_pct)),
        )

        # Determine status based on results
        total_entries = reco_result.statistics.total_company_entries + reco_result.statistics.total_vendor_entries
        total_matched = reco_result.statistics.total_matched_company + reco_result.statistics.total_matched_vendor
        has_unmatched = len(reco_result.unmatched_company_ids) > 0 or len(reco_result.unmatched_vendor_ids) > 0

        if has_unmatched:
            # Not everything matched — needs manual column mapping
            final_status = "mapping_pending"
        else:
            # Everything matched automatically
            final_status = "auto_completed"

        await case_repo.update(case.id, {"status": final_status, "modified_by": "vendor_portal"})
        reco_status = "reconciliation_complete"
        reco_stats = {
            "total_matched_company": reco_result.statistics.total_matched_company,
            "total_matched_vendor": reco_result.statistics.total_matched_vendor,
            "total_company_entries": reco_result.statistics.total_company_entries,
            "total_vendor_entries": reco_result.statistics.total_vendor_entries,
            "match_pairs": len(reco_result.match_pairs),
            "match_groups": len(reco_result.match_groups),
            "unmatched_company": len(reco_result.unmatched_company_ids),
            "unmatched_vendor": len(reco_result.unmatched_vendor_ids),
        }
        logger.info(
            "Reconciliation completed after vendor upload: case_id=%s, matched_company=%d/%d",
            case.id, reco_result.statistics.total_matched_company, reco_result.statistics.total_company_entries,
        )
    except Exception as reco_exc:
        logger.error(
            "Reconciliation engine failed after vendor upload: case_id=%s, error=%s",
            case.id, str(reco_exc),
        )
        reco_status = "reconciliation_failed"

    logger.info(
        "Portal upload successful: case_id=%s, upload_count=%d, entries=%d, is_reupload=%s",
        case.id,
        new_upload_count,
        len(result.entries),
        is_reupload,
    )

    # Emit audit event for vendor portal upload (Requirement 38.2)
    audit_service = AuditTrailService(audit_repository=AuditTrailRepositoryImpl(session))
    await audit_service.log_event(AuditEvent(
        actor_username="vendor_portal",
        event_type=AuditEventType.VENDOR_INTERACTION,
        case_id=case.id,
        event_details={
            "action": "file_upload",
            "upload_count": new_upload_count,
            "entries_parsed": len(result.entries),
            "is_reupload": is_reupload,
            "filename": file.filename,
        },
        ip_address=request.client.host if request.client else None,
    ))

    return PortalUploadResponse(
        case_id=case.id,
        status=reco_status if reco_status == "reconciliation_complete" else "data_received",
        upload_count=new_upload_count,
        entries_parsed=len(result.entries),
        message=(
            f"Successfully uploaded {len(result.entries)} entries. "
            + (f"Reconciliation complete: {reco_stats['total_matched_company']}/{reco_stats['total_company_entries']} company entries matched."
               if reco_stats else "Reconciliation engine is processing.")
        ),
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

    # Emit audit event for vendor sign-off (Requirement 38.2)
    audit_service = AuditTrailService(audit_repository=AuditTrailRepositoryImpl(session))
    await audit_service.log_event(AuditEvent(
        actor_username="vendor_portal",
        event_type=AuditEventType.VENDOR_INTERACTION,
        case_id=case.id,
        event_details={
            "action": "sign_off",
            "statement_version": body.statement_version,
        },
        ip_address=client_ip,
    ))

    return PortalSignOffResponse(
        case_id=case.id,
        signed_at=signed_at,
        ip_address=client_ip,
        statement_version=body.statement_version,
        status="signed_off",
        message="Digital sign-off recorded successfully.",
    )


# ──────────────────────────────────────────────────────────────────────
# New Endpoints — Requirements 24.1, 24.2, 24.3, 24.4, 33.1, 33.2
# ──────────────────────────────────────────────────────────────────────


@router.post(
    "/validate-token",
    response_model=PortalValidateTokenResponse,
    summary="Validate portal access token",
    responses={
        410: {"description": "Token has expired (90-day validity exceeded)"},
        404: {"description": "Token not found"},
    },
)
async def validate_token(
    body: PortalValidateTokenRequest,
    session: AsyncSession = Depends(get_db_session),
) -> PortalValidateTokenResponse:
    """
    POST /api/v1/vlr/portal/validate-token

    Validates the portal access token. Checks that the token exists in the cases
    table and that the token_expiry has not been exceeded (90-day validity per Req 33.1).

    Returns case summary (vendor name, period, status) if valid.
    Returns 410 Gone if token has expired.
    Returns 404 Not Found if token does not exist.

    Requirement 24.1: Token validation for portal authentication.
    Requirement 33.1: 90-day validity enforcement.
    Requirement 33.2: Expiry message on denied access.
    """
    # Look up the case by portal token
    case_repo = CaseRepositoryImpl(session)
    case = await case_repo.get_by_token(body.token)

    if case is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Portal token not found. Please check the link or contact the reconciliation team.",
        )

    # Check token expiry — return 410 Gone if expired (per design.md error handling)
    if case.token_expiry and case.token_expiry < datetime.now(timezone.utc):
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail=(
                "This portal link has expired. Portal links are valid for 90 days. "
                "Please contact the reconciliation team to request a new invitation."
            ),
        )

    # Fetch vendor name
    vendor_stmt = select(VendorModel).where(VendorModel.id == case.vendor_id)
    vendor_result = await session.execute(vendor_stmt)
    vendor = vendor_result.scalar_one_or_none()
    vendor_name = vendor.name if vendor else "Unknown Vendor"

    # Fetch reconciliation period from the parent request
    request_stmt = select(ReconciliationRequestModel).where(
        ReconciliationRequestModel.id == case.request_id
    )
    request_result = await session.execute(request_stmt)
    recon_request = request_result.scalar_one_or_none()

    period_start = recon_request.period_start if recon_request else None
    period_end = recon_request.period_end if recon_request else None

    logger.info(
        "Portal token validated successfully: case_id=%s, vendor=%s",
        case.id,
        vendor_name,
    )

    return PortalValidateTokenResponse(
        case_id=case.id,
        vendor_name=vendor_name,
        period_start=period_start,
        period_end=period_end,
        status=case.status,
        upload_count=case.upload_count,
        max_uploads=MAX_UPLOAD_ATTEMPTS,
        token_valid_until=case.token_expiry,
    )


@router.post(
    "/request-new-link",
    response_model=PortalRequestNewLinkResponse,
    summary="Request a new portal access link",
    responses={
        404: {"description": "No active cases found for this email address"},
    },
)
async def request_new_link(
    body: PortalRequestNewLinkRequest,
    session: AsyncSession = Depends(get_db_session),
) -> PortalRequestNewLinkResponse:
    """
    POST /api/v1/vlr/portal/request-new-link

    Allows a vendor to request a new portal access link when their existing link
    has expired or been lost. Looks up active reconciliation cases by vendor email,
    generates a new UUID token, invalidates the old one, and dispatches a
    send_vendor_invite Celery task.

    This endpoint does NOT require authentication (the vendor is unauthenticated).

    Requirement 5: Vendor can request a new portal access link.
    """
    email = body.email.strip().lower()

    # Find vendor contacts matching this email
    contact_stmt = select(VendorContactModel).where(
        func.lower(VendorContactModel.email) == email
    )
    contact_result = await session.execute(contact_stmt)
    contacts = contact_result.scalars().all()

    if not contacts:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active cases found for this email address. Please check the email or contact the reconciliation team.",
        )

    # Collect vendor IDs from matching contacts
    vendor_ids = list({c.vendor_id for c in contacts})

    # Find active (non-closed, non-deleted) reconciliation cases for these vendors
    cases_stmt = select(ReconciliationCaseModel).where(
        and_(
            ReconciliationCaseModel.vendor_id.in_(vendor_ids),
            ReconciliationCaseModel.is_deleted == False,  # noqa: E712
            ReconciliationCaseModel.status.notin_(["closed", "signed_off", "approved"]),
        )
    )
    cases_result = await session.execute(cases_stmt)
    cases = cases_result.scalars().all()

    if not cases:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active cases found for this email address. Please check the email or contact the reconciliation team.",
        )

    # For each active case, generate a new token and dispatch invite email
    now = datetime.now(timezone.utc)
    token_validity_days = 90

    for case in cases:
        # Generate new token and invalidate old one
        new_token = str(uuid4())
        new_expiry = now + timedelta(days=token_validity_days)

        case_repo = CaseRepositoryImpl(session)
        await case_repo.update(
            case.id,
            {
                "portal_token": new_token,
                "token_expiry": new_expiry,
                "modified_by": "vendor_portal",
                "modified_date": now,
            },
        )

        # Get vendor name for the email
        vendor_stmt = select(VendorModel).where(VendorModel.id == case.vendor_id)
        vendor_result = await session.execute(vendor_stmt)
        vendor = vendor_result.scalar_one_or_none()
        vendor_name = vendor.name if vendor else "Vendor"

        # Dispatch send_vendor_invite via notification service
        try:
            from src.domain.services.vlr.notification_service import NotificationService
            from src.infrastructure.database.repositories.vlr.notification_repository_impl import (
                NotificationRepositoryImpl,
            )

            notification_repo = NotificationRepositoryImpl(session)
            notification_service = NotificationService(notification_repository=notification_repo)

            await notification_service.send_vendor_invite(
                case_id=case.id,
                vendor_email=email,
                vendor_name=vendor_name,
                portal_token=new_token,
            )
        except Exception as exc:
            logger.warning(
                "Failed to dispatch invite email for case_id=%s, email=%s: %s",
                case.id,
                email,
                str(exc),
            )

    await session.flush()

    logger.info(
        "New portal link(s) requested: email=%s, cases_updated=%d",
        email,
        len(cases),
    )

    return PortalRequestNewLinkResponse(
        message="A new link has been sent to your email.",
    )


@router.get(
    "/statement/{case_id}",
    response_model=PortalStatementResultResponse,
    summary="Get vendor-facing reconciliation results",
    responses={
        410: {"description": "Token has expired"},
        404: {"description": "Case not found or access denied"},
    },
)
async def get_statement_by_case(
    case_id: UUID,
    request: Request,
    x_portal_token: str = Header(..., alias="X-Portal-Token"),
    session: AsyncSession = Depends(get_db_session),
) -> PortalStatementResultResponse:
    """
    GET /api/v1/vlr/portal/statement/{case_id}

    Returns vendor-facing reconciliation results for a specific case.
    Displays matched items summary, status, and balances.
    Does NOT include internal SAP data per BRD Section 7.1.

    Requirement 24.3: Statement view for vendor portal.
    """
    # Validate token and verify case access
    case = await _validate_portal_token_with_expiry(x_portal_token, session)

    # Verify the token belongs to this case
    if str(case.id) != str(case_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Case not found or access denied.",
        )

    # Fetch vendor name
    vendor_stmt = select(VendorModel).where(VendorModel.id == case.vendor_id)
    vendor_result = await session.execute(vendor_stmt)
    vendor = vendor_result.scalar_one_or_none()
    vendor_name = vendor.name if vendor else "Unknown Vendor"

    # Fetch reconciliation period
    request_stmt = select(ReconciliationRequestModel).where(
        ReconciliationRequestModel.id == case.request_id
    )
    request_result = await session.execute(request_stmt)
    recon_request = request_result.scalar_one_or_none()

    period_start = recon_request.period_start if recon_request else None
    period_end = recon_request.period_end if recon_request else None

    # Count matched entries (pairs)
    matched_count_stmt = select(func.count(MatchResultModel.id)).where(
        MatchResultModel.case_id == case.id
    )
    matched_count_result = await session.execute(matched_count_stmt)
    total_matched_entries = matched_count_result.scalar_one() or 0

    # Count unmatched vendor entries (entries with no match_id)
    unmatched_vendor_stmt = select(func.count(LedgerEntryModel.id)).where(
        and_(
            LedgerEntryModel.case_id == case.id,
            LedgerEntryModel.side == "vendor",
            LedgerEntryModel.match_id.is_(None),
        )
    )
    unmatched_vendor_result = await session.execute(unmatched_vendor_stmt)
    total_unmatched_vendor = unmatched_vendor_result.scalar_one() or 0

    # Build match summary (grouped by match_type)
    match_summary_stmt = (
        select(
            MatchResultModel.match_type,
            func.count(MatchResultModel.id).label("count"),
            func.sum(MatchResultModel.matched_amount).label("total_amount"),
        )
        .where(MatchResultModel.case_id == case.id)
        .group_by(MatchResultModel.match_type)
    )
    match_summary_result = await session.execute(match_summary_stmt)
    match_summary = [
        {
            "match_type": row.match_type,
            "count": row.count,
            "total_amount": str(row.total_amount) if row.total_amount else "0",
        }
        for row in match_summary_result.all()
    ]

    # Generate statement version
    version_input = f"{case.id}:{case.upload_count}:{case.modified_date.isoformat() if case.modified_date else ''}"
    statement_version = hashlib.sha256(version_input.encode()).hexdigest()[:16]

    return PortalStatementResultResponse(
        case_id=case.id,
        status=case.status,
        vendor_name=vendor_name,
        period_start=period_start,
        period_end=period_end,
        total_matched_entries=total_matched_entries,
        total_unmatched_vendor=total_unmatched_vendor,
        vendor_opening_balance=case.vendor_opening_balance,
        vendor_closing_balance=case.vendor_closing_balance,
        net_difference=case.net_difference,
        match_summary=match_summary,
        statement_version=statement_version,
    )


@router.post(
    "/sign-off/{case_id}",
    response_model=PortalCaseSignOffResponse,
    summary="Record vendor approval for a specific case",
    responses={
        410: {"description": "Token has expired"},
        404: {"description": "Case not found or access denied"},
        409: {"description": "Case not in a state that allows sign-off"},
    },
)
async def sign_off_case(
    case_id: UUID,
    body: PortalCaseSignOffRequest,
    request: Request,
    x_portal_token: str = Header(..., alias="X-Portal-Token"),
    session: AsyncSession = Depends(get_db_session),
) -> PortalCaseSignOffResponse:
    """
    POST /api/v1/vlr/portal/sign-off/{case_id}

    Records the vendor's confirmation/approval for a specific reconciliation case.
    Captures IP address, timestamp, confirmation text, and statement version.
    Creates a PortalSignOff record and updates case status.

    Requirement 24.4: Vendor approval recording.
    """
    # Validate token with expiry check
    case = await _validate_portal_token_with_expiry(x_portal_token, session)

    # Verify the token belongs to this case
    if str(case.id) != str(case_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Case not found or access denied.",
        )

    # Ensure the case is in a state that allows sign-off
    allowed_statuses = ("matched", "review", "pending_approval")
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
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        client_ip = forwarded_for.split(",")[0].strip()

    signed_at = datetime.now(timezone.utc)

    # Create sign-off record with confirmation text
    sign_off_record = PortalSignOffModel(
        id=uuid4(),
        case_id=case.id,
        ip_address=client_ip,
        statement_version=body.statement_version,
        confirmation_text=body.confirmation_text,
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
        "Portal sign-off recorded: case_id=%s, ip=%s, version=%s, confirmation='%s'",
        case.id,
        client_ip,
        body.statement_version,
        body.confirmation_text[:50],
    )

    # Emit audit event for vendor case sign-off (Requirement 38.2)
    audit_service = AuditTrailService(audit_repository=AuditTrailRepositoryImpl(session))
    await audit_service.log_event(AuditEvent(
        actor_username="vendor_portal",
        event_type=AuditEventType.VENDOR_INTERACTION,
        case_id=case.id,
        event_details={
            "action": "case_sign_off",
            "statement_version": body.statement_version,
            "confirmation_text": body.confirmation_text[:100],
        },
        ip_address=client_ip,
    ))

    return PortalCaseSignOffResponse(
        case_id=case.id,
        signed_at=signed_at,
        ip_address=client_ip,
        confirmation_text=body.confirmation_text,
        statement_version=body.statement_version,
        status="signed_off",
        message="Vendor approval recorded successfully.",
    )


# ──────────────────────────────────────────────────────────────────────
# Reconciliation Status Polling — Requirement 6
# ──────────────────────────────────────────────────────────────────────


@router.get(
    "/reconciliation-status/{case_id}",
    response_model=PortalReconciliationStatusResponse,
    summary="Get reconciliation processing status for polling",
    responses={
        401: {"description": "Invalid or expired portal token"},
        404: {"description": "Case not found or access denied"},
    },
)
async def get_reconciliation_status(
    case_id: UUID,
    x_portal_token: str = Header(..., alias="X-Portal-Token"),
    session: AsyncSession = Depends(get_db_session),
) -> PortalReconciliationStatusResponse:
    """
    GET /api/v1/vlr/portal/reconciliation-status/{case_id}

    Returns the current reconciliation processing status for a case.
    Used by the portal upload page to poll for completion after file upload.

    Status mapping:
    - 'processing': case is in 'data_received' or 'matching' status (reconciliation in progress)
    - 'completed': case is in 'matched', 'review', or any later status (reconciliation done)
    - 'error': case has encountered an error during processing

    Requirement 6: Vendor Portal — Upload Processing State.
    """
    # Validate portal token
    case = await _validate_portal_token(x_portal_token, session)

    # Verify the token belongs to this case
    if str(case.id) != str(case_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Case not found or access denied.",
        )

    # Map case status to polling status
    processing_statuses = ("data_received", "matching", "created", "ledger_confirmed", "invited")
    completed_statuses = ("matched", "review", "pending_approval", "approved", "signed_off", "closed")

    if case.status in completed_statuses:
        return PortalReconciliationStatusResponse(
            status="completed",
            message="Reconciliation completed successfully. You can now view your statement.",
        )
    elif case.status in processing_statuses:
        return PortalReconciliationStatusResponse(
            status="processing",
            message="Your statement is being processed. This may take a few minutes.",
        )
    else:
        # Unknown or error status
        return PortalReconciliationStatusResponse(
            status="error",
            message="An error occurred during processing. Please contact support for assistance.",
        )


# ──────────────────────────────────────────────────────────────────────
# Raise Dispute — Requirement 8
# ──────────────────────────────────────────────────────────────────────


@router.post(
    "/dispute/{case_id}",
    response_model=PortalDisputeResponse,
    summary="Raise a dispute on reconciliation results",
    responses={
        401: {"description": "Invalid or expired portal token"},
        404: {"description": "Case not found or access denied"},
        409: {"description": "Case already disputed or in an invalid state"},
        422: {"description": "Validation error (missing reason)"},
    },
)
async def raise_dispute(
    case_id: UUID,
    request: Request,
    reason: str = Form("", description="Reason for disputing the reconciliation results"),
    attachment: UploadFile | None = None,
    x_portal_token: str = Header(..., alias="X-Portal-Token"),
    session: AsyncSession = Depends(get_db_session),
) -> PortalDisputeResponse:
    """
    POST /api/v1/vlr/portal/dispute/{case_id}

    Allows a vendor to raise a dispute on reconciliation results they disagree with.
    Updates the case status to 'disputed', creates an audit event, and notifies the finance team.

    Accepts multipart/form-data with:
    - reason (required): Text description of the dispute
    - attachment (optional): Supporting document file

    Requirement 8: Vendor Portal — Raise Dispute.
    """
    # Validate portal token
    case = await _validate_portal_token(x_portal_token, session)

    # Verify the token belongs to this case
    if str(case.id) != str(case_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Case not found or access denied.",
        )

    # Validate reason is provided
    if not reason or not reason.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Reason is required to raise a dispute.",
        )

    # Prevent duplicate disputes
    if case.status == "disputed":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A dispute has already been raised for this case.",
        )

    # Extract client IP address
    client_ip = request.client.host if request.client else "unknown"
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        client_ip = forwarded_for.split(",")[0].strip()

    now = datetime.now(timezone.utc)

    # Handle optional file attachment
    attachment_filename = None
    if attachment and attachment.filename:
        attachment_filename = attachment.filename
        # In production, the file would be stored in object storage.
        # For now, we log the filename and skip actual file persistence.
        logger.info(
            "Dispute attachment received: case_id=%s, filename=%s",
            case.id,
            attachment_filename,
        )

    # Update case status to disputed
    case_repo = CaseRepositoryImpl(session)
    await case_repo.update(
        case.id,
        {
            "status": "disputed",
            "modified_by": "vendor_portal",
            "modified_date": now,
        },
    )

    await session.flush()

    # Emit audit event for the dispute
    audit_service = AuditTrailService(audit_repository=AuditTrailRepositoryImpl(session))
    await audit_service.log_event(AuditEvent(
        actor_username="vendor_portal",
        event_type=AuditEventType.VENDOR_INTERACTION,
        case_id=case.id,
        event_details={
            "action": "raise_dispute",
            "reason": reason.strip()[:500],
            "has_attachment": attachment_filename is not None,
            "attachment_filename": attachment_filename,
        },
        ip_address=client_ip,
    ))

    # Notify finance team about the dispute
    try:
        from src.domain.services.vlr.notification_service import NotificationService
        from src.infrastructure.database.repositories.vlr.notification_repository_impl import (
            NotificationRepositoryImpl,
        )

        notification_repo = NotificationRepositoryImpl(session)
        notification_service = NotificationService(notification_repository=notification_repo)

        # Fetch vendor name for notification context
        vendor_stmt = select(VendorModel).where(VendorModel.id == case.vendor_id)
        vendor_result = await session.execute(vendor_stmt)
        vendor = vendor_result.scalar_one_or_none()
        vendor_name = vendor.name if vendor else "Unknown Vendor"

        await notification_service.send_dispute_notification(
            case_id=case.id,
            vendor_name=vendor_name,
            reason=reason.strip(),
        )
    except Exception as exc:
        # Notification failure should not block the dispute submission
        logger.warning(
            "Failed to send dispute notification for case_id=%s: %s",
            case.id,
            str(exc),
        )

    logger.info(
        "Vendor dispute raised: case_id=%s, reason='%s', attachment=%s",
        case.id,
        reason.strip()[:100],
        attachment_filename,
    )

    return PortalDisputeResponse(
        case_id=case.id,
        status="disputed",
        message="Dispute raised successfully. The reconciliation team will review your concern.",
    )


# ──────────────────────────────────────────────────────────────────────
# Helper — Token validation with 410 Gone on expiry
# ──────────────────────────────────────────────────────────────────────


async def _validate_portal_token_with_expiry(
    token: str,
    session: AsyncSession,
) -> ReconciliationCaseModel:
    """
    Validate a portal token and return the associated case.
    Returns 410 Gone for expired tokens (per design.md error handling).

    Raises:
        HTTPException 404: Token not found.
        HTTPException 410: Token has expired (90-day validity exceeded).
    """
    case_repo = CaseRepositoryImpl(session)
    case = await case_repo.get_by_token(token)

    if case is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Portal token not found.",
        )

    # Check token expiry — return 410 Gone per design.md
    if case.token_expiry and case.token_expiry < datetime.now(timezone.utc):
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail=(
                "This portal link has expired. Portal links are valid for 90 days. "
                "Please contact the reconciliation team to request a new invitation."
            ),
        )

    return case
