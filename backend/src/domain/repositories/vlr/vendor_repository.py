"""
Vendor repository interface (Port).
Defines the contract for vendor persistence operations with
company_code scoping, soft-delete filtering, and pagination.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from uuid import UUID


@dataclass
class VendorFilters:
    """Filter criteria for vendor queries."""

    vendor_code: str | None = None
    name: str | None = None
    status: str | None = None
    city: str | None = None
    pan: str | None = None


@dataclass
class PaginationParams:
    """Pagination parameters with default page size of 50."""

    page: int = 1
    page_size: int = 50

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


@dataclass
class PaginatedResult[T]:
    """Generic paginated result container."""

    items: list[T]
    total: int
    page: int
    page_size: int

    @property
    def total_pages(self) -> int:
        return (self.total + self.page_size - 1) // self.page_size if self.page_size > 0 else 0


class IVendorRepository(ABC):
    """Abstract repository for Vendor persistence with multi-tenant scoping."""

    @abstractmethod
    async def get_by_id(self, vendor_id: UUID, company_code: str) -> object | None:
        """Retrieve a vendor by ID, scoped to company_code, excluding soft-deleted."""
        ...

    @abstractmethod
    async def get_by_vendor_code(
        self, vendor_code: str, company_code: str
    ) -> object | None:
        """Retrieve a vendor by vendor_code within a company, excluding soft-deleted."""
        ...

    @abstractmethod
    async def create(self, vendor_data: dict) -> object:
        """Persist a new vendor record."""
        ...

    @abstractmethod
    async def update(self, vendor_id: UUID, company_code: str, update_data: dict) -> object:
        """Update an existing vendor record."""
        ...

    @abstractmethod
    async def soft_delete(self, vendor_id: UUID, company_code: str) -> None:
        """Soft-delete a vendor (set is_deleted=True, deleted_at=now)."""
        ...

    @abstractmethod
    async def list_vendors(
        self,
        company_code: str,
        filters: VendorFilters | None = None,
        pagination: PaginationParams | None = None,
    ) -> PaginatedResult:
        """List vendors with filtering and pagination, excluding soft-deleted."""
        ...

    @abstractmethod
    async def exists_by_vendor_code(self, vendor_code: str, company_code: str) -> bool:
        """Check if a vendor_code already exists within a company."""
        ...

    @abstractmethod
    async def has_active_cases(self, vendor_id: UUID) -> bool:
        """Check if a vendor has any non-closed reconciliation cases."""
        ...

    @abstractmethod
    async def bulk_create(self, vendors_data: list[dict]) -> list[object]:
        """Bulk insert multiple vendor records."""
        ...

    @abstractmethod
    async def count(self, company_code: str, filters: VendorFilters | None = None) -> int:
        """Count vendors matching filters, excluding soft-deleted."""
        ...

    @abstractmethod
    async def add_contacts(self, vendor_id: UUID, contacts: list[dict]) -> list[object]:
        """Add contact records to a vendor."""
        ...

    @abstractmethod
    async def remove_contacts_by_source(self, vendor_id: UUID, source: str) -> None:
        """Remove all contacts for a vendor with the given source."""
        ...

    @abstractmethod
    async def get_contacts(self, vendor_id: UUID) -> list[object]:
        """Get all contacts for a vendor."""
        ...
