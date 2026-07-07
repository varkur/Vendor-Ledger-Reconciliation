"""
Reconciliation Case repository interface (Port).
Defines the contract for case persistence operations.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from uuid import UUID

from src.domain.repositories.vlr.vendor_repository import PaginatedResult, PaginationParams


@dataclass
class CaseFilters:
    """Filter criteria for case queries."""

    status: str | None = None
    vendor_id: UUID | None = None
    request_id: UUID | None = None
    case_type: str | None = None


class ICaseRepository(ABC):
    """Abstract repository for ReconciliationCase persistence."""

    @abstractmethod
    async def get_by_id(self, case_id: UUID, company_code: str | None = None) -> object | None:
        """Retrieve a case by ID, optionally scoped to company_code. Excludes soft-deleted."""
        ...

    @abstractmethod
    async def get_by_token(self, portal_token: str) -> object | None:
        """Retrieve a case by portal token (for vendor portal auth)."""
        ...

    @abstractmethod
    async def create(self, case_data: dict) -> object:
        """Persist a new reconciliation case."""
        ...

    @abstractmethod
    async def bulk_create(self, cases_data: list[dict]) -> list[object]:
        """Bulk insert multiple case records."""
        ...

    @abstractmethod
    async def update(self, case_id: UUID, update_data: dict) -> object:
        """Update an existing case record."""
        ...

    @abstractmethod
    async def soft_delete(self, case_id: UUID) -> None:
        """Soft-delete a case (set is_deleted=True, deleted_at=now)."""
        ...

    @abstractmethod
    async def list_cases(
        self,
        company_code: str,
        filters: CaseFilters | None = None,
        pagination: PaginationParams | None = None,
    ) -> PaginatedResult:
        """List cases with filtering and pagination, excluding soft-deleted."""
        ...

    @abstractmethod
    async def list_by_request(
        self,
        request_id: UUID,
        pagination: PaginationParams | None = None,
    ) -> PaginatedResult:
        """List all cases for a given request, excluding soft-deleted."""
        ...

    @abstractmethod
    async def get_active_cases_for_vendor(self, vendor_id: UUID) -> list[object]:
        """Get all non-closed cases for a vendor (used for deletion checks)."""
        ...

    @abstractmethod
    async def increment_upload_count(self, case_id: UUID) -> int:
        """Increment upload_count and return the new value."""
        ...

    @abstractmethod
    async def increment_edit_count(self, case_id: UUID) -> int:
        """Increment edit_count and return the new value."""
        ...

    @abstractmethod
    async def count_by_request(self, request_id: UUID) -> int:
        """Count total cases for a request."""
        ...

    @abstractmethod
    async def count_by_status(self, request_id: UUID) -> dict[str, int]:
        """Count cases grouped by status for a request."""
        ...
