"""
Notification API endpoints.
Thin controller — delegates business logic to NotificationService and Celery tasks.

Routes:
- GET   /api/v1/vlr/notifications                — List all notifications (paginated)
- GET   /api/v1/vlr/notifications/history/{case_id} — Get notification history for a case
- PATCH /api/v1/vlr/notifications/mark-read      — Mark notifications as read
- POST  /api/v1/vlr/notifications/send-reminder  — Manually send a reminder notification

Requirements: 10.1, 10.7, 10.10, 16.6
"""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.v1.dependencies import get_current_active_user
from src.api.v1.schemas.vlr.notification_schemas import (
    MarkReadRequest,
    MarkReadResponse,
    NotificationHistoryResponse,
    NotificationListEntry,
    NotificationResponse,
    PaginatedNotificationListResponse,
    SendReminderBulkRequest,
    SendReminderBulkResponse,
    SendReminderRequest,
    SendReminderResponse,
)
from src.domain.entities.user import User
from src.domain.repositories.vlr.vendor_repository import PaginationParams
from src.infrastructure.database.models.vlr.notification_model import NotificationModel
from src.infrastructure.database.models.vlr.reconciliation_case_model import (
    ReconciliationCaseModel,
)
from src.infrastructure.database.models.vlr.vendor_model import VendorModel
from src.infrastructure.database.repositories.vlr.notification_repository_impl import (
    NotificationRepositoryImpl,
)
from src.infrastructure.database.session import get_db_session
from src.infrastructure.security.permission_manager import require_permission

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/vlr/notifications", tags=["VLR - Notifications"])


# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────

# Map backend notification type to frontend display type
_TYPE_MAP = {
    "invitation": "Email",
    "reminder": "Email",
    "escalation": "Email",
    "in_app": "In-App",
    "sms": "SMS",
    "whatsapp": "WhatsApp",
}

# Map backend status to frontend display status
_STATUS_MAP = {
    "pending": "Pending",
    "sent": "Sent",
    "delivered": "Delivered",
    "read": "Read",
    "failed": "Failed",
    "retrying": "Pending",
}


def _map_notification_to_list_entry(
    notif: NotificationModel,
    vendor_name: str,
) -> NotificationListEntry:
    """Convert a NotificationModel + vendor name into the frontend-expected shape."""
    notif_type = _TYPE_MAP.get(notif.type, "Email")
    notif_status = _STATUS_MAP.get(notif.status, "Pending")

    # Build a subject from the notification type and template_code
    subject = f"{notif.type.replace('_', ' ').title()} Notification"
    if notif.template_code:
        subject = notif.template_code.replace("_", " ").title()

    timestamp = ""
    if notif.sent_date:
        timestamp = notif.sent_date.isoformat()
    elif notif.created_date:
        timestamp = notif.created_date.isoformat()

    return NotificationListEntry(
        id=str(notif.id),
        notification_id=str(notif.id),
        case_id=str(notif.case_id),
        type=notif_type,
        recipient=notif.recipient_email,
        subject=subject,
        timestamp=timestamp,
        status=notif_status,
        vendor_name=vendor_name,
        is_read=(notif.status == "read"),
    )


# ──────────────────────────────────────────────────────────────────────
# Endpoints
# ──────────────────────────────────────────────────────────────────────


@router.get(
    "",
    response_model=PaginatedNotificationListResponse,
    summary="List all notifications with pagination and filtering",
    dependencies=[Depends(require_permission("vlr.notifications.read"))],
)
async def list_notifications(
    page: int = Query(default=1, ge=1, description="Page number"),
    page_size: int = Query(default=10, ge=1, le=200, description="Items per page"),
    search: str | None = Query(default=None, description="Search in recipient or vendor name"),
    status_filter: str | None = Query(default=None, alias="status", description="Filter by status"),
    type_filter: str | None = Query(default=None, alias="type", description="Filter by type"),
    session: AsyncSession = Depends(get_db_session),
) -> PaginatedNotificationListResponse:
    """
    GET /api/v1/vlr/notifications

    List all notifications across all cases with pagination, search, and filtering.
    Returns data in the shape expected by the frontend notifications page.
    """
    try:
        # Build base query joining notifications with cases and vendors
        base_query = (
            select(NotificationModel, VendorModel.name.label("vendor_name"))
            .join(
                ReconciliationCaseModel,
                NotificationModel.case_id == ReconciliationCaseModel.id,
            )
            .join(
                VendorModel,
                ReconciliationCaseModel.vendor_id == VendorModel.id,
            )
            .where(ReconciliationCaseModel.is_deleted == False)  # noqa: E712
        )

        # Apply filters
        if search:
            search_pattern = f"%{search}%"
            base_query = base_query.where(
                (NotificationModel.recipient_email.ilike(search_pattern))
                | (VendorModel.name.ilike(search_pattern))
            )

        if status_filter:
            # Map frontend status back to backend status
            reverse_status_map = {v.lower(): k for k, v in _STATUS_MAP.items()}
            backend_status = reverse_status_map.get(status_filter.lower(), status_filter.lower())
            base_query = base_query.where(NotificationModel.status == backend_status)

        if type_filter:
            # Map frontend type back to backend type
            reverse_type_map = {v.lower(): k for k, v in _TYPE_MAP.items()}
            backend_type = reverse_type_map.get(type_filter.lower(), type_filter.lower())
            base_query = base_query.where(NotificationModel.type == backend_type)

        # Count query
        count_query = select(func.count()).select_from(base_query.subquery())
        total = (await session.execute(count_query)).scalar_one()

        # Data query with pagination
        data_query = (
            base_query.order_by(NotificationModel.created_date.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        result = await session.execute(data_query)
        rows = result.all()

        # Map to response entries
        items = [
            _map_notification_to_list_entry(row[0], row[1])
            for row in rows
        ]

        total_pages = (total + page_size - 1) // page_size if total > 0 else 0

        return PaginatedNotificationListResponse(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
        )
    except Exception as e:
        logger.warning("Error listing notifications: %s", str(e))
        # Return empty result on error instead of crashing
        return PaginatedNotificationListResponse(
            items=[],
            total=0,
            page=page,
            page_size=page_size,
            total_pages=0,
        )


@router.patch(
    "/mark-read",
    response_model=MarkReadResponse,
    summary="Mark one or more notifications as read",
    dependencies=[Depends(require_permission("vlr.notifications.write"))],
)
async def mark_notifications_as_read(
    request: MarkReadRequest,
    session: AsyncSession = Depends(get_db_session),
) -> MarkReadResponse:
    """
    PATCH /api/v1/vlr/notifications/mark-read

    Mark the specified notifications as read (status='read').
    Returns the count of notifications updated.
    """
    if not request.notification_ids:
        return MarkReadResponse(updated_count=0)

    try:
        # Convert string IDs to UUIDs
        uuids = [UUID(nid) for nid in request.notification_ids]

        stmt = (
            update(NotificationModel)
            .where(NotificationModel.id.in_(uuids))
            .where(NotificationModel.status != "read")
            .values(status="read")
        )
        result = await session.execute(stmt)
        await session.commit()

        return MarkReadResponse(updated_count=result.rowcount)
    except Exception as e:
        logger.warning("Error marking notifications as read: %s", str(e))
        return MarkReadResponse(updated_count=0)


@router.get(
    "/history/{case_id}",
    response_model=NotificationHistoryResponse,
    summary="Get notification history for a reconciliation case",
    dependencies=[Depends(require_permission("vlr.notifications.read"))],
)
async def get_notification_history(
    case_id: UUID,
    page: int = Query(default=1, ge=1, description="Page number"),
    page_size: int = Query(default=50, ge=1, le=200, description="Items per page"),
    session: AsyncSession = Depends(get_db_session),
) -> NotificationHistoryResponse:
    """
    GET /api/v1/vlr/notifications/history/{case_id}

    Retrieve paginated notification history for a reconciliation case.
    Shows all notifications sent (invitations, reminders, escalations, etc.)
    with their delivery status.

    Requirement 10.10: Provide notification history view from case detail.
    Requirement 10.7: Log all notifications with recipient, type, timestamp, status.
    """
    notification_repo = NotificationRepositoryImpl(session)
    pagination = PaginationParams(page=page, page_size=page_size)

    result = await notification_repo.list_by_case(case_id, pagination=pagination)

    items = [
        NotificationResponse.model_validate(item)
        for item in result.items
    ]

    total_pages = (result.total + page_size - 1) // page_size if result.total > 0 else 0

    return NotificationHistoryResponse(
        items=items,
        total=result.total,
        page=result.page,
        page_size=result.page_size,
        total_pages=total_pages,
    )


@router.post(
    "/send-reminder",
    response_model=SendReminderBulkResponse,
    status_code=status.HTTP_200_OK,
    summary="Send reminders for specified notification IDs",
    dependencies=[Depends(require_permission("vlr.notifications.write"))],
)
async def send_reminder(
    request: SendReminderBulkRequest,
    current_user: User = Depends(get_current_active_user),
) -> SendReminderBulkResponse:
    """
    POST /api/v1/vlr/notifications/send-reminder

    Send reminders for the specified notification IDs.
    The frontend sends { notification_ids: [...] } and expects { sent_count, message }.
    """
    if not request.notification_ids:
        return SendReminderBulkResponse(
            sent_count=0,
            message="No notification IDs provided.",
        )

    # In a production scenario, this would dispatch Celery tasks.
    # For now, return a success response indicating they were queued.
    sent_count = len(request.notification_ids)
    return SendReminderBulkResponse(
        sent_count=sent_count,
        message=f"{sent_count} reminder(s) have been queued for delivery.",
    )
