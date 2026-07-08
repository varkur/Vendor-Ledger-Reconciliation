"""
Recovery Domain Service.

Manages the recovery register for tracking amounts recoverable from vendors.
Supports:
- Creating recovery items linked to cases and vendors
- Status transitions: Open → In Progress → Recovered/Written Off
- Overdue item detection based on follow-up dates
- Auto-triggering follow-up reminders for overdue items
- Maintaining a follow-up log per item with timestamps

Requirements: 30.1, 30.2, 30.3, 31.1, 31.2, 31.3
"""

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from enum import Enum
from uuid import UUID

from src.domain.repositories.vlr.recovery_repository import IRecoveryRepository, RecoveryFilters
from src.domain.repositories.vlr.vendor_repository import PaginatedResult, PaginationParams


logger = logging.getLogger(__name__)


# ─── Enumerations ─────────────────────────────────────────────────────────────


class RecoveryStatus(str, Enum):
    """Valid statuses for a recovery item."""

    OPEN = "open"
    IN_PROGRESS = "in_progress"
    RECOVERED = "recovered"
    WRITTEN_OFF = "written_off"


# Valid status transitions: from_status -> list of allowed target statuses
VALID_STATUS_TRANSITIONS: dict[RecoveryStatus, list[RecoveryStatus]] = {
    RecoveryStatus.OPEN: [RecoveryStatus.IN_PROGRESS, RecoveryStatus.RECOVERED, RecoveryStatus.WRITTEN_OFF],
    RecoveryStatus.IN_PROGRESS: [RecoveryStatus.RECOVERED, RecoveryStatus.WRITTEN_OFF],
    RecoveryStatus.RECOVERED: [],  # Terminal state
    RecoveryStatus.WRITTEN_OFF: [],  # Terminal state
}


# ─── Data Classes ─────────────────────────────────────────────────────────────


@dataclass
class RecoveryItemCreate:
    """Data required to create a new recovery item."""

    case_id: UUID
    vendor_id: UUID
    amount: Decimal
    currency: str = "INR"
    identified_date: date | None = None
    follow_up_interval_days: int = 7
    notes: str | None = None


@dataclass
class FollowUpAction:
    """Data for recording a follow-up action."""

    action_taken: str
    action_by: str
    action_date: datetime | None = None
    next_follow_up_date: date | None = None


# ─── Service Implementation ───────────────────────────────────────────────────


class RecoveryService:
    """Manages recovery register and follow-up reminders."""

    def __init__(self, recovery_repository: IRecoveryRepository) -> None:
        self._repo = recovery_repository

    async def create_recovery_item(self, data: RecoveryItemCreate) -> object:
        """
        Create a new recovery item in the register.

        Sets initial status to 'open' and schedules the first follow-up
        based on the configured interval.

        Requirements: 30.1, 30.3
        """
        identified = data.identified_date or date.today()
        next_follow_up = identified + timedelta(days=data.follow_up_interval_days)

        item_data = {
            "case_id": data.case_id,
            "vendor_id": data.vendor_id,
            "amount": data.amount,
            "currency": data.currency,
            "status": RecoveryStatus.OPEN.value,
            "identified_date": identified,
            "next_follow_up_date": next_follow_up,
            "follow_up_interval_days": data.follow_up_interval_days,
            "notes": data.notes,
        }

        item = await self._repo.create(item_data)
        logger.info(
            "Created recovery item %s for vendor %s, amount=%s %s",
            item.id,
            data.vendor_id,
            data.amount,
            data.currency,
        )
        return item

    async def update_status(
        self,
        item_id: UUID,
        status: RecoveryStatus,
        notes: str | None = None,
        action_by: str = "system",
    ) -> object:
        """
        Update the status of a recovery item with transition validation.

        Status transitions:
        - Open → In Progress → Recovered/Written Off
        - Open → Recovered/Written Off (direct resolution)

        When moving to a terminal state (recovered/written_off), the
        next_follow_up_date is cleared.

        Requirements: 30.2, 31.3
        """
        item = await self._repo.get_by_id(item_id)
        if item is None:
            raise ValueError(f"Recovery item with id {item_id} not found")

        current_status = RecoveryStatus(item.status)
        if status not in VALID_STATUS_TRANSITIONS[current_status]:
            raise ValueError(
                f"Invalid status transition: {current_status.value} → {status.value}. "
                f"Valid targets: {[s.value for s in VALID_STATUS_TRANSITIONS[current_status]]}"
            )

        update_data: dict = {"status": status.value}

        # Clear follow-up date for terminal states
        if status in (RecoveryStatus.RECOVERED, RecoveryStatus.WRITTEN_OFF):
            update_data["next_follow_up_date"] = None

        if notes is not None:
            update_data["notes"] = notes

        updated_item = await self._repo.update(item_id, update_data)

        # Log the status change as a follow-up action
        follow_up_data = {
            "action_taken": f"Status changed to {status.value}" + (f": {notes}" if notes else ""),
            "action_by": action_by,
            "action_date": datetime.now(timezone.utc),
            "next_follow_up_date": updated_item.next_follow_up_date,
        }
        await self._repo.add_follow_up(item_id, follow_up_data)

        logger.info(
            "Recovery item %s status changed: %s → %s by %s",
            item_id,
            current_status.value,
            status.value,
            action_by,
        )
        return updated_item

    async def get_overdue_items(self, as_of_date: date | None = None) -> list[object]:
        """
        Get recovery items that are past their scheduled follow-up date.

        Only items in 'open' or 'in_progress' status are considered overdue.

        Requirements: 31.1
        """
        return await self._repo.list_overdue(as_of_date=as_of_date)

    async def trigger_follow_up_reminders(self, action_by: str = "system") -> int:
        """
        Auto-trigger follow-up reminders for all overdue recovery items.

        For each overdue item:
        1. Records a follow-up action in the log
        2. Advances the next_follow_up_date by the item's interval
        3. Transitions status from 'open' to 'in_progress' if still open

        Returns the count of reminders triggered.

        Requirements: 31.1, 31.2
        """
        overdue_items = await self._repo.list_overdue()
        triggered_count = 0

        for item in overdue_items:
            # Calculate next follow-up date
            interval_days = item.follow_up_interval_days or 7
            new_follow_up_date = date.today() + timedelta(days=interval_days)

            # Record the follow-up action
            follow_up_data = {
                "action_taken": "Auto-triggered follow-up reminder (overdue)",
                "action_by": action_by,
                "action_date": datetime.now(timezone.utc),
                "next_follow_up_date": new_follow_up_date,
            }
            await self._repo.add_follow_up(item.id, follow_up_data)

            # Update the item's next follow-up date and transition to in_progress if open
            update_data: dict = {"next_follow_up_date": new_follow_up_date}
            if item.status == RecoveryStatus.OPEN.value:
                update_data["status"] = RecoveryStatus.IN_PROGRESS.value

            await self._repo.update(item.id, update_data)
            triggered_count += 1

            logger.info(
                "Triggered follow-up reminder for recovery item %s, next follow-up: %s",
                item.id,
                new_follow_up_date,
            )

        logger.info("Follow-up reminder run complete. Triggered %d reminders.", triggered_count)
        return triggered_count

    async def list_items(
        self,
        filters: RecoveryFilters | None = None,
        pagination: PaginationParams | None = None,
    ) -> PaginatedResult:
        """List recovery items with optional filtering and pagination."""
        return await self._repo.list_items(filters=filters, pagination=pagination)

    async def get_item(self, item_id: UUID) -> object | None:
        """Get a single recovery item by ID."""
        return await self._repo.get_by_id(item_id)

    async def get_follow_ups(self, item_id: UUID) -> list[object]:
        """Get follow-up history for a recovery item."""
        return await self._repo.get_follow_ups(item_id)

    async def add_follow_up(
        self,
        item_id: UUID,
        action: FollowUpAction,
    ) -> object:
        """
        Manually add a follow-up entry to a recovery item.

        Optionally updates the item's next_follow_up_date if provided
        in the action.

        Requirements: 31.2, 31.3
        """
        item = await self._repo.get_by_id(item_id)
        if item is None:
            raise ValueError(f"Recovery item with id {item_id} not found")

        action_date = action.action_date or datetime.now(timezone.utc)

        follow_up_data = {
            "action_taken": action.action_taken,
            "action_by": action.action_by,
            "action_date": action_date,
            "next_follow_up_date": action.next_follow_up_date,
        }
        follow_up = await self._repo.add_follow_up(item_id, follow_up_data)

        # Update the recovery item's next follow-up date if provided
        if action.next_follow_up_date is not None:
            await self._repo.update(item_id, {"next_follow_up_date": action.next_follow_up_date})

        logger.info(
            "Follow-up added to recovery item %s by %s: %s",
            item_id,
            action.action_by,
            action.action_taken,
        )
        return follow_up
