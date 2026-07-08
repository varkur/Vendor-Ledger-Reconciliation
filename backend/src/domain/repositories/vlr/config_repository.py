"""
Configuration repository interface (Port).
Defines the contract for retrieving system configuration values used by
domain services such as the Data Transformation Engine.
"""

from abc import ABC, abstractmethod


class IConfigRepository(ABC):
    """Abstract repository for retrieving VLR configuration values."""

    @abstractmethod
    async def get_document_type_category(self, doc_type: str) -> str | None:
        """
        Retrieve the category for a document type code.

        Returns the category string (e.g., 'Invoice', 'Payment', 'Credit Note')
        or None if the document type is not configured.
        """
        ...

    @abstractmethod
    async def is_tds_document_type(self, doc_type: str) -> bool:
        """Check if a document type is classified as TDS."""
        ...

    @abstractmethod
    async def get_clean_special_characters(self) -> list[str]:
        """
        Retrieve the list of special characters to strip during CLEAN function.

        Default: ['/', '\\', '-', '_']
        """
        ...

    @abstractmethod
    async def get_all_document_type_mappings(self) -> dict[str, str]:
        """
        Retrieve all configured document type to category mappings.

        Returns a dict mapping document_type_code -> category.
        """
        ...
