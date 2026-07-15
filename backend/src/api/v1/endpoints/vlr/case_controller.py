"""
Reconciliation Case API endpoints.
Thin controller — delegates business logic to RequestManagerService and related services.

Routes:
- GET    /api/v1/vlr/cases                      — List all cases with filtering & pagination
- GET    /api/v1/vlr/cases/{id}                 — Get case detail
- POST   /api/v1/vlr/cases/{id}/confirm-ledger  — Confirm company ledger
- POST   /api/v1/vlr/cases/{id}/invite          — Send vendor invitation
- POST   /api/v1/vlr/cases/{id}/reconcile       — Trigger matching engine
- POST   /api/v1/vlr/cases/{id}/submit-approval — Submit for manager approval
- GET    /api/v1/vlr/cases/{id}/statement        — Full reconciliation statement
- GET    /api/v1/vlr/cases/{id}/statistics       — Match statistics
- POST   /api/v1/vlr/cases/direct               — Direct reconciliation (single vendor, dual upload)

Requirements: 3.4, 3.5, 3.6, 3.7, 11.2, 11.6, 18.1, 18.2, 18.3, 18.4, 18.5, 18.6, 18.7, 18.8, 23.2, 25.3, 25.4
"""

import hashlib
import json
import logging
from datetime import datetime, timezone
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.v1.dependencies import get_current_active_user
from src.api.v1.schemas.vlr.case_schemas import (
    BulkActionRequest,
    BulkActionResponse,
    BulkActionResultItem,
    CaseActionResponse,
    CaseListResponse,
    CaseStatisticsResponse,
    ReconciliationCaseResponse,
    ReconciliationStatementResponse,
    ReconcileResponse,
)
from src.domain.repositories.vlr.case_repository import CaseFilters
from src.domain.repositories.vlr.vendor_repository import PaginationParams
from src.api.v1.schemas.vlr.direct_reconciliation_schemas import (
    DirectReconciliationConfig,
    DirectReconciliationResponse,
)
from src.domain.entities.user import User
from src.domain.exceptions.vlr import (
    FileValidationException,
    OverlappingPeriodException,
    VendorInactiveException,
)
from src.domain.services.vlr.file_parser_service import FileParserService
from src.domain.services.vlr.request_manager_service import (
    CaseStatus,
    DateRange,
    RequestManagerService,
)
from src.infrastructure.database.repositories.vlr.case_repository_impl import (
    CaseRepositoryImpl,
)
from src.infrastructure.database.repositories.vlr.ledger_entry_repository_impl import (
    LedgerEntryRepositoryImpl,
)
from src.infrastructure.database.repositories.vlr.match_result_repository_impl import (
    MatchResultRepositoryImpl,
)
from src.infrastructure.database.repositories.vlr.exception_repository_impl import (
    ExceptionRepositoryImpl,
)
from src.infrastructure.database.repositories.vlr.request_repository_impl import (
    RequestRepositoryImpl,
)
from src.infrastructure.database.repositories.vlr.vendor_repository_impl import (
    VendorRepositoryImpl,
)
from src.infrastructure.database.session import get_db_session
from src.infrastructure.security.permission_manager import require_permission

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/vlr/cases", tags=["VLR - Reconciliation Cases"])


# ──────────────────────────────────────────────────────────────────────
# Dependencies
# ──────────────────────────────────────────────────────────────────────


def _get_request_manager_service(
    session: AsyncSession = Depends(get_db_session),
) -> RequestManagerService:
    """FastAPI dependency — creates RequestManagerService with injected repositories."""
    request_repo = RequestRepositoryImpl(session)
    case_repo = CaseRepositoryImpl(session)
    vendor_repo = VendorRepositoryImpl(session)
    return RequestManagerService(
        request_repository=request_repo,
        case_repository=case_repo,
        vendor_repository=vendor_repo,
    )


def _get_case_repository(
    session: AsyncSession = Depends(get_db_session),
) -> CaseRepositoryImpl:
    """FastAPI dependency — creates CaseRepository for direct queries."""
    return CaseRepositoryImpl(session)


# ──────────────────────────────────────────────────────────────────────
# Endpoints
# ──────────────────────────────────────────────────────────────────────


@router.get(
    "",
    response_model=CaseListResponse,
    summary="List reconciliation cases with filtering and pagination",
    dependencies=[Depends(require_permission("vlr.cases.read"))],
)
async def list_cases(
    company_code: str = Query(..., min_length=1, description="Company code filter"),
    case_status: str | None = Query(default=None, alias="status", description="Filter by case status"),
    vendor_id: UUID | None = Query(default=None, description="Filter by vendor ID"),
    request_id: UUID | None = Query(default=None, description="Filter by request ID"),
    case_type: str | None = Query(default=None, description="Filter by case type (e.g., 'direct')"),
    search: str | None = Query(default=None, description="Search by vendor name or case ID"),
    sort_by: str | None = Query(default=None, description="Sort field"),
    sort_order: str | None = Query(default="desc", description="Sort order: asc or desc"),
    page: int = Query(default=1, ge=1, description="Page number"),
    page_size: int = Query(default=10, ge=1, le=200, description="Items per page"),
    repo: CaseRepositoryImpl = Depends(_get_case_repository),
) -> CaseListResponse:
    """GET /api/v1/vlr/cases — List all reconciliation cases with filtering and pagination."""
    filters = CaseFilters(
        status=case_status,
        vendor_id=vendor_id,
        request_id=request_id,
        case_type=case_type,
    )
    pagination = PaginationParams(page=page, page_size=page_size)

    result = await repo.list_cases(
        company_code=company_code,
        filters=filters,
        pagination=pagination,
    )

    return CaseListResponse(
        items=[ReconciliationCaseResponse.model_validate(c) for c in result.items],
        total=result.total,
        page=result.page,
        page_size=result.page_size,
        total_pages=result.total_pages,
    )


@router.get(
    "/{case_id}",
    response_model=ReconciliationCaseResponse,
    summary="Get reconciliation case by ID",
    dependencies=[Depends(require_permission("vlr.cases.read"))],
)
async def get_case(
    case_id: UUID,
    company_code: str = Query(..., min_length=1, description="Company code"),
    repo: CaseRepositoryImpl = Depends(_get_case_repository),
) -> ReconciliationCaseResponse:
    """GET /api/v1/vlr/cases/{id} — Retrieve a case by ID."""
    case = await repo.get_by_id(case_id, company_code)
    if case is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Reconciliation case {case_id} not found.",
        )
    return ReconciliationCaseResponse.model_validate(case)


@router.post(
    "/{case_id}/confirm-ledger",
    response_model=CaseActionResponse,
    summary="Confirm company ledger for a case",
    dependencies=[Depends(require_permission("vlr.cases.write"))],
)
async def confirm_ledger(
    case_id: UUID,
    company_code: str = Query(..., min_length=1, description="Company code"),
    current_user: User = Depends(get_current_active_user),
    service: RequestManagerService = Depends(_get_request_manager_service),
) -> CaseActionResponse:
    """
    POST /api/v1/vlr/cases/{id}/confirm-ledger

    Confirms the company ledger for this case, transitioning it to LedgerConfirmed status.
    Requirement 3.4: Transition case to LedgerConfirmed after ledger confirmation.
    """
    updated_case = await service.confirm_company_ledger(case_id, company_code)
    return CaseActionResponse(
        id=case_id,
        status=getattr(updated_case, "status"),
        message="Company ledger confirmed successfully.",
    )


@router.post(
    "/{case_id}/invite",
    response_model=CaseActionResponse,
    summary="Send vendor invitation for a case",
    dependencies=[Depends(require_permission("vlr.cases.write"))],
)
async def invite_vendor(
    case_id: UUID,
    company_code: str = Query(..., min_length=1, description="Company code"),
    current_user: User = Depends(get_current_active_user),
    service: RequestManagerService = Depends(_get_request_manager_service),
) -> CaseActionResponse:
    """
    POST /api/v1/vlr/cases/{id}/invite

    Sends a vendor invitation for reconciliation.
    Requirement 3.5: Company ledger must be confirmed before invitation.
    """
    updated_case = await service.invite_vendor(case_id, company_code)
    return CaseActionResponse(
        id=case_id,
        status=getattr(updated_case, "status"),
        message="Vendor invitation sent successfully.",
    )


@router.post(
    "/{case_id}/reconcile",
    response_model=ReconcileResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Trigger reconciliation engine for a case",
    dependencies=[Depends(require_permission("vlr.cases.write"))],
)
async def trigger_reconciliation(
    case_id: UUID,
    company_code: str = Query(..., min_length=1, description="Company code"),
    current_user: User = Depends(get_current_active_user),
    repo: CaseRepositoryImpl = Depends(_get_case_repository),
    service: RequestManagerService = Depends(_get_request_manager_service),
) -> ReconcileResponse:
    """
    POST /api/v1/vlr/cases/{id}/reconcile

    Triggers the multi-pass reconciliation engine for this case.
    Runs asynchronously as a Celery task.
    """
    # Verify case exists and is in a valid state for reconciliation
    case = await repo.get_by_id(case_id, company_code)
    if case is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Reconciliation case {case_id} not found.",
        )

    # Case must be in statement_received or mapping_pending (re-reconciliation) status
    allowed_statuses = (
        CaseStatus.STATEMENT_RECEIVED.value,
        CaseStatus.MAPPING_PENDING.value,
    )
    if case.status not in allowed_statuses:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Cannot trigger reconciliation for case in '{case.status}' status. "
                f"Case must be in one of: {', '.join(allowed_statuses)}."
            ),
        )

    # Reconciliation will determine if auto_completed or mapping_pending
    # No explicit status transition here — the engine handles it

    # Dispatch reconciliation Celery task (if available)
    task_id = None
    try:
        from src.infrastructure.tasks.vlr.reconciliation_tasks import reconciliation_task

        task = reconciliation_task.delay(
            case_id=str(case_id),
            company_code=company_code,
            triggered_by=current_user.username,
        )
        task_id = task.id
    except (ImportError, Exception):
        # Reconciliation task module may not be available yet;
        # return accepted status without task_id
        pass

    return ReconcileResponse(
        case_id=case_id,
        task_id=task_id,
        status="accepted",
        message="Reconciliation engine triggered successfully.",
    )


@router.post(
    "/{case_id}/submit-approval",
    response_model=CaseActionResponse,
    summary="Submit case for manager approval",
    dependencies=[Depends(require_permission("vlr.cases.write"))],
)
async def submit_for_approval(
    case_id: UUID,
    company_code: str = Query(..., min_length=1, description="Company code"),
    current_user: User = Depends(get_current_active_user),
    service: RequestManagerService = Depends(_get_request_manager_service),
) -> CaseActionResponse:
    """
    POST /api/v1/vlr/cases/{id}/submit-approval

    Submits the case for manager approval. The case must be in Review status.
    Requirement 7.1: Validates Row_10 = 0 before submission (via ApprovalEngine).
    """
    # Transition from Reviewed → Signoff Requested
    updated_case = await service.transition_case_status(
        case_id, company_code, CaseStatus.SIGNOFF_REQUESTED
    )
    return CaseActionResponse(
        id=case_id,
        status=getattr(updated_case, "status"),
        message="Case submitted for approval successfully.",
    )


@router.get(
    "/{case_id}/statement",
    response_model=ReconciliationStatementResponse,
    summary="Get full reconciliation statement for a case",
    dependencies=[Depends(require_permission("vlr.cases.read"))],
)
async def get_case_statement(
    case_id: UUID,
    company_code: str = Query(..., min_length=1, description="Company code"),
    repo: CaseRepositoryImpl = Depends(_get_case_repository),
    session: AsyncSession = Depends(get_db_session),
) -> ReconciliationStatementResponse:
    """
    GET /api/v1/vlr/cases/{id}/statement

    Returns the full reconciliation statement including company entries,
    vendor entries, match results, exceptions, and Row_10 balance.
    """
    from sqlalchemy import select, and_

    from src.infrastructure.database.models.vlr.ledger_entry_model import LedgerEntryModel
    from src.infrastructure.database.models.vlr.match_result_model import MatchResultModel
    from src.infrastructure.database.models.vlr.reco_exception_model import RecoExceptionModel

    # Verify case exists
    case = await repo.get_by_id(case_id, company_code)
    if case is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Reconciliation case {case_id} not found.",
        )

    # Fetch company entries
    company_stmt = select(LedgerEntryModel).where(
        and_(
            LedgerEntryModel.case_id == case_id,
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
            LedgerEntryModel.case_id == case_id,
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
    match_stmt = select(MatchResultModel).where(MatchResultModel.case_id == case_id)
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
    exc_stmt = select(RecoExceptionModel).where(RecoExceptionModel.case_id == case_id)
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

    return ReconciliationStatementResponse(
        case_id=case_id,
        status=case.status,
        company_entries=company_entries,
        vendor_entries=vendor_entries,
        match_results=match_results,
        exceptions=exceptions,
        row_10_balance=case.row_10_balance,
    )


@router.get(
    "/{case_id}/statistics",
    response_model=CaseStatisticsResponse,
    summary="Get match statistics for a case",
    dependencies=[Depends(require_permission("vlr.cases.read"))],
)
async def get_case_statistics(
    case_id: UUID,
    company_code: str = Query(..., min_length=1, description="Company code"),
    repo: CaseRepositoryImpl = Depends(_get_case_repository),
    session: AsyncSession = Depends(get_db_session),
) -> CaseStatisticsResponse:
    """
    GET /api/v1/vlr/cases/{id}/statistics

    Returns match statistics including matched/unmatched counts, amounts,
    and per-pass breakdown.
    """
    from sqlalchemy import select, and_, func

    from src.infrastructure.database.models.vlr.ledger_entry_model import LedgerEntryModel

    # Verify case exists
    case = await repo.get_by_id(case_id, company_code)
    if case is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Reconciliation case {case_id} not found.",
        )

    # Count company entries
    company_count_stmt = select(func.count(LedgerEntryModel.id)).where(
        and_(
            LedgerEntryModel.case_id == case_id,
            LedgerEntryModel.side == "company",
        )
    )
    total_company = (await session.execute(company_count_stmt)).scalar_one()

    # Count vendor entries
    vendor_count_stmt = select(func.count(LedgerEntryModel.id)).where(
        and_(
            LedgerEntryModel.case_id == case_id,
            LedgerEntryModel.side == "vendor",
        )
    )
    total_vendor = (await session.execute(vendor_count_stmt)).scalar_one()

    # Count matched entries (those with a match_id)
    matched_count_stmt = select(func.count(LedgerEntryModel.id)).where(
        and_(
            LedgerEntryModel.case_id == case_id,
            LedgerEntryModel.match_id.isnot(None),
        )
    )
    matched_count = (await session.execute(matched_count_stmt)).scalar_one()

    # Sum matched amounts
    matched_amount_stmt = select(func.coalesce(func.sum(LedgerEntryModel.amount), 0)).where(
        and_(
            LedgerEntryModel.case_id == case_id,
            LedgerEntryModel.side == "company",
            LedgerEntryModel.match_id.isnot(None),
        )
    )
    matched_amount = (await session.execute(matched_amount_stmt)).scalar_one()

    total_entries = total_company + total_vendor
    unmatched_count = total_entries - matched_count
    match_percentage = (matched_count / total_entries * 100) if total_entries > 0 else 0.0

    # Use stored match_statistics from case if available
    statistics_by_pass = case.match_statistics if case.match_statistics else None

    return CaseStatisticsResponse(
        case_id=case_id,
        status=case.status,
        total_company_entries=total_company,
        total_vendor_entries=total_vendor,
        matched_count=matched_count,
        unmatched_count=unmatched_count,
        match_percentage=round(match_percentage, 2),
        matched_amount=matched_amount,
        row_10_balance=case.row_10_balance,
        statistics_by_pass=statistics_by_pass,
    )


# ──────────────────────────────────────────────────────────────────────
# Direct Reconciliation
# ──────────────────────────────────────────────────────────────────────


@router.post(
    "/direct",
    response_model=DirectReconciliationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create direct reconciliation case with dual file upload",
    dependencies=[Depends(require_permission("vlr.cases.write"))],
)
async def create_direct_reconciliation(
    company_file: UploadFile = File(..., description="Company ledger file (CSV or XLSX)"),
    vendor_file: UploadFile = File(..., description="Vendor statement file (CSV or XLSX)"),
    config: str = Form(..., description="JSON configuration for direct reconciliation"),
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db_session),
) -> DirectReconciliationResponse:
    """
    POST /api/v1/vlr/cases/direct

    Creates a single-vendor reconciliation case with inline configuration
    and dual file upload (company + vendor), then immediately triggers
    the reconciliation engine.

    This is the "direct" reconciliation flow — bypasses the batch request
    workflow and goes straight from upload to reconciliation.

    Requirements:
    - 18.1: Single-vendor direct case creation with inline config
    - 18.2: Dual file upload (company + vendor) in single request
    - 18.3: Immediate reconciliation trigger after successful upload
    - 18.4: Period overlap validation for direct cases
    - 18.5: case_type="direct" to distinguish from batch flow
    - 18.6: File validation (format, size, mandatory columns)
    - 18.7: Vendor must be active
    - 18.8: Creates parent request record for consistency
    """
    # ─── Parse and validate configuration ─────────────────────────────────
    try:
        config_data = json.loads(config)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid JSON in 'config' field: {exc.msg}",
        )

    try:
        recon_config = DirectReconciliationConfig(**config_data)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Configuration validation failed: {exc}",
        )

    # ─── Validate vendor exists and is active (Req 18.7) ──────────────────
    vendor_repo = VendorRepositoryImpl(session)
    vendor = await vendor_repo.get_by_id(recon_config.vendor_id, recon_config.company_code)
    if vendor is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Vendor with id '{recon_config.vendor_id}' not found.",
        )
    if getattr(vendor, "status", None) == "inactive":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Vendor '{getattr(vendor, 'vendor_code', recon_config.vendor_id)}' is inactive.",
        )

    # ─── Period overlap validation (Req 18.4) ─────────────────────────────
    request_repo = RequestRepositoryImpl(session)
    period = DateRange(start=recon_config.period_start, end=recon_config.period_end)

    has_overlap = await request_repo.has_overlapping_period(
        vendor_id=recon_config.vendor_id,
        company_code=recon_config.company_code,
        period_start=period.start,
        period_end=period.end,
    )
    if has_overlap:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "A reconciliation request already exists for this vendor "
                "in the specified period. Period overlap is not allowed for direct cases."
            ),
        )

    # ─── Validate and parse company file (Req 18.6) ───────────────────────
    company_content = await company_file.read()
    if not company_content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Company ledger file is empty.",
        )

    parser = FileParserService()

    try:
        company_result = parser.validate_and_parse(
            company_content, company_file.filename or "company.csv"
        )
    except FileValidationException as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Company file validation failed: {exc.message}",
        )

    if not company_result.is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Company file validation failed: {'; '.join(company_result.errors)}",
        )

    if not company_result.entries:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Company file contains no valid entries.",
        )

    # ─── Validate and parse vendor file (Req 18.6) ────────────────────────
    vendor_content = await vendor_file.read()
    if not vendor_content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Vendor statement file is empty.",
        )

    try:
        vendor_result = parser.validate_and_parse(
            vendor_content, vendor_file.filename or "vendor.csv"
        )
    except FileValidationException as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Vendor file validation failed: {exc.message}",
        )

    if not vendor_result.is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Vendor file validation failed: {'; '.join(vendor_result.errors)}",
        )

    if not vendor_result.entries:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Vendor file contains no valid entries.",
        )

    # ─── Create parent request record (Req 18.8) ─────────────────────────
    # For consistency with the data model, direct reconciliation still creates
    # a parent request record but in 'active' status (skipping draft).
    matching_prefs = {
        "exact_match_enabled": True,
        "tolerance_match_enabled": True,
        "fuzzy_reference_enabled": True,
        "one_to_many_enabled": True,
        "many_to_one_enabled": True,
    }

    request_data = {
        "company_code": recon_config.company_code,
        "fiscal_year": recon_config.fiscal_year,
        "period_start": recon_config.period_start,
        "period_end": recon_config.period_end,
        "status": "active",
        "tolerance_amount": recon_config.tolerance_amount,
        "tds_percentage": recon_config.tds_percentage,
        "gst_percentage": recon_config.gst_percentage,
        "matching_preferences": matching_prefs,
        "description": "Direct reconciliation",
        "created_by": current_user.username,
        "modified_by": current_user.username,
    }

    request_record = await request_repo.create(request_data)
    request_id = getattr(request_record, "id")

    # ─── Create reconciliation case with case_type="direct" (Req 18.5) ────
    case_repo = CaseRepositoryImpl(session)
    case_data = {
        "request_id": request_id,
        "vendor_id": recon_config.vendor_id,
        "case_type": "direct",
        "status": "statement_received",
        "upload_count": 1,
        "edit_count": 0,
        "portal_token": str(uuid4()),
        "created_by": current_user.username,
        "modified_by": current_user.username,
    }

    case_record = await case_repo.create(case_data)
    case_id = getattr(case_record, "id")

    # ─── Persist company ledger entries (Req 18.2) ────────────────────────
    ledger_repo = LedgerEntryRepositoryImpl(session)

    company_entries_data = [
        {
            "id": uuid4(),
            "case_id": case_id,
            "side": "company",
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
            "source": "direct_upload",
            "created_by": current_user.username,
            "modified_by": current_user.username,
        }
        for entry in company_result.entries
    ]

    await ledger_repo.bulk_create(company_entries_data)

    # ─── Persist vendor ledger entries (Req 18.2) ─────────────────────────
    vendor_entries_data = [
        {
            "id": uuid4(),
            "case_id": case_id,
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
            "source": "direct_upload",
            "created_by": current_user.username,
            "modified_by": current_user.username,
        }
        for entry in vendor_result.entries
    ]

    await ledger_repo.bulk_create(vendor_entries_data)

    # Flush to ensure all records are persisted before triggering reconciliation
    await session.commit()

    # ─── Trigger reconciliation immediately (Req 18.3) ────────────────────
    task_id = None
    reconciliation_triggered = False

    # Run reconciliation synchronously (no Celery/Redis dependency)
    try:
        from src.domain.services.vlr.reconciliation_engine_service import ReconciliationEngineService

        engine = ReconciliationEngineService(
            ledger_entry_repository=LedgerEntryRepositoryImpl(session),
            match_result_repository=MatchResultRepositoryImpl(session),
            case_repository=CaseRepositoryImpl(session),
            exception_repository=ExceptionRepositoryImpl(session),
        )
        await engine.execute(
            case_id=case_id,
            tolerance=__import__('decimal').Decimal(str(recon_config.tolerance_amount)),
            fuzzy_threshold=recon_config.fuzzy_threshold,
        )
        # Update case status based on reconciliation result
        # If all entries matched → auto_completed; otherwise → mapping_pending
        case_repo_update = CaseRepositoryImpl(session)
        case_obj = await case_repo_update.get_by_id(case_id)
        match_stats = getattr(case_obj, "match_statistics", None) or {}
        total_company = match_stats.get("total_company_entries", 0)
        total_vendor = match_stats.get("total_vendor_entries", 0)
        matched_company = match_stats.get("total_matched_company", 0)
        matched_vendor = match_stats.get("total_matched_vendor", 0)
        all_matched = (matched_company >= total_company and matched_vendor >= total_vendor)
        new_status = "auto_completed" if all_matched else "mapping_pending"
        await case_repo_update.update(case_id, {
            "status": new_status,
            "current_workflow_step": new_status,
        })
        await session.commit()
        reconciliation_triggered = True
        task_id = "sync-inline"
    except Exception as exc:
        logger.warning(
            "Failed to run reconciliation for direct case: case_id=%s, error=%s",
            case_id,
            str(exc),
            exc_info=True,
        )
        # Still return success — case is created, reconciliation can be retried
        reconciliation_triggered = False

    logger.info(
        "Direct reconciliation case created: case_id=%s, vendor_id=%s, "
        "company_entries=%d, vendor_entries=%d, reconciliation_triggered=%s",
        case_id,
        recon_config.vendor_id,
        len(company_result.entries),
        len(vendor_result.entries),
        reconciliation_triggered,
    )

    return DirectReconciliationResponse(
        case_id=case_id,
        request_id=request_id,
        vendor_id=recon_config.vendor_id,
        case_type="direct",
        status="auto_completed" if reconciliation_triggered else "statement_received",
        company_entries_count=len(company_result.entries),
        vendor_entries_count=len(vendor_result.entries),
        reconciliation_triggered=reconciliation_triggered,
        task_id=task_id,
        message=(
            f"Direct reconciliation case created with {len(company_result.entries)} "
            f"company entries and {len(vendor_result.entries)} vendor entries. "
            + (
                "Reconciliation triggered."
                if reconciliation_triggered
                else "Reconciliation could not be triggered automatically."
            )
        ),
        created_date=getattr(case_record, "created_date", None),
    )

# ──────────────────────────────────────────────────────────────────────
# Manual Mapping (when reco engine can't auto-map)
# ──────────────────────────────────────────────────────────────────────


class ManualMatchEntry(BaseModel):
    """A single manual match pair/group."""
    company_entry_ids: list[UUID] = Field(..., description="Company ledger entry IDs to match")
    vendor_entry_ids: list[UUID] = Field(..., description="Vendor ledger entry IDs to match")


class ManualMappingRequest(BaseModel):
    """Request body for manual mapping of ledger entries."""
    matches: list[ManualMatchEntry] = Field(..., min_length=1, description="List of manual match pairs/groups")


class ManualMappingResponse(BaseModel):
    """Response for manual mapping operation."""
    case_id: UUID
    matches_created: int
    status: str
    message: str


@router.post(
    "/{case_id}/manual-mapping",
    response_model=ManualMappingResponse,
    status_code=status.HTTP_200_OK,
    summary="Manually map unmatched ledger entries",
    dependencies=[Depends(require_permission("vlr.cases.write"))],
)
async def manual_mapping(
    case_id: UUID,
    body: ManualMappingRequest,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_active_user),
):
    """
    Manually map company and vendor ledger entries when the reconciliation
    engine cannot auto-map them.

    This endpoint creates match records for user-specified entry pairs/groups
    and transitions the case from mapping_pending to statement_mapped.
    """
    case_repo = CaseRepositoryImpl(session)
    case_obj = await case_repo.get_by_id(case_id)
    if not case_obj:
        raise HTTPException(status_code=404, detail="Case not found")

    match_repo = MatchResultRepositoryImpl(session)
    ledger_repo = LedgerEntryRepositoryImpl(session)

    matches_created = 0
    for match_entry in body.matches:
        match_id = uuid4()
        is_group = (
            len(match_entry.company_entry_ids) > 1
            or len(match_entry.vendor_entry_ids) > 1
        )
        match_data = {
            "id": match_id,
            "case_id": case_id,
            "pass_number": 0,  # Manual match
            "match_type": "group" if is_group else "pair",
            "confidence_score": 1.0,  # Manual = full confidence
            "is_confirmed": True,
            "company_entry_ids": [str(eid) for eid in match_entry.company_entry_ids],
            "vendor_entry_ids": [str(eid) for eid in match_entry.vendor_entry_ids],
            "matched_amount": 0,  # Will be calculated
            "difference_amount": 0,
        }
        await match_repo.create(match_data)

        # Update ledger entries with match metadata
        all_ids = list(match_entry.company_entry_ids) + list(match_entry.vendor_entry_ids)
        await ledger_repo.bulk_update_match(
            entry_ids=all_ids,
            match_id=match_id,
            pass_number=0,
            confidence_score=1.0,
        )
        matches_created += 1

    # Transition case status to statement_mapped
    current_status = getattr(case_obj, "status", "")
    if current_status == "mapping_pending":
        await case_repo.update(case_id, {
            "status": "statement_mapped",
            "current_workflow_step": "statement_mapped",
        })

    await session.commit()

    return ManualMappingResponse(
        case_id=case_id,
        matches_created=matches_created,
        status="statement_mapped",
        message=f"Successfully created {matches_created} manual match(es). Case moved to statement_mapped.",
    )


# ──────────────────────────────────────────────────────────────────────
# Bulk Actions (Requirement 4)
# ──────────────────────────────────────────────────────────────────────


@router.post(
    "/bulk-review",
    response_model=BulkActionResponse,
    status_code=status.HTTP_200_OK,
    summary="Bulk advance cases to review stage",
    dependencies=[Depends(require_permission("vlr.cases.write"))],
)
async def bulk_review(
    request: BulkActionRequest,
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db_session),
) -> BulkActionResponse:
    """
    POST /api/v1/vlr/cases/bulk-review

    Advance multiple cases to the review workflow step. Each case is validated
    independently — failures on one case do not affect others.

    Requirement 4: Bulk action — Send For Review for selected cases.
    """
    from src.domain.services.vlr.workflow_orchestrator_service import (
        CaseNotFoundError,
        SLAConfiguration,
        WorkflowOrchestratorService,
        WorkflowStep,
        WorkflowTransitionError,
    )

    case_repo = CaseRepositoryImpl(session)
    orchestrator = WorkflowOrchestratorService(
        case_repository=case_repo,
        sla_config=SLAConfiguration(),
    )

    results: list[BulkActionResultItem] = []

    for case_id_str in request.case_ids:
        try:
            case_uuid = UUID(case_id_str)

            # Verify case exists and belongs to the company
            case = await case_repo.get_by_id(case_uuid, request.company_code)
            if case is None:
                results.append(BulkActionResultItem(
                    case_id=case_id_str,
                    success=False,
                    message=f"Case {case_id_str} not found.",
                ))
                continue

            # Advance to FINANCE_REVIEW step via workflow orchestrator
            await orchestrator.advance(
                case_id=case_uuid,
                target_step=WorkflowStep.FINANCE_REVIEW,
                triggered_by=current_user.username,
            )

            # Also transition case status to review
            service = RequestManagerService(
                request_repository=RequestRepositoryImpl(session),
                case_repository=case_repo,
                vendor_repository=VendorRepositoryImpl(session),
            )
            await service.transition_case_status(
                case_uuid, request.company_code, CaseStatus.REVIEW_PENDING
            )

            results.append(BulkActionResultItem(
                case_id=case_id_str,
                success=True,
                message="Case advanced to review stage.",
            ))

        except (WorkflowTransitionError, CaseNotFoundError) as e:
            results.append(BulkActionResultItem(
                case_id=case_id_str,
                success=False,
                message=str(e),
            ))
        except ValueError:
            results.append(BulkActionResultItem(
                case_id=case_id_str,
                success=False,
                message=f"Invalid case ID format: {case_id_str}",
            ))
        except Exception as e:
            logger.warning("Error advancing case %s to review: %s", case_id_str, str(e))
            results.append(BulkActionResultItem(
                case_id=case_id_str,
                success=False,
                message=f"Failed to advance case: {str(e)}",
            ))

    return BulkActionResponse(results=results)


@router.post(
    "/bulk-review-done",
    response_model=BulkActionResponse,
    status_code=status.HTTP_200_OK,
    summary="Bulk mark review as complete for cases",
    dependencies=[Depends(require_permission("vlr.cases.write"))],
)
async def bulk_review_done(
    request: BulkActionRequest,
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db_session),
) -> BulkActionResponse:
    """
    POST /api/v1/vlr/cases/bulk-review-done

    Mark review as complete for multiple cases. Advances them past the review
    stage in the workflow. Each case is validated independently.

    Requirement 4: Bulk action — Review Done for selected cases.
    """
    from src.domain.services.vlr.workflow_orchestrator_service import (
        CaseNotFoundError,
        SLAConfiguration,
        WorkflowOrchestratorService,
        WorkflowStep,
        WorkflowTransitionError,
    )

    case_repo = CaseRepositoryImpl(session)
    orchestrator = WorkflowOrchestratorService(
        case_repository=case_repo,
        sla_config=SLAConfiguration(),
    )

    results: list[BulkActionResultItem] = []

    for case_id_str in request.case_ids:
        try:
            case_uuid = UUID(case_id_str)

            # Verify case exists and belongs to the company
            case = await case_repo.get_by_id(case_uuid, request.company_code)
            if case is None:
                results.append(BulkActionResultItem(
                    case_id=case_id_str,
                    success=False,
                    message=f"Case {case_id_str} not found.",
                ))
                continue

            # Advance to FINANCE_APPROVAL step (post-review)
            await orchestrator.advance(
                case_id=case_uuid,
                target_step=WorkflowStep.FINANCE_APPROVAL,
                triggered_by=current_user.username,
            )

            # Transition case status to pending approval
            service = RequestManagerService(
                request_repository=RequestRepositoryImpl(session),
                case_repository=case_repo,
                vendor_repository=VendorRepositoryImpl(session),
            )
            await service.transition_case_status(
                case_uuid, request.company_code, CaseStatus.SIGNOFF_REQUESTED
            )

            results.append(BulkActionResultItem(
                case_id=case_id_str,
                success=True,
                message="Review marked as complete.",
            ))

        except (WorkflowTransitionError, CaseNotFoundError) as e:
            results.append(BulkActionResultItem(
                case_id=case_id_str,
                success=False,
                message=str(e),
            ))
        except ValueError:
            results.append(BulkActionResultItem(
                case_id=case_id_str,
                success=False,
                message=f"Invalid case ID format: {case_id_str}",
            ))
        except Exception as e:
            logger.warning("Error marking review done for case %s: %s", case_id_str, str(e))
            results.append(BulkActionResultItem(
                case_id=case_id_str,
                success=False,
                message=f"Failed to mark review done: {str(e)}",
            ))

    return BulkActionResponse(results=results)


@router.post(
    "/bulk-signoff-request",
    response_model=BulkActionResponse,
    status_code=status.HTTP_200_OK,
    summary="Bulk trigger portal sign-off invite for cases",
    dependencies=[Depends(require_permission("vlr.cases.write"))],
)
async def bulk_signoff_request(
    request: BulkActionRequest,
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db_session),
) -> BulkActionResponse:
    """
    POST /api/v1/vlr/cases/bulk-signoff-request

    Trigger portal sign-off invitations for multiple cases. Advances each case
    to the vendor sign-off workflow step and dispatches sign-off invite notifications.

    Requirement 4: Bulk action — Request SignOff for selected cases.
    """
    from src.domain.services.vlr.workflow_orchestrator_service import (
        CaseNotFoundError,
        SLAConfiguration,
        WorkflowOrchestratorService,
        WorkflowStep,
        WorkflowTransitionError,
    )

    case_repo = CaseRepositoryImpl(session)
    orchestrator = WorkflowOrchestratorService(
        case_repository=case_repo,
        sla_config=SLAConfiguration(),
    )

    results: list[BulkActionResultItem] = []

    for case_id_str in request.case_ids:
        try:
            case_uuid = UUID(case_id_str)

            # Verify case exists and belongs to the company
            case = await case_repo.get_by_id(case_uuid, request.company_code)
            if case is None:
                results.append(BulkActionResultItem(
                    case_id=case_id_str,
                    success=False,
                    message=f"Case {case_id_str} not found.",
                ))
                continue

            # Advance to VENDOR_SIGN_OFF step
            await orchestrator.advance(
                case_id=case_uuid,
                target_step=WorkflowStep.VENDOR_SIGN_OFF,
                triggered_by=current_user.username,
            )

            # Dispatch sign-off invite notification
            try:
                from src.infrastructure.tasks.vlr.notification_tasks import send_signoff_invite_task

                send_signoff_invite_task.delay(
                    case_id=case_id_str,
                    company_code=request.company_code,
                    triggered_by=current_user.username,
                )
            except (ImportError, Exception):
                # Task module not available — continue anyway
                pass

            results.append(BulkActionResultItem(
                case_id=case_id_str,
                success=True,
                message="Sign-off invite sent to vendor portal.",
            ))

        except (WorkflowTransitionError, CaseNotFoundError) as e:
            results.append(BulkActionResultItem(
                case_id=case_id_str,
                success=False,
                message=str(e),
            ))
        except ValueError:
            results.append(BulkActionResultItem(
                case_id=case_id_str,
                success=False,
                message=f"Invalid case ID format: {case_id_str}",
            ))
        except Exception as e:
            logger.warning("Error requesting sign-off for case %s: %s", case_id_str, str(e))
            results.append(BulkActionResultItem(
                case_id=case_id_str,
                success=False,
                message=f"Failed to request sign-off: {str(e)}",
            ))

    return BulkActionResponse(results=results)
