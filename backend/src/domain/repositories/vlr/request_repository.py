"""
Reconciliation Request repository interface (Port).
Defines the contract for request persistence operations.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date
from uuid import UUID

from src.domain.repositories.vlr.vendor_repository import PaginatedResult, PaginationParams


@dataclass
class RequestFilters:
    """Filter criteria for request queries."""

    status: str | None = None
    date_from: date | None = None
    date_to: date | None = None
    assigned_manager_id: UUID | None = None
    fiscal_year: str | None = None


class IRequestRepository(ABC):
    """Abstract repository for ReconciliationRequest persistence."""

    @abstractmethod
    async def get_by_id(self, request_id: UUID, company_code: str) -> object | None:
        """Retrieve a request by ID, scoped to company_code."""
        ...

    @abstractmethod
    async def create(self, request_data: dict) -> object:
        """Persist a new reconciliation request."""
        ...

    @abstractmethod
    async def update(self, request_id: UUID, company_code: str, update_data: dict) -> object:
        """Update an existing request record."""
        ...

    @abstractmethod
    async def list_requests(
        self,
        company_code: str,
        filters: RequestFilters | None = None,
        pagination: PaginationParams | None = None,
    ) -> PaginatedResult:
        """List requests with filtering and pagination."""
        ...

    @abstractmethod
    async def has_overlapping_period(
        self,
        vendor_id: UUID,
        company_code: str,
        period_start: date,
        period_end: date,
        exclude_request_id: UUID | None = None,
    ) -> bool:
        """Check if an overlapping reconciliation period exists for a vendor."""
        ...

    @abstractmethod
    async def get_statistics(self, request_id: UUID, company_code: str) -> dict:
        """Get aggregated statistics for a request (case counts by status)."""
        ...

    @abstractmethod
    async def count(self, company_code: str, filters: RequestFilters | None = None) -> int:
        """Count requests matching filters."""
        ...
