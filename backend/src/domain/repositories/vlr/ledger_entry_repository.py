"""
Ledger Entry repository interface (Port).
Defines the contract for ledger entry persistence operations.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from uuid import UUID

from src.domain.repositories.vlr.vendor_repository import PaginatedResult, PaginationParams


@dataclass
class LedgerEntryFilters:
    """Filter criteria for ledger entry queries."""

    side: str | None = None
    match_id: UUID | None = None
    is_matched: bool | None = None
    document_type: str | None = None


class ILedgerEntryRepository(ABC):
    """Abstract repository for LedgerEntry persistence."""

    @abstractmethod
    async def get_by_id(self, entry_id: UUID) -> object | None:
        """Retrieve a ledger entry by ID."""
        ...

    @abstractmethod
    async def create(self, entry_data: dict) -> object:
        """Persist a new ledger entry."""
        ...

    @abstractmethod
    async def bulk_create(self, entries_data: list[dict]) -> list[object]:
        """Bulk insert multiple ledger entries."""
        ...

    @abstractmethod
    async def update(self, entry_id: UUID, update_data: dict) -> object:
        """Update an existing ledger entry."""
        ...

    @abstractmethod
    async def bulk_update_match(
        self, entry_ids: list[UUID], match_id: UUID, pass_number: int, confidence_score: float
    ) -> None:
        """Bulk update match metadata for entries matched by the engine."""
        ...

    @abstractmethod
    async def list_by_case(
        self,
        case_id: UUID,
        filters: LedgerEntryFilters | None = None,
        pagination: PaginationParams | None = None,
    ) -> PaginatedResult:
        """List ledger entries for a case with filtering and pagination."""
        ...

    @abstractmethod
    async def get_unmatched_by_case(self, case_id: UUID, side: str | None = None) -> list[object]:
        """Get all unmatched entries for a case (match_id is NULL)."""
        ...

    @abstractmethod
    async def get_by_case_and_side(self, case_id: UUID, side: str) -> list[object]:
        """Get all entries for a case on a specific side (company/vendor)."""
        ...

    @abstractmethod
    async def delete_by_case(self, case_id: UUID) -> int:
        """Delete all entries for a case (used for re-upload). Returns count deleted."""
        ...

    @abstractmethod
    async def delete_unmatched_by_case_and_side(self, case_id: UUID, side: str) -> int:
        """Delete unmatched entries for a case on a specific side. Returns count deleted."""
        ...

    @abstractmethod
    async def clear_match_data_by_case(self, case_id: UUID) -> int:
        """Clear match metadata (match_id, pass_number, confidence_score) for all entries in a case."""
        ...

    @abstractmethod
    async def count_by_case(self, case_id: UUID, side: str | None = None) -> int:
        """Count entries for a case, optionally filtered by side."""
        ...

    @abstractmethod
    async def sum_amount_by_case(self, case_id: UUID, side: str) -> float:
        """Sum amounts for a case on a specific side."""
        ...
