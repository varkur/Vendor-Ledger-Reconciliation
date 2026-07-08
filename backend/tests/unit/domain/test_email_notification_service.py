"""
Unit tests for EmailNotificationService - enhanced notification service
with Jinja2 templates, BRD D3/D7/D10 reminder scheduling, and Celery dispatch.

Tests cover:
- Vendor invite sending with unique portal link
- Scheduled reminders at D3/D7/D10 intervals
- Escalation when all reminders exhausted
- Approval request notifications
- Upload confirmation notifications
- BRDReminderSchedule logic
- Template rendering with Jinja2
- Reminder action determination
"""

import pytest
import tempfile
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

from src.domain.services.vlr.notification_service import (
    BRD_MAX_REMINDERS,
    BRD_REMINDER_INTERVALS_DAYS,
    BRDReminderSchedule,
    EmailNotificationService,
    NotificationStatus,
    NotificationType,
)


# ─── Test Helpers ─────────────────────────────────────────────────────────────


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
    repo.create = AsyncMock()
    repo.update = AsyncMock()
    repo.count_reminders_for_case = AsyncMock(return_value=0)
    return repo


@pytest.fixture
def mock_case_repo() -> AsyncMock:
    """Create a mock case repository."""
    return AsyncMock()


@pytest.fixture
def mock_setting_repo() -> AsyncMock:
    """Create a mock setting repository."""
    return AsyncMock()


@pytest.fixture
def fake_email_sender() -> FakeEmailSender:
    """Create a fake email sender that succeeds."""
    return FakeEmailSender(should_succeed=True)


@pytest.fixture
def templates_dir(tmp_path: Path) -> Path:
    """Create temporary templates directory with test templates."""
    # Create minimal Jinja2 templates for testing
    templates = {
        "vendor_invite.html": (
            "<html><body><p>Dear {{ vendor_name }},</p>"
            "<a href=\"{{ portal_url }}\">Upload</a>"
            "<p>Case: {{ case_id }}</p></body></html>"
        ),
        "reminder_d3.html": (
            "<html><body><p>Dear {{ vendor_name }},</p>"
            "<p>Day 3 reminder</p>"
            "<a href=\"{{ portal_url }}\">Upload</a>"
            "<p>Case: {{ case_id }}</p></body></html>"
        ),
        "reminder_d7.html": (
            "<html><body><p>Dear {{ vendor_name }},</p>"
            "<p>Day 7 reminder</p>"
            "<a href=\"{{ portal_url }}\">Upload</a>"
            "<p>Case: {{ case_id }}</p></body></html>"
        ),
        "reminder_d10.html": (
            "<html><body><p>Dear {{ vendor_name }},</p>"
            "<p>Day 10 FINAL reminder</p>"
            "<a href=\"{{ portal_url }}\">Upload</a>"
            "<p>Case: {{ case_id }}</p></body></html>"
        ),
        "escalation.html": (
            "<html><body><p>Dear {{ manager_name }},</p>"
            "<p>Escalation for case {{ case_id }}</p>"
            "<p>Vendor: {{ vendor_name }}</p>"
            "<a href=\"{{ case_url }}\">View Case</a></body></html>"
        ),
        "approval_request.html": (
            "<html><body><p>Dear {{ approver_name }},</p>"
            "<p>Approval needed for case {{ case_id }}</p>"
            "<a href=\"{{ case_url }}\">Review</a></body></html>"
        ),
        "upload_confirmation.html": (
            "<html><body><p>Dear {{ user_name }},</p>"
            "<p>{{ vendor_name }} uploaded statement</p>"
            "<a href=\"{{ case_url }}\">View Case</a></body></html>"
        ),
    }
    for name, content in templates.items():
        (tmp_path / name).write_text(content)
    return tmp_path


@pytest.fixture
def email_service(
    mock_notification_repo: AsyncMock,
    mock_case_repo: AsyncMock,
    mock_setting_repo: AsyncMock,
    fake_email_sender: FakeEmailSender,
    templates_dir: Path,
) -> EmailNotificationService:
    """Create EmailNotificationService with mocked deps and test templates."""
    service = EmailNotificationService(
        notification_repository=mock_notification_repo,
        case_repository=mock_case_repo,
        setting_repository=mock_setting_repo,
        email_sender=fake_email_sender,
        templates_dir=templates_dir,
        base_url="http://localhost:3000",
    )
    # Mock the Celery dispatch to avoid import issues in tests
    service._dispatch_email_task = AsyncMock()
    return service


# ─── BRDReminderSchedule Tests ───────────────────────────────────────────────


class TestBRDReminderSchedule:
    """Tests for BRDReminderSchedule dataclass."""

    def test_default_intervals(self):
        """Should have D3, D7, D10 intervals."""
        schedule = BRDReminderSchedule()
        assert schedule.INTERVALS_DAYS == [3, 7, 10]

    def test_max_reminders_is_three(self):
        """Should have max 3 reminders."""
        schedule = BRDReminderSchedule()
        assert schedule.MAX_REMINDERS == 3

    def test_get_interval_days_valid(self):
        """Should return correct interval for each reminder."""
        schedule = BRDReminderSchedule()
        assert schedule.get_interval_days(1) == 3
        assert schedule.get_interval_days(2) == 7
        assert schedule.get_interval_days(3) == 10

    def test_get_interval_days_invalid(self):
        """Should return None for out-of-range reminder number."""
        schedule = BRDReminderSchedule()
        assert schedule.get_interval_days(0) is None
        assert schedule.get_interval_days(4) is None
        assert schedule.get_interval_days(-1) is None

    def test_get_template_name(self):
        """Should return correct template for each reminder."""
        schedule = BRDReminderSchedule()
        assert schedule.get_template_name(1) == "reminder_d3.html"
        assert schedule.get_template_name(2) == "reminder_d7.html"
        assert schedule.get_template_name(3) == "reminder_d10.html"
        assert schedule.get_template_name(4) is None

    def test_is_exhausted(self):
        """Should be exhausted when all reminders sent."""
        schedule = BRDReminderSchedule()
        assert schedule.is_exhausted(0) is False
        assert schedule.is_exhausted(1) is False
        assert schedule.is_exhausted(2) is False
        assert schedule.is_exhausted(3) is True
        assert schedule.is_exhausted(5) is True

    def test_get_next_reminder_number(self):
        """Should return the next reminder number based on sent count."""
        schedule = BRDReminderSchedule()
        assert schedule.get_next_reminder_number(0) == 1
        assert schedule.get_next_reminder_number(1) == 2
        assert schedule.get_next_reminder_number(2) == 3
        assert schedule.get_next_reminder_number(3) is None


# ─── Send Vendor Invite Tests ─────────────────────────────────────────────────


class TestSendVendorInvite:
    """Tests for send_vendor_invite method."""

    async def test_sends_invite_with_portal_link(
        self,
        email_service: EmailNotificationService,
        mock_notification_repo: AsyncMock,
    ):
        """Should send invite with unique portal URL (Req 14.1)."""
        case_id = uuid4()
        token = "unique-token-abc123"

        result = await email_service.send_vendor_invite(
            case_id=case_id,
            vendor_email="vendor@test.com",
            vendor_name="Acme Corp",
            portal_token=token,
        )

        assert result.notification_type == NotificationType.VENDOR_INVITE.value
        assert result.recipient_email == "vendor@test.com"
        assert result.status == NotificationStatus.PENDING.value
        assert result.context_data is not None
        assert token in result.context_data["portal_url"]

    async def test_persists_notification_record(
        self,
        email_service: EmailNotificationService,
        mock_notification_repo: AsyncMock,
    ):
        """Should persist notification in database (Req 14.1)."""
        case_id = uuid4()

        await email_service.send_vendor_invite(
            case_id=case_id,
            vendor_email="vendor@test.com",
            vendor_name="Acme Corp",
            portal_token="token123",
        )

        mock_notification_repo.create.assert_called_once()
        call_args = mock_notification_repo.create.call_args[0][0]
        assert call_args["type"] == NotificationType.VENDOR_INVITE.value
        assert call_args["recipient_email"] == "vendor@test.com"

    async def test_generates_unique_portal_url(
        self,
        email_service: EmailNotificationService,
    ):
        """Should generate portal URL with token (Req 14.1)."""
        case_id = uuid4()
        token = "my-unique-token"

        result = await email_service.send_vendor_invite(
            case_id=case_id,
            vendor_email="v@test.com",
            vendor_name="Test",
            portal_token=token,
        )

        expected_url = f"http://localhost:3000/portal/access/{token}"
        assert result.context_data["portal_url"] == expected_url


# ─── Send Scheduled Reminder Tests ────────────────────────────────────────────


class TestSendScheduledReminder:
    """Tests for send_scheduled_reminder method (D3/D7/D10)."""

    async def test_send_d3_reminder(
        self,
        email_service: EmailNotificationService,
        mock_notification_repo: AsyncMock,
    ):
        """Should send D3 reminder (Req 15.1)."""
        case_id = uuid4()

        result = await email_service.send_scheduled_reminder(
            case_id=case_id,
            reminder_number=1,
            vendor_email="vendor@test.com",
            vendor_name="Acme Corp",
            portal_token="token-abc",
        )

        assert result.notification_type == NotificationType.REMINDER_D3.value
        assert result.template_code == "reminder_d3.html"
        assert result.status == NotificationStatus.PENDING.value

    async def test_send_d7_reminder(
        self,
        email_service: EmailNotificationService,
        mock_notification_repo: AsyncMock,
    ):
        """Should send D7 reminder (Req 15.2)."""
        case_id = uuid4()

        result = await email_service.send_scheduled_reminder(
            case_id=case_id,
            reminder_number=2,
            vendor_email="vendor@test.com",
            vendor_name="Acme Corp",
            portal_token="token-abc",
        )

        assert result.notification_type == NotificationType.REMINDER_D7.value
        assert result.template_code == "reminder_d7.html"

    async def test_send_d10_reminder(
        self,
        email_service: EmailNotificationService,
        mock_notification_repo: AsyncMock,
    ):
        """Should send D10 final reminder (Req 15.3)."""
        case_id = uuid4()

        result = await email_service.send_scheduled_reminder(
            case_id=case_id,
            reminder_number=3,
            vendor_email="vendor@test.com",
            vendor_name="Acme Corp",
            portal_token="token-abc",
        )

        assert result.notification_type == NotificationType.REMINDER_D10.value
        assert result.template_code == "reminder_d10.html"

    async def test_invalid_reminder_number_raises(
        self,
        email_service: EmailNotificationService,
    ):
        """Should raise ValueError for invalid reminder number."""
        with pytest.raises(ValueError, match="Invalid reminder number"):
            await email_service.send_scheduled_reminder(
                case_id=uuid4(),
                reminder_number=4,
                vendor_email="v@test.com",
                vendor_name="Test",
                portal_token="t",
            )

    async def test_zero_reminder_number_raises(
        self,
        email_service: EmailNotificationService,
    ):
        """Should raise ValueError for reminder number 0."""
        with pytest.raises(ValueError, match="Invalid reminder number"):
            await email_service.send_scheduled_reminder(
                case_id=uuid4(),
                reminder_number=0,
                vendor_email="v@test.com",
                vendor_name="Test",
                portal_token="t",
            )

    async def test_reminder_includes_portal_link(
        self,
        email_service: EmailNotificationService,
    ):
        """Should include portal URL in all reminder emails."""
        case_id = uuid4()
        token = "portal-token-xyz"

        result = await email_service.send_scheduled_reminder(
            case_id=case_id,
            reminder_number=1,
            vendor_email="v@test.com",
            vendor_name="Test",
            portal_token=token,
        )

        assert token in result.context_data["portal_url"]

    async def test_reminder_includes_case_id(
        self,
        email_service: EmailNotificationService,
    ):
        """Should include case ID in context."""
        case_id = uuid4()

        result = await email_service.send_scheduled_reminder(
            case_id=case_id,
            reminder_number=2,
            vendor_email="v@test.com",
            vendor_name="Test",
            portal_token="t",
        )

        assert result.context_data["case_id"] == str(case_id)


# ─── Send Escalation Tests ────────────────────────────────────────────────────


class TestSendEscalation:
    """Tests for send_escalation method."""

    async def test_sends_escalation_to_manager(
        self,
        email_service: EmailNotificationService,
        mock_notification_repo: AsyncMock,
    ):
        """Should send escalation after all reminders exhausted (Req 15.4)."""
        case_id = uuid4()

        result = await email_service.send_escalation(
            case_id=case_id,
            manager_email="manager@company.com",
            manager_name="John Doe",
            vendor_name="Non-Responsive Vendor",
            reminder_count=3,
            days_since_invite=12,
        )

        assert result.notification_type == NotificationType.ESCALATION.value
        assert result.recipient_email == "manager@company.com"
        assert result.template_code == "escalation.html"
        assert result.status == NotificationStatus.PENDING.value

    async def test_escalation_includes_case_link(
        self,
        email_service: EmailNotificationService,
    ):
        """Should include case URL in escalation (Req 16.3)."""
        case_id = uuid4()

        result = await email_service.send_escalation(
            case_id=case_id,
            manager_email="mgr@test.com",
            vendor_name="Acme",
        )

        assert str(case_id) in result.context_data["case_url"]

    async def test_escalation_includes_reminder_count(
        self,
        email_service: EmailNotificationService,
    ):
        """Should include reminder count in context."""
        case_id = uuid4()

        result = await email_service.send_escalation(
            case_id=case_id,
            manager_email="mgr@test.com",
            reminder_count=3,
            days_since_invite=15,
        )

        assert result.context_data["reminder_count"] == 3
        assert result.context_data["days_since_invite"] == 15


# ─── Send Approval Request Tests ──────────────────────────────────────────────


class TestSendApprovalRequest:
    """Tests for send_approval_request method."""

    async def test_sends_approval_request(
        self,
        email_service: EmailNotificationService,
        mock_notification_repo: AsyncMock,
    ):
        """Should send approval request to finance user (Req 16.1)."""
        case_id = uuid4()

        result = await email_service.send_approval_request(
            case_id=case_id,
            approver_email="finance@company.com",
            approver_name="Jane Smith",
            vendor_name="Supplier Inc",
        )

        assert result.notification_type == NotificationType.APPROVAL_REQUEST.value
        assert result.recipient_email == "finance@company.com"
        assert result.template_code == "approval_request.html"
        assert result.status == NotificationStatus.PENDING.value

    async def test_approval_includes_case_link(
        self,
        email_service: EmailNotificationService,
    ):
        """Should include case URL in approval request (Req 16.3)."""
        case_id = uuid4()

        result = await email_service.send_approval_request(
            case_id=case_id,
            approver_email="fin@test.com",
        )

        assert str(case_id) in result.context_data["case_url"]


# ─── Send Upload Confirmation Tests ───────────────────────────────────────────


class TestSendUploadConfirmation:
    """Tests for send_upload_confirmation method."""

    async def test_sends_upload_confirmation(
        self,
        email_service: EmailNotificationService,
        mock_notification_repo: AsyncMock,
    ):
        """Should send upload confirmation to finance user (Req 16.2)."""
        case_id = uuid4()

        result = await email_service.send_upload_confirmation(
            case_id=case_id,
            user_email="finance@company.com",
            user_name="Jane Smith",
            vendor_name="Acme Corp",
        )

        assert result.notification_type == NotificationType.UPLOAD_CONFIRMATION.value
        assert result.recipient_email == "finance@company.com"
        assert result.template_code == "upload_confirmation.html"

    async def test_upload_confirmation_includes_case_link(
        self,
        email_service: EmailNotificationService,
    ):
        """Should include case URL (Req 16.3)."""
        case_id = uuid4()

        result = await email_service.send_upload_confirmation(
            case_id=case_id,
            user_email="user@test.com",
            vendor_name="Vendor X",
        )

        assert str(case_id) in result.context_data["case_url"]


# ─── Determine Reminder Action Tests ──────────────────────────────────────────


class TestDetermineReminderAction:
    """Tests for determine_reminder_action method."""

    def test_send_d3_when_3_days_elapsed(
        self,
        email_service: EmailNotificationService,
    ):
        """Should suggest D3 reminder after 3 days (Req 15.1)."""
        invite_date = datetime.now(timezone.utc) - timedelta(days=3)

        action = email_service.determine_reminder_action(
            reminders_sent=0,
            invite_date=invite_date,
        )

        assert action["action"] == "send_reminder"
        assert action["reminder_number"] == 1
        assert action["interval_days"] == 3

    def test_send_d7_when_7_days_elapsed(
        self,
        email_service: EmailNotificationService,
    ):
        """Should suggest D7 reminder after 7 days (Req 15.2)."""
        invite_date = datetime.now(timezone.utc) - timedelta(days=7)

        action = email_service.determine_reminder_action(
            reminders_sent=1,
            invite_date=invite_date,
        )

        assert action["action"] == "send_reminder"
        assert action["reminder_number"] == 2
        assert action["interval_days"] == 7

    def test_send_d10_when_10_days_elapsed(
        self,
        email_service: EmailNotificationService,
    ):
        """Should suggest D10 reminder after 10 days (Req 15.3)."""
        invite_date = datetime.now(timezone.utc) - timedelta(days=10)

        action = email_service.determine_reminder_action(
            reminders_sent=2,
            invite_date=invite_date,
        )

        assert action["action"] == "send_reminder"
        assert action["reminder_number"] == 3
        assert action["interval_days"] == 10

    def test_escalate_when_all_reminders_sent(
        self,
        email_service: EmailNotificationService,
    ):
        """Should escalate after all 3 reminders sent (Req 15.4)."""
        invite_date = datetime.now(timezone.utc) - timedelta(days=12)

        action = email_service.determine_reminder_action(
            reminders_sent=3,
            invite_date=invite_date,
        )

        assert action["action"] == "escalate"

    def test_no_action_when_not_yet_time(
        self,
        email_service: EmailNotificationService,
    ):
        """Should return 'none' when not enough time has elapsed."""
        invite_date = datetime.now(timezone.utc) - timedelta(days=1)

        action = email_service.determine_reminder_action(
            reminders_sent=0,
            invite_date=invite_date,
        )

        assert action["action"] == "none"
        assert "days_remaining" in action

    def test_no_action_for_d7_when_only_4_days(
        self,
        email_service: EmailNotificationService,
    ):
        """Should not send D7 when only 4 days elapsed (needs 7)."""
        invite_date = datetime.now(timezone.utc) - timedelta(days=4)

        action = email_service.determine_reminder_action(
            reminders_sent=1,
            invite_date=invite_date,
        )

        assert action["action"] == "none"


# ─── Jinja2 Template Rendering Tests ─────────────────────────────────────────


class TestJinja2TemplateRendering:
    """Tests for Jinja2 template rendering."""

    def test_renders_vendor_invite_template(
        self,
        email_service: EmailNotificationService,
    ):
        """Should render vendor_invite.html with context variables."""
        html = email_service._render_jinja_template(
            "vendor_invite.html",
            {
                "vendor_name": "Acme Corp",
                "portal_url": "http://example.com/portal/abc",
                "case_id": "case-123",
            },
        )

        assert "Acme Corp" in html
        assert "http://example.com/portal/abc" in html
        assert "case-123" in html

    def test_renders_escalation_template(
        self,
        email_service: EmailNotificationService,
    ):
        """Should render escalation.html with context variables."""
        html = email_service._render_jinja_template(
            "escalation.html",
            {
                "manager_name": "John Manager",
                "case_id": "case-456",
                "vendor_name": "Slow Vendor",
                "case_url": "http://example.com/cases/456",
            },
        )

        assert "John Manager" in html
        assert "case-456" in html
        assert "Slow Vendor" in html
        assert "http://example.com/cases/456" in html

    def test_fallback_rendering_on_missing_template(
        self,
        email_service: EmailNotificationService,
    ):
        """Should use fallback when template doesn't exist."""
        html = email_service._render_jinja_template(
            "nonexistent_template.html",
            {"key": "value"},
        )

        # Fallback renders a simple HTML with key-value pairs
        assert "nonexistent_template.html" in html
        assert "value" in html


# ─── Portal Link Generation Tests ────────────────────────────────────────────


class TestPortalLinkGeneration:
    """Tests for portal and case link generation."""

    def test_generate_portal_link(
        self,
        email_service: EmailNotificationService,
    ):
        """Should generate correct portal URL (Req 14.1)."""
        link = email_service.generate_portal_link("my-token-123")
        assert link == "http://localhost:3000/portal/access/my-token-123"

    def test_generate_case_link(
        self,
        email_service: EmailNotificationService,
    ):
        """Should generate correct case URL (Req 16.3)."""
        case_id = uuid4()
        link = email_service.generate_case_link(case_id)
        assert link == f"http://localhost:3000/vlr/cases/{case_id}"


# ─── Celery Task Dispatch Tests ───────────────────────────────────────────────


class TestCeleryDispatch:
    """Tests for Celery task dispatching (non-blocking email send)."""

    async def test_dispatch_is_called_for_each_send_method(
        self,
        email_service: EmailNotificationService,
        mock_notification_repo: AsyncMock,
    ):
        """Should call _dispatch_email_task for all send methods (Req 14.4)."""
        case_id = uuid4()

        await email_service.send_vendor_invite(
            case_id=case_id,
            vendor_email="vendor@test.com",
            vendor_name="Test Vendor",
            portal_token="test-token",
        )

        # Dispatch should have been called
        email_service._dispatch_email_task.assert_called_once()

    async def test_all_methods_persist_notification(
        self,
        email_service: EmailNotificationService,
        mock_notification_repo: AsyncMock,
    ):
        """All send methods should persist a notification record."""
        case_id = uuid4()

        await email_service.send_vendor_invite(
            case_id=case_id,
            vendor_email="v@t.com",
            vendor_name="V",
            portal_token="p",
        )
        await email_service.send_scheduled_reminder(
            case_id=case_id,
            reminder_number=1,
            vendor_email="v@t.com",
            vendor_name="V",
            portal_token="p",
        )
        await email_service.send_escalation(
            case_id=case_id,
            manager_email="m@t.com",
        )
        await email_service.send_approval_request(
            case_id=case_id,
            approver_email="a@t.com",
        )
        await email_service.send_upload_confirmation(
            case_id=case_id,
            user_email="u@t.com",
        )

        # All 5 should have created notification records
        assert mock_notification_repo.create.call_count == 5
