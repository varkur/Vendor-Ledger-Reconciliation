"""
Unit tests for NotificationService domain logic.

Tests email sending with template rendering, retry with exponential backoff,
reminder scheduling, escalation logic, and notification history.
"""

import pytest
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

from src.domain.repositories.vlr.vendor_repository import PaginatedResult
from src.domain.services.vlr.notification_service import (
    DEFAULT_MAX_REMINDERS,
    DEFAULT_REMINDER_INTERVALS_DAYS,
    MAX_RETRY_ATTEMPTS,
    RETRY_BACKOFF_SECONDS,
    NotificationResult,
    NotificationService,
    NotificationStatus,
    NotificationType,
    ReminderSchedule,
    VendorContact,
)


# ─── Test Helpers ─────────────────────────────────────────────────────────────


@dataclass
class FakeNotification:
    """Fake notification object for testing."""

    id: UUID = field(default_factory=uuid4)
    case_id: UUID = field(default_factory=uuid4)
    type: str = "invitation"
    recipient_email: str = "vendor@test.com"
    status: str = "sent"
    retry_count: int = 0
    template_code: str = "vlr_invitation"
    context_data: dict = field(default_factory=dict)
    sent_date: datetime | None = None
    next_retry_date: datetime | None = None


@dataclass
class FakeSetting:
    """Fake setting object for testing."""

    id: UUID = field(default_factory=uuid4)
    key: str = "reminder_intervals_days"
    value: str = "3,7,14"


class FakeEmailSender:
    """Fake email sender that tracks calls."""

    def __init__(self, should_succeed: bool = True):
        self.should_succeed = should_succeed
        self.calls: list[dict] = []

    async def send_email(
        self,
        to_email: str,
        subject: str,
        body_html: str,
        template_code: str | None = None,
    ) -> bool:
        self.calls.append({
            "to_email": to_email,
            "subject": subject,
            "body_html": body_html,
            "template_code": template_code,
        })
        return self.should_succeed


# ─── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_notification_repo() -> AsyncMock:
    """Create a mock notification repository."""
    repo = AsyncMock()
    repo.get_by_id = AsyncMock(return_value=None)
    repo.create = AsyncMock()
    repo.update = AsyncMock()
    repo.list_by_case = AsyncMock(
        return_value=PaginatedResult(items=[], total=0, page=1, page_size=50)
    )
    repo.get_pending_retries = AsyncMock(return_value=[])
    repo.get_reminders_for_case = AsyncMock(return_value=[])
    repo.count_reminders_for_case = AsyncMock(return_value=0)
    repo.count_by_case = AsyncMock(return_value=0)
    return repo


@pytest.fixture
def mock_case_repo() -> AsyncMock:
    """Create a mock case repository."""
    repo = AsyncMock()
    repo.get_by_id = AsyncMock(return_value=None)
    return repo


@pytest.fixture
def mock_setting_repo() -> AsyncMock:
    """Create a mock setting repository."""
    repo = AsyncMock()
    repo.get_by_key = AsyncMock(return_value=None)
    return repo


@pytest.fixture
def fake_email_sender() -> FakeEmailSender:
    """Create a fake email sender that succeeds."""
    return FakeEmailSender(should_succeed=True)


@pytest.fixture
def failing_email_sender() -> FakeEmailSender:
    """Create a fake email sender that fails."""
    return FakeEmailSender(should_succeed=False)


@pytest.fixture
def notification_service(
    mock_notification_repo: AsyncMock,
    mock_case_repo: AsyncMock,
    mock_setting_repo: AsyncMock,
    fake_email_sender: FakeEmailSender,
) -> NotificationService:
    """Create NotificationService with mocked dependencies."""
    return NotificationService(
        notification_repository=mock_notification_repo,
        case_repository=mock_case_repo,
        setting_repository=mock_setting_repo,
        email_sender=fake_email_sender,
    )


@pytest.fixture
def notification_service_failing_email(
    mock_notification_repo: AsyncMock,
    mock_case_repo: AsyncMock,
    mock_setting_repo: AsyncMock,
    failing_email_sender: FakeEmailSender,
) -> NotificationService:
    """Create NotificationService with a failing email sender."""
    return NotificationService(
        notification_repository=mock_notification_repo,
        case_repository=mock_case_repo,
        setting_repository=mock_setting_repo,
        email_sender=failing_email_sender,
    )


@pytest.fixture
def sample_vendor_contact() -> VendorContact:
    """Create a sample vendor contact."""
    return VendorContact(
        id=uuid4(),
        vendor_id=uuid4(),
        name="Test Vendor",
        email="vendor@testcompany.com",
        phone="+1234567890",
        designation="Finance Manager",
        is_primary=True,
    )


# ─── Send Invitation Tests ────────────────────────────────────────────────────


class TestSendInvitation:
    """Tests for send_invitation method."""

    async def test_send_invitation_success(
        self,
        notification_service: NotificationService,
        mock_notification_repo: AsyncMock,
        sample_vendor_contact: VendorContact,
        fake_email_sender: FakeEmailSender,
    ):
        """Should send invitation email and persist notification (Req 10.1)."""
        case_id = uuid4()

        result = await notification_service.send_invitation(
            case_id=case_id,
            vendor_contact=sample_vendor_contact,
            portal_url="https://portal.example.com/token/abc123",
        )

        assert result.notification_type == NotificationType.INVITATION.value
        assert result.recipient_email == sample_vendor_contact.email
        assert result.status == NotificationStatus.SENT.value
        assert result.case_id == case_id
        assert result.template_code == "vlr_invitation"
        mock_notification_repo.create.assert_called_once()
        assert len(fake_email_sender.calls) == 1

    async def test_send_invitation_includes_portal_url_in_context(
        self,
        notification_service: NotificationService,
        sample_vendor_contact: VendorContact,
    ):
        """Should include portal URL in notification context data."""
        case_id = uuid4()
        portal_url = "https://portal.example.com/token/xyz"

        result = await notification_service.send_invitation(
            case_id=case_id,
            vendor_contact=sample_vendor_contact,
            portal_url=portal_url,
        )

        assert result.context_data is not None
        assert result.context_data["portal_url"] == portal_url

    async def test_send_invitation_failure_schedules_retry(
        self,
        notification_service_failing_email: NotificationService,
        mock_notification_repo: AsyncMock,
        sample_vendor_contact: VendorContact,
    ):
        """Should schedule retry when email delivery fails (Req 10.9)."""
        case_id = uuid4()

        result = await notification_service_failing_email.send_invitation(
            case_id=case_id,
            vendor_contact=sample_vendor_contact,
        )

        assert result.status == NotificationStatus.RETRYING.value
        assert result.next_retry_date is not None
        mock_notification_repo.create.assert_called_once()


# ─── Send Reminder Tests ──────────────────────────────────────────────────────


class TestSendReminder:
    """Tests for send_reminder method."""

    async def test_send_reminder_success(
        self,
        notification_service: NotificationService,
        mock_notification_repo: AsyncMock,
    ):
        """Should send reminder when count is below max (Req 10.2)."""
        case_id = uuid4()
        mock_notification_repo.count_reminders_for_case.return_value = 1

        result = await notification_service.send_reminder(
            case_id=case_id,
            recipient_email="vendor@test.com",
        )

        assert result.notification_type == NotificationType.REMINDER.value
        assert result.status == NotificationStatus.SENT.value
        assert result.recipient_email == "vendor@test.com"

    async def test_send_reminder_escalates_when_max_exceeded(
        self,
        notification_service: NotificationService,
        mock_notification_repo: AsyncMock,
    ):
        """Should escalate instead of sending reminder when max exceeded (Req 10.3)."""
        case_id = uuid4()
        # Already sent DEFAULT_MAX_REMINDERS reminders
        mock_notification_repo.count_reminders_for_case.return_value = (
            DEFAULT_MAX_REMINDERS
        )

        result = await notification_service.send_reminder(
            case_id=case_id,
            recipient_email="vendor@test.com",
        )

        assert result.notification_type == NotificationType.ESCALATION.value

    async def test_send_reminder_uses_default_email_when_none_provided(
        self,
        notification_service: NotificationService,
        mock_notification_repo: AsyncMock,
    ):
        """Should resolve contact email when not provided."""
        case_id = uuid4()
        mock_notification_repo.count_reminders_for_case.return_value = 0

        result = await notification_service.send_reminder(
            case_id=case_id,
            recipient_email=None,
        )

        # Falls back to placeholder
        assert result.recipient_email == "vendor@example.com"
        assert result.notification_type == NotificationType.REMINDER.value


# ─── Send Approval Notification Tests ─────────────────────────────────────────


class TestSendApprovalNotification:
    """Tests for send_approval_notification method."""

    async def test_send_approval_notification_success(
        self,
        notification_service: NotificationService,
        mock_notification_repo: AsyncMock,
    ):
        """Should send approval notification to manager (Req 10.4)."""
        case_id = uuid4()
        manager_email = "manager@company.com"

        result = await notification_service.send_approval_notification(
            case_id=case_id,
            manager_email=manager_email,
        )

        assert result.notification_type == NotificationType.APPROVAL_REQUEST.value
        assert result.recipient_email == manager_email
        assert result.status == NotificationStatus.SENT.value


# ─── Send Rejection Notification Tests ────────────────────────────────────────


class TestSendRejectionNotification:
    """Tests for send_rejection_notification method."""

    async def test_send_rejection_notification_success(
        self,
        notification_service: NotificationService,
        mock_notification_repo: AsyncMock,
    ):
        """Should notify user with rejection reason (Req 10.5)."""
        case_id = uuid4()
        user_email = "user@company.com"
        reason = "Write-off amount exceeds allowed threshold"

        result = await notification_service.send_rejection_notification(
            case_id=case_id,
            user_email=user_email,
            reason=reason,
        )

        assert result.notification_type == NotificationType.REJECTION.value
        assert result.recipient_email == user_email
        assert result.context_data["rejection_reason"] == reason


# ─── Sign-Off Tests ───────────────────────────────────────────────────────────


class TestSignOffNotifications:
    """Tests for sign-off related notifications."""

    async def test_send_sign_off_request(
        self,
        notification_service: NotificationService,
    ):
        """Should send sign-off request to vendor."""
        case_id = uuid4()

        result = await notification_service.send_sign_off_request(
            case_id=case_id,
            vendor_email="vendor@test.com",
            portal_url="https://portal.example.com/signoff",
        )

        assert result.notification_type == NotificationType.SIGN_OFF_REQUEST.value
        assert result.recipient_email == "vendor@test.com"

    async def test_send_sign_off_complete(
        self,
        notification_service: NotificationService,
    ):
        """Should notify user when vendor completes sign-off (Req 10.6)."""
        case_id = uuid4()

        result = await notification_service.send_sign_off_complete(
            case_id=case_id,
            user_email="user@company.com",
            vendor_name="Acme Corp",
        )

        assert result.notification_type == NotificationType.SIGN_OFF_COMPLETE.value
        assert result.recipient_email == "user@company.com"
        assert result.context_data["vendor_name"] == "Acme Corp"


# ─── Escalation Tests ─────────────────────────────────────────────────────────


class TestEscalation:
    """Tests for escalation logic."""

    async def test_escalate_sends_to_manager(
        self,
        notification_service: NotificationService,
        mock_notification_repo: AsyncMock,
    ):
        """Should send escalation to manager (Req 10.3)."""
        case_id = uuid4()
        mock_notification_repo.count_reminders_for_case.return_value = 5

        result = await notification_service.escalate(
            case_id=case_id,
            manager_email="manager@company.com",
        )

        assert result.notification_type == NotificationType.ESCALATION.value
        assert result.recipient_email == "manager@company.com"
        assert result.context_data["reminder_count"] == 5

    async def test_escalate_resolves_manager_email_if_not_provided(
        self,
        notification_service: NotificationService,
        mock_notification_repo: AsyncMock,
    ):
        """Should resolve manager email when not provided."""
        case_id = uuid4()
        mock_notification_repo.count_reminders_for_case.return_value = 3

        result = await notification_service.escalate(case_id=case_id)

        # Falls back to placeholder
        assert result.recipient_email == "manager@example.com"
        assert result.notification_type == NotificationType.ESCALATION.value


# ─── Reminder Scheduling Tests ────────────────────────────────────────────────


class TestReminderScheduling:
    """Tests for reminder scheduling."""

    async def test_schedule_reminders_with_defaults(
        self,
        notification_service: NotificationService,
    ):
        """Should schedule with default intervals (3, 7, 14 days) (Req 10.2)."""
        case_id = uuid4()

        schedule = await notification_service.schedule_reminders(case_id=case_id)

        assert schedule.case_id == case_id
        assert schedule.intervals_days == DEFAULT_REMINDER_INTERVALS_DAYS
        assert schedule.max_reminders == DEFAULT_MAX_REMINDERS
        assert schedule.next_reminder_index == 0
        assert schedule.next_reminder_date is not None

    async def test_schedule_reminders_with_custom_intervals(
        self,
        notification_service: NotificationService,
    ):
        """Should schedule with custom intervals."""
        case_id = uuid4()
        custom_intervals = [2, 5, 10]

        schedule = await notification_service.schedule_reminders(
            case_id=case_id,
            intervals=custom_intervals,
        )

        assert schedule.intervals_days == custom_intervals

    async def test_schedule_reminders_from_settings(
        self,
        notification_service: NotificationService,
        mock_setting_repo: AsyncMock,
    ):
        """Should load intervals from settings when company_code provided."""
        case_id = uuid4()
        mock_setting_repo.get_by_key.return_value = FakeSetting(
            key="reminder_intervals_days", value="5,10,20"
        )

        schedule = await notification_service.schedule_reminders(
            case_id=case_id,
            company_code="1000",
        )

        assert schedule.intervals_days == [5, 10, 20]

    async def test_get_next_reminder_date_first_reminder(
        self,
        notification_service: NotificationService,
        mock_notification_repo: AsyncMock,
    ):
        """Should return date for first reminder interval."""
        case_id = uuid4()
        mock_notification_repo.count_reminders_for_case.return_value = 0

        next_date = await notification_service.get_next_reminder_date(case_id)

        assert next_date is not None
        # Should be approximately 3 days from now (default first interval)
        expected_delta = timedelta(days=DEFAULT_REMINDER_INTERVALS_DAYS[0])
        now = datetime.now(timezone.utc)
        assert abs((next_date - now) - expected_delta) < timedelta(seconds=5)

    async def test_get_next_reminder_date_max_exceeded(
        self,
        notification_service: NotificationService,
        mock_notification_repo: AsyncMock,
    ):
        """Should return None when max reminders exceeded."""
        case_id = uuid4()
        mock_notification_repo.count_reminders_for_case.return_value = (
            DEFAULT_MAX_REMINDERS
        )

        next_date = await notification_service.get_next_reminder_date(case_id)

        assert next_date is None


# ─── Retry Tests ──────────────────────────────────────────────────────────────


class TestRetryLogic:
    """Tests for retry with exponential backoff."""

    async def test_retry_success_on_second_attempt(
        self,
        notification_service: NotificationService,
        mock_notification_repo: AsyncMock,
    ):
        """Should retry and succeed (Req 10.9)."""
        notification_id = uuid4()
        case_id = uuid4()
        mock_notification_repo.get_by_id.return_value = FakeNotification(
            id=notification_id,
            case_id=case_id,
            status="retrying",
            retry_count=1,
            type="invitation",
            template_code="vlr_invitation",
            recipient_email="vendor@test.com",
        )

        result = await notification_service.retry_failed_notification(
            notification_id
        )

        assert result.status == NotificationStatus.SENT.value
        assert result.retry_count == 2
        mock_notification_repo.update.assert_called_once()

    async def test_retry_failure_schedules_next_retry(
        self,
        notification_service_failing_email: NotificationService,
        mock_notification_repo: AsyncMock,
    ):
        """Should schedule next retry on failure with backoff."""
        notification_id = uuid4()
        case_id = uuid4()
        mock_notification_repo.get_by_id.return_value = FakeNotification(
            id=notification_id,
            case_id=case_id,
            status="retrying",
            retry_count=0,
            type="invitation",
            template_code="vlr_invitation",
            recipient_email="vendor@test.com",
        )

        result = await notification_service_failing_email.retry_failed_notification(
            notification_id
        )

        assert result.status == NotificationStatus.RETRYING.value
        assert result.retry_count == 1
        assert result.next_retry_date is not None

    async def test_retry_exceeds_max_marks_failed(
        self,
        notification_service_failing_email: NotificationService,
        mock_notification_repo: AsyncMock,
    ):
        """Should mark as failed when max retries reached (Req 10.9)."""
        notification_id = uuid4()
        case_id = uuid4()
        mock_notification_repo.get_by_id.return_value = FakeNotification(
            id=notification_id,
            case_id=case_id,
            status="retrying",
            retry_count=2,  # Already retried twice, this is the 3rd attempt
            type="invitation",
            template_code="vlr_invitation",
            recipient_email="vendor@test.com",
        )

        result = await notification_service_failing_email.retry_failed_notification(
            notification_id
        )

        assert result.status == NotificationStatus.FAILED.value
        assert result.retry_count == 3

    async def test_retry_raises_when_max_already_exceeded(
        self,
        notification_service: NotificationService,
        mock_notification_repo: AsyncMock,
    ):
        """Should raise ValueError when retries already exceeded."""
        notification_id = uuid4()
        mock_notification_repo.get_by_id.return_value = FakeNotification(
            id=notification_id,
            retry_count=MAX_RETRY_ATTEMPTS,
        )

        with pytest.raises(ValueError, match="exceeded maximum"):
            await notification_service.retry_failed_notification(notification_id)

    async def test_retry_raises_when_notification_not_found(
        self,
        notification_service: NotificationService,
        mock_notification_repo: AsyncMock,
    ):
        """Should raise ValueError when notification does not exist."""
        mock_notification_repo.get_by_id.return_value = None

        with pytest.raises(ValueError, match="not found"):
            await notification_service.retry_failed_notification(uuid4())


# ─── Exponential Backoff Calculation Tests ────────────────────────────────────


class TestBackoffCalculation:
    """Tests for retry backoff calculation."""

    def test_first_retry_backoff_30s(self):
        """First retry should be 30 seconds (Req 10.9)."""
        now = datetime.now(timezone.utc)
        result = NotificationService._calculate_next_retry_date(0)

        assert result is not None
        delta = (result - now).total_seconds()
        assert 28 <= delta <= 32  # Allow small timing variance

    def test_second_retry_backoff_120s(self):
        """Second retry should be 120 seconds (Req 10.9)."""
        now = datetime.now(timezone.utc)
        result = NotificationService._calculate_next_retry_date(1)

        assert result is not None
        delta = (result - now).total_seconds()
        assert 118 <= delta <= 122

    def test_third_retry_backoff_480s(self):
        """Third retry should be 480 seconds (Req 10.9)."""
        now = datetime.now(timezone.utc)
        result = NotificationService._calculate_next_retry_date(2)

        assert result is not None
        delta = (result - now).total_seconds()
        assert 478 <= delta <= 482

    def test_max_retries_returns_none(self):
        """Should return None when max retries exceeded."""
        result = NotificationService._calculate_next_retry_date(
            MAX_RETRY_ATTEMPTS
        )
        assert result is None


# ─── Notification History Tests ───────────────────────────────────────────────


class TestNotificationHistory:
    """Tests for notification history retrieval."""

    async def test_get_notification_history_returns_records(
        self,
        notification_service: NotificationService,
        mock_notification_repo: AsyncMock,
    ):
        """Should return all notifications for a case (Req 10.10)."""
        case_id = uuid4()
        notifications = [
            FakeNotification(case_id=case_id, type="invitation"),
            FakeNotification(case_id=case_id, type="reminder"),
        ]
        mock_notification_repo.list_by_case.return_value = PaginatedResult(
            items=notifications, total=2, page=1, page_size=50
        )

        history = await notification_service.get_notification_history(case_id)

        assert len(history) == 2

    async def test_get_notification_history_empty(
        self,
        notification_service: NotificationService,
        mock_notification_repo: AsyncMock,
    ):
        """Should return empty list when no history exists."""
        mock_notification_repo.list_by_case.return_value = PaginatedResult(
            items=[], total=0, page=1, page_size=50
        )

        history = await notification_service.get_notification_history(uuid4())
        assert history == []


# ─── Process Pending Retries Tests ────────────────────────────────────────────


class TestProcessPendingRetries:
    """Tests for batch retry processing."""

    async def test_process_pending_retries_empty(
        self,
        notification_service: NotificationService,
        mock_notification_repo: AsyncMock,
    ):
        """Should handle no pending retries gracefully."""
        mock_notification_repo.get_pending_retries.return_value = []

        results = await notification_service.process_pending_retries()

        assert results == []

    async def test_process_pending_retries_batch(
        self,
        notification_service: NotificationService,
        mock_notification_repo: AsyncMock,
    ):
        """Should process multiple pending retries."""
        notif_1 = FakeNotification(
            id=uuid4(), retry_count=1, type="invitation",
            template_code="vlr_invitation",
        )
        notif_2 = FakeNotification(
            id=uuid4(), retry_count=0, type="reminder",
            template_code="vlr_reminder",
        )
        mock_notification_repo.get_pending_retries.return_value = [
            notif_1, notif_2
        ]
        # Return the notification when get_by_id is called
        mock_notification_repo.get_by_id.side_effect = [notif_1, notif_2]

        results = await notification_service.process_pending_retries()

        assert len(results) == 2


# ─── Template Rendering Tests ─────────────────────────────────────────────────


class TestTemplateRendering:
    """Tests for email template rendering."""

    def test_render_template_includes_context_data(
        self,
        notification_service: NotificationService,
    ):
        """Should render template with context data (Req 10.8)."""
        context = {"vendor_name": "Acme Corp", "portal_url": "https://test.com"}

        result = notification_service._render_template("vlr_invitation", context)

        assert "Acme Corp" in result
        assert "https://test.com" in result
        assert "<html>" in result

    def test_render_template_handles_empty_context(
        self,
        notification_service: NotificationService,
    ):
        """Should render template with empty context."""
        result = notification_service._render_template("vlr_reminder", {})

        assert "<html>" in result
        assert "Vlr Reminder" in result


# ─── Settings Loading Tests ───────────────────────────────────────────────────


class TestSettingsLoading:
    """Tests for loading configuration from settings."""

    async def test_load_reminder_intervals_default(
        self,
        notification_service: NotificationService,
    ):
        """Should return defaults when no company_code."""
        intervals = await notification_service._load_reminder_intervals(None)
        assert intervals == DEFAULT_REMINDER_INTERVALS_DAYS

    async def test_load_reminder_intervals_from_settings(
        self,
        notification_service: NotificationService,
        mock_setting_repo: AsyncMock,
    ):
        """Should parse intervals from settings."""
        mock_setting_repo.get_by_key.return_value = FakeSetting(
            key="reminder_intervals_days", value="2,5,10"
        )

        intervals = await notification_service._load_reminder_intervals("1000")
        assert intervals == [2, 5, 10]

    async def test_load_max_reminders_default(
        self,
        notification_service: NotificationService,
    ):
        """Should return default max reminders when no company_code."""
        max_rem = await notification_service._load_max_reminders(None)
        assert max_rem == DEFAULT_MAX_REMINDERS

    async def test_load_max_reminders_from_settings(
        self,
        notification_service: NotificationService,
        mock_setting_repo: AsyncMock,
    ):
        """Should load max reminders from settings."""
        mock_setting_repo.get_by_key.return_value = FakeSetting(
            key="max_reminders", value="5"
        )

        max_rem = await notification_service._load_max_reminders("1000")
        assert max_rem == 5

    async def test_load_settings_fallback_on_error(
        self,
        notification_service: NotificationService,
        mock_setting_repo: AsyncMock,
    ):
        """Should fall back to defaults on setting retrieval error."""
        mock_setting_repo.get_by_key.side_effect = Exception("DB error")

        intervals = await notification_service._load_reminder_intervals("1000")
        assert intervals == DEFAULT_REMINDER_INTERVALS_DAYS

        max_rem = await notification_service._load_max_reminders("1000")
        assert max_rem == DEFAULT_MAX_REMINDERS
