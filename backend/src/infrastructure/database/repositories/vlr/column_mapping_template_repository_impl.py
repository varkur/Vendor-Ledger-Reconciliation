"""
Column mapping template repository implementation (Adapter).
Implements IColumnMappingTemplateRepository using async SQLAlchemy.
"""

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.repositories.vlr.column_mapping_template_repository import (
    IColumnMappingTemplateRepository,
)
from src.infrastructure.database.models.vlr.column_mapping_template_model import (
    ColumnMappingTemplateModel,
)


class ColumnMappingTemplateRepositoryImpl(IColumnMappingTemplateRepository):
    """Concrete implementation of column mapping template persistence using async SQLAlchemy."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_vendor(self, vendor_id: UUID) -> ColumnMappingTemplateModel | None:
        stmt = select(ColumnMappingTemplateModel).where(
            ColumnMappingTemplateModel.vendor_id == vendor_id
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def save(self, template_data: dict) -> ColumnMappingTemplateModel:
        vendor_id = template_data.get("vendor_id")
        if vendor_id is None:
            raise ValueError("vendor_id is required in template_data")

        # Check if a template already exists for this vendor
        existing = await self.get_by_vendor(vendor_id)

        if existing is not None:
            # Update existing template
            for key, value in template_data.items():
                if key != "vendor_id":
                    setattr(existing, key, value)
            existing.modified_date = datetime.now(timezone.utc)
            await self._session.flush()
            return existing
        else:
            # Create new template
            model = ColumnMappingTemplateModel(**template_data)
            self._session.add(model)
            await self._session.flush()
            return model

    async def delete(self, vendor_id: UUID) -> None:
        existing = await self.get_by_vendor(vendor_id)
        if existing is None:
            raise ValueError(
                f"No column mapping template found for vendor_id {vendor_id}"
            )
        await self._session.delete(existing)
        await self._session.flush()
