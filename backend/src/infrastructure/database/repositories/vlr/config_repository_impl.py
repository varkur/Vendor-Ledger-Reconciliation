"""
Configuration repository implementation (Adapter).
Implements IConfigRepository using async SQLAlchemy to query document type mappings.

Requirements: 7.5 (configurable document type classification)
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.repositories.vlr.config_repository import IConfigRepository
from src.infrastructure.database.models.vlr.document_type_mapping_model import (
    DocumentTypeMappingModel,
)


class ConfigRepositoryImpl(IConfigRepository):
    """Concrete implementation of config repository using async SQLAlchemy."""

    # Default special characters to strip in CLEAN function
    DEFAULT_SPECIAL_CHARACTERS = ["/", "\\", "-", "_"]

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_document_type_category(self, doc_type: str) -> str | None:
        """
        Retrieve the category for a document type code from the database.

        Returns None if the document type is not configured or inactive.
        """
        stmt = select(DocumentTypeMappingModel.category).where(
            DocumentTypeMappingModel.document_type_code == doc_type,
            DocumentTypeMappingModel.is_active.is_(True),
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def is_tds_document_type(self, doc_type: str) -> bool:
        """Check if a document type is classified as TDS."""
        stmt = select(DocumentTypeMappingModel.is_tds).where(
            DocumentTypeMappingModel.document_type_code == doc_type,
            DocumentTypeMappingModel.is_active.is_(True),
        )
        result = await self._session.execute(stmt)
        is_tds = result.scalar_one_or_none()
        return bool(is_tds)

    async def get_clean_special_characters(self) -> list[str]:
        """
        Retrieve the list of special characters to strip during CLEAN function.

        Currently returns the default list. Can be extended to read from
        a settings table in the future.
        """
        return self.DEFAULT_SPECIAL_CHARACTERS

    async def get_all_document_type_mappings(self) -> dict[str, str]:
        """
        Retrieve all active document type to category mappings.

        Returns a dict mapping document_type_code -> category.
        """
        stmt = select(
            DocumentTypeMappingModel.document_type_code,
            DocumentTypeMappingModel.category,
        ).where(DocumentTypeMappingModel.is_active.is_(True))
        result = await self._session.execute(stmt)
        return {row[0]: row[1] for row in result.all()}

    async def get_tds_document_types(self) -> set[str]:
        """
        Retrieve all document type codes classified as TDS.

        Returns a set of document type codes where is_tds=True.
        """
        stmt = select(DocumentTypeMappingModel.document_type_code).where(
            DocumentTypeMappingModel.is_tds.is_(True),
            DocumentTypeMappingModel.is_active.is_(True),
        )
        result = await self._session.execute(stmt)
        return {row[0] for row in result.all()}
