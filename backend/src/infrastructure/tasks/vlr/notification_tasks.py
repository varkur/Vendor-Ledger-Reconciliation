"""
Notification Celery tasks.

Provides async task execution for email delivery, retry processing,
scheduled reminder sending, and periodic vendor reminder checking.
Prevents API request blocking for email operations that may have
latency or require retry logic.

Requirements: 10.1, 10.7, 10.10, 14.4, 15.1, 15.2, 15.3, 15.4, 16.6
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from uuid import UUID, uuid4

from celery import Task
from celery.schedules import crontab

from src.infrastructure.background.celery_app import celery_app
from src.infrastructure.logging.structured_logger import get_structured_logger

logger = logging.getLogger(__name__)
_structured_logger = get_structured_logger("celery_notification")

# Default interval for periodic vendor reminder check (in hours)
DEFAULT_REMINDER_CHECK_INTERVAL_HOURS: int = 4


# ──────────────────────────────────────────────────────────────────────
# Celery Beat Schedule - Vendor Reminder Checking
# ──────────────────────────────────────────────────────────────────────

# Register vendor reminder check as a periodic task (every 4 hours)
celery_app.conf.beat_schedule = {
    **getattr(celery_app.conf, "beat_schedule", {}),
    "vlr-check-vendor-reminders": {
        "task": "vlr.check_vendor_reminders",
        "schedule": crontab(minute=0, hour=f"*/{DEFAULT_REMINDER_CHECK_INTERVAL_HOURS}"),
        "options": {"queue": "notifications"},
    },
}


class NotificationDeliveryTask(Task):
    """Custom base task class with error handling for notification delivery."""

    name = "vlr.notification_delivery"
    max_retries = 3
    default_retry_delay = 30  # seconds

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """Log task failure."""
        case_id = kwargs.get("case_id") or (args[0] if args else "unknown")
        _structured_logger.log_failure(
            operation="notification_delivery",
            duration_ms=0.0,
            error=str(exc),
            error_type=type(exc).__name__,
            case_id=case_id,
            task_id=task_id,
        )
        logger.error(
            "Notification delivery task failed: task_id=%s, case_id=%s, error=%s",
            task_id,
            case_id,
            str(exc),
        )

    def on_success(self, retval, task_id, args, kwargs):
        """Log task success."""
        case_id = kwargs.get("case_id") or (args[0] if args else "unknown")
        _structured_logger.log_success(
            operation="notification_delivery",
            duration_ms=0.0,
            case_id=case_id,
            task_id=task_id,
        )
        logger.info(
            "Notification delivery task completed: task_id=%s, case_id=%s",
            task_id,
            case_id,
        )


class ReminderTask(Task):
    """Custom base task class for scheduled reminder processing."""

    name = "vlr.send_reminder"
    max_retries = 2
    default_retry_delay = 60  # seconds

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """Log task failure."""
        case_id = kwargs.get("case_id") or (args[0] if args else "unknown")
        _structured_logger.log_failure(
            operation="send_reminder",
            duration_ms=0.0,
            error=str(exc),
            error_type=type(exc).__name__,
            case_id=case_id,
            task_id=task_id,
        )
        logger.error(
            "Reminder task failed: task_id=%s, case_id=%s, error=%s",
            task_id,
            case_id,
            str(exc),
        )

    def on_success(self, retval, task_id, args, kwargs):
        """Log task success."""
        case_id = kwargs.get("case_id") or (args[0] if args else "unknown")
        _structured_logger.log_success(
            operation="send_reminder",
            duration_ms=0.0,
            case_id=case_id,
            task_id=task_id,
        )
        logger.info(
            "Reminder task completed: task_id=%s, case_id=%s",
            task_id,
            case_id,
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


class VendorReminderCheckTask(Task):
    """Custom base task class for periodic vendor reminder checking."""

    name = "vlr.check_vendor_reminders"
    max_retries = 1
    default_retry_delay = 300  # seconds

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """Log task failure."""
        logger.error(
            "Vendor reminder check task failed: task_id=%s, error=%s",
            task_id,
            str(exc),
        )

    def on_success(self, retval, task_id, args, kwargs):
        """Log task success."""
        logger.info(
            "Vendor reminder check task completed: task_id=%s, "
            "reminders_sent=%s, escalations_sent=%s",
            task_id,
            retval.get("reminders_sent", 0) if retval else 0,
            retval.get("escalations_sent", 0) if retval else 0,
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


# ──────────────────────────────────────────────────────────────────────
# Task: Check Vendor Reminders (Periodic)
# ──────────────────────────────────────────────────────────────────────


@celery_app.task(
    base=VendorReminderCheckTask,
    bind=True,
    name="vlr.check_vendor_reminders",
    acks_late=True,
    time_limit=300,  # Hard limit: 5 minutes
    soft_time_limit=240,  # Soft limit: 4 minutes
)
def check_vendor_reminders_periodic(self: VendorReminderCheckTask) -> dict:
    """
    Periodic task that checks for overdue vendor engagements and triggers
    appropriate reminders (D3, D7, D10) or escalation.

    Runs every 4 hours via Celery Beat. For each reconciliation case in the
    "vendor_engagement" workflow step:
    1. Determines the invite date and number of reminders already sent
    2. Checks if the vendor has uploaded a statement
    3. Calls EmailNotificationService.determine_reminder_action() to decide
    4. If action is "send_reminder" → calls send_scheduled_reminder()
    5. If action is "escalate" → calls send_escalation()
    6. If action is "none" → skips

    Uses max_retries=1 since this task runs periodically and will
    execute again on the next schedule.

    Requirements: 15.1, 15.2, 15.3, 15.4

    Returns:
        Dict with reminder check results including counts of
        reminders sent, escalations triggered, and cases processed.
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        result = loop.run_until_complete(
            _execute_check_vendor_reminders(task=self)
        )
        return result
    except Exception as exc:
        raise self.retry(exc=exc, countdown=self.default_retry_delay)
    finally:
        loop.close()


async def _execute_check_vendor_reminders(task: VendorReminderCheckTask) -> dict:
    """
    Execute vendor reminder check across all cases in vendor_engagement step.

    For each case:
    - Queries the invite date (step_entered_at for vendor_engagement)
    - Counts D3/D7/D10 type reminders already sent
    - Checks vendor upload status (upload_count > 0 means uploaded)
    - Uses EmailNotificationService.determine_reminder_action() to decide action
    - Dispatches reminders or escalations as needed
    """
    from sqlalchemy import select, and_, func
    from sqlalchemy.orm import selectinload

    from src.infrastructure.database.session import async_session_factory
    from src.infrastructure.database.models.vlr.reconciliation_case_model import (
        ReconciliationCaseModel,
    )
    from src.infrastructure.database.models.vlr.notification_model import (
        NotificationModel,
    )
    from src.infrastructure.database.models.vlr.vendor_model import VendorModel
    from src.infrastructure.database.models.vlr.vendor_contact_model import (
        VendorContactModel,
    )
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
        EmailNotificationService,
        NotificationType,
    )

    check_start = datetime.now(timezone.utc)

    task.update_state(
        state="PROGRESS",
        meta={
            "phase": "checking_vendor_reminders",
            "status": "Checking for overdue vendor engagements...",
        },
    )

    async with async_session_factory() as session:
        try:
            # Query all cases in "vendor_engagement" workflow step
            # that haven't been uploaded yet (upload_count == 0)
            # and are not deleted
            vendor_engagement_stmt = (
                select(ReconciliationCaseModel)
                .options(selectinload(ReconciliationCaseModel.vendor))
                .where(
                    and_(
                        ReconciliationCaseModel.is_deleted == False,  # noqa: E712
                        ReconciliationCaseModel.current_workflow_step == "vendor_engagement",
                        ReconciliationCaseModel.upload_count == 0,
                        ReconciliationCaseModel.step_entered_at.isnot(None),
                    )
                )
            )
            result = await session.execute(vendor_engagement_stmt)
            engagement_cases = result.scalars().all()

            if not engagement_cases:
                return {
                    "status": "completed",
                    "cases_checked": 0,
                    "reminders_sent": 0,
                    "escalations_sent": 0,
                    "skipped": 0,
                    "checked_at": check_start.isoformat(),
                    "duration_seconds": 0.0,
                }

            # Initialize the EmailNotificationService
            notification_repo = NotificationRepositoryImpl(session)
            case_repo = CaseRepositoryImpl(session)
            setting_repo = SettingRepositoryImpl(session)

            email_service = EmailNotificationService(
                notification_repository=notification_repo,
                case_repository=case_repo,
                setting_repository=setting_repo,
                email_sender=None,  # Uses default (dev mode) or configure via DI
            )

            reminders_sent = 0
            escalations_sent = 0
            skipped = 0
            errors = 0

            for case in engagement_cases:
                try:
                    case_id = case.id
                    invite_date = case.step_entered_at

                    # Count BRD-specific reminders (D3/D7/D10) already sent for this case
                    brd_reminder_types = [
                        NotificationType.REMINDER_D3.value,
                        NotificationType.REMINDER_D7.value,
                        NotificationType.REMINDER_D10.value,
                    ]
                    reminder_count_stmt = select(
                        func.count(NotificationModel.id)
                    ).where(
                        and_(
                            NotificationModel.case_id == case_id,
                            NotificationModel.type.in_(brd_reminder_types),
                        )
                    )
                    reminder_count_result = await session.execute(reminder_count_stmt)
                    reminders_already_sent = reminder_count_result.scalar_one()

                    # Determine what action to take
                    action = email_service.determine_reminder_action(
                        reminders_sent=reminders_already_sent,
                        invite_date=invite_date,
                    )

                    if action["action"] == "send_reminder":
                        # Get vendor info for the email
                        vendor = case.vendor
                        if vendor is None:
                            logger.warning(
                                "No vendor found for case %s, skipping reminder",
                                str(case_id),
                            )
                            skipped += 1
                            continue

                        # Get primary contact email
                        contact_stmt = select(VendorContactModel).where(
                            and_(
                                VendorContactModel.vendor_id == vendor.id,
                                VendorContactModel.is_primary == True,  # noqa: E712
                            )
                        )
                        contact_result = await session.execute(contact_stmt)
                        primary_contact = contact_result.scalar_one_or_none()

                        if primary_contact is None:
                            # Fallback: get any contact
                            any_contact_stmt = select(VendorContactModel).where(
                                VendorContactModel.vendor_id == vendor.id
                            ).limit(1)
                            any_contact_result = await session.execute(any_contact_stmt)
                            primary_contact = any_contact_result.scalar_one_or_none()

                        if primary_contact is None:
                            logger.warning(
                                "No contact found for vendor %s (case %s), skipping",
                                str(vendor.id),
                                str(case_id),
                            )
                            skipped += 1
                            continue

                        # Send the scheduled reminder
                        portal_token = case.portal_token or str(uuid4())
                        await email_service.send_scheduled_reminder(
                            case_id=case_id,
                            reminder_number=action["reminder_number"],
                            vendor_email=primary_contact.email,
                            vendor_name=vendor.name,
                            portal_token=portal_token,
                        )
                        reminders_sent += 1

                        logger.info(
                            "Reminder D%d sent: case_id=%s, vendor=%s",
                            action["interval_days"],
                            str(case_id),
                            vendor.name,
                        )

                    elif action["action"] == "escalate":
                        # Check if escalation was already sent for this case
                        escalation_count_stmt = select(
                            func.count(NotificationModel.id)
                        ).where(
                            and_(
                                NotificationModel.case_id == case_id,
                                NotificationModel.type == NotificationType.ESCALATION.value,
                            )
                        )
                        esc_result = await session.execute(escalation_count_stmt)
                        escalation_already_sent = esc_result.scalar_one()

                        if escalation_already_sent > 0:
                            # Already escalated, skip
                            skipped += 1
                            continue

                        # Resolve the manager email
                        # Use a default or look up from SLA configuration
                        manager_email = await _resolve_manager_email(session, case)

                        days_elapsed = action.get("days_elapsed", 10)
                        vendor = case.vendor
                        vendor_name = vendor.name if vendor else "Unknown Vendor"

                        await email_service.send_escalation(
                            case_id=case_id,
                            manager_email=manager_email,
                            vendor_name=vendor_name,
                            reminder_count=reminders_already_sent,
                            days_since_invite=days_elapsed,
                        )
                        escalations_sent += 1

                        logger.info(
                            "Escalation sent: case_id=%s, vendor=%s, "
                            "days_since_invite=%d",
                            str(case_id),
                            vendor_name,
                            days_elapsed,
                        )

                    else:
                        # action is "none" - not yet time for a reminder
                        skipped += 1

                except Exception as case_exc:
                    errors += 1
                    logger.error(
                        "Error processing vendor reminder for case %s: %s",
                        str(case.id),
                        str(case_exc),
                    )
                    continue

            await session.commit()

            check_end = datetime.now(timezone.utc)
            duration = (check_end - check_start).total_seconds()

            logger.info(
                "Vendor reminder check completed: cases=%d, reminders=%d, "
                "escalations=%d, skipped=%d, errors=%d, duration=%.2fs",
                len(engagement_cases),
                reminders_sent,
                escalations_sent,
                skipped,
                errors,
                duration,
            )

            return {
                "status": "completed",
                "cases_checked": len(engagement_cases),
                "reminders_sent": reminders_sent,
                "escalations_sent": escalations_sent,
                "skipped": skipped,
                "errors": errors,
                "checked_at": check_start.isoformat(),
                "duration_seconds": round(duration, 2),
            }

        except Exception as exc:
            await session.rollback()
            logger.error(
                "Vendor reminder check failed: error=%s",
                str(exc),
            )
            raise


async def _resolve_manager_email(session: object, case: object) -> str:
    """
    Resolve the Reconciliation Manager email for escalation.

    Attempts to find the manager email from:
    1. SLA configuration for the vendor_engagement step
    2. The reconciliation request's assigned manager
    3. Falls back to a default escalation email

    Args:
        session: The database session.
        case: The ReconciliationCaseModel instance.

    Returns:
        Email address for the escalation recipient.
    """
    try:
        from sqlalchemy import select, and_
        from src.infrastructure.database.models.vlr.sla_configuration_model import (
            SLAConfigurationModel,
        )

        # Try to get escalation email from SLA config
        sla_stmt = select(SLAConfigurationModel).where(
            and_(
                SLAConfigurationModel.step_name == "vendor_engagement",
                SLAConfigurationModel.is_active == True,  # noqa: E712
            )
        )
        sla_result = await session.execute(sla_stmt)
        sla_config = sla_result.scalar_one_or_none()

        if sla_config and sla_config.escalation_email:
            return sla_config.escalation_email
    except Exception:
        pass

    # Fallback to a default manager email
    return "recon.manager@example.com"
