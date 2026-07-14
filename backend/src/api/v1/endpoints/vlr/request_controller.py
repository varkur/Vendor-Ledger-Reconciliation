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
        file_type = parser.detect_file_type(filename)
        result = parser.parse_file(io.BytesIO(file_content), filename)
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
            source="upload",
            created_by=current_user.username,
            modified_by=current_user.username,
        )
        session.add(ledger_entry)

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
