"""
Match Result repository interface (Port).
Defines the contract for match result persistence operations.
"""

from abc import ABC, abstractmethod
from uuid import UUID

from src.domain.repositories.vlr.vendor_repository import PaginatedResult, PaginationParams


class IMatchResultRepository(ABC):
    """Abstract repository for MatchResult persistence."""

    @abstractmethod
    async def get_by_id(self, match_id: UUID) -> object | None:
        """Retrieve a match result by ID."""
        ...

    @abstractmethod
    async def create(self, match_data: dict) -> object:
        """Persist a new match result."""
        ...

    @abstractmethod
    async def bulk_create(self, matches_data: list[dict]) -> list[object]:
        """Bulk insert multiple match results."""
        ...

    @abstractmethod
    async def list_by_case(
        self,
        case_id: UUID,
        pagination: PaginationParams | None = None,
    ) -> PaginatedResult:
        """List match results for a case with pagination."""
        ...

    @abstractmethod
    async def get_by_case_and_pass(self, case_id: UUID, pass_number: int) -> list[object]:
        """Get all match results for a case and specific pass number."""
        ...

    @abstractmethod
    async def delete_by_case(self, case_id: UUID) -> int:
        """Delete all match results for a case (used for re-reconciliation). Returns count deleted."""
        ...

    @abstractmethod
    async def get_statistics_by_case(self, case_id: UUID) -> dict:
        """
        Get match statistics per pass for a case.
        Returns dict with pass_number -> {match_count, matched_amount, percentage}.
        """
        ...

    @abstractmethod
    async def get_unconfirmed_by_case(self, case_id: UUID) -> list[object]:
        """Get all unconfirmed match results (fuzzy/combination matches needing review)."""
        ...

    @abstractmethod
    async def confirm_match(self, match_id: UUID) -> object:
        """Mark a match result as confirmed."""
        ...

    @abstractmethod
    async def count_by_case(self, case_id: UUID) -> int:
        """Count total match results for a case."""
        ...
