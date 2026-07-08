"""
VLR Recovery API endpoints.
Thin controller — delegates recovery operations to RecoveryService.

Routes:
- GET   /api/v1/vlr/recovery               — List recovery items (with filters and pagination)
- POST  /api/v1/vlr/recovery               — Create a recovery item
- PATCH /api/v1/vlr/recovery/{item_id}     — Update status/notes
- GET   /api/v1/vlr/recovery/{item_id}/follow-ups — Get follow-up log

Requirements: 30.1, 31.1, 31.3
"""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.v1.dependencies import get_current_active_user
from src.api.v1.schemas.vlr.recovery_schemas import (
    CreateRecoveryItemRequest,
    FollowUpEntryResponse,
    FollowUpListResponse,
    RecoveryItemListResponse,
    RecoveryItemResponse,
    UpdateRecoveryItemRequest,
)
from src.domain.entities.user import User
from src.domain.repositories.vlr.recovery_repository import RecoveryFilters
from src.domain.repositories.vlr.vendor_repository import PaginationParams
from src.domain.services.vlr.recovery_service import (
    RecoveryItemCreate,
    RecoveryService,
    RecoveryStatus,
)
from src.infrastructure.database.repositories.vlr.recovery_repository_impl import (
    RecoveryRepositoryImpl,
)
from src.infrastructure.database.session import get_db_session
from src.infrastructure.security.permission_manager import require_permission

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/vlr/recovery", tags=["VLR - Recovery"])


# ──────────────────────────────────────────────────────────────────────
# Dependencies
# ──────────────────────────────────────────────────────────────────────


def _get_recovery_service(
    session: AsyncSession = Depends(get_db_session),
) -> RecoveryService:
    """FastAPI dependency — creates RecoveryService with injected repository."""
    return RecoveryService(
        recovery_repository=RecoveryRepositoryImpl(session),
    )


# ──────────────────────────────────────────────────────────────────────
# Endpoints
# ──────────────────────────────────────────────────────────────────────


@router.get(
    "",
    response_model=RecoveryItemListResponse,
    summary="List recovery items with filtering and pagination",
    dependencies=[Depends(require_permission("vlr.recovery.read"))],
)
async def list_recovery_items(
    recovery_status: str | None = Query(
        None,
        alias="status",
        description="Filter by status: open, in_progress, recovered, written_off",
    ),
    vendor_id: UUID | None = Query(None, description="Filter by vendor ID"),
    case_id: UUID | None = Query(None, description="Filter by case ID"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(50, ge=1, le=200, description="Items per page"),
    current_user: User = Depends(get_current_active_user),
    service: RecoveryService = Depends(_get_recovery_service),
) -> RecoveryItemListResponse:
    """
    GET /api/v1/vlr/recovery

    List recovery items with optional filtering by status, vendor_id, and case_id.
    Supports pagination.

    Requirements: 30.1, 31.3
    """
    filters = RecoveryFilters(
        status=recovery_status,
        vendor_id=vendor_id,
        case_id=case_id,
    )
    pagination = PaginationParams(page=page, page_size=page_size)

    result = await service.list_items(filters=filters, pagination=pagination)

    return RecoveryItemListResponse(
        items=[
            RecoveryItemResponse.model_validate(item) for item in result.items
        ],
        total=result.total,
        page=result.page,
        page_size=result.page_size,
        total_pages=result.total_pages,
    )


@router.post(
    "",
    response_model=RecoveryItemResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new recovery item",
    dependencies=[Depends(require_permission("vlr.recovery.write"))],
)
async def create_recovery_item(
    request: CreateRecoveryItemRequest,
    current_user: User = Depends(get_current_active_user),
    service: RecoveryService = Depends(_get_recovery_service),
    session: AsyncSession = Depends(get_db_session),
) -> RecoveryItemResponse:
    """
    POST /api/v1/vlr/recovery

    Create a new recovery item in the register.
    Initial status is set to 'open' and first follow-up is scheduled.

    Requirements: 30.1
    """
    create_data = RecoveryItemCreate(
        case_id=request.case_id,
        vendor_id=request.vendor_id,
        amount=request.amount,
        currency=request.currency,
        identified_date=request.identified_date,
        follow_up_interval_days=request.follow_up_interval_days,
        notes=request.notes,
    )

    item = await service.create_recovery_item(create_data)
    await session.commit()

    logger.info(
        "Recovery item created by %s: item_id=%s, vendor_id=%s, amount=%s",
        current_user.username,
        item.id,
        request.vendor_id,
        request.amount,
    )

    return RecoveryItemResponse.model_validate(item)


@router.patch(
    "/{item_id}",
    response_model=RecoveryItemResponse,
    summary="Update recovery item status and/or notes",
    dependencies=[Depends(require_permission("vlr.recovery.write"))],
)
async def update_recovery_item(
    item_id: UUID,
    request: UpdateRecoveryItemRequest,
    current_user: User = Depends(get_current_active_user),
    service: RecoveryService = Depends(_get_recovery_service),
    session: AsyncSession = Depends(get_db_session),
) -> RecoveryItemResponse:
    """
    PATCH /api/v1/vlr/recovery/{item_id}

    Update the status and/or notes of a recovery item.
    Valid status transitions:
    - open → in_progress, recovered, written_off
    - in_progress → recovered, written_off

    Requirements: 31.1, 31.3
    """
    if request.status is None and request.notes is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one of 'status' or 'notes' must be provided",
        )

    try:
        if request.status:
            # Validate the status value
            try:
                target_status = RecoveryStatus(request.status)
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid status: {request.status}. "
                    f"Valid values: {[s.value for s in RecoveryStatus]}",
                )

            item = await service.update_status(
                item_id=item_id,
                status=target_status,
                notes=request.notes,
                action_by=current_user.username,
            )
        else:
            # Only updating notes — directly update via repository
            repo = service._repo
            existing = await repo.get_by_id(item_id)
            if existing is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Recovery item {item_id} not found",
                )
            item = await repo.update(item_id, {"notes": request.notes})

        await session.commit()

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    logger.info(
        "Recovery item %s updated by %s: status=%s",
        item_id,
        current_user.username,
        request.status,
    )

    return RecoveryItemResponse.model_validate(item)


@router.get(
    "/{item_id}/follow-ups",
    response_model=FollowUpListResponse,
    summary="Get follow-up log for a recovery item",
    dependencies=[Depends(require_permission("vlr.recovery.read"))],
)
async def get_follow_ups(
    item_id: UUID,
    current_user: User = Depends(get_current_active_user),
    service: RecoveryService = Depends(_get_recovery_service),
) -> FollowUpListResponse:
    """
    GET /api/v1/vlr/recovery/{item_id}/follow-ups

    Get the full follow-up log for a recovery item,
    ordered by action_date descending.

    Requirements: 31.3
    """
    # Verify item exists
    item = await service.get_item(item_id)
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Recovery item {item_id} not found",
        )

    follow_ups = await service.get_follow_ups(item_id)

    return FollowUpListResponse(
        items=[
            FollowUpEntryResponse.model_validate(fu) for fu in follow_ups
        ],
        total=len(follow_ups),
    )
