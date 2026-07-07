"""
Reconciliation Request API endpoints.
Thin controller — delegates all business logic to RequestManagerService.

Routes:
- GET    /api/v1/vlr/requests          — List requests with filters & pagination
- POST   /api/v1/vlr/requests          — Create a new reconciliation request
- GET    /api/v1/vlr/requests/{id}     — Get request by ID
- POST   /api/v1/vlr/requests/{id}/clone      — Clone request for new period
- GET    /api/v1/vlr/requests/{id}/statistics  — Get request statistics

Note: POST /api/v1/vlr/requests/{id}/sap-pull is handled by sap_pull_controller.py

Requirements: 3.1, 3.2, 3.4, 3.5, 3.6, 3.7, 3.10, 11.2, 11.6
"""

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
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

    return RequestListResponse(
        items=[ReconciliationRequestResponse.model_validate(r) for r in result.items],
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
        tolerance_amount=request.tolerance_amount,
        tds_percentage=request.tds_percentage,
        gst_percentage=request.gst_percentage,
        matching_preferences=matching_prefs,
        assigned_manager_id=request.assigned_manager_id,
        created_by=current_user.id,
    )

    result = await service.create_request(dto)
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
        created_by=current_user.id,
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
    repo: RequestRepositoryImpl = Depends(_get_request_repository),
) -> RequestStatisticsResponse:
    """GET /api/v1/vlr/requests/{id}/statistics — Get case counts by status for a request."""
    # Verify request exists
    request_obj = await repo.get_by_id(request_id, company_code)
    if request_obj is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Reconciliation request {request_id} not found.",
        )

    cases_by_status = await repo.get_statistics(request_id, company_code)
    total_cases = sum(cases_by_status.values())

    return RequestStatisticsResponse(
        request_id=request_id,
        total_cases=total_cases,
        cases_by_status=cases_by_status,
    )
