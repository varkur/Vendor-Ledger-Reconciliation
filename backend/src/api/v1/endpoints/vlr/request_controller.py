"""
Reconciliation Request API endpoints.
Thin controller — delegates all business logic to RequestManagerService.

Routes:
- GET    /api/v1/vlr/requests          — List requests with filters & pagination
- POST   /api/v1/vlr/requests          — Create a new reconciliation request
- GET    /api/v1/vlr/requests/{id}     — Get request by ID
- POST   /api/v1/vlr/requests/{id}/clone      — Clone request for new period
- GET    /api/v1/vlr/requests/{id}/statistics  — Get request statistics
- POST   /api/v1/vlr/reconciliation-requests/{request_id}/upload-company-ledger — Upload company ledger file

Note: POST /api/v1/vlr/requests/{id}/sap-pull is handled by sap_pull_controller.py

Requirements: 3.1, 3.2, 3.4, 3.5, 3.6, 3.7, 3.10, 11.2, 11.6
"""

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.v1.dependencies import get_current_active_user
from src.api.v1.schemas.vlr.request_schemas import (
    CloneRequestRequest,
    CreateRequestRequest,
    ReconciliationRequestResponse,
    RequestListResponse,
    RequestStatisticsResponse,
)
from src.domain.entities.user import User
from src.domain.repositories.vlr.request_repository import RequestFilters
from src.domain.repositories.vlr.vendor_repository import PaginationParams
from src.domain.services.vlr.request_manager_service import (
    DateRange,
    MatchingPreferences,
    RequestCreateDTO,
    RequestManagerService,
)
from src.infrastructure.database.repositories.vlr.case_repository_impl import (
    CaseRepositoryImpl,
)
from src.infrastructure.database.repositories.vlr.request_repository_impl import (
    RequestRepositoryImpl,
)
from src.infrastructure.database.repositories.vlr.vendor_repository_impl import (
    VendorRepositoryImpl,
)
from src.infrastructure.database.session import get_db_session
from src.infrastructure.security.permission_manager import require_permission

router = APIRouter(prefix="/vlr/requests", tags=["VLR - Reconciliation Requests"])


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


def _get_request_repository(
    session: AsyncSession = Depends(get_db_session),
) -> RequestRepositoryImpl:
    """FastAPI dependency — creates RequestRepository for direct queries."""
    return RequestRepositoryImpl(session)


# ──────────────────────────────────────────────────────────────────────
# Endpoints
# ──────────────────────────────────────────────────────────────────────


@router.get(
    "",
    response_model=RequestListResponse,
    summary="List reconciliation requests with filters and pagination",
    dependencies=[Depends(require_permission("vlr.requests.read"))],
)
async def list_requests(
    company_code: str = Query(..., min_length=1, description="Company code filter"),
    request_status: str | None = Query(default=None, alias="status", description="Filter by request status"),
    fiscal_year: str | None = Query(default=None, description="Filter by fiscal year"),
    date_from: date | None = Query(default=None, description="Filter by creation date from"),
    date_to: date | None = Query(default=None, description="Filter by creation date to"),
    assigned_manager_id: UUID | None = Query(default=None, description="Filter by assigned manager"),
    page: int = Query(default=1, ge=1, description="Page number"),
    page_size: int = Query(default=50, ge=1, le=200, description="Items per page"),
    repo: RequestRepositoryImpl = Depends(_get_request_repository),
) -> RequestListResponse:
    """GET /api/v1/vlr/requests — List requests with filtering and pagination."""
    filters = RequestFilters(
        status=request_status,
        fiscal_year=fiscal_year,
        date_from=date_from,
        date_to=date_to,
        assigned_manager_id=assigned_manager_id,
    )
    pagination = PaginationParams(page=page, page_size=page_size)

    result = await repo.list_requests(
        company_code=company_code,
        filters=filters,
        pagination=pagination,
    )

    # Enrich each request with its party (case) count so the Track
    # Reconciliation list can show one row per request with N parties.
    from sqlalchemy import func as _func, select as _select
    from src.infrastructure.database.models.vlr.reconciliation_case_model import (
        ReconciliationCaseModel as _CaseModel,
    )

    request_ids = [r.id for r in result.items]
    counts_by_request: dict = {}
    if request_ids:
        count_stmt = (
            _select(
                _CaseModel.request_id,
                _func.count(_CaseModel.id),
            )
            .where(
                _CaseModel.request_id.in_(request_ids),
                _CaseModel.is_deleted == False,  # noqa: E712
            )
            .group_by(_CaseModel.request_id)
        )
        count_result = await repo._session.execute(count_stmt)
        counts_by_request = {row[0]: row[1] for row in count_result.all()}

    items = []
    for r in result.items:
        resp = ReconciliationRequestResponse.model_validate(r)
        resp.party_count = int(counts_by_request.get(r.id, 0))
        items.append(resp)

    return RequestListResponse(
        items=items,
        total=result.total,
        page=result.page,
        page_size=result.page_size,
        total_pages=result.total_pages,
    )


@router.post(
    "",
    response_model=ReconciliationRequestResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new reconciliation request",
    dependencies=[Depends(require_permission("vlr.requests.write"))],
)
async def create_request(
    request: CreateRequestRequest,
    current_user: User = Depends(get_current_active_user),
    service: RequestManagerService = Depends(_get_request_manager_service),
) -> ReconciliationRequestResponse:
    """POST /api/v1/vlr/requests — Create a new reconciliation request with cases."""
    matching_prefs = None
    if request.matching_preferences:
        matching_prefs = MatchingPreferences(
            exact_match_enabled=request.matching_preferences.exact_match_enabled,
            tolerance_match_enabled=request.matching_preferences.tolerance_match_enabled,
            fuzzy_reference_enabled=request.matching_preferences.fuzzy_reference_enabled,
            one_to_many_enabled=request.matching_preferences.one_to_many_enabled,
            many_to_one_enabled=request.matching_preferences.many_to_one_enabled,
        )

    dto = RequestCreateDTO(
        company_code=request.company_code,
        fiscal_year=request.fiscal_year,
        period_start=request.period_start,
        period_end=request.period_end,
        vendor_ids=request.vendor_ids,
        title=request.title,
        tolerance_amount=request.tolerance_amount,
        tds_percentage=request.tds_percentage,
        gst_percentage=request.gst_percentage,
        matching_preferences=matching_prefs,
        assigned_manager_id=request.assigned_manager_id,
        created_by=current_user.username or str(current_user.id),
    )

    from src.domain.exceptions.vlr import OverlappingPeriodException
    try:
        result = await service.create_request(dto)
    except OverlappingPeriodException as e:
        raise HTTPException(
            status_code=409,
            detail=e.message or "A reconciliation request already exists for one or more selected vendors in the specified date range. Please use a different period or remove the overlapping vendor(s).",
        )
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=str(e),
        )
    except Exception as e:
        import logging
        logging.getLogger(__name__).exception("Unexpected error creating request: %s", e)
        raise HTTPException(
            status_code=500,
            detail=f"An unexpected error occurred while creating the request: {str(e)}",
        )
    return ReconciliationRequestResponse.model_validate(result)


@router.get(
    "/{request_id}",
    response_model=ReconciliationRequestResponse,
    summary="Get reconciliation request by ID",
    dependencies=[Depends(require_permission("vlr.requests.read"))],
)
async def get_request(
    request_id: UUID,
    company_code: str = Query(..., min_length=1, description="Company code"),
    repo: RequestRepositoryImpl = Depends(_get_request_repository),
) -> ReconciliationRequestResponse:
    """GET /api/v1/vlr/requests/{id} — Retrieve a request by ID."""
    request_obj = await repo.get_by_id(request_id, company_code)
    if request_obj is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Reconciliation request {request_id} not found.",
        )
    return ReconciliationRequestResponse.model_validate(request_obj)


@router.post(
    "/{request_id}/clone",
    response_model=ReconciliationRequestResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Clone a reconciliation request for a new period",
    dependencies=[Depends(require_permission("vlr.requests.write"))],
)
async def clone_request(
    request_id: UUID,
    body: CloneRequestRequest,
    company_code: str = Query(..., min_length=1, description="Company code"),
    current_user: User = Depends(get_current_active_user),
    service: RequestManagerService = Depends(_get_request_manager_service),
) -> ReconciliationRequestResponse:
    """POST /api/v1/vlr/requests/{id}/clone — Clone request configuration for a new period."""
    new_period = DateRange(start=body.period_start, end=body.period_end)

    result = await service.clone_request(
        request_id=request_id,
        company_code=company_code,
        new_period=new_period,
        created_by=current_user.username or str(current_user.id),
    )
    return ReconciliationRequestResponse.model_validate(result)


@router.get(
    "/{request_id}/statistics",
    response_model=RequestStatisticsResponse,
    summary="Get request-level statistics",
    dependencies=[Depends(require_permission("vlr.requests.read"))],
)
async def get_request_statistics(
    request_id: UUID,
    company_code: str = Query(..., min_length=1, description="Company code"),
    session: AsyncSession = Depends(get_db_session),
    repo: RequestRepositoryImpl = Depends(_get_request_repository),
) -> RequestStatisticsResponse:
    """GET /api/v1/vlr/requests/{id}/statistics — Full statistics for a request."""
    from sqlalchemy import case as sql_case, func, literal
    from sqlalchemy import select as sa_select

    from src.api.v1.schemas.vlr.request_schemas import (
        AmountCategoryRow,
        AmountEntry,
        ReconciliationStatusCounts,
        ReminderInfo,
        StatementStatusCounts,
    )
    from src.infrastructure.database.models.vlr.ledger_entry_model import LedgerEntryModel
    from src.infrastructure.database.models.vlr.notification_model import NotificationModel
    from src.infrastructure.database.models.vlr.reco_exception_model import RecoExceptionModel
    from src.infrastructure.database.models.vlr.reconciliation_case_model import (
        ReconciliationCaseModel,
    )
    from src.infrastructure.database.models.vlr.reconciliation_request_model import (
        ReconciliationRequestModel,
    )

    # Verify request exists
    request_obj = await repo.get_by_id(request_id, company_code)
    if request_obj is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Reconciliation request {request_id} not found.",
        )

    # ─── Case counts by status ────────────────────────────────────────────
    cases_by_status = await repo.get_statistics(request_id, company_code)
    total_cases = sum(cases_by_status.values())

    # ─── Statement Status ─────────────────────────────────────────────────
    # Map case statuses to statement status buckets. A vendor has "responded"
    # once they've uploaded (any status past 'created'/'invited').
    responded_statuses = {
        "data_received", "matching", "matched", "review",
        "pending_approval", "approved", "signed_off", "closed",
        "mapping_pending", "statement_mapped", "in_progress", "auto_completed",
        "review_pending", "reviewed", "signoff_requested", "signoff_completed",
    }
    rejected_statuses = {"rejected", "reco_rejected"}
    failed_statuses = {"failed"}

    responded = sum(v for k, v in cases_by_status.items() if k in responded_statuses)
    rejected = sum(v for k, v in cases_by_status.items() if k in rejected_statuses)
    failed = sum(v for k, v in cases_by_status.items() if k in failed_statuses)
    not_responded = total_cases - responded - rejected - failed

    statement_status = StatementStatusCounts(
        total=total_cases,
        responded=responded,
        not_responded=not_responded,
        rejected=rejected,
        failed=failed,
    )

    # ─── Reconciliation Status ────────────────────────────────────────────
    # Use the actual case status field (reflects real reconciliation state)
    status_stmt = (
        sa_select(
            ReconciliationCaseModel.status,
            func.count(ReconciliationCaseModel.id).label("count"),
        )
        .join(
            ReconciliationRequestModel,
            ReconciliationCaseModel.request_id == ReconciliationRequestModel.id,
        )
        .where(
            ReconciliationCaseModel.request_id == request_id,
            ReconciliationCaseModel.is_deleted == False,  # noqa: E712
            ReconciliationRequestModel.company_code == company_code,
        )
        .group_by(ReconciliationCaseModel.status)
    )
    ws_result = await session.execute(status_stmt)
    step_counts = {(row[0] or "unknown"): row[1] for row in ws_result.all()}

    reconciliation_status = ReconciliationStatusCounts(
        in_progress=step_counts.get("in_progress", 0) + step_counts.get("matching", 0) + step_counts.get("created", 0),
        statement_received=step_counts.get("data_received", 0) + step_counts.get("statement_received", 0),
        mapping_pending=step_counts.get("mapping_pending", 0),
        statement_mapped=step_counts.get("statement_mapped", 0),
        auto_completed=step_counts.get("auto_completed", 0) + step_counts.get("matched", 0),
        review_pending=step_counts.get("review_pending", 0) + step_counts.get("review", 0),
        reviewed=step_counts.get("reviewed", 0),
        signoff_requested=step_counts.get("signoff_requested", 0),
        signoff_completed=step_counts.get("signoff_completed", 0) + step_counts.get("signed_off", 0),
        reco_rejected=step_counts.get("reco_rejected", 0),
    )

    # ─── Amount Statistics ────────────────────────────────────────────────
    # Aggregate company closing balance and vendor closing balance per case
    amount_stmt = (
        sa_select(
            func.coalesce(func.sum(ReconciliationCaseModel.company_closing_balance), 0).label(
                "total_company"
            ),
            func.coalesce(func.sum(ReconciliationCaseModel.vendor_closing_balance), 0).label(
                "total_vendor"
            ),
            func.coalesce(func.sum(ReconciliationCaseModel.net_difference), 0).label(
                "total_net_diff"
            ),
            # Responded amounts (only cases in responded statuses)
            func.coalesce(
                func.sum(
                    sql_case(
                        (
                            ReconciliationCaseModel.status.in_(list(responded_statuses)),
                            ReconciliationCaseModel.company_closing_balance,
                        ),
                        else_=literal(0),
                    )
                ),
                0,
            ).label("company_responded"),
            func.coalesce(
                func.sum(
                    sql_case(
                        (
                            ReconciliationCaseModel.status.in_(list(responded_statuses)),
                            ReconciliationCaseModel.vendor_closing_balance,
                        ),
                        else_=literal(0),
                    )
                ),
                0,
            ).label("vendor_responded"),
            func.coalesce(
                func.sum(
                    sql_case(
                        (
                            ReconciliationCaseModel.status.in_(list(responded_statuses)),
                            ReconciliationCaseModel.net_difference,
                        ),
                        else_=literal(0),
                    )
                ),
                0,
            ).label("net_diff_responded"),
        )
        .join(
            ReconciliationRequestModel,
            ReconciliationCaseModel.request_id == ReconciliationRequestModel.id,
        )
        .where(
            ReconciliationCaseModel.request_id == request_id,
            ReconciliationCaseModel.is_deleted == False,  # noqa: E712
            ReconciliationRequestModel.company_code == company_code,
        )
    )
    amt_result = await session.execute(amount_stmt)
    amt_row = amt_result.one()

    amount_statistics = [
        AmountCategoryRow(
            category="Vendor Payable",
            total_company_amount=float(amt_row.total_company or 0),
            company_amount_responded=float(amt_row.company_responded or 0),
            party_amount_responded=float(amt_row.vendor_responded or 0),
            net_difference=float(amt_row.net_diff_responded or 0),
        ),
    ]

    # ─── Reason for Difference (from exceptions) ─────────────────────────
    exception_stmt = (
        sa_select(
            RecoExceptionModel.category,
            func.coalesce(func.sum(RecoExceptionModel.amount), 0).label("total_amount"),
            func.count(RecoExceptionModel.id).label("entry_count"),
        )
        .join(
            ReconciliationCaseModel,
            RecoExceptionModel.case_id == ReconciliationCaseModel.id,
        )
        .join(
            ReconciliationRequestModel,
            ReconciliationCaseModel.request_id == ReconciliationRequestModel.id,
        )
        .where(
            ReconciliationCaseModel.request_id == request_id,
            ReconciliationCaseModel.is_deleted == False,  # noqa: E712
            ReconciliationRequestModel.company_code == company_code,
        )
        .group_by(RecoExceptionModel.category)
    )
    exc_result = await session.execute(exception_stmt)
    reason_for_difference = {
        row.category: AmountEntry(amount=float(row.total_amount), entry_count=row.entry_count)
        for row in exc_result.all()
    }

    # ─── Action Summary (from exception statuses) ─────────────────────────
    action_stmt = (
        sa_select(
            RecoExceptionModel.status,
            func.coalesce(func.sum(RecoExceptionModel.amount), 0).label("total_amount"),
            func.count(RecoExceptionModel.id).label("entry_count"),
        )
        .join(
            ReconciliationCaseModel,
            RecoExceptionModel.case_id == ReconciliationCaseModel.id,
        )
        .join(
            ReconciliationRequestModel,
            ReconciliationCaseModel.request_id == ReconciliationRequestModel.id,
        )
        .where(
            ReconciliationCaseModel.request_id == request_id,
            ReconciliationCaseModel.is_deleted == False,  # noqa: E712
            ReconciliationRequestModel.company_code == company_code,
        )
        .group_by(RecoExceptionModel.status)
    )
    act_result = await session.execute(action_stmt)
    action_rows = {
        row.status: AmountEntry(amount=float(row.total_amount), entry_count=row.entry_count)
        for row in act_result.all()
    }

    # Map to expected action summary keys
    total_entries = sum(e.entry_count for e in action_rows.values())
    total_amount = sum(e.amount for e in action_rows.values())
    pending_party = action_rows.get("pending_with_party", AmountEntry())
    pending_company = action_rows.get("pending_with_company", AmountEntry())
    no_action = action_rows.get("resolved", AmountEntry())

    action_summary = {
        "total_differences": AmountEntry(amount=total_amount, entry_count=total_entries),
        "pending_with_party": pending_party,
        "pending_with_company": pending_company,
        "no_action_required": no_action,
    }

    # ─── Reminder Info ────────────────────────────────────────────────────
    reminder_stmt = (
        sa_select(
            func.count(NotificationModel.id).label("total_sent"),
            func.max(NotificationModel.sent_date).label("last_sent"),
        )
        .join(
            ReconciliationCaseModel,
            NotificationModel.case_id == ReconciliationCaseModel.id,
        )
        .where(
            ReconciliationCaseModel.request_id == request_id,
            ReconciliationCaseModel.is_deleted == False,  # noqa: E712
            NotificationModel.type == "reminder",
            NotificationModel.status == "sent",
        )
    )
    rem_result = await session.execute(reminder_stmt)
    rem_row = rem_result.one()

    reminder_info = ReminderInfo(
        reminders_sent=rem_row.total_sent or 0,
        max_reminders=5,
        last_reminder_date=(
            rem_row.last_sent.isoformat() if rem_row.last_sent else None
        ),
    )

    return RequestStatisticsResponse(
        request_id=request_id,
        total_cases=total_cases,
        cases_by_status=cases_by_status,
        statement_status=statement_status,
        reconciliation_status=reconciliation_status,
        amount_statistics=amount_statistics,
        reason_for_difference=reason_for_difference,
        action_summary=action_summary,
        reminder_info=reminder_info,
    )


# ──────────────────────────────────────────────────────────────────────
# Reconciliation Requests Router (alternate prefix for frontend compatibility)
# ──────────────────────────────────────────────────────────────────────


class UploadCompanyLedgerResponse(BaseModel):
    """Response for company ledger file upload."""

    request_id: UUID
    filename: str
    entries_parsed: int
    status: str = Field(default="uploaded", description="Upload processing status")
    message: str = Field(default="", description="Descriptive message")


reconciliation_requests_router = APIRouter(
    prefix="/vlr/reconciliation-requests",
    tags=["VLR - Reconciliation Requests"],
)


# ──────────────────────────────────────────────────────────────────────
# GET /{request_id}/cases — List cases for a request with stage filtering
# ──────────────────────────────────────────────────────────────────────


class BatchCaseRow(BaseModel):
    """Enriched case row for the Track Reconciliation page."""
    id: str
    case_id: str
    vendor_code: str
    vendor_name: str
    status: str
    workflow_step: str = ""
    last_update_date: str = ""
    days_elapsed: int = 0
    company_amount: float = 0
    difference_amount: float = 0
    file_extension: str = ""
    owner: str = ""
    reviewer: str = ""
    no_of_lines: int = 0
    unmatched_entries: int = 0
    reminder_count: int = 0
    contact_person: str = ""


class BatchCasesSummary(BaseModel):
    total_parties: int = 0
    reco_stage_count: int = 0
    review_stage_count: int = 0
    signoff_stage_count: int = 0


class BatchCasesResponse(BaseModel):
    items: list[BatchCaseRow]
    total: int = 0
    page: int = 1
    page_size: int = 50
    summary: BatchCasesSummary = Field(default_factory=BatchCasesSummary)


# Stage filter mapping (maps stage query param to case status values)
STAGE_STATUS_MAP = {
    "reconciliation": ["created", "data_received", "matching", "mapping_pending", "statement_mapped", "in_progress", "auto_completed", "matched", "ledger_confirmed", "invited"],
    "review": ["review", "review_pending", "pending_approval"],
    "signoff": ["approved", "signed_off", "signoff_requested", "signoff_completed", "closed"],
    "action_tracker": None,  # Special: returns action summary, not case list
}


@reconciliation_requests_router.get(
    "/{request_id}/cases",
    response_model=BatchCasesResponse,
    summary="List enriched cases for a reconciliation request with stage filtering",
    dependencies=[Depends(require_permission("vlr.cases.read"))],
)
async def get_batch_cases(
    request_id: UUID,
    company_code: str = Query(..., min_length=1, description="Company code"),
    stage: str | None = Query(default=None, description="Stage filter: reconciliation, review, signoff"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db_session),
) -> BatchCasesResponse:
    """
    GET /api/v1/vlr/reconciliation-requests/{request_id}/cases

    Returns enriched case rows with vendor details, computed days elapsed,
    amounts, and stage filtering for the Track Reconciliation tabs.
    """
    from datetime import datetime, timezone
    from sqlalchemy import select, func, and_, case as sql_case
    from src.infrastructure.database.models.vlr.reconciliation_case_model import ReconciliationCaseModel
    from src.infrastructure.database.models.vlr.reconciliation_request_model import ReconciliationRequestModel
    from src.infrastructure.database.models.vlr.vendor_model import VendorModel
    from src.infrastructure.database.models.vlr.ledger_entry_model import LedgerEntryModel

    # Verify request belongs to company
    req_stmt = select(ReconciliationRequestModel).where(
        ReconciliationRequestModel.id == request_id,
        ReconciliationRequestModel.company_code == company_code,
    )
    req_result = await session.execute(req_stmt)
    req_obj = req_result.scalar_one_or_none()
    if req_obj is None:
        raise HTTPException(status_code=404, detail="Request not found")

    # Base query: cases joined with vendor
    base_query = (
        select(ReconciliationCaseModel, VendorModel)
        .join(VendorModel, ReconciliationCaseModel.vendor_id == VendorModel.id)
        .where(
            ReconciliationCaseModel.request_id == request_id,
            ReconciliationCaseModel.is_deleted == False,  # noqa: E712
        )
    )

    # Apply stage filter
    if stage and stage in STAGE_STATUS_MAP and STAGE_STATUS_MAP[stage] is not None:
        statuses = STAGE_STATUS_MAP[stage]
        base_query = base_query.where(ReconciliationCaseModel.status.in_(statuses))

    # Count total
    count_query = select(func.count()).select_from(
        base_query.with_only_columns(ReconciliationCaseModel.id).subquery()
    )
    total = (await session.execute(count_query)).scalar_one()

    # Paginate
    offset = (page - 1) * page_size
    data_query = base_query.order_by(ReconciliationCaseModel.created_date.desc()).offset(offset).limit(page_size)
    result = await session.execute(data_query)
    rows = result.all()

    # Build enriched response
    now = datetime.now(timezone.utc)
    items: list[BatchCaseRow] = []

    for case_model, vendor_model in rows:
        # Compute days elapsed
        created = case_model.created_date
        days = (now - created).days if created else 0

        # Get company amount (sum of company-side ledger entries)
        amt_stmt = select(func.coalesce(func.sum(LedgerEntryModel.amount), 0)).where(
            LedgerEntryModel.case_id == case_model.id,
            LedgerEntryModel.side == "company",
        )
        company_amount = float((await session.execute(amt_stmt)).scalar_one())

        # Get difference amount (net_difference from case or compute)
        difference = float(case_model.net_difference or 0)

        # Count lines (vendor-side entries)
        lines_stmt = select(func.count(LedgerEntryModel.id)).where(
            LedgerEntryModel.case_id == case_model.id,
            LedgerEntryModel.side == "vendor",
        )
        no_of_lines = (await session.execute(lines_stmt)).scalar_one()

        # Count unmatched entries
        unmatched_stmt = select(func.count(LedgerEntryModel.id)).where(
            LedgerEntryModel.case_id == case_model.id,
            LedgerEntryModel.match_id == None,  # noqa: E711
        )
        unmatched = (await session.execute(unmatched_stmt)).scalar_one()

        items.append(BatchCaseRow(
            id=str(case_model.id),
            case_id=str(case_model.id),
            vendor_code=vendor_model.vendor_code,
            vendor_name=vendor_model.name,
            status=case_model.status,
            workflow_step=case_model.current_workflow_step or case_model.status,
            last_update_date=case_model.modified_date.strftime("%d-%b-%Y") if case_model.modified_date else "",
            days_elapsed=days,
            company_amount=company_amount,
            difference_amount=difference,
            no_of_lines=no_of_lines,
            unmatched_entries=unmatched,
            reminder_count=0,
            owner="",
            reviewer="",
            contact_person="",
        ))

    # Compute summary counts (across ALL cases, not just filtered)
    all_cases_stmt = select(ReconciliationCaseModel.status).where(
        ReconciliationCaseModel.request_id == request_id,
        ReconciliationCaseModel.is_deleted == False,  # noqa: E712
    )
    all_cases_result = await session.execute(all_cases_stmt)
    all_statuses = [r[0] for r in all_cases_result.all()]

    reco_statuses = set(STAGE_STATUS_MAP.get("reconciliation", []))
    review_statuses = set(STAGE_STATUS_MAP.get("review", []))
    signoff_statuses = set(STAGE_STATUS_MAP.get("signoff", []))

    summary = BatchCasesSummary(
        total_parties=len(all_statuses),
        reco_stage_count=sum(1 for s in all_statuses if s in reco_statuses),
        review_stage_count=sum(1 for s in all_statuses if s in review_statuses),
        signoff_stage_count=sum(1 for s in all_statuses if s in signoff_statuses),
    )

    return BatchCasesResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        summary=summary,
    )


@reconciliation_requests_router.post(
    "/{request_id}/upload-company-ledger",
    response_model=UploadCompanyLedgerResponse,
    summary="Upload company ledger file for a reconciliation request",
    dependencies=[Depends(require_permission("vlr.requests.write"))],
)
async def upload_company_ledger(
    request_id: UUID,
    file: UploadFile = File(..., description="Company ledger file (CSV, XLSX, or XLS)"),
    company_code: str = Query(..., min_length=1, description="Company code"),
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db_session),
) -> UploadCompanyLedgerResponse:
    """
    POST /api/v1/vlr/reconciliation-requests/{request_id}/upload-company-ledger

    Accepts a company ledger file upload (.csv, .xlsx, .xls), validates it,
    parses the entries, stores them in the database against the first case of
    the request, and triggers the data transformation pipeline.

    Requirements: 11
    """
    import logging

    from src.domain.exceptions.vlr import FileValidationException
    from src.domain.services.vlr.file_parser_service import FileParserService
    from src.infrastructure.database.models.vlr.ledger_entry_model import LedgerEntryModel
    from src.infrastructure.database.models.vlr.reconciliation_case_model import (
        ReconciliationCaseModel,
    )
    from src.infrastructure.database.repositories.vlr.request_repository_impl import (
        RequestRepositoryImpl,
    )
    from sqlalchemy import select

    logger = logging.getLogger(__name__)

    # ─── Verify request exists ────────────────────────────────────────────
    repo = RequestRepositoryImpl(session)
    request_obj = await repo.get_by_id(request_id, company_code)
    if request_obj is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Reconciliation request {request_id} not found.",
        )

    # ─── Validate file type ───────────────────────────────────────────────
    filename = file.filename or ""
    allowed_extensions = (".csv", ".xlsx", ".xls")
    if not filename.lower().endswith(allowed_extensions):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Unsupported file type. Please upload one of: "
                f"{', '.join(allowed_extensions)}"
            ),
        )

    # ─── Read and validate file content ───────────────────────────────────
    file_content = await file.read()
    if not file_content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty.",
        )

    # Enforce max file size (50MB as per task spec)
    max_size = 50 * 1024 * 1024
    if len(file_content) > max_size:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="File size exceeds the maximum allowed size of 50MB.",
        )

    # ─── Parse the file ───────────────────────────────────────────────────
    import io

    parser = FileParserService(max_file_size_bytes=max_size)

    try:
        result = parser.validate_and_parse(file_content, filename)
    except FileValidationException as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"File validation failed: {'; '.join(e.errors)}",
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Failed to parse file: {str(e)}",
        )

    if not result.is_valid:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"File validation errors: {'; '.join(result.errors)}",
        )

    if not result.entries:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No valid entries found in the uploaded file.",
        )

    # ─── Find or get the first case for this request ──────────────────────
    case_stmt = (
        select(ReconciliationCaseModel)
        .where(ReconciliationCaseModel.request_id == request_id)
        .order_by(ReconciliationCaseModel.created_date.asc())
        .limit(1)
    )
    case_result = await session.execute(case_stmt)
    case = case_result.scalar_one_or_none()

    if case is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No cases found for reconciliation request {request_id}.",
        )

    # ─── Save original file headers for column mapping UI ────────────────
    if result.raw_headers:
        import json as _json
        from src.infrastructure.database.repositories.vlr.setting_repository_impl import (
            SettingRepositoryImpl as _SettingRepoHeaders,
        )
        _headers_repo = _SettingRepoHeaders(session)
        await _headers_repo.upsert(
            company_code="__global__",
            key=f"file_headers.{case.id}.company",
            value=_json.dumps(result.raw_headers),
            value_type="json",
            description="Original file headers from company ledger upload",
        )

    # ─── Store ledger entries ─────────────────────────────────────────────
    for entry in result.entries:
        ledger_entry = LedgerEntryModel(
            case_id=case.id,
            side="company",
            document_number=entry.document_number,
            document_type=entry.document_type,
            reference_number=entry.reference_number,
            posting_date=entry.posting_date,
            clearing_date=entry.clearing_date,
            clearing_document=entry.clearing_document,
            amount=float(entry.amount),
            currency=entry.currency,
            assignment_number=entry.assignment_number,
            description=entry.description,
            raw_data=getattr(entry, "raw_data", None),
            source="upload",
            created_by=current_user.username,
            modified_by=current_user.username,
        )
        session.add(ledger_entry)

    # ─── Store the ORIGINAL uploaded file bytes (verbatim download) ───────
    from src.api.v1.endpoints.vlr.column_mapping_controller import (
        store_original_ledger_file as _store_original,
    )
    await _store_original(
        session, case.id, "company", filename, file_content,
        modified_by=current_user.username,
    )

    await session.flush()

    # ─── Trigger transformation pipeline (async, best-effort) ─────────────
    try:
        from src.infrastructure.tasks.vlr.reconciliation_tasks import transformation_task

        transformation_task.delay(
            case_id=str(case.id),
            company_code=company_code,
            triggered_by=current_user.username,
        )
        pipeline_status = "processing"
        message = (
            f"Successfully uploaded {len(result.entries)} entries from '{filename}'. "
            f"Transformation pipeline has been triggered."
        )
    except (ImportError, Exception) as exc:
        logger.warning(
            "Failed to trigger transformation pipeline: request_id=%s, error=%s",
            request_id,
            str(exc),
        )
        pipeline_status = "uploaded"
        message = (
            f"Successfully uploaded {len(result.entries)} entries from '{filename}'. "
            f"Transformation pipeline could not be triggered automatically."
        )

    logger.info(
        "Company ledger uploaded: request_id=%s, case_id=%s, entries=%d, file=%s",
        request_id,
        case.id,
        len(result.entries),
        filename,
    )

    return UploadCompanyLedgerResponse(
        request_id=request_id,
        filename=filename,
        entries_parsed=len(result.entries),
        status=pipeline_status,
        message=message,
    )


# ──────────────────────────────────────────────────────────────────────
# Send Vendor Invite Emails
# ──────────────────────────────────────────────────────────────────────


class SendInviteResponse(BaseModel):
    """Response for send vendor invite endpoint."""

    request_id: UUID
    emails_sent: int
    emails_failed: int
    details: list[dict] = Field(default_factory=list)


class SendInviteRequest(BaseModel):
    """Optional request body for send vendor invites.

    `cc_emails` are additional recipients (e.g. the contact person selected in
    the UI dropdown) that get CC'd on every invite email alongside the vendor's
    primary contact.

    `remarks` is an optional free-text message included in each invite email.
    """

    cc_emails: list[str] = Field(default_factory=list)
    remarks: str = Field(default="", description="Optional remarks/message shown in the invite email")


@reconciliation_requests_router.post(
    "/{request_id}/send-vendor-invites",
    response_model=SendInviteResponse,
    summary="Send vendor invite emails with portal links",
    dependencies=[Depends(require_permission("vlr.requests.write"))],
)
async def send_vendor_invites(
    request_id: UUID,
    company_code: str = Query(..., min_length=1, description="Company code"),
    body: SendInviteRequest | None = None,
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db_session),
) -> SendInviteResponse:
    """
    POST /api/v1/vlr/reconciliation-requests/{request_id}/send-vendor-invites

    Sends vendor invite emails for all cases in the request. Each vendor's primary
    contact receives an email with a unique tokenized portal link where they can
    upload their ledger statement.

    This should be called after the company ledger has been uploaded.
    """
    import logging
    from datetime import datetime, timedelta, timezone

    from sqlalchemy import select
    from src.infrastructure.database.models.vlr.reconciliation_case_model import (
        ReconciliationCaseModel,
    )
    from src.infrastructure.database.models.vlr.reconciliation_request_model import (
        ReconciliationRequestModel,
    )
    from src.infrastructure.database.models.vlr.vendor_model import VendorModel
    from src.infrastructure.database.models.vlr.vendor_contact_model import VendorContactModel
    from src.infrastructure.database.repositories.vlr.setting_repository_impl import (
        SettingRepositoryImpl,
    )
    from src.infrastructure.external.email.smtp_provider import SmtpEmailSender

    logger = logging.getLogger(__name__)

    # Verify request exists
    repo = RequestRepositoryImpl(session)
    request_obj = await repo.get_by_id(request_id, company_code)
    if request_obj is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Reconciliation request {request_id} not found.",
        )

    # Load email configuration
    setting_repo = SettingRepositoryImpl(session)
    prefix = "email.__global__."

    async def _get_setting(key: str, default: str = "") -> str:
        setting = await setting_repo.get_by_key("__global__", f"{prefix}{key}")
        return setting.value if setting else default

    smtp_host = await _get_setting("smtp_host")
    smtp_port_str = await _get_setting("smtp_port", "587")
    smtp_username = await _get_setting("smtp_username")
    smtp_password = await _get_setting("smtp_password")
    sender_email = await _get_setting("sender_email")
    sender_name = await _get_setting("sender_name")
    use_tls = (await _get_setting("use_tls", "true")).lower() == "true"

    # Additional CC recipients selected in the UI (contact person dropdown).
    cc_emails = [e.strip() for e in (body.cc_emails if body else []) if e and e.strip()]

    # Optional free-text remarks/message included in each invite email.
    remarks = (body.remarks if body else "").strip()

    # Base URL for the vendor portal link. Resolution order:
    #   1. portal_base_url DB setting
    #   2. PORTAL_BASE_URL env var
    #   3. first configured CORS origin (the real frontend URL, e.g.
    #      http://10.21.191.52:8085) — avoids needing extra .env config
    #   4. localhost fallback (dev only)
    portal_base_url = (await _get_setting("portal_base_url")).rstrip("/")
    if not portal_base_url:
        import os
        portal_base_url = os.getenv("PORTAL_BASE_URL", "").rstrip("/")
    if not portal_base_url:
        from src.config.settings import settings as _app_settings
        cors_origins = [
            o.rstrip("/")
            for o in (_app_settings.CORS_ORIGINS or [])
            if o and "localhost" not in o and "127.0.0.1" not in o
        ]
        if cors_origins:
            portal_base_url = cors_origins[0]
    if not portal_base_url:
        portal_base_url = "http://localhost:3000"

    if not smtp_host or not sender_email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email is not configured. Please configure SMTP settings first (Settings > Email Config).",
        )

    email_sender = SmtpEmailSender(
        host=smtp_host,
        port=int(smtp_port_str),
        username=smtp_username,
        password=smtp_password,
        sender_email=sender_email,
        sender_name=sender_name,
        use_tls=use_tls,
    )

    # Get all cases for this request
    case_stmt = (
        select(ReconciliationCaseModel)
        .where(
            ReconciliationCaseModel.request_id == request_id,
            ReconciliationCaseModel.is_deleted == False,  # noqa: E712
        )
    )
    case_result = await session.execute(case_stmt)
    cases = list(case_result.scalars().all())

    if not cases:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No cases found for this request.",
        )

    emails_sent = 0
    emails_failed = 0
    details = []

    # Set token expiry (90 days from now)
    token_expiry = datetime.now(timezone.utc) + timedelta(days=90)

    for case in cases:
        # Get vendor info
        vendor_stmt = select(VendorModel).where(VendorModel.id == case.vendor_id)
        vendor_result = await session.execute(vendor_stmt)
        vendor = vendor_result.scalar_one_or_none()

        if not vendor:
            details.append({
                "case_id": str(case.id),
                "status": "skipped",
                "reason": "Vendor not found",
            })
            emails_failed += 1
            continue

        # Get primary vendor contact email
        contact_stmt = (
            select(VendorContactModel)
            .where(
                VendorContactModel.vendor_id == vendor.id,
                VendorContactModel.is_primary == True,  # noqa: E712
            )
            .limit(1)
        )
        contact_result = await session.execute(contact_stmt)
        contact = contact_result.scalar_one_or_none()

        # Fallback: get any contact
        if not contact:
            contact_stmt2 = (
                select(VendorContactModel)
                .where(VendorContactModel.vendor_id == vendor.id)
                .limit(1)
            )
            contact_result2 = await session.execute(contact_stmt2)
            contact = contact_result2.scalar_one_or_none()

        if not contact or not contact.email:
            details.append({
                "case_id": str(case.id),
                "vendor_code": vendor.vendor_code,
                "vendor_name": vendor.name,
                "status": "skipped",
                "reason": "No contact email found for vendor",
            })
            emails_failed += 1
            continue

        # Set token expiry on the case
        case.token_expiry = token_expiry
        await session.flush()

        # Build portal URL (uses configurable base so it works off-localhost)
        portal_url = f"{portal_base_url}/portal/access/{case.portal_token}"

        # Build email body. Format the period as dd-Mon-yyyy to match the UI.
        def _fmt_period(d) -> str:
            try:
                return d.strftime("%d-%b-%Y")
            except AttributeError:
                return str(d) if d else ""

        period_start = _fmt_period(request_obj.period_start)
        period_end = _fmt_period(request_obj.period_end)

        # Optional remarks block (only rendered when remarks were provided).
        remarks_block = (
            f"""<p style="margin: 16px 0; padding: 12px; background:#f8f8f8;
                    border-left: 3px solid #C41E3A;">
                    <strong>Remarks:</strong> {remarks}
                </p>"""
            if remarks else ""
        )

        body_html = f"""
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                <h2 style="color: #C41E3A;">Vendor Ledger Reconciliation Request</h2>
                <p>Dear {contact.name or vendor.name},</p>
                <p>
                    You have been invited to participate in a ledger reconciliation by
                    <strong>Emcure Pharmaceuticals Limited</strong>.
                </p>
                <p><strong>Vendor:</strong> {vendor.name} ({vendor.vendor_code})</p>
                <p><strong>Reconciliation Period:</strong> {period_start} to {period_end}</p>
                {remarks_block}
                <p>
                    Please click the link below to access the portal and upload your
                    ledger statement:
                </p>
                <p style="text-align: center; margin: 30px 0;">
                    <a href="{portal_url}"
                       style="background-color: #C41E3A; color: white; padding: 12px 30px;
                              text-decoration: none; border-radius: 5px; font-weight: bold;">
                        Upload Statement
                    </a>
                </p>
                <p style="font-size: 12px; color: #666;">
                    This link is valid for 90 days. If you have any questions, please
                    contact the reconciliation team.
                </p>
                <p style="font-size: 12px; color: #666;">
                    Portal Link: <a href="{portal_url}">{portal_url}</a>
                </p>
            </div>
        </body>
        </html>
        """

        subject = f"Ledger Reconciliation Request - {period_start} to {period_end}"

        # Send email to the vendor's primary contact, CC the selected contact(s)
        success = await email_sender.send_email(
            to_email=contact.email,
            subject=subject,
            body_html=body_html,
            cc=cc_emails,
        )

        if success:
            emails_sent += 1
            details.append({
                "case_id": str(case.id),
                "vendor_code": vendor.vendor_code,
                "vendor_name": vendor.name,
                "email": contact.email,
                "cc": cc_emails,
                "portal_url": portal_url,
                "status": "sent",
            })
        else:
            emails_failed += 1
            details.append({
                "case_id": str(case.id),
                "vendor_code": vendor.vendor_code,
                "vendor_name": vendor.name,
                "email": contact.email,
                "status": "failed",
                "reason": "SMTP delivery failed",
            })

    # Stamp the request's sent_date on first successful send so the Track
    # Reconciliation list can show the Send Date (and "Not Sent" until then).
    if emails_sent > 0 and getattr(request_obj, "sent_date", None) is None:
        request_obj.sent_date = datetime.now(timezone.utc)
        await session.flush()

    await session.commit()

    logger.info(
        "Vendor invites sent: request_id=%s, sent=%d, failed=%d",
        request_id, emails_sent, emails_failed,
    )

    return SendInviteResponse(
        request_id=request_id,
        emails_sent=emails_sent,
        emails_failed=emails_failed,
        details=details,
    )
