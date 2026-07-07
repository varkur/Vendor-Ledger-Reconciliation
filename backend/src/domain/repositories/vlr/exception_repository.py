"""
Exception repository interface (Port).
Defines the contract for reconciliation exception persistence operations.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from uuid import UUID

from src.domain.repositories.vlr.vendor_repository import PaginatedResult, PaginationParams


@dataclass
class ExceptionFilters:
    """Filter criteria for exception queries."""

    case_id: UUID | None = None
    severity: str | None = None
    category: str | None = None
    status: str | None = None


class IExceptionRepository(ABC):
    """Abstract repository for RecoException persistence."""

    @abstractmethod
    async def get_by_id(self, exception_id: UUID) -> object | None:
        """Retrieve an exception by ID."""
        ...

    @abstractmethod
    async def create(self, exception_data: dict) -> object:
        """Persist a new exception record."""
        ...

    @abstractmethod
    async def bulk_create(self, exceptions_data: list[dict]) -> list[object]:
        """Bulk insert multiple exception records."""
        ...

    @abstractmethod
    async def update(self, exception_id: UUID, update_data: dict) -> object:
        """Update an existing exception record."""
        ...

    @abstractmethod
    async def list_exceptions(
        self,
        company_code: str,
        filters: ExceptionFilters | None = None,
        pagination: PaginationParams | None = None,
    ) -> PaginatedResult:
        """List exceptions with filtering and pagination, scoped by company_code."""
        ...

    @abstractmethod
    async def list_by_case(
        self,
        case_id: UUID,
        filters: ExceptionFilters | None = None,
        pagination: PaginationParams | None = None,
    ) -> PaginatedResult:
        """List exceptions for a specific case with filtering and pagination."""
        ...

    @abstractmethod
    async def get_open_by_case(self, case_id: UUID) -> list[object]:
        """Get all open (unresolved) exceptions for a case."""
        ...

    @abstractmethod
    async def get_critical_open_by_case(self, case_id: UUID) -> list[object]:
        """Get all open critical exceptions for a case (blocks closure)."""
        ...

    @abstractmethod
    async def delete_by_case(self, case_id: UUID) -> int:
        """Delete all exceptions for a case (used for re-reconciliation). Returns count deleted."""
        ...

    @abstractmethod
    async def count_by_case(self, case_id: UUID, status: str | None = None) -> int:
        """Count exceptions for a case, optionally filtered by status."""
        ...

    @abstractmethod
    async def count_by_severity(self, case_id: UUID) -> dict[str, int]:
        """Count exceptions grouped by severity for a case."""
        ...
