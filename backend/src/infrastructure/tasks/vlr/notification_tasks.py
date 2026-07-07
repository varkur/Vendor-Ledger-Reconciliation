"""
Notification Celery tasks.

Provides async task execution for email delivery, retry processing,
and scheduled reminder sending. Prevents API request blocking for
email operations that may have latency or require retry logic.

Requirements: 10.1, 10.7, 10.10, 16.6
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from uuid import UUID, uuid4

from celery import Task

from src.infrastructure.background.celery_app import celery_app

logger = logging.getLogger(__name__)


class NotificationDeliveryTask(Task):
    """Custom base task class with error handling for notification delivery."""

    name = "vlr.notification_delivery"
    max_retries = 3
    default_retry_delay = 30  # seconds

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """Log task failure."""
        logger.error(
            "Notification delivery task failed: task_id=%s, case_id=%s, error=%s",
            task_id,
            kwargs.get("case_id") or (args[0] if args else "unknown"),
            str(exc),
        )

    def on_success(self, retval, task_id, args, kwargs):
        """Log task success."""
        logger.info(
            "Notification delivery task completed: task_id=%s, case_id=%s",
            task_id,
            kwargs.get("case_id") or (args[0] if args else "unknown"),
        )


class ReminderTask(Task):
    """Custom base task class for scheduled reminder processing."""

    name = "vlr.send_reminder"
    max_retries = 2
    default_retry_delay = 60  # seconds

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """Log task failure."""
        logger.error(
            "Reminder task failed: task_id=%s, case_id=%s, error=%s",
            task_id,
            kwargs.get("case_id") or (args[0] if args else "unknown"),
            str(exc),
        )

    def on_success(self, retval, task_id, args, kwargs):
        """Log task success."""
        logger.info(
            "Reminder task completed: task_id=%s, case_id=%s",
            task_id,
            kwargs.get("case_id") or (args[0] if args else "unknown"),
        )


class RetryProcessingTask(Task):
    """Custom base task class for processing pending notification retries."""

    name = "vlr.process_notification_retries"
    max_retries = 1
    default_retry_delay = 120  # seconds

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """Log task failure."""
        logger.error(
            "Notification retry processing task failed: task_id=%s, error=%s",
            task_id,
            str(exc),
        )

    def on_success(self, retval, task_id, args, kwargs):
        """Log task success."""
        logger.info(
            "Notification retry processing task completed: task_id=%s",
            task_id,
        )


# ──────────────────────────────────────────────────────────────────────
# Task: Send notification email (async delivery)
# ──────────────────────────────────────────────────────────────────────


@celery_app.task(
    base=NotificationDeliveryTask,
    bind=True,
    name="vlr.notification_delivery",
    acks_late=True,
    time_limit=60,  # Hard limit: 1 minute
    soft_time_limit=45,  # Soft limit: 45 seconds
)
def send_notification_task(
    self: NotificationDeliveryTask,
    case_id: str,
    notification_type: str,
    recipient_email: str,
    triggered_by: str,
    company_code: str | None = None,
    portal_url: str | None = None,
    context_data: dict | None = None,
) -> dict:
    """
    Async Celery task for sending notification emails.

    Delegates to the NotificationService for template rendering,
    email delivery, retry scheduling, and logging.

    Args:
        case_id: UUID of the reconciliation case.
        notification_type: Type of notification (invitation, reminder, etc.).
        recipient_email: Email address of the recipient.
        triggered_by: Username of the user who triggered the notification.
        company_code: Optional company code for settings lookup.
        portal_url: Optional portal URL for invitation emails.
        context_data: Optional additional context data for template.

    Returns:
        Dict with notification delivery results.
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        result = loop.run_until_complete(
            _execute_notification_delivery(
                task=self,
                case_id=case_id,
                notification_type=notification_type,
                recipient_email=recipient_email,
                triggered_by=triggered_by,
                company_code=company_code,
                portal_url=portal_url,
                context_data=context_data,
            )
        )
        return result
    finally:
        loop.close()


async def _execute_notification_delivery(
    task: NotificationDeliveryTask,
    case_id: str,
    notification_type: str,
    recipient_email: str,
    triggered_by: str,
    company_code: str | None = None,
    portal_url: str | None = None,
    context_data: dict | None = None,
) -> dict:
    """
    Execute notification delivery via the NotificationService.

    Connects to the database, initializes the service with repositories,
    and delegates to the appropriate send method based on notification_type.
    """
    from src.infrastructure.database.session import async_session_factory
    from src.infrastructure.database.repositories.vlr.notification_repository_impl import (
        NotificationRepositoryImpl,
    )
    from src.infrastructure.database.repositories.vlr.case_repository_impl import (
        CaseRepositoryImpl,
    )
    from src.infrastructure.database.repositories.vlr.setting_repository_impl import (
        SettingRepositoryImpl,
    )
    from src.domain.services.vlr.notification_service import (
        NotificationService,
        NotificationType,
        VendorContact,
    )

    delivery_start = datetime.now(timezone.utc)

    task.update_state(
        state="PROGRESS",
        meta={
            "phase": "sending",
            "status": f"Sending {notification_type} notification to {recipient_email}...",
            "case_id": case_id,
        },
    )

    async with async_session_factory() as session:
        try:
            notification_repo = NotificationRepositoryImpl(session)
            case_repo = CaseRepositoryImpl(session)
            setting_repo = SettingRepositoryImpl(session)

            service = NotificationService(
                notification_repository=notification_repo,
                case_repository=case_repo,
                setting_repository=setting_repo,
                email_sender=None,  # Uses default (dev mode) or configure via DI
            )

            # Delegate to the appropriate service method based on type
            case_uuid = UUID(case_id)

            if notification_type == NotificationType.INVITATION.value:
                # Build a VendorContact for invitation
                contact = VendorContact(
                    id=uuid4(),
                    vendor_id=uuid4(),
                    name=context_data.get("vendor_name", "") if context_data else "",
                    email=recipient_email,
                )
                result = await service.send_invitation(
                    case_id=case_uuid,
                    vendor_contact=contact,
                    portal_url=portal_url,
                    company_code=company_code,
                )
            elif notification_type == NotificationType.REMINDER.value:
                result = await service.send_reminder(
                    case_id=case_uuid,
                    recipient_email=recipient_email,
                    company_code=company_code,
                )
            elif notification_type == NotificationType.APPROVAL_REQUEST.value:
                result = await service.send_approval_notification(
                    case_id=case_uuid,
                    manager_email=recipient_email,
                    company_code=company_code,
                )
            elif notification_type == NotificationType.REJECTION.value:
                reason = context_data.get("rejection_reason", "") if context_data else ""
                result = await service.send_rejection_notification(
                    case_id=case_uuid,
                    user_email=recipient_email,
                    reason=reason,
                    company_code=company_code,
                )
            elif notification_type == NotificationType.SIGN_OFF_REQUEST.value:
                result = await service.send_sign_off_request(
                    case_id=case_uuid,
                    vendor_email=recipient_email,
                    portal_url=portal_url,
                    company_code=company_code,
                )
            elif notification_type == NotificationType.SIGN_OFF_COMPLETE.value:
                vendor_name = context_data.get("vendor_name", "") if context_data else ""
                result = await service.send_sign_off_complete(
                    case_id=case_uuid,
                    user_email=recipient_email,
                    vendor_name=vendor_name,
                    company_code=company_code,
                )
            elif notification_type == NotificationType.ESCALATION.value:
                result = await service.escalate(
                    case_id=case_uuid,
                    manager_email=recipient_email,
                    company_code=company_code,
                )
            else:
                raise ValueError(f"Unknown notification type: {notification_type}")

            await session.commit()

            delivery_end = datetime.now(timezone.utc)
            duration = (delivery_end - delivery_start).total_seconds()

            logger.info(
                "Notification delivered: case_id=%s, type=%s, "
                "recipient=%s, status=%s, duration=%.2fs",
                case_id,
                notification_type,
                recipient_email,
                result.status,
                duration,
            )

            return {
                "case_id": case_id,
                "notification_id": str(result.notification_id),
                "notification_type": notification_type,
                "recipient_email": recipient_email,
                "status": result.status,
                "retry_count": result.retry_count,
                "sent_date": result.sent_date.isoformat() if result.sent_date else None,
                "duration_seconds": round(duration, 2),
            }

        except Exception as exc:
            await session.rollback()
            logger.error(
                "Notification delivery failed: case_id=%s, type=%s, error=%s",
                case_id,
                notification_type,
                str(exc),
            )
            raise


# ──────────────────────────────────────────────────────────────────────
# Task: Send reminder (scheduled)
# ──────────────────────────────────────────────────────────────────────


@celery_app.task(
    base=ReminderTask,
    bind=True,
    name="vlr.send_reminder",
    acks_late=True,
    time_limit=60,
    soft_time_limit=45,
)
def send_reminder_task(
    self: ReminderTask,
    case_id: str,
    recipient_email: str | None = None,
    triggered_by: str = "system",
    company_code: str | None = None,
) -> dict:
    """
    Async Celery task for sending scheduled reminders.

    Sends a reminder for the given case. If the maximum reminder count
    is exceeded, automatically escalates to the reconciliation manager.

    Args:
        case_id: UUID of the reconciliation case.
        recipient_email: Optional recipient email override.
        triggered_by: Username or 'system' for scheduled reminders.
        company_code: Optional company code for settings lookup.

    Returns:
        Dict with reminder delivery results.
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        result = loop.run_until_complete(
            _execute_send_reminder(
                task=self,
                case_id=case_id,
                recipient_email=recipient_email,
                triggered_by=triggered_by,
                company_code=company_code,
            )
        )
        return result
    finally:
        loop.close()


async def _execute_send_reminder(
    task: ReminderTask,
    case_id: str,
    recipient_email: str | None,
    triggered_by: str,
    company_code: str | None,
) -> dict:
    """
    Execute reminder send via the NotificationService.

    Handles escalation automatically when max reminders are exceeded.
    """
    from src.infrastructure.database.session import async_session_factory
    from src.infrastructure.database.repositories.vlr.notification_repository_impl import (
        NotificationRepositoryImpl,
    )
    from src.infrastructure.database.repositories.vlr.case_repository_impl import (
        CaseRepositoryImpl,
    )
    from src.infrastructure.database.repositories.vlr.setting_repository_impl import (
        SettingRepositoryImpl,
    )
    from src.domain.services.vlr.notification_service import NotificationService

    task.update_state(
        state="PROGRESS",
        meta={
            "phase": "sending_reminder",
            "status": f"Sending reminder for case {case_id}...",
            "case_id": case_id,
        },
    )

    async with async_session_factory() as session:
        try:
            notification_repo = NotificationRepositoryImpl(session)
            case_repo = CaseRepositoryImpl(session)
            setting_repo = SettingRepositoryImpl(session)

            service = NotificationService(
                notification_repository=notification_repo,
                case_repository=case_repo,
                setting_repository=setting_repo,
                email_sender=None,
            )

            case_uuid = UUID(case_id)
            result = await service.send_reminder(
                case_id=case_uuid,
                recipient_email=recipient_email,
                company_code=company_code,
            )

            await session.commit()

            logger.info(
                "Reminder sent: case_id=%s, type=%s, recipient=%s, status=%s",
                case_id,
                result.notification_type,
                result.recipient_email,
                result.status,
            )

            return {
                "case_id": case_id,
                "notification_id": str(result.notification_id),
                "notification_type": result.notification_type,
                "recipient_email": result.recipient_email,
                "status": result.status,
                "retry_count": result.retry_count,
                "sent_date": result.sent_date.isoformat() if result.sent_date else None,
            }

        except Exception as exc:
            await session.rollback()
            logger.error(
                "Reminder task failed: case_id=%s, error=%s",
                case_id,
                str(exc),
            )
            raise


# ──────────────────────────────────────────────────────────────────────
# Task: Process pending notification retries
# ──────────────────────────────────────────────────────────────────────


@celery_app.task(
    base=RetryProcessingTask,
    bind=True,
    name="vlr.process_notification_retries",
    acks_late=True,
    time_limit=120,
    soft_time_limit=90,
)
def process_notification_retries_task(self: RetryProcessingTask) -> dict:
    """
    Async Celery task for processing pending notification retries.

    Finds all notifications with status 'failed' that are due for retry
    (next_retry_date <= now) and attempts to resend them using
    exponential backoff (30s, 120s, 480s).

    This task is designed to be called by Celery Beat on a schedule
    (e.g., every 60 seconds).

    Returns:
        Dict with retry processing summary.
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        result = loop.run_until_complete(
            _execute_process_retries(task=self)
        )
        return result
    finally:
        loop.close()


async def _execute_process_retries(task: RetryProcessingTask) -> dict:
    """
    Execute pending retry processing via the NotificationService.

    Iterates over all due retries and processes them.
    """
    from src.infrastructure.database.session import async_session_factory
    from src.infrastructure.database.repositories.vlr.notification_repository_impl import (
        NotificationRepositoryImpl,
    )
    from src.infrastructure.database.repositories.vlr.case_repository_impl import (
        CaseRepositoryImpl,
    )
    from src.infrastructure.database.repositories.vlr.setting_repository_impl import (
        SettingRepositoryImpl,
    )
    from src.domain.services.vlr.notification_service import NotificationService

    task.update_state(
        state="PROGRESS",
        meta={
            "phase": "processing_retries",
            "status": "Processing pending notification retries...",
        },
    )

    async with async_session_factory() as session:
        try:
            notification_repo = NotificationRepositoryImpl(session)
            case_repo = CaseRepositoryImpl(session)
            setting_repo = SettingRepositoryImpl(session)

            service = NotificationService(
                notification_repository=notification_repo,
                case_repository=case_repo,
                setting_repository=setting_repo,
                email_sender=None,
            )

            results = await service.process_pending_retries()
            await session.commit()

            succeeded = sum(1 for r in results if r.status == "sent")
            failed = sum(1 for r in results if r.status in ("failed", "retrying"))

            logger.info(
                "Notification retry processing complete: "
                "total=%d, succeeded=%d, failed=%d",
                len(results),
                succeeded,
                failed,
            )

            return {
                "status": "completed",
                "total_processed": len(results),
                "succeeded": succeeded,
                "failed": failed,
                "processed_at": datetime.now(timezone.utc).isoformat(),
            }

        except Exception as exc:
            await session.rollback()
            logger.error(
                "Notification retry processing failed: error=%s",
                str(exc),
            )
            raise
