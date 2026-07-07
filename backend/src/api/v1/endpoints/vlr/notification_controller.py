"""
Notification API endpoints.
Thin controller — delegates business logic to NotificationService and Celery tasks.

Routes:
- GET  /api/v1/vlr/notifications/history/{case_id} — Get notification history for a case
- POST /api/v1/vlr/notifications/send-reminder      — Manually send a reminder notification

Requirements: 10.1, 10.7, 10.10, 16.6
"""

from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.v1.dependencies import get_current_active_user
from src.api.v1.schemas.vlr.notification_schemas import (
    NotificationHistoryResponse,
    NotificationResponse,
    SendReminderRequest,
    SendReminderResponse,
)
from src.domain.entities.user import User
from src.domain.repositories.vlr.vendor_repository import PaginationParams
from src.infrastructure.database.repositories.vlr.notification_repository_impl import (
    NotificationRepositoryImpl,
)
from src.infrastructure.database.session import get_db_session
from src.infrastructure.security.permission_manager import require_permission

router = APIRouter(prefix="/vlr/notifications", tags=["VLR - Notifications"])


# ──────────────────────────────────────────────────────────────────────
# Endpoints
# ──────────────────────────────────────────────────────────────────────


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
    response_model=SendReminderResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Send a reminder notification for a case",
    dependencies=[Depends(require_permission("vlr.notifications.write"))],
)
async def send_reminder(
    request: SendReminderRequest,
    current_user: User = Depends(get_current_active_user),
) -> SendReminderResponse:
    """
    POST /api/v1/vlr/notifications/send-reminder

    Manually trigger a reminder notification for a reconciliation case.
    The reminder is dispatched asynchronously via a Celery task.

    If the maximum number of reminders has been sent, the system will
    automatically escalate instead.

    Requirement 10.1: Send email notifications to vendors.
    Requirement 10.7: Log notification with delivery status.
    """
    from src.infrastructure.tasks.vlr.notification_tasks import send_reminder_task

    # Dispatch the reminder task asynchronously
    task_result = send_reminder_task.delay(
        case_id=str(request.case_id),
        recipient_email=request.recipient_email,
        triggered_by=current_user.username,
        company_code=request.company_code,
    )

    return SendReminderResponse(
        case_id=request.case_id,
        notification_id=None,
        task_id=task_result.id,
        notification_type="reminder",
        recipient_email=request.recipient_email or "primary_contact",
        status="queued",
        message="Reminder notification has been queued for delivery.",
    )
