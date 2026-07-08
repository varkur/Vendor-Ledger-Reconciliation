"""
Recovery repository interface (Port).
Defines the contract for recovery item and follow-up persistence operations.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date
from uuid import UUID

from src.domain.repositories.vlr.vendor_repository import PaginatedResult, PaginationParams


@dataclass
class RecoveryFilters:
    """Filter criteria for recovery item queries."""

    status: str | None = None
    vendor_id: UUID | None = None
    case_id: UUID | None = None


class IRecoveryRepository(ABC):
    """Abstract repository for Recovery item persistence."""

    @abstractmethod
    async def create(self, data: dict) -> object:
        """Persist a new recovery item."""
        ...

    @abstractmethod
    async def get_by_id(self, item_id: UUID) -> object | None:
        """Retrieve a recovery item by ID."""
        ...

    @abstractmethod
    async def update(self, item_id: UUID, data: dict) -> object:
        """Update an existing recovery item."""
        ...

    @abstractmethod
    async def list_items(
        self,
        filters: RecoveryFilters | None = None,
        pagination: PaginationParams | None = None,
    ) -> PaginatedResult:
        """List recovery items with filtering and pagination."""
        ...

    @abstractmethod
    async def list_overdue(self, as_of_date: date | None = None) -> list[object]:
        """Get recovery items past their follow-up date."""
        ...

    @abstractmethod
    async def add_follow_up(self, item_id: UUID, follow_up_data: dict) -> object:
        """Add a follow-up entry to a recovery item."""
        ...

    @abstractmethod
    async def get_follow_ups(self, item_id: UUID) -> list[object]:
        """Get all follow-up entries for a recovery item, ordered by action_date desc."""
        ...
