"""
Unit tests for RecoveryService domain logic.

Tests recovery item creation, status transitions, overdue detection,
follow-up reminder triggering, and follow-up log management.
"""

import pytest
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

from src.domain.services.vlr.recovery_service import (
    FollowUpAction,
    RecoveryItemCreate,
    RecoveryService,
    RecoveryStatus,
    VALID_STATUS_TRANSITIONS,
)


# ─── Test Helpers ─────────────────────────────────────────────────────────────


@dataclass
class FakeRecoveryItem:
    """Fake recovery item object for testing."""

    id: UUID = field(default_factory=uuid4)
    case_id: UUID = field(default_factory=uuid4)
    vendor_id: UUID = field(default_factory=uuid4)
    amount: Decimal = Decimal("10000.00")
    currency: str = "INR"
    status: str = "open"
    identified_date: date = field(default_factory=date.today)
    next_follow_up_date: date | None = None
    follow_up_interval_days: int = 7
    notes: str | None = None


@dataclass
class FakeFollowUp:
    """Fake follow-up object for testing."""

    id: UUID = field(default_factory=uuid4)
    recovery_item_id: UUID = field(default_factory=uuid4)
    action_taken: str = "Called vendor"
    action_by: str = "user@example.com"
    action_date: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    next_follow_up_date: date | None = None


# ─── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_recovery_repo() -> AsyncMock:
    """Create a mock recovery repository."""
    repo = AsyncMock()
    repo.create = AsyncMock(return_value=FakeRecoveryItem())
    repo.get_by_id = AsyncMock(return_value=None)
    repo.update = AsyncMock(return_value=FakeRecoveryItem())
    repo.list_items = AsyncMock(return_value=None)
    repo.list_overdue = AsyncMock(return_value=[])
    repo.add_follow_up = AsyncMock(return_value=FakeFollowUp())
    repo.get_follow_ups = AsyncMock(return_value=[])
    return repo


@pytest.fixture
def recovery_service(mock_recovery_repo: AsyncMock) -> RecoveryService:
    """Create RecoveryService with mocked repository."""
    return RecoveryService(recovery_repository=mock_recovery_repo)


# ─── Creation Tests ───────────────────────────────────────────────────────────


class TestCreateRecoveryItem:
    """Tests for recovery item creation."""

    async def test_create_item_with_defaults(
        self,
        recovery_service: RecoveryService,
        mock_recovery_repo: AsyncMock,
    ):
        """Should create a recovery item with default values."""
        case_id = uuid4()
        vendor_id = uuid4()
        data = RecoveryItemCreate(
            case_id=case_id,
            vendor_id=vendor_id,
            amount=Decimal("5000.00"),
        )

        await recovery_service.create_recovery_item(data)

        mock_recovery_repo.create.assert_called_once()
        call_args = mock_recovery_repo.create.call_args[0][0]
        assert call_args["case_id"] == case_id
        assert call_args["vendor_id"] == vendor_id
        assert call_args["amount"] == Decimal("5000.00")
        assert call_args["currency"] == "INR"
        assert call_args["status"] == "open"
        assert call_args["follow_up_interval_days"] == 7
        assert call_args["identified_date"] == date.today()
        assert call_args["next_follow_up_date"] == date.today() + timedelta(days=7)

    async def test_create_item_with_custom_values(
        self,
        recovery_service: RecoveryService,
        mock_recovery_repo: AsyncMock,
    ):
        """Should create a recovery item with custom currency and interval."""
        identified = date(2024, 6, 1)
        data = RecoveryItemCreate(
            case_id=uuid4(),
            vendor_id=uuid4(),
            amount=Decimal("25000.00"),
            currency="USD",
            identified_date=identified,
            follow_up_interval_days=14,
            notes="High priority recovery",
        )

        await recovery_service.create_recovery_item(data)

        call_args = mock_recovery_repo.create.call_args[0][0]
        assert call_args["currency"] == "USD"
        assert call_args["identified_date"] == identified
        assert call_args["follow_up_interval_days"] == 14
        assert call_args["next_follow_up_date"] == date(2024, 6, 15)
        assert call_args["notes"] == "High priority recovery"

    async def test_create_item_returns_created_model(
        self,
        recovery_service: RecoveryService,
        mock_recovery_repo: AsyncMock,
    ):
        """Should return the created model from the repository."""
        expected_item = FakeRecoveryItem(amount=Decimal("9999.99"))
        mock_recovery_repo.create.return_value = expected_item

        data = RecoveryItemCreate(
            case_id=uuid4(),
            vendor_id=uuid4(),
            amount=Decimal("9999.99"),
        )
        result = await recovery_service.create_recovery_item(data)

        assert result == expected_item


# ─── Status Update Tests ──────────────────────────────────────────────────────


class TestUpdateStatus:
    """Tests for recovery item status transitions."""

    async def test_open_to_in_progress(
        self,
        recovery_service: RecoveryService,
        mock_recovery_repo: AsyncMock,
    ):
        """Should allow transition from open to in_progress."""
        item = FakeRecoveryItem(status="open")
        mock_recovery_repo.get_by_id.return_value = item
        mock_recovery_repo.update.return_value = FakeRecoveryItem(
            status="in_progress", next_follow_up_date=date.today() + timedelta(days=7)
        )

        await recovery_service.update_status(
            item.id, RecoveryStatus.IN_PROGRESS, action_by="user1"
        )

        mock_recovery_repo.update.assert_called_once()
        update_data = mock_recovery_repo.update.call_args[0][1]
        assert update_data["status"] == "in_progress"

    async def test_open_to_recovered(
        self,
        recovery_service: RecoveryService,
        mock_recovery_repo: AsyncMock,
    ):
        """Should allow direct transition from open to recovered."""
        item = FakeRecoveryItem(status="open")
        mock_recovery_repo.get_by_id.return_value = item
        mock_recovery_repo.update.return_value = FakeRecoveryItem(
            status="recovered", next_follow_up_date=None
        )

        await recovery_service.update_status(
            item.id, RecoveryStatus.RECOVERED, notes="Payment received"
        )

        update_data = mock_recovery_repo.update.call_args[0][1]
        assert update_data["status"] == "recovered"
        assert update_data["next_follow_up_date"] is None
        assert update_data["notes"] == "Payment received"

    async def test_in_progress_to_written_off(
        self,
        recovery_service: RecoveryService,
        mock_recovery_repo: AsyncMock,
    ):
        """Should allow transition from in_progress to written_off."""
        item = FakeRecoveryItem(status="in_progress")
        mock_recovery_repo.get_by_id.return_value = item
        mock_recovery_repo.update.return_value = FakeRecoveryItem(
            status="written_off", next_follow_up_date=None
        )

        await recovery_service.update_status(
            item.id, RecoveryStatus.WRITTEN_OFF, notes="Vendor bankrupt"
        )

        update_data = mock_recovery_repo.update.call_args[0][1]
        assert update_data["status"] == "written_off"
        assert update_data["next_follow_up_date"] is None

    async def test_invalid_transition_from_recovered(
        self,
        recovery_service: RecoveryService,
        mock_recovery_repo: AsyncMock,
    ):
        """Should reject transition from terminal state recovered."""
        item = FakeRecoveryItem(status="recovered")
        mock_recovery_repo.get_by_id.return_value = item

        with pytest.raises(ValueError, match="Invalid status transition"):
            await recovery_service.update_status(item.id, RecoveryStatus.OPEN)

    async def test_invalid_transition_from_written_off(
        self,
        recovery_service: RecoveryService,
        mock_recovery_repo: AsyncMock,
    ):
        """Should reject transition from terminal state written_off."""
        item = FakeRecoveryItem(status="written_off")
        mock_recovery_repo.get_by_id.return_value = item

        with pytest.raises(ValueError, match="Invalid status transition"):
            await recovery_service.update_status(item.id, RecoveryStatus.IN_PROGRESS)

    async def test_invalid_transition_in_progress_to_open(
        self,
        recovery_service: RecoveryService,
        mock_recovery_repo: AsyncMock,
    ):
        """Should reject transition from in_progress back to open."""
        item = FakeRecoveryItem(status="in_progress")
        mock_recovery_repo.get_by_id.return_value = item

        with pytest.raises(ValueError, match="Invalid status transition"):
            await recovery_service.update_status(item.id, RecoveryStatus.OPEN)

    async def test_update_nonexistent_item(
        self,
        recovery_service: RecoveryService,
        mock_recovery_repo: AsyncMock,
    ):
        """Should raise error for non-existent item."""
        mock_recovery_repo.get_by_id.return_value = None

        with pytest.raises(ValueError, match="not found"):
            await recovery_service.update_status(uuid4(), RecoveryStatus.IN_PROGRESS)

    async def test_status_change_logs_follow_up(
        self,
        recovery_service: RecoveryService,
        mock_recovery_repo: AsyncMock,
    ):
        """Should log a follow-up action when status changes."""
        item = FakeRecoveryItem(status="open")
        mock_recovery_repo.get_by_id.return_value = item
        mock_recovery_repo.update.return_value = FakeRecoveryItem(
            status="in_progress", next_follow_up_date=date.today() + timedelta(days=7)
        )

        await recovery_service.update_status(
            item.id, RecoveryStatus.IN_PROGRESS, notes="Follow-up initiated", action_by="finance1"
        )

        mock_recovery_repo.add_follow_up.assert_called_once()
        follow_up_data = mock_recovery_repo.add_follow_up.call_args[0][1]
        assert "Status changed to in_progress" in follow_up_data["action_taken"]
        assert "Follow-up initiated" in follow_up_data["action_taken"]
        assert follow_up_data["action_by"] == "finance1"


# ─── Overdue Items Tests ──────────────────────────────────────────────────────


class TestGetOverdueItems:
    """Tests for overdue item detection."""

    async def test_get_overdue_items_delegates_to_repo(
        self,
        recovery_service: RecoveryService,
        mock_recovery_repo: AsyncMock,
    ):
        """Should delegate overdue item retrieval to repository."""
        overdue_items = [
            FakeRecoveryItem(next_follow_up_date=date.today() - timedelta(days=3)),
            FakeRecoveryItem(next_follow_up_date=date.today() - timedelta(days=1)),
        ]
        mock_recovery_repo.list_overdue.return_value = overdue_items

        result = await recovery_service.get_overdue_items()

        assert len(result) == 2
        mock_recovery_repo.list_overdue.assert_called_once_with(as_of_date=None)

    async def test_get_overdue_items_with_custom_date(
        self,
        recovery_service: RecoveryService,
        mock_recovery_repo: AsyncMock,
    ):
        """Should pass custom as_of_date to repository."""
        custom_date = date(2024, 6, 15)
        mock_recovery_repo.list_overdue.return_value = []

        await recovery_service.get_overdue_items(as_of_date=custom_date)

        mock_recovery_repo.list_overdue.assert_called_once_with(as_of_date=custom_date)


# ─── Follow-Up Reminder Triggering Tests ──────────────────────────────────────


class TestTriggerFollowUpReminders:
    """Tests for auto-triggering follow-up reminders."""

    async def test_trigger_no_overdue_items(
        self,
        recovery_service: RecoveryService,
        mock_recovery_repo: AsyncMock,
    ):
        """Should return 0 when no items are overdue."""
        mock_recovery_repo.list_overdue.return_value = []

        count = await recovery_service.trigger_follow_up_reminders()

        assert count == 0
        mock_recovery_repo.add_follow_up.assert_not_called()

    async def test_trigger_single_overdue_item(
        self,
        recovery_service: RecoveryService,
        mock_recovery_repo: AsyncMock,
    ):
        """Should trigger reminder for a single overdue item."""
        item = FakeRecoveryItem(
            status="open",
            next_follow_up_date=date.today() - timedelta(days=2),
            follow_up_interval_days=7,
        )
        mock_recovery_repo.list_overdue.return_value = [item]

        count = await recovery_service.trigger_follow_up_reminders()

        assert count == 1
        mock_recovery_repo.add_follow_up.assert_called_once()
        follow_up_data = mock_recovery_repo.add_follow_up.call_args[0][1]
        assert "Auto-triggered" in follow_up_data["action_taken"]
        assert follow_up_data["next_follow_up_date"] == date.today() + timedelta(days=7)

    async def test_trigger_transitions_open_to_in_progress(
        self,
        recovery_service: RecoveryService,
        mock_recovery_repo: AsyncMock,
    ):
        """Should transition open items to in_progress when triggered."""
        item = FakeRecoveryItem(
            status="open",
            next_follow_up_date=date.today() - timedelta(days=1),
            follow_up_interval_days=7,
        )
        mock_recovery_repo.list_overdue.return_value = [item]

        await recovery_service.trigger_follow_up_reminders()

        update_data = mock_recovery_repo.update.call_args[0][1]
        assert update_data["status"] == "in_progress"
        assert update_data["next_follow_up_date"] == date.today() + timedelta(days=7)

    async def test_trigger_keeps_in_progress_status(
        self,
        recovery_service: RecoveryService,
        mock_recovery_repo: AsyncMock,
    ):
        """Should keep in_progress status for items already in that state."""
        item = FakeRecoveryItem(
            status="in_progress",
            next_follow_up_date=date.today() - timedelta(days=1),
            follow_up_interval_days=14,
        )
        mock_recovery_repo.list_overdue.return_value = [item]

        await recovery_service.trigger_follow_up_reminders()

        update_data = mock_recovery_repo.update.call_args[0][1]
        assert "status" not in update_data
        assert update_data["next_follow_up_date"] == date.today() + timedelta(days=14)

    async def test_trigger_multiple_overdue_items(
        self,
        recovery_service: RecoveryService,
        mock_recovery_repo: AsyncMock,
    ):
        """Should trigger reminders for all overdue items."""
        items = [
            FakeRecoveryItem(
                status="open",
                next_follow_up_date=date.today() - timedelta(days=5),
                follow_up_interval_days=7,
            ),
            FakeRecoveryItem(
                status="in_progress",
                next_follow_up_date=date.today() - timedelta(days=2),
                follow_up_interval_days=10,
            ),
            FakeRecoveryItem(
                status="open",
                next_follow_up_date=date.today() - timedelta(days=1),
                follow_up_interval_days=7,
            ),
        ]
        mock_recovery_repo.list_overdue.return_value = items

        count = await recovery_service.trigger_follow_up_reminders()

        assert count == 3
        assert mock_recovery_repo.add_follow_up.call_count == 3
        assert mock_recovery_repo.update.call_count == 3


# ─── Follow-Up Management Tests ──────────────────────────────────────────────


class TestFollowUpManagement:
    """Tests for manual follow-up actions."""

    async def test_add_follow_up_action(
        self,
        recovery_service: RecoveryService,
        mock_recovery_repo: AsyncMock,
    ):
        """Should add a follow-up entry to an existing item."""
        item = FakeRecoveryItem()
        mock_recovery_repo.get_by_id.return_value = item

        action = FollowUpAction(
            action_taken="Called vendor, promised payment by next week",
            action_by="finance_user@company.com",
            next_follow_up_date=date.today() + timedelta(days=7),
        )

        await recovery_service.add_follow_up(item.id, action)

        mock_recovery_repo.add_follow_up.assert_called_once()
        follow_up_data = mock_recovery_repo.add_follow_up.call_args[0][1]
        assert follow_up_data["action_taken"] == "Called vendor, promised payment by next week"
        assert follow_up_data["action_by"] == "finance_user@company.com"
        assert follow_up_data["next_follow_up_date"] == date.today() + timedelta(days=7)

    async def test_add_follow_up_updates_item_next_date(
        self,
        recovery_service: RecoveryService,
        mock_recovery_repo: AsyncMock,
    ):
        """Should update item's next_follow_up_date when provided in action."""
        item = FakeRecoveryItem()
        mock_recovery_repo.get_by_id.return_value = item
        next_date = date.today() + timedelta(days=10)

        action = FollowUpAction(
            action_taken="Sent email reminder",
            action_by="user1",
            next_follow_up_date=next_date,
        )

        await recovery_service.add_follow_up(item.id, action)

        mock_recovery_repo.update.assert_called_once_with(
            item.id, {"next_follow_up_date": next_date}
        )

    async def test_add_follow_up_without_next_date(
        self,
        recovery_service: RecoveryService,
        mock_recovery_repo: AsyncMock,
    ):
        """Should not update item's next_follow_up_date when not provided."""
        item = FakeRecoveryItem()
        mock_recovery_repo.get_by_id.return_value = item

        action = FollowUpAction(
            action_taken="Left voicemail",
            action_by="user1",
        )

        await recovery_service.add_follow_up(item.id, action)

        mock_recovery_repo.update.assert_not_called()

    async def test_add_follow_up_nonexistent_item(
        self,
        recovery_service: RecoveryService,
        mock_recovery_repo: AsyncMock,
    ):
        """Should raise error when adding follow-up to non-existent item."""
        mock_recovery_repo.get_by_id.return_value = None

        action = FollowUpAction(
            action_taken="Attempt",
            action_by="user1",
        )

        with pytest.raises(ValueError, match="not found"):
            await recovery_service.add_follow_up(uuid4(), action)

    async def test_get_follow_ups(
        self,
        recovery_service: RecoveryService,
        mock_recovery_repo: AsyncMock,
    ):
        """Should retrieve follow-ups from repository."""
        item_id = uuid4()
        follow_ups = [
            FakeFollowUp(action_taken="First call"),
            FakeFollowUp(action_taken="Second call"),
        ]
        mock_recovery_repo.get_follow_ups.return_value = follow_ups

        result = await recovery_service.get_follow_ups(item_id)

        assert len(result) == 2
        mock_recovery_repo.get_follow_ups.assert_called_once_with(item_id)


# ─── Status Transition Map Tests ──────────────────────────────────────────────


class TestStatusTransitionMap:
    """Tests for the status transition validation map."""

    def test_open_allows_in_progress_recovered_written_off(self):
        """Open status should allow transitions to in_progress, recovered, written_off."""
        allowed = VALID_STATUS_TRANSITIONS[RecoveryStatus.OPEN]
        assert RecoveryStatus.IN_PROGRESS in allowed
        assert RecoveryStatus.RECOVERED in allowed
        assert RecoveryStatus.WRITTEN_OFF in allowed

    def test_in_progress_allows_recovered_written_off(self):
        """In progress status should allow transitions to recovered and written_off."""
        allowed = VALID_STATUS_TRANSITIONS[RecoveryStatus.IN_PROGRESS]
        assert RecoveryStatus.RECOVERED in allowed
        assert RecoveryStatus.WRITTEN_OFF in allowed
        assert RecoveryStatus.OPEN not in allowed

    def test_recovered_is_terminal(self):
        """Recovered status should have no valid transitions."""
        allowed = VALID_STATUS_TRANSITIONS[RecoveryStatus.RECOVERED]
        assert allowed == []

    def test_written_off_is_terminal(self):
        """Written off status should have no valid transitions."""
        allowed = VALID_STATUS_TRANSITIONS[RecoveryStatus.WRITTEN_OFF]
        assert allowed == []
