"""
Exception Management API endpoints.
Thin controller — delegates all business logic to ExceptionManagerService.

Routes:
- GET    /api/v1/vlr/exceptions              — List exceptions with filters & pagination
- POST   /api/v1/vlr/exceptions/{id}/resolve — Resolve a single exception
- POST   /api/v1/vlr/exceptions/bulk-resolve — Bulk resolve exceptions
- GET    /api/v1/vlr/exceptions/categories   — Get exception categories with counts

Requirements: 6.2, 6.3, 6.9, 11.2
"""

from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.v1.dependencies import get_current_active_user
from src.api.v1.schemas.vlr.exception_schemas import (
    BulkResolveRequest,
    BulkResolveResponse,
    ExceptionCategoriesResponse,
    ExceptionCategoryResponse,
    ExceptionListResponse,
    ExceptionResponse,
    ResolveExceptionRequest,
    ResolutionResponse,
)
from src.domain.entities.user import User
from src.domain.repositories.vlr.exception_repository import ExceptionFilters
from src.domain.repositories.vlr.vendor_repository import PaginationParams
from src.domain.services.vlr.exception_manager_service import (
    ExceptionManagerService,
    ResolutionAction,
)
from src.infrastructure.database.repositories.vlr.case_repository_impl import (
    CaseRepositoryImpl,
)
from src.infrastructure.database.repositories.vlr.exception_repository_impl import (
    ExceptionRepositoryImpl,
)
from src.infrastructure.database.repositories.vlr.ledger_entry_repository_impl import (
    LedgerEntryRepositoryImpl,
)
from src.infrastructure.database.repositories.vlr.setting_repository_impl import (
    SettingRepositoryImpl,
)
from src.infrastructure.database.session import get_db_session
from src.infrastructure.security.permission_manager import require_permission

router = APIRouter(prefix="/vlr/exceptions", tags=["VLR - Exception Management"])


# ──────────────────────────────────────────────────────────────────────
# Dependencies
# ──────────────────────────────────────────────────────────────────────


def _get_exception_service(
    session: AsyncSession = Depends(get_db_session),
) -> ExceptionManagerService:
    """FastAPI dependency — creates ExceptionManagerService with injected repositories."""
    exception_repo = ExceptionRepositoryImpl(session)
    case_repo = CaseRepositoryImpl(session)
    ledger_repo = LedgerEntryRepositoryImpl(session)
    setting_repo = SettingRepositoryImpl(session)
    return ExceptionManagerService(
        exception_repository=exception_repo,
        case_repository=case_repo,
        ledger_entry_repository=ledger_repo,
        setting_repository=setting_repo,
    )


def _get_exception_repository(
    session: AsyncSession = Depends(get_db_session),
) -> ExceptionRepositoryImpl:
    """FastAPI dependency — creates ExceptionRepository for direct queries."""
    return ExceptionRepositoryImpl(session)


# ──────────────────────────────────────────────────────────────────────
# Endpoints
# ──────────────────────────────────────────────────────────────────────


@router.get(
    "",
    response_model=ExceptionListResponse,
    summary="List exceptions with filters and pagination",
    dependencies=[Depends(require_permission("vlr.exceptions.read"))],
)
async def list_exceptions(
    company_code: str = Query(..., min_length=1, description="Company code filter"),
    case_id: UUID | None = Query(default=None, description="Filter by case ID"),
    severity: str | None = Query(default=None, description="Filter by severity"),
    category: str | None = Query(default=None, description="Filter by category"),
    exception_status: str | None = Query(
        default=None, alias="status", description="Filter by status"
    ),
    page: int = Query(default=1, ge=1, description="Page number"),
    page_size: int = Query(default=50, ge=1, le=200, description="Items per page"),
    repo: ExceptionRepositoryImpl = Depends(_get_exception_repository),
) -> ExceptionListResponse:
    """GET /api/v1/vlr/exceptions — List exceptions with filtering and pagination."""
    filters = ExceptionFilters(
        case_id=case_id,
        severity=severity,
        category=category,
        status=exception_status,
    )
    pagination = PaginationParams(page=page, page_size=page_size)

    result = await repo.list_exceptions(
        company_code=company_code,
        filters=filters,
        pagination=pagination,
    )

    return ExceptionListResponse(
        items=[ExceptionResponse.model_validate(item) for item in result.items],
        total=result.total,
        page=result.page,
        page_size=result.page_size,
        total_pages=result.total_pages,
    )


@router.post(
    "/{exception_id}/resolve",
    response_model=ResolutionResponse,
    summary="Resolve a single exception",
    dependencies=[Depends(require_permission("vlr.exceptions.write"))],
)
async def resolve_exception(
    exception_id: UUID,
    request: ResolveExceptionRequest,
    company_code: str = Query(..., min_length=1, description="Company code"),
    current_user: User = Depends(get_current_active_user),
    service: ExceptionManagerService = Depends(_get_exception_service),
) -> ResolutionResponse:
    """
    POST /api/v1/vlr/exceptions/{id}/resolve

    Resolves an exception with the specified action.
    Requirement 6.2: Support resolution actions ACM, RDV, MTD, MAA, WOF, ESC.
    Requirement 6.3: Record action, actor, timestamp, and comments.
    """
    action = ResolutionAction(request.action)

    result = await service.resolve_exception(
        exception_id=exception_id,
        action=action,
        resolved_by=current_user.id,
        comment=request.comment,
        company_code=company_code,
    )

    return ResolutionResponse(
        exception_id=result.exception_id,
        action=result.action,
        status=result.status,
        resolved_by=result.resolved_by,
        resolved_date=result.resolved_date,
        comments=result.comments,
    )


@router.post(
    "/bulk-resolve",
    response_model=BulkResolveResponse,
    summary="Bulk resolve multiple exceptions",
    dependencies=[Depends(require_permission("vlr.exceptions.write"))],
)
async def bulk_resolve_exceptions(
    request: BulkResolveRequest,
    company_code: str = Query(..., min_length=1, description="Company code"),
    current_user: User = Depends(get_current_active_user),
    service: ExceptionManagerService = Depends(_get_exception_service),
) -> BulkResolveResponse:
    """
    POST /api/v1/vlr/exceptions/bulk-resolve

    Resolves multiple exceptions with the same action.
    Requirement 6.9: Support bulk resolution for same-category exceptions.
    """
    action = ResolutionAction(request.action)

    result = await service.bulk_resolve(
        exception_ids=request.exception_ids,
        action=action,
        resolved_by=current_user.id,
        comment=request.comment,
        company_code=company_code,
    )

    return BulkResolveResponse(
        total=result.total,
        resolved=result.resolved,
        failed=result.failed,
        results=[
            ResolutionResponse(
                exception_id=r.exception_id,
                action=r.action,
                status=r.status,
                resolved_by=r.resolved_by,
                resolved_date=r.resolved_date,
                comments=r.comments,
            )
            for r in result.results
        ],
        errors=result.errors,
    )


@router.get(
    "/categories",
    response_model=ExceptionCategoriesResponse,
    summary="Get exception categories with counts for a case",
    dependencies=[Depends(require_permission("vlr.exceptions.read"))],
)
async def get_exception_categories(
    case_id: UUID = Query(..., description="Case ID to get categories for"),
    company_code: str = Query(..., min_length=1, description="Company code"),
    repo: ExceptionRepositoryImpl = Depends(_get_exception_repository),
) -> ExceptionCategoriesResponse:
    """
    GET /api/v1/vlr/exceptions/categories

    Returns exception severity categories with counts for a specific case.
    """
    severity_counts = await repo.count_by_severity(case_id)
    total = sum(severity_counts.values())

    categories = [
        ExceptionCategoryResponse(severity=severity, count=count)
        for severity, count in severity_counts.items()
    ]

    return ExceptionCategoriesResponse(
        case_id=case_id,
        categories=categories,
        total=total,
    )
