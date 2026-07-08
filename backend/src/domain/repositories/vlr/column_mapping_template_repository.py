"""
Column mapping template repository interface (Port).
Defines the contract for persisting and retrieving column mapping
templates per vendor.
"""

from abc import ABC, abstractmethod
from uuid import UUID


class IColumnMappingTemplateRepository(ABC):
    """Abstract repository for column mapping template persistence."""

    @abstractmethod
    async def get_by_vendor(self, vendor_id: UUID) -> object | None:
        """
        Retrieve the column mapping template for a vendor.

        Returns the template model or None if no template exists for the vendor.
        """
        ...

    @abstractmethod
    async def save(self, template_data: dict) -> object:
        """
        Save or update a column mapping template.

        If a template already exists for the vendor, it is updated.
        Otherwise, a new template is created.
        """
        ...

    @abstractmethod
    async def delete(self, vendor_id: UUID) -> None:
        """
        Delete the column mapping template for a vendor.

        Raises ValueError if no template exists for the vendor.
        """
        ...
