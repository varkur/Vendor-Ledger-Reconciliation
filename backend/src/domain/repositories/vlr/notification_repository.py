"""
Notification repository interface (Port).
Defines the contract for notification persistence operations.
"""

from abc import ABC, abstractmethod
from datetime import datetime
from uuid import UUID

from src.domain.repositories.vlr.vendor_repository import PaginatedResult, PaginationParams


class INotificationRepository(ABC):
    """Abstract repository for Notification persistence."""

    @abstractmethod
    async def get_by_id(self, notification_id: UUID) -> object | None:
        """Retrieve a notification by ID."""
        ...

    @abstractmethod
    async def create(self, notification_data: dict) -> object:
        """Persist a new notification record."""
        ...

    @abstractmethod
    async def update(self, notification_id: UUID, update_data: dict) -> object:
        """Update a notification record (e.g., status, retry_count)."""
        ...

    @abstractmethod
    async def list_by_case(
        self,
        case_id: UUID,
        pagination: PaginationParams | None = None,
    ) -> PaginatedResult:
        """List notifications for a case with pagination."""
        ...

    @abstractmethod
    async def get_pending_retries(self, before: datetime) -> list[object]:
        """Get notifications due for retry (next_retry_date <= before and status=failed)."""
        ...

    @abstractmethod
    async def get_reminders_for_case(self, case_id: UUID) -> list[object]:
        """Get all reminder notifications sent for a case."""
        ...

    @abstractmethod
    async def count_reminders_for_case(self, case_id: UUID) -> int:
        """Count reminder notifications sent for a case."""
        ...

    @abstractmethod
    async def count_by_case(self, case_id: UUID) -> int:
        """Count total notifications for a case."""
        ...
