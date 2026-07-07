"""
Approval repository interface (Port).
Defines the contract for approval record persistence operations.
"""

from abc import ABC, abstractmethod
from uuid import UUID

from src.domain.repositories.vlr.vendor_repository import PaginatedResult, PaginationParams


class IApprovalRepository(ABC):
    """Abstract repository for ApprovalRecord persistence."""

    @abstractmethod
    async def get_by_id(self, approval_id: UUID) -> object | None:
        """Retrieve an approval record by ID."""
        ...

    @abstractmethod
    async def create(self, approval_data: dict) -> object:
        """Persist a new approval record."""
        ...

    @abstractmethod
    async def list_by_case(
        self,
        case_id: UUID,
        pagination: PaginationParams | None = None,
    ) -> PaginatedResult:
        """List approval records for a case with pagination."""
        ...

    @abstractmethod
    async def get_pending_approvals(
        self,
        approver_id: UUID,
        company_code: str,
        pagination: PaginationParams | None = None,
    ) -> PaginatedResult:
        """Get cases pending approval for a specific approver, scoped by company_code."""
        ...

    @abstractmethod
    async def get_latest_by_case(self, case_id: UUID) -> object | None:
        """Get the most recent approval record for a case."""
        ...

    @abstractmethod
    async def count_pending(self, approver_id: UUID, company_code: str) -> int:
        """Count pending approvals for an approver within a company."""
        ...
