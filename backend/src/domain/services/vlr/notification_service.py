"""
Notification Domain Service.

Implements the notification lifecycle for reconciliation cases including:
- Email sending with template rendering (invitation, reminder, approval, rejection, sign-off)
- Retry with exponential backoff (30s, 120s, 480s) up to 3 attempts
- Reminder scheduling at configurable intervals (default: 3, 7, 14 days)
- Escalation when reminder count exceeds maximum
- Logging all notifications with recipient, type, timestamp, delivery status
- Enhanced EmailNotificationService with Jinja2 templates and Celery task dispatch
- BRD-specific D3/D7/D10 reminder scheduling with escalation

Requirements: 10.1, 10.2, 10.3, 10.4, 10.5, 10.6, 10.7, 10.8, 10.9, 10.10
Requirements: 14.1, 14.3, 14.4, 15.1, 15.2, 15.3, 15.4, 16.1, 16.2
"""

import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from uuid import UUID, uuid4

from jinja2 import Environment, FileSystemLoader, select_autoescape

from src.infrastructure.logging.structured_logger import get_structured_logger


# ─── Constants ────────────────────────────────────────────────────────────────

DEFAULT_REMINDER_INTERVALS_DAYS: list[int] = [3, 7, 14]
DEFAULT_MAX_REMINDERS: int = 3
MAX_RETRY_ATTEMPTS: int = 3
RETRY_BACKOFF_SECONDS: list[int] = [30, 120, 480]

# BRD-specified reminder intervals (D3, D7, D10)
BRD_REMINDER_INTERVALS_DAYS: list[int] = [3, 7, 10]
BRD_MAX_REMINDERS: int = 3

# Template directory path
TEMPLATES_DIR = Path(__file__).resolve().parents[2] / "infrastructure" / "email" / "templates"

logger = logging.getLogger(__name__)
_structured_logger = get_structured_logger("email_service")


# ─── Enumerations ─────────────────────────────────────────────────────────────


class NotificationType(str, Enum):
    """Types of notifications the system can send."""

    INVITATION = "invitation"
    REMINDER = "reminder"
    ESCALATION = "escalation"
    APPROVAL_REQUEST = "approval_request"
    REJECTION = "rejection"
    SIGN_OFF_REQUEST = "sign_off_request"
    SIGN_OFF_COMPLETE = "sign_off_complete"
    UPLOAD_CONFIRMATION = "upload_confirmation"
    VENDOR_INVITE = "vendor_invite"
    REMINDER_D3 = "reminder_d3"
    REMINDER_D7 = "reminder_d7"
    REMINDER_D10 = "reminder_d10"


class NotificationStatus(str, Enum):
    """Delivery status of a notification."""

    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"
    RETRYING = "retrying"


# ─── Data Transfer Objects ────────────────────────────────────────────────────


@dataclass
class VendorContact:
    """Vendor contact information for notifications."""

    id: UUID
    vendor_id: UUID
    name: str
    email: str
    phone: str | None = None
    designation: str | None = None
    is_primary: bool = False


@dataclass
class NotificationResult:
    """Result of a notification send operation."""

    notification_id: UUID
    case_id: UUID
    notification_type: str
    recipient_email: str
    status: str
    retry_count: int = 0
    sent_date: datetime | None = None
    next_retry_date: datetime | None = None
    template_code: str | None = None
    context_data: dict | None = None


@dataclass
class ReminderSchedule:
    """Schedule for sending reminders to a vendor."""

    case_id: UUID
    intervals_days: list[int] = field(
        default_factory=lambda: list(DEFAULT_REMINDER_INTERVALS_DAYS)
    )
    max_reminders: int = DEFAULT_MAX_REMINDERS
    next_reminder_index: int = 0
    next_reminder_date: datetime | None = None


@dataclass
class BRDReminderSchedule:
    """
    BRD-specified reminder schedule with D3/D7/D10 intervals.

    Defines the exact reminder cadence per the BRD:
    - D3: First reminder, 3 days after invite with no upload
    - D7: Second reminder, 7 days after invite with no upload
    - D10: Third (final) reminder, 10 days after invite with no upload
    - After D10 with no response: escalation to Reconciliation Manager

    Requirements: 15.1, 15.2, 15.3, 15.4
    """

    INTERVALS_DAYS: list[int] = field(
        default_factory=lambda: list(BRD_REMINDER_INTERVALS_DAYS)
    )
    MAX_REMINDERS: int = BRD_MAX_REMINDERS

    # Mapping of reminder number (1-indexed) to template name
    REMINDER_TEMPLATES: dict[int, str] = field(default_factory=lambda: {
        1: "reminder_d3.html",
        2: "reminder_d7.html",
        3: "reminder_d10.html",
    })

    def get_interval_days(self, reminder_number: int) -> int | None:
        """
        Get the interval in days for a given reminder number (1-indexed).

        Returns None if reminder_number exceeds the schedule.
        """
        if reminder_number < 1 or reminder_number > len(self.INTERVALS_DAYS):
            return None
        return self.INTERVALS_DAYS[reminder_number - 1]

    def get_template_name(self, reminder_number: int) -> str | None:
        """
        Get the template filename for a given reminder number (1-indexed).

        Returns None if reminder_number exceeds the schedule.
        """
        return self.REMINDER_TEMPLATES.get(reminder_number)

    def is_exhausted(self, reminders_sent: int) -> bool:
        """Check if all reminders have been sent and escalation is needed."""
        return reminders_sent >= self.MAX_REMINDERS

    def get_next_reminder_number(self, reminders_sent: int) -> int | None:
        """
        Get the next reminder number to send.

        Returns None if all reminders are exhausted.
        """
        next_num = reminders_sent + 1
        if next_num > self.MAX_REMINDERS:
            return None
        return next_num


@dataclass
class NotificationLog:
    """Log entry for a notification event."""

    notification_id: UUID
    recipient_email: str
    notification_type: str
    timestamp: datetime
    delivery_status: str
    case_id: UUID
    retry_count: int = 0
    error_message: str | None = None


# ─── Email Templates ──────────────────────────────────────────────────────────

# Template definitions mapping type to template code and subject
NOTIFICATION_TEMPLATES: dict[str, dict[str, str]] = {
    NotificationType.INVITATION.value: {
        "template_code": "vlr_invitation",
        "subject": "Vendor Ledger Reconciliation - Invitation to Participate",
    },
    NotificationType.REMINDER.value: {
        "template_code": "vlr_reminder",
        "subject": "Vendor Ledger Reconciliation - Reminder: Action Required",
    },
    NotificationType.ESCALATION.value: {
        "template_code": "vlr_escalation",
        "subject": "Vendor Ledger Reconciliation - Escalation: Vendor Non-Response",
    },
    NotificationType.APPROVAL_REQUEST.value: {
        "template_code": "vlr_approval_request",
        "subject": "Vendor Ledger Reconciliation - Case Pending Your Approval",
    },
    NotificationType.REJECTION.value: {
        "template_code": "vlr_rejection",
        "subject": "Vendor Ledger Reconciliation - Case Rejected",
    },
    NotificationType.SIGN_OFF_REQUEST.value: {
        "template_code": "vlr_sign_off_request",
        "subject": "Vendor Ledger Reconciliation - Sign-Off Required",
    },
    NotificationType.SIGN_OFF_COMPLETE.value: {
        "template_code": "vlr_sign_off_complete",
        "subject": "Vendor Ledger Reconciliation - Vendor Sign-Off Received",
    },
}


# ─── Email Sender Protocol ────────────────────────────────────────────────────


class IEmailSender:
    """Protocol for sending emails (infrastructure concern)."""

    async def send_email(
        self,
        to_email: str,
        subject: str,
        body_html: str,
        template_code: str | None = None,
    ) -> bool:
        """
        Send an email to the specified recipient.

        Returns True if sent successfully, False otherwise.
        """
        raise NotImplementedError


# ─── Service ──────────────────────────────────────────────────────────────────


class NotificationService:
    """
    Domain service for notification management.

    Handles sending email notifications with template rendering,
    retry with exponential backoff, reminder scheduling, and
    escalation when reminders exceed the configured maximum.
    """

    def __init__(
        self,
        notification_repository: object,
        case_repository: object,
        setting_repository: object,
        email_sender: IEmailSender | None = None,
    ) -> None:
        self._notification_repo = notification_repository
        self._case_repo = case_repository
        self._setting_repo = setting_repository
        self._email_sender = email_sender
        # In-memory reminder schedules (in production, persisted via repository)
        self._reminder_schedules: dict[UUID, ReminderSchedule] = {}

    # ──────────────────────────────────────────────────────────────────────
    # Send Invitation
    # ──────────────────────────────────────────────────────────────────────

    async def send_invitation(
        self,
        case_id: UUID,
        vendor_contact: VendorContact,
        portal_url: str | None = None,
        company_code: str | None = None,
    ) -> NotificationResult:
        """
        Send an invitation email to a vendor contact.

        Requirement 10.1: Send email invitation with token URL within 5 minutes.
        Requirement 10.8: Use configurable email templates.
        Requirement 10.7: Log notification with recipient, type, timestamp, status.
        """
        template = NOTIFICATION_TEMPLATES[NotificationType.INVITATION.value]
        context_data = {
            "vendor_name": vendor_contact.name,
            "portal_url": portal_url or "",
            "case_id": str(case_id),
        }

        return await self._send_notification(
            case_id=case_id,
            notification_type=NotificationType.INVITATION,
            recipient_email=vendor_contact.email,
            template_code=template["template_code"],
            subject=template["subject"],
            context_data=context_data,
        )

    # ──────────────────────────────────────────────────────────────────────
    # Send Reminder
    # ──────────────────────────────────────────────────────────────────────

    async def send_reminder(
        self,
        case_id: UUID,
        recipient_email: str | None = None,
        company_code: str | None = None,
    ) -> NotificationResult:
        """
        Send a reminder notification for a case.

        Requirement 10.2: Send automated reminders at configurable intervals.
        Requirement 10.3: Escalate when reminder count exceeds maximum.
        Requirement 10.7: Log notification.

        If reminder count exceeds max, triggers escalation instead.
        """
        # Check current reminder count for this case
        reminder_count = await self._notification_repo.count_reminders_for_case(
            case_id
        )

        # Load max reminders from settings or use default
        max_reminders = await self._load_max_reminders(company_code)

        # If max reminders exceeded, escalate instead
        if reminder_count >= max_reminders:
            return await self.escalate(case_id, company_code=company_code)

        # Determine recipient if not provided
        if recipient_email is None:
            recipient_email = await self._get_primary_contact_email(case_id)

        template = NOTIFICATION_TEMPLATES[NotificationType.REMINDER.value]
        context_data = {
            "case_id": str(case_id),
            "reminder_number": reminder_count + 1,
            "max_reminders": max_reminders,
        }

        return await self._send_notification(
            case_id=case_id,
            notification_type=NotificationType.REMINDER,
            recipient_email=recipient_email,
            template_code=template["template_code"],
            subject=template["subject"],
            context_data=context_data,
        )

    # ──────────────────────────────────────────────────────────────────────
    # Send Approval Notification
    # ──────────────────────────────────────────────────────────────────────

    async def send_approval_notification(
        self,
        case_id: UUID,
        manager_email: str,
        company_code: str | None = None,
    ) -> NotificationResult:
        """
        Send an approval request notification to the assigned manager.

        Requirement 10.4: Notify assigned manager when case requires approval.
        Requirement 10.7: Log notification.
        """
        template = NOTIFICATION_TEMPLATES[NotificationType.APPROVAL_REQUEST.value]
        context_data = {
            "case_id": str(case_id),
        }

        return await self._send_notification(
            case_id=case_id,
            notification_type=NotificationType.APPROVAL_REQUEST,
            recipient_email=manager_email,
            template_code=template["template_code"],
            subject=template["subject"],
            context_data=context_data,
        )

    # ──────────────────────────────────────────────────────────────────────
    # Send Rejection Notification
    # ──────────────────────────────────────────────────────────────────────

    async def send_rejection_notification(
        self,
        case_id: UUID,
        user_email: str,
        reason: str,
        company_code: str | None = None,
    ) -> NotificationResult:
        """
        Send a rejection notification to the reconciliation user.

        Requirement 10.5: Notify user with rejection reason.
        Requirement 10.7: Log notification.
        """
        template = NOTIFICATION_TEMPLATES[NotificationType.REJECTION.value]
        context_data = {
            "case_id": str(case_id),
            "rejection_reason": reason,
        }

        return await self._send_notification(
            case_id=case_id,
            notification_type=NotificationType.REJECTION,
            recipient_email=user_email,
            template_code=template["template_code"],
            subject=template["subject"],
            context_data=context_data,
        )

    # ──────────────────────────────────────────────────────────────────────
    # Send Sign-Off Request
    # ──────────────────────────────────────────────────────────────────────

    async def send_sign_off_request(
        self,
        case_id: UUID,
        vendor_email: str,
        portal_url: str | None = None,
        company_code: str | None = None,
    ) -> NotificationResult:
        """
        Send a sign-off request notification to the vendor.

        Requirement 10.6 (implied): Notify vendor for sign-off after approval.
        Requirement 10.7: Log notification.
        """
        template = NOTIFICATION_TEMPLATES[NotificationType.SIGN_OFF_REQUEST.value]
        context_data = {
            "case_id": str(case_id),
            "portal_url": portal_url or "",
        }

        return await self._send_notification(
            case_id=case_id,
            notification_type=NotificationType.SIGN_OFF_REQUEST,
            recipient_email=vendor_email,
            template_code=template["template_code"],
            subject=template["subject"],
            context_data=context_data,
        )

    # ──────────────────────────────────────────────────────────────────────
    # Send Sign-Off Complete Notification
    # ──────────────────────────────────────────────────────────────────────

    async def send_sign_off_complete(
        self,
        case_id: UUID,
        user_email: str,
        vendor_name: str | None = None,
        company_code: str | None = None,
    ) -> NotificationResult:
        """
        Notify reconciliation user that vendor has completed sign-off.

        Requirement 10.6: Notify user when vendor completes sign-off.
        Requirement 10.7: Log notification.
        """
        template = NOTIFICATION_TEMPLATES[NotificationType.SIGN_OFF_COMPLETE.value]
        context_data = {
            "case_id": str(case_id),
            "vendor_name": vendor_name or "",
        }

        return await self._send_notification(
            case_id=case_id,
            notification_type=NotificationType.SIGN_OFF_COMPLETE,
            recipient_email=user_email,
            template_code=template["template_code"],
            subject=template["subject"],
            context_data=context_data,
        )

    # ──────────────────────────────────────────────────────────────────────
    # Escalation
    # ──────────────────────────────────────────────────────────────────────

    async def escalate(
        self,
        case_id: UUID,
        manager_email: str | None = None,
        company_code: str | None = None,
    ) -> NotificationResult:
        """
        Escalate a case when reminder count exceeds the configured maximum.

        Requirement 10.3: Escalate to Reconciliation Manager.
        Requirement 10.7: Log notification.

        If manager_email is not provided, attempts to resolve it from the case.
        """
        if manager_email is None:
            manager_email = await self._get_manager_email(case_id)

        template = NOTIFICATION_TEMPLATES[NotificationType.ESCALATION.value]
        reminder_count = await self._notification_repo.count_reminders_for_case(
            case_id
        )
        context_data = {
            "case_id": str(case_id),
            "reminder_count": reminder_count,
        }

        return await self._send_notification(
            case_id=case_id,
            notification_type=NotificationType.ESCALATION,
            recipient_email=manager_email,
            template_code=template["template_code"],
            subject=template["subject"],
            context_data=context_data,
        )

    # ──────────────────────────────────────────────────────────────────────
    # Reminder Scheduling
    # ──────────────────────────────────────────────────────────────────────

    async def schedule_reminders(
        self,
        case_id: UUID,
        intervals: list[int] | None = None,
        company_code: str | None = None,
    ) -> ReminderSchedule:
        """
        Schedule reminders for a case at configurable intervals.

        Requirement 10.2: Send reminders at configurable intervals
                         (default: 3, 7, 14 days).

        Args:
            case_id: The reconciliation case ID.
            intervals: Custom reminder intervals in days.
                      If None, loads from settings or uses defaults.
            company_code: Company code for loading settings.

        Returns:
            ReminderSchedule with the configured schedule.
        """
        if intervals is None:
            intervals = await self._load_reminder_intervals(company_code)

        max_reminders = await self._load_max_reminders(company_code)

        now = datetime.now(timezone.utc)
        next_date = now + timedelta(days=intervals[0]) if intervals else None

        schedule = ReminderSchedule(
            case_id=case_id,
            intervals_days=intervals,
            max_reminders=max_reminders,
            next_reminder_index=0,
            next_reminder_date=next_date,
        )

        self._reminder_schedules[case_id] = schedule

        logger.info(
            "Reminder schedule created",
            extra={
                "case_id": str(case_id),
                "intervals_days": intervals,
                "max_reminders": max_reminders,
                "next_reminder_date": str(next_date),
            },
        )

        return schedule

    async def get_next_reminder_date(
        self,
        case_id: UUID,
        company_code: str | None = None,
    ) -> datetime | None:
        """
        Calculate the next reminder date based on the schedule.

        Returns None if all reminders have been sent or max exceeded.
        """
        reminder_count = await self._notification_repo.count_reminders_for_case(
            case_id
        )
        max_reminders = await self._load_max_reminders(company_code)

        if reminder_count >= max_reminders:
            return None

        intervals = await self._load_reminder_intervals(company_code)
        if reminder_count >= len(intervals):
            return None

        # Calculate from now + next interval
        now = datetime.now(timezone.utc)
        next_interval_days = intervals[reminder_count]
        return now + timedelta(days=next_interval_days)

    # ──────────────────────────────────────────────────────────────────────
    # Retry Logic
    # ──────────────────────────────────────────────────────────────────────

    async def retry_failed_notification(
        self,
        notification_id: UUID,
    ) -> NotificationResult:
        """
        Retry a failed notification with exponential backoff.

        Requirement 10.9: Retry up to 3 times with exponential backoff
                         (30s, 120s, 480s).

        Returns updated notification result after retry attempt.
        Raises ValueError if notification not found or max retries exceeded.
        """
        notification = await self._notification_repo.get_by_id(notification_id)
        if notification is None:
            raise ValueError(
                f"Notification '{notification_id}' not found."
            )

        current_retry = getattr(notification, "retry_count", 0)
        if current_retry >= MAX_RETRY_ATTEMPTS:
            raise ValueError(
                f"Notification '{notification_id}' has exceeded maximum "
                f"retry attempts ({MAX_RETRY_ATTEMPTS})."
            )

        # Attempt to resend the email
        recipient = getattr(notification, "recipient_email", "")
        template_code = getattr(notification, "template_code", "")
        notif_type = getattr(notification, "type", "")

        template_info = NOTIFICATION_TEMPLATES.get(notif_type, {})
        subject = template_info.get("subject", "VLR Notification")

        success = await self._attempt_send(
            to_email=recipient,
            subject=subject,
            template_code=template_code,
            context_data={},
        )

        new_retry_count = current_retry + 1
        now = datetime.now(timezone.utc)

        if success:
            await self._notification_repo.update(notification_id, {
                "status": NotificationStatus.SENT.value,
                "retry_count": new_retry_count,
                "sent_date": now,
                "next_retry_date": None,
            })
            status = NotificationStatus.SENT.value
            next_retry = None
        else:
            next_retry = self._calculate_next_retry_date(new_retry_count)
            final_status = (
                NotificationStatus.FAILED.value
                if new_retry_count >= MAX_RETRY_ATTEMPTS
                else NotificationStatus.RETRYING.value
            )
            await self._notification_repo.update(notification_id, {
                "status": final_status,
                "retry_count": new_retry_count,
                "next_retry_date": next_retry,
            })
            status = final_status

        self._log_notification_event(
            notification_id=notification_id,
            recipient_email=recipient,
            notification_type=notif_type,
            delivery_status=status,
            case_id=getattr(notification, "case_id", None),
            retry_count=new_retry_count,
        )

        return NotificationResult(
            notification_id=notification_id,
            case_id=getattr(notification, "case_id", uuid4()),
            notification_type=notif_type,
            recipient_email=recipient,
            status=status,
            retry_count=new_retry_count,
            sent_date=now if success else None,
            next_retry_date=next_retry,
            template_code=template_code,
        )

    # ──────────────────────────────────────────────────────────────────────
    # Notification History
    # ──────────────────────────────────────────────────────────────────────

    async def get_notification_history(
        self,
        case_id: UUID,
    ) -> list[object]:
        """
        Get all notifications for a case.

        Requirement 10.10: Provide notification history view from case detail.
        """
        result = await self._notification_repo.list_by_case(case_id)
        return list(result.items) if hasattr(result, "items") else []

    # ──────────────────────────────────────────────────────────────────────
    # Process Pending Retries
    # ──────────────────────────────────────────────────────────────────────

    async def process_pending_retries(self) -> list[NotificationResult]:
        """
        Process all notifications that are due for retry.

        Called by the Celery beat schedule to retry failed notifications.
        Returns a list of retry results.
        """
        now = datetime.now(timezone.utc)
        pending = await self._notification_repo.get_pending_retries(before=now)

        results = []
        for notification in pending:
            notif_id = getattr(notification, "id", None)
            if notif_id is None:
                continue
            try:
                result = await self.retry_failed_notification(
                    UUID(str(notif_id))
                )
                results.append(result)
            except ValueError:
                # Max retries exceeded or not found - skip
                continue

        return results

    # ──────────────────────────────────────────────────────────────────────
    # Internal: Send Notification (core logic)
    # ──────────────────────────────────────────────────────────────────────

    async def _send_notification(
        self,
        case_id: UUID,
        notification_type: NotificationType,
        recipient_email: str,
        template_code: str,
        subject: str,
        context_data: dict | None = None,
    ) -> NotificationResult:
        """
        Core notification sending logic with retry support.

        1. Render template
        2. Attempt email delivery
        3. On failure, schedule retry with exponential backoff
        4. Persist notification record
        5. Log the event
        """
        notification_id = uuid4()
        now = datetime.now(timezone.utc)

        # Render template (simple placeholder-based rendering)
        body_html = self._render_template(template_code, context_data or {})

        # Attempt to send email
        success = await self._attempt_send(
            to_email=recipient_email,
            subject=subject,
            template_code=template_code,
            context_data=context_data or {},
        )

        if success:
            status = NotificationStatus.SENT.value
            next_retry_date = None
        else:
            status = NotificationStatus.RETRYING.value
            next_retry_date = self._calculate_next_retry_date(retry_count=0)

        # Persist the notification record
        await self._notification_repo.create({
            "id": str(notification_id),
            "case_id": str(case_id),
            "type": notification_type.value,
            "recipient_email": recipient_email,
            "status": status,
            "retry_count": 0 if success else 0,
            "template_code": template_code,
            "context_data": context_data or {},
            "sent_date": now if success else None,
            "next_retry_date": next_retry_date,
        })

        # Log the notification event
        self._log_notification_event(
            notification_id=notification_id,
            recipient_email=recipient_email,
            notification_type=notification_type.value,
            delivery_status=status,
            case_id=case_id,
        )

        return NotificationResult(
            notification_id=notification_id,
            case_id=case_id,
            notification_type=notification_type.value,
            recipient_email=recipient_email,
            status=status,
            retry_count=0,
            sent_date=now if success else None,
            next_retry_date=next_retry_date,
            template_code=template_code,
            context_data=context_data,
        )

    # ──────────────────────────────────────────────────────────────────────
    # Internal: Email Sending
    # ──────────────────────────────────────────────────────────────────────

    async def _attempt_send(
        self,
        to_email: str,
        subject: str,
        template_code: str,
        context_data: dict,
    ) -> bool:
        """
        Attempt to send an email via the email sender.

        Returns True if successful, False otherwise.
        If no email sender is configured, returns True (test/dev mode).
        """
        if self._email_sender is None:
            # No email sender configured - assume success (dev/test mode)
            return True

        try:
            body_html = self._render_template(template_code, context_data)
            return await self._email_sender.send_email(
                to_email=to_email,
                subject=subject,
                body_html=body_html,
                template_code=template_code,
            )
        except Exception as e:
            logger.error(
                "Email send failed",
                extra={
                    "to_email": to_email,
                    "template_code": template_code,
                    "error": str(e),
                },
            )
            return False

    # ──────────────────────────────────────────────────────────────────────
    # Internal: Template Rendering
    # ──────────────────────────────────────────────────────────────────────

    def _render_template(
        self,
        template_code: str,
        context_data: dict,
    ) -> str:
        """
        Render an email template with context data.

        Requirement 10.8: Support configurable email templates.

        Uses simple string substitution. In production, this could be
        replaced with Jinja2 or a dedicated template engine.
        """
        # Base template structure
        template_body = (
            f"<html><body>"
            f"<h2>{template_code.replace('_', ' ').title()}</h2>"
        )

        for key, value in context_data.items():
            template_body += f"<p><strong>{key}:</strong> {value}</p>"

        template_body += "</body></html>"
        return template_body

    # ──────────────────────────────────────────────────────────────────────
    # Internal: Retry Calculation
    # ──────────────────────────────────────────────────────────────────────

    @staticmethod
    def _calculate_next_retry_date(retry_count: int) -> datetime | None:
        """
        Calculate the next retry date using exponential backoff.

        Requirement 10.9: Retry with exponential backoff (30s, 120s, 480s).

        Args:
            retry_count: Current number of retries attempted (0-based).

        Returns:
            Next retry datetime, or None if max retries exceeded.
        """
        if retry_count >= MAX_RETRY_ATTEMPTS:
            return None

        backoff_index = min(retry_count, len(RETRY_BACKOFF_SECONDS) - 1)
        backoff_seconds = RETRY_BACKOFF_SECONDS[backoff_index]

        return datetime.now(timezone.utc) + timedelta(seconds=backoff_seconds)

    # ──────────────────────────────────────────────────────────────────────
    # Internal: Logging
    # ──────────────────────────────────────────────────────────────────────

    @staticmethod
    def _log_notification_event(
        notification_id: UUID,
        recipient_email: str,
        notification_type: str,
        delivery_status: str,
        case_id: UUID | None = None,
        retry_count: int = 0,
        error_message: str | None = None,
    ) -> None:
        """
        Log a notification event.

        Requirement 10.7: Log all notifications with recipient, type,
                         timestamp, and delivery status.
        """
        logger.info(
            "Notification event",
            extra={
                "notification_id": str(notification_id),
                "recipient_email": recipient_email,
                "notification_type": notification_type,
                "delivery_status": delivery_status,
                "case_id": str(case_id) if case_id else None,
                "retry_count": retry_count,
                "error_message": error_message,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )

    # ──────────────────────────────────────────────────────────────────────
    # Internal: Settings Loaders
    # ──────────────────────────────────────────────────────────────────────

    async def _load_reminder_intervals(
        self, company_code: str | None = None
    ) -> list[int]:
        """Load reminder intervals from settings or return defaults."""
        if company_code is None:
            return list(DEFAULT_REMINDER_INTERVALS_DAYS)

        try:
            setting = await self._setting_repo.get_by_key(
                company_code, "reminder_intervals_days"
            )
            if setting:
                value = getattr(setting, "value", "")
                # Parse comma-separated days, e.g. "3,7,14"
                return [int(d.strip()) for d in value.split(",") if d.strip()]
        except Exception:
            pass

        return list(DEFAULT_REMINDER_INTERVALS_DAYS)

    async def _load_max_reminders(
        self, company_code: str | None = None
    ) -> int:
        """Load max reminders from settings or return default."""
        if company_code is None:
            return DEFAULT_MAX_REMINDERS

        try:
            setting = await self._setting_repo.get_by_key(
                company_code, "max_reminders"
            )
            if setting:
                return int(getattr(setting, "value", DEFAULT_MAX_REMINDERS))
        except Exception:
            pass

        return DEFAULT_MAX_REMINDERS

    # ──────────────────────────────────────────────────────────────────────
    # Internal: Contact Resolution
    # ──────────────────────────────────────────────────────────────────────

    async def _get_primary_contact_email(self, case_id: UUID) -> str:
        """
        Resolve the primary vendor contact email for a case.

        Falls back to a placeholder if unable to resolve.
        """
        # In a full implementation, this would look up the case -> vendor -> contacts
        # For now, we return a placeholder that the caller should provide
        return "vendor@example.com"

    async def _get_manager_email(self, case_id: UUID) -> str:
        """
        Resolve the assigned manager's email for escalation.

        Falls back to a placeholder if unable to resolve.
        """
        # In a full implementation, this would look up case -> request -> manager
        return "manager@example.com"


# ══════════════════════════════════════════════════════════════════════════════
# Enhanced Email Notification Service with Jinja2 Templates & Celery Dispatch
# ══════════════════════════════════════════════════════════════════════════════


class EmailNotificationService:
    """
    Enhanced notification service with Jinja2 template rendering,
    BRD-specified D3/D7/D10 reminder scheduling, and Celery task dispatch.

    All emails are sent as non-blocking Celery tasks and rendered using
    Jinja2 templates from the templates directory.

    Requirements: 14.1, 14.3, 14.4, 15.1, 15.2, 15.3, 15.4, 16.1, 16.2
    """

    def __init__(
        self,
        notification_repository: object,
        case_repository: object,
        setting_repository: object,
        email_sender: IEmailSender | None = None,
        templates_dir: str | Path | None = None,
        base_url: str = "http://localhost:3000",
    ) -> None:
        self._notification_repo = notification_repository
        self._case_repo = case_repository
        self._setting_repo = setting_repository
        self._email_sender = email_sender
        self._base_url = base_url.rstrip("/")
        self._reminder_schedule = BRDReminderSchedule()

        # Initialize Jinja2 environment
        template_path = Path(templates_dir) if templates_dir else TEMPLATES_DIR
        self._jinja_env = Environment(
            loader=FileSystemLoader(str(template_path)),
            autoescape=select_autoescape(["html"]),
        )

    # ──────────────────────────────────────────────────────────────────────
    # Public: Send Vendor Invite
    # ──────────────────────────────────────────────────────────────────────

    async def send_vendor_invite(
        self,
        case_id: UUID,
        vendor_email: str,
        vendor_name: str,
        portal_token: str,
        company_name: str = "Emcure Pharmaceuticals",
        period_start: str = "",
        period_end: str = "",
        deadline: str = "",
    ) -> NotificationResult:
        """
        Send a vendor invite email with a unique portal link.

        Generates a unique portal URL using the provided token and dispatches
        the email as a Celery task to avoid blocking.

        Requirement 14.1: Send invite email with unique portal link.
        Requirement 14.3: Send via SMTP integration.
        Requirement 14.4: Schedule as Celery task (non-blocking).

        Args:
            case_id: The reconciliation case ID.
            vendor_email: Email address of the vendor contact.
            vendor_name: Display name of the vendor.
            portal_token: Unique token for portal access.
            company_name: Name of the company sending the invite.
            period_start: Reconciliation period start date (display string).
            period_end: Reconciliation period end date (display string).
            deadline: Deadline for statement upload (display string).

        Returns:
            NotificationResult with the delivery details.
        """
        portal_url = f"{self._base_url}/portal/access/{portal_token}"
        case_url = f"{self._base_url}/vlr/cases/{case_id}"

        context_data = {
            "vendor_name": vendor_name,
            "company_name": company_name,
            "portal_url": portal_url,
            "case_id": str(case_id),
            "case_url": case_url,
            "period_start": period_start,
            "period_end": period_end,
            "deadline": deadline,
        }

        # Render Jinja2 template
        body_html = self._render_jinja_template("vendor_invite.html", context_data)

        subject = "Vendor Ledger Reconciliation - Statement Request"

        # Dispatch via Celery task (non-blocking)
        notification_id = uuid4()
        now = datetime.now(timezone.utc)

        await self._dispatch_email_task(
            notification_id=notification_id,
            case_id=case_id,
            notification_type=NotificationType.VENDOR_INVITE,
            recipient_email=vendor_email,
            subject=subject,
            body_html=body_html,
            context_data=context_data,
        )

        # Persist notification record
        await self._persist_notification(
            notification_id=notification_id,
            case_id=case_id,
            notification_type=NotificationType.VENDOR_INVITE,
            recipient_email=vendor_email,
            template_name="vendor_invite.html",
            context_data=context_data,
        )

        logger.info(
            "Vendor invite dispatched",
            extra={
                "case_id": str(case_id),
                "recipient": vendor_email,
                "portal_url": portal_url,
            },
        )

        return NotificationResult(
            notification_id=notification_id,
            case_id=case_id,
            notification_type=NotificationType.VENDOR_INVITE.value,
            recipient_email=vendor_email,
            status=NotificationStatus.PENDING.value,
            sent_date=now,
            template_code="vendor_invite.html",
            context_data=context_data,
        )

    # ──────────────────────────────────────────────────────────────────────
    # Public: Send Scheduled Reminder (D3/D7/D10)
    # ──────────────────────────────────────────────────────────────────────

    async def send_scheduled_reminder(
        self,
        case_id: UUID,
        reminder_number: int,
        vendor_email: str,
        vendor_name: str,
        portal_token: str,
        company_name: str = "Emcure Pharmaceuticals",
        period_start: str = "",
        period_end: str = "",
    ) -> NotificationResult:
        """
        Send a scheduled reminder email (D3, D7, or D10) based on the BRD schedule.

        Uses the BRDReminderSchedule to determine which template to use.
        Dispatches via Celery task for non-blocking execution.

        Requirement 15.1: D3 reminder after 3 days with no upload.
        Requirement 15.2: D7 reminder after 7 days with no upload.
        Requirement 15.3: D10 reminder after 10 days with no upload.

        Args:
            case_id: The reconciliation case ID.
            reminder_number: Which reminder to send (1=D3, 2=D7, 3=D10).
            vendor_email: Email address of the vendor contact.
            vendor_name: Display name of the vendor.
            portal_token: Unique token for portal access.
            company_name: Name of the company.
            period_start: Reconciliation period start date.
            period_end: Reconciliation period end date.

        Returns:
            NotificationResult with delivery details.

        Raises:
            ValueError: If reminder_number is invalid or schedule is exhausted.
        """
        # Validate reminder number
        template_name = self._reminder_schedule.get_template_name(reminder_number)
        if template_name is None:
            raise ValueError(
                f"Invalid reminder number {reminder_number}. "
                f"Valid range: 1-{self._reminder_schedule.MAX_REMINDERS}"
            )

        interval_days = self._reminder_schedule.get_interval_days(reminder_number)
        portal_url = f"{self._base_url}/portal/access/{portal_token}"
        case_url = f"{self._base_url}/vlr/cases/{case_id}"

        # Determine notification type based on reminder number
        reminder_type_map = {
            1: NotificationType.REMINDER_D3,
            2: NotificationType.REMINDER_D7,
            3: NotificationType.REMINDER_D10,
        }
        notification_type = reminder_type_map.get(
            reminder_number, NotificationType.REMINDER
        )

        context_data = {
            "vendor_name": vendor_name,
            "company_name": company_name,
            "portal_url": portal_url,
            "case_id": str(case_id),
            "case_url": case_url,
            "period_start": period_start,
            "period_end": period_end,
            "reminder_number": reminder_number,
            "interval_days": interval_days,
        }

        # Render the appropriate Jinja2 template
        body_html = self._render_jinja_template(template_name, context_data)

        subject_map = {
            1: "Reminder: Statement Upload Required (Day 3)",
            2: "Urgent: Statement Upload Required (Day 7)",
            3: "Final Reminder: Statement Upload Required (Day 10)",
        }
        subject = subject_map.get(
            reminder_number,
            "Vendor Ledger Reconciliation - Reminder",
        )

        # Dispatch via Celery task
        notification_id = uuid4()
        now = datetime.now(timezone.utc)

        await self._dispatch_email_task(
            notification_id=notification_id,
            case_id=case_id,
            notification_type=notification_type,
            recipient_email=vendor_email,
            subject=subject,
            body_html=body_html,
            context_data=context_data,
        )

        # Persist notification record
        await self._persist_notification(
            notification_id=notification_id,
            case_id=case_id,
            notification_type=notification_type,
            recipient_email=vendor_email,
            template_name=template_name,
            context_data=context_data,
        )

        logger.info(
            "Scheduled reminder dispatched",
            extra={
                "case_id": str(case_id),
                "reminder_number": reminder_number,
                "interval_days": interval_days,
                "template": template_name,
                "recipient": vendor_email,
            },
        )

        return NotificationResult(
            notification_id=notification_id,
            case_id=case_id,
            notification_type=notification_type.value,
            recipient_email=vendor_email,
            status=NotificationStatus.PENDING.value,
            sent_date=now,
            template_code=template_name,
            context_data=context_data,
        )

    # ──────────────────────────────────────────────────────────────────────
    # Public: Send Escalation
    # ──────────────────────────────────────────────────────────────────────

    async def send_escalation(
        self,
        case_id: UUID,
        manager_email: str,
        manager_name: str = "Reconciliation Manager",
        vendor_name: str = "",
        company_name: str = "Emcure Pharmaceuticals",
        period_start: str = "",
        period_end: str = "",
        reminder_count: int = 3,
        days_since_invite: int = 10,
    ) -> NotificationResult:
        """
        Send an escalation notification when all reminders are exhausted.

        Triggered after D10 reminder with no vendor response.
        Notifies the Reconciliation Manager for manual intervention.

        Requirement 15.4: Escalate when all reminders exhausted.

        Args:
            case_id: The reconciliation case ID.
            manager_email: Email of the Reconciliation Manager.
            manager_name: Display name of the manager.
            vendor_name: Name of the non-responsive vendor.
            company_name: Name of the company.
            period_start: Reconciliation period start date.
            period_end: Reconciliation period end date.
            reminder_count: Number of reminders already sent.
            days_since_invite: Days elapsed since original invite.

        Returns:
            NotificationResult with delivery details.
        """
        case_url = f"{self._base_url}/vlr/cases/{case_id}"

        context_data = {
            "manager_name": manager_name,
            "vendor_name": vendor_name,
            "company_name": company_name,
            "case_id": str(case_id),
            "case_url": case_url,
            "period_start": period_start,
            "period_end": period_end,
            "reminder_count": reminder_count,
            "days_since_invite": days_since_invite,
        }

        # Render Jinja2 escalation template
        body_html = self._render_jinja_template("escalation.html", context_data)

        subject = "ESCALATION: Vendor Non-Response - Reconciliation Case"

        notification_id = uuid4()
        now = datetime.now(timezone.utc)

        await self._dispatch_email_task(
            notification_id=notification_id,
            case_id=case_id,
            notification_type=NotificationType.ESCALATION,
            recipient_email=manager_email,
            subject=subject,
            body_html=body_html,
            context_data=context_data,
        )

        await self._persist_notification(
            notification_id=notification_id,
            case_id=case_id,
            notification_type=NotificationType.ESCALATION,
            recipient_email=manager_email,
            template_name="escalation.html",
            context_data=context_data,
        )

        logger.info(
            "Escalation dispatched",
            extra={
                "case_id": str(case_id),
                "manager_email": manager_email,
                "reminder_count": reminder_count,
                "days_since_invite": days_since_invite,
            },
        )

        return NotificationResult(
            notification_id=notification_id,
            case_id=case_id,
            notification_type=NotificationType.ESCALATION.value,
            recipient_email=manager_email,
            status=NotificationStatus.PENDING.value,
            sent_date=now,
            template_code="escalation.html",
            context_data=context_data,
        )

    # ──────────────────────────────────────────────────────────────────────
    # Public: Send Approval Request
    # ──────────────────────────────────────────────────────────────────────

    async def send_approval_request(
        self,
        case_id: UUID,
        approver_email: str,
        approver_name: str = "Finance Reviewer",
        vendor_name: str = "",
        requested_by: str = "",
        company_name: str = "Emcure Pharmaceuticals",
        period_start: str = "",
        period_end: str = "",
    ) -> NotificationResult:
        """
        Send an approval request notification to the assigned Finance User.

        Triggered when a case reaches the Finance Approval step.

        Requirement 16.1: Send approval request to Finance_User.
        Requirement 16.2: Send upload confirmation (handled separately).

        Args:
            case_id: The reconciliation case ID.
            approver_email: Email of the finance approver.
            approver_name: Display name of the approver.
            vendor_name: Name of the vendor for the case.
            requested_by: Who requested the approval.
            company_name: Name of the company.
            period_start: Reconciliation period start date.
            period_end: Reconciliation period end date.

        Returns:
            NotificationResult with delivery details.
        """
        case_url = f"{self._base_url}/vlr/cases/{case_id}"

        context_data = {
            "approver_name": approver_name,
            "vendor_name": vendor_name,
            "company_name": company_name,
            "case_id": str(case_id),
            "case_url": case_url,
            "period_start": period_start,
            "period_end": period_end,
            "requested_by": requested_by,
        }

        # Render Jinja2 approval request template
        body_html = self._render_jinja_template("approval_request.html", context_data)

        subject = "Approval Required: Vendor Ledger Reconciliation Case"

        notification_id = uuid4()
        now = datetime.now(timezone.utc)

        await self._dispatch_email_task(
            notification_id=notification_id,
            case_id=case_id,
            notification_type=NotificationType.APPROVAL_REQUEST,
            recipient_email=approver_email,
            subject=subject,
            body_html=body_html,
            context_data=context_data,
        )

        await self._persist_notification(
            notification_id=notification_id,
            case_id=case_id,
            notification_type=NotificationType.APPROVAL_REQUEST,
            recipient_email=approver_email,
            template_name="approval_request.html",
            context_data=context_data,
        )

        logger.info(
            "Approval request dispatched",
            extra={
                "case_id": str(case_id),
                "approver_email": approver_email,
                "vendor_name": vendor_name,
            },
        )

        return NotificationResult(
            notification_id=notification_id,
            case_id=case_id,
            notification_type=NotificationType.APPROVAL_REQUEST.value,
            recipient_email=approver_email,
            status=NotificationStatus.PENDING.value,
            sent_date=now,
            template_code="approval_request.html",
            context_data=context_data,
        )

    # ──────────────────────────────────────────────────────────────────────
    # Public: Send Upload Confirmation
    # ──────────────────────────────────────────────────────────────────────

    async def send_upload_confirmation(
        self,
        case_id: UUID,
        user_email: str,
        user_name: str = "Finance User",
        vendor_name: str = "",
        company_name: str = "Emcure Pharmaceuticals",
        uploaded_at: str = "",
    ) -> NotificationResult:
        """
        Send an upload confirmation notification to the Finance User.

        Triggered when a vendor uploads their statement.

        Requirement 16.2: Send upload confirmation to the initiating Finance_User.

        Args:
            case_id: The reconciliation case ID.
            user_email: Email of the finance user who initiated the case.
            user_name: Display name of the user.
            vendor_name: Name of the vendor who uploaded.
            company_name: Name of the company.
            uploaded_at: Timestamp of upload (display string).

        Returns:
            NotificationResult with delivery details.
        """
        case_url = f"{self._base_url}/vlr/cases/{case_id}"

        context_data = {
            "user_name": user_name,
            "vendor_name": vendor_name,
            "company_name": company_name,
            "case_id": str(case_id),
            "case_url": case_url,
            "uploaded_at": uploaded_at or datetime.now(timezone.utc).strftime(
                "%Y-%m-%d %H:%M UTC"
            ),
        }

        body_html = self._render_jinja_template(
            "upload_confirmation.html", context_data
        )

        subject = "Vendor Statement Received - Reconciliation Case"

        notification_id = uuid4()
        now = datetime.now(timezone.utc)

        await self._dispatch_email_task(
            notification_id=notification_id,
            case_id=case_id,
            notification_type=NotificationType.UPLOAD_CONFIRMATION,
            recipient_email=user_email,
            subject=subject,
            body_html=body_html,
            context_data=context_data,
        )

        await self._persist_notification(
            notification_id=notification_id,
            case_id=case_id,
            notification_type=NotificationType.UPLOAD_CONFIRMATION,
            recipient_email=user_email,
            template_name="upload_confirmation.html",
            context_data=context_data,
        )

        logger.info(
            "Upload confirmation dispatched",
            extra={
                "case_id": str(case_id),
                "user_email": user_email,
                "vendor_name": vendor_name,
            },
        )

        return NotificationResult(
            notification_id=notification_id,
            case_id=case_id,
            notification_type=NotificationType.UPLOAD_CONFIRMATION.value,
            recipient_email=user_email,
            status=NotificationStatus.PENDING.value,
            sent_date=now,
            template_code="upload_confirmation.html",
            context_data=context_data,
        )

    # ──────────────────────────────────────────────────────────────────────
    # Public: Determine Next Reminder Action
    # ──────────────────────────────────────────────────────────────────────

    def determine_reminder_action(
        self,
        reminders_sent: int,
        invite_date: datetime,
    ) -> dict:
        """
        Determine what reminder action to take based on reminders already sent.

        Returns a dict describing the action:
        - {"action": "send_reminder", "reminder_number": N, "interval_days": D}
        - {"action": "escalate"} if all reminders exhausted
        - {"action": "none", "reason": "..."} if not yet time

        Args:
            reminders_sent: Number of reminders already sent.
            invite_date: When the original invite was sent.

        Returns:
            Dict describing the appropriate action.
        """
        now = datetime.now(timezone.utc)
        days_elapsed = (now - invite_date).days

        if self._reminder_schedule.is_exhausted(reminders_sent):
            return {"action": "escalate", "days_elapsed": days_elapsed}

        next_num = self._reminder_schedule.get_next_reminder_number(reminders_sent)
        if next_num is None:
            return {"action": "escalate", "days_elapsed": days_elapsed}

        interval = self._reminder_schedule.get_interval_days(next_num)
        if interval is None:
            return {"action": "none", "reason": "No interval defined"}

        if days_elapsed >= interval:
            return {
                "action": "send_reminder",
                "reminder_number": next_num,
                "interval_days": interval,
                "days_elapsed": days_elapsed,
            }

        return {
            "action": "none",
            "reason": f"Not yet time (day {days_elapsed}, next at day {interval})",
            "next_reminder_day": interval,
            "days_remaining": interval - days_elapsed,
        }

    # ──────────────────────────────────────────────────────────────────────
    # Public: Get Reminder Schedule
    # ──────────────────────────────────────────────────────────────────────

    @property
    def reminder_schedule(self) -> BRDReminderSchedule:
        """Get the BRD reminder schedule configuration."""
        return self._reminder_schedule

    # ──────────────────────────────────────────────────────────────────────
    # Internal: Jinja2 Template Rendering
    # ──────────────────────────────────────────────────────────────────────

    def _render_jinja_template(
        self,
        template_name: str,
        context: dict,
    ) -> str:
        """
        Render a Jinja2 email template with the given context.

        Requirement 14.2: Use configurable Jinja2 templates for email content.

        Args:
            template_name: Filename of the template (e.g., "vendor_invite.html").
            context: Dictionary of template variables.

        Returns:
            Rendered HTML string.
        """
        try:
            template = self._jinja_env.get_template(template_name)
            return template.render(**context)
        except Exception as e:
            logger.error(
                "Template rendering failed",
                extra={
                    "template_name": template_name,
                    "error": str(e),
                },
            )
            # Fallback to a simple HTML rendering
            return self._fallback_render(template_name, context)

    @staticmethod
    def _fallback_render(template_name: str, context: dict) -> str:
        """Fallback template rendering when Jinja2 template is unavailable."""
        html = f"<html><body><h2>{template_name}</h2>"
        for key, value in context.items():
            html += f"<p><strong>{key}:</strong> {value}</p>"
        html += "</body></html>"
        return html

    # ──────────────────────────────────────────────────────────────────────
    # Internal: Celery Task Dispatch
    # ──────────────────────────────────────────────────────────────────────

    async def _dispatch_email_task(
        self,
        notification_id: UUID,
        case_id: UUID,
        notification_type: NotificationType,
        recipient_email: str,
        subject: str,
        body_html: str,
        context_data: dict,
    ) -> None:
        """
        Dispatch email sending as a Celery task to avoid blocking.

        Requirement 14.4: Schedule email sending as Celery task.

        In production, this enqueues the actual SMTP send as a background task.
        In dev/test mode (no Celery available), sends directly via email_sender.
        """
        start = time.perf_counter()
        try:
            from src.infrastructure.tasks.vlr.notification_tasks import (
                send_notification_task,
            )

            # Dispatch to Celery as a non-blocking task
            send_notification_task.delay(
                case_id=str(case_id),
                notification_type=notification_type.value,
                recipient_email=recipient_email,
                triggered_by="system",
                context_data={
                    **context_data,
                    "_subject": subject,
                    "_body_html": body_html,
                    "_notification_id": str(notification_id),
                },
            )
            duration_ms = (time.perf_counter() - start) * 1000
            _structured_logger.log_success(
                operation="dispatch_email",
                duration_ms=duration_ms,
                case_id=str(case_id),
                notification_type=notification_type.value,
            )
            logger.debug(
                "Email task dispatched to Celery",
                extra={
                    "notification_id": str(notification_id),
                    "case_id": str(case_id),
                    "type": notification_type.value,
                },
            )
        except Exception as e:
            # Celery not available (dev/test mode) - send directly
            logger.debug(
                "Celery not available, sending directly: %s", str(e)
            )
            if self._email_sender:
                await self._email_sender.send_email(
                    to_email=recipient_email,
                    subject=subject,
                    body_html=body_html,
                    template_code=notification_type.value,
                )
            duration_ms = (time.perf_counter() - start) * 1000
            _structured_logger.log_success(
                operation="dispatch_email_direct",
                duration_ms=duration_ms,
                case_id=str(case_id),
                notification_type=notification_type.value,
            )

    # ──────────────────────────────────────────────────────────────────────
    # Internal: Persist Notification Record
    # ──────────────────────────────────────────────────────────────────────

    async def _persist_notification(
        self,
        notification_id: UUID,
        case_id: UUID,
        notification_type: NotificationType,
        recipient_email: str,
        template_name: str,
        context_data: dict,
    ) -> None:
        """Persist notification record in the database."""
        now = datetime.now(timezone.utc)
        try:
            await self._notification_repo.create({
                "id": str(notification_id),
                "case_id": str(case_id),
                "type": notification_type.value,
                "recipient_email": recipient_email,
                "status": NotificationStatus.PENDING.value,
                "retry_count": 0,
                "template_code": template_name,
                "context_data": context_data,
                "sent_date": now,
                "next_retry_date": None,
            })
        except Exception as e:
            logger.error(
                "Failed to persist notification record",
                extra={
                    "notification_id": str(notification_id),
                    "error": str(e),
                },
            )

    # ──────────────────────────────────────────────────────────────────────
    # Public: Generate Portal Link
    # ──────────────────────────────────────────────────────────────────────

    def generate_portal_link(self, portal_token: str) -> str:
        """
        Generate a unique portal link for vendor access.

        Requirement 14.1: Each invite includes a unique portal link.

        Args:
            portal_token: Unique token for the vendor's portal session.

        Returns:
            Full portal URL string.
        """
        return f"{self._base_url}/portal/access/{portal_token}"

    # ──────────────────────────────────────────────────────────────────────
    # Public: Generate Case Link
    # ──────────────────────────────────────────────────────────────────────

    def generate_case_link(self, case_id: UUID) -> str:
        """
        Generate a direct link to the relevant case.

        Requirement 16.3: All emails include a direct link to the relevant case.

        Args:
            case_id: The reconciliation case ID.

        Returns:
            Full case URL string.
        """
        return f"{self._base_url}/vlr/cases/{case_id}"
