"""
Setting repository interface (Port).
Defines the contract for system configuration persistence operations.
"""

from abc import ABC, abstractmethod
from uuid import UUID

from src.domain.repositories.vlr.vendor_repository import PaginatedResult, PaginationParams


class ISettingRepository(ABC):
    """Abstract repository for Setting persistence with company_code scoping."""

    @abstractmethod
    async def get_by_id(self, setting_id: UUID) -> object | None:
        """Retrieve a setting by ID."""
        ...

    @abstractmethod
    async def get_by_key(self, company_code: str, key: str) -> object | None:
        """Retrieve a setting by company_code and key."""
        ...

    @abstractmethod
    async def create(self, setting_data: dict) -> object:
        """Persist a new setting record."""
        ...

    @abstractmethod
    async def update(self, setting_id: UUID, update_data: dict) -> object:
        """Update an existing setting record."""
        ...

    @abstractmethod
    async def upsert(self, company_code: str, key: str, value: str, **kwargs) -> object:
        """Create or update a setting by company_code and key."""
        ...

    @abstractmethod
    async def list_by_company(
        self,
        company_code: str,
        pagination: PaginationParams | None = None,
    ) -> PaginatedResult:
        """List all settings for a company with pagination."""
        ...

    @abstractmethod
    async def get_all_by_company(self, company_code: str) -> list[object]:
        """Get all settings for a company (no pagination, for config loading)."""
        ...

    @abstractmethod
    async def delete_by_key(self, company_code: str, key: str) -> bool:
        """Delete a setting by company_code and key. Returns True if deleted."""
        ...
