"""
Vendor repository implementation (Adapter).
Implements IVendorRepository using async SQLAlchemy with company_code scoping,
soft-delete filtering, and pagination support.
"""

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.domain.repositories.vlr.vendor_repository import (
    IVendorRepository,
    PaginatedResult,
    PaginationParams,
    VendorFilters,
)
from src.infrastructure.database.models.vlr.reconciliation_case_model import ReconciliationCaseModel
from src.infrastructure.database.models.vlr.vendor_contact_model import VendorContactModel
from src.infrastructure.database.models.vlr.vendor_model import VendorModel


class VendorRepositoryImpl(IVendorRepository):
    """Concrete implementation of vendor persistence using async SQLAlchemy."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, vendor_id: UUID, company_code: str) -> VendorModel | None:
        stmt = select(VendorModel).where(
            and_(
                VendorModel.id == vendor_id,
                VendorModel.company_code == company_code,
                VendorModel.is_deleted == False,  # noqa: E712
            )
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_vendor_code(
        self, vendor_code: str, company_code: str
    ) -> VendorModel | None:
        stmt = select(VendorModel).where(
            and_(
                VendorModel.vendor_code == vendor_code,
                VendorModel.company_code == company_code,
                VendorModel.is_deleted == False,  # noqa: E712
            )
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def create(self, vendor_data: dict) -> VendorModel:
        model = VendorModel(**vendor_data)
        self._session.add(model)
        await self._session.flush()
        return model

    async def update(self, vendor_id: UUID, company_code: str, update_data: dict) -> VendorModel:
        stmt = select(VendorModel).where(
            and_(
                VendorModel.id == vendor_id,
                VendorModel.company_code == company_code,
                VendorModel.is_deleted == False,  # noqa: E712
            )
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        if model is None:
            raise ValueError(f"Vendor with id {vendor_id} not found in company {company_code}")

        for key, value in update_data.items():
            setattr(model, key, value)

        await self._session.flush()
        return model

    async def soft_delete(self, vendor_id: UUID, company_code: str) -> None:
        stmt = select(VendorModel).where(
            and_(
                VendorModel.id == vendor_id,
                VendorModel.company_code == company_code,
                VendorModel.is_deleted == False,  # noqa: E712
            )
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        if model is None:
            raise ValueError(f"Vendor with id {vendor_id} not found in company {company_code}")

        model.is_deleted = True
        model.deleted_at = datetime.now(timezone.utc)
        await self._session.flush()

    async def list_vendors(
        self,
        company_code: str,
        filters: VendorFilters | None = None,
        pagination: PaginationParams | None = None,
    ) -> PaginatedResult:
        pagination = pagination or PaginationParams()

        base_conditions = and_(
            VendorModel.company_code == company_code,
            VendorModel.is_deleted == False,  # noqa: E712
        )

        # Build filter conditions
        filter_conditions = self._build_filter_conditions(filters)

        # Count query
        count_stmt = select(func.count(VendorModel.id)).where(
            and_(base_conditions, *filter_conditions)
        )
        total = (await self._session.execute(count_stmt)).scalar_one()

        # Data query
        data_stmt = (
            select(VendorModel)
            .options(selectinload(VendorModel.contacts))
            .where(and_(base_conditions, *filter_conditions))
            .order_by(VendorModel.created_date.desc())
            .offset(pagination.offset)
            .limit(pagination.page_size)
        )
        result = await self._session.execute(data_stmt)
        items = list(result.scalars().all())

        return PaginatedResult(
            items=items,
            total=total,
            page=pagination.page,
            page_size=pagination.page_size,
        )

    async def exists_by_vendor_code(self, vendor_code: str, company_code: str) -> bool:
        stmt = select(func.count(VendorModel.id)).where(
            and_(
                VendorModel.vendor_code == vendor_code,
                VendorModel.company_code == company_code,
                VendorModel.is_deleted == False,  # noqa: E712
            )
        )
        result = await self._session.execute(stmt)
        return result.scalar_one() > 0

    async def has_active_cases(self, vendor_id: UUID) -> bool:
        stmt = select(func.count(ReconciliationCaseModel.id)).where(
            and_(
                ReconciliationCaseModel.vendor_id == vendor_id,
                ReconciliationCaseModel.is_deleted == False,  # noqa: E712
                ReconciliationCaseModel.status != "closed",
            )
        )
        result = await self._session.execute(stmt)
        return result.scalar_one() > 0

    async def bulk_create(self, vendors_data: list[dict]) -> list[VendorModel]:
        models = [VendorModel(**data) for data in vendors_data]
        self._session.add_all(models)
        await self._session.flush()
        return models

    async def count(self, company_code: str, filters: VendorFilters | None = None) -> int:
        base_conditions = and_(
            VendorModel.company_code == company_code,
            VendorModel.is_deleted == False,  # noqa: E712
        )
        filter_conditions = self._build_filter_conditions(filters)

        stmt = select(func.count(VendorModel.id)).where(
            and_(base_conditions, *filter_conditions)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one()

    @staticmethod
    def _build_filter_conditions(filters: VendorFilters | None) -> list:
        """Build SQLAlchemy filter conditions from VendorFilters."""
        conditions = []
        if filters is None:
            return conditions

        if filters.vendor_code:
            conditions.append(VendorModel.vendor_code.ilike(f"%{filters.vendor_code}%"))
        if filters.name:
            conditions.append(VendorModel.name.ilike(f"%{filters.name}%"))
        if filters.status:
            conditions.append(VendorModel.status == filters.status)
        if filters.city:
            conditions.append(VendorModel.city.ilike(f"%{filters.city}%"))
        if filters.pan:
            conditions.append(VendorModel.pan.ilike(f"%{filters.pan}%"))

        return conditions


    async def add_contacts(self, vendor_id: UUID, contacts: list[dict]) -> list[VendorContactModel]:
        """Add contact records to a vendor."""
        models = []
        for contact_data in contacts:
            contact_data["vendor_id"] = vendor_id
            model = VendorContactModel(**contact_data)
            self._session.add(model)
            models.append(model)
        await self._session.flush()
        return models

    async def remove_contacts_by_source(self, vendor_id: UUID, source: str) -> None:
        """Remove all contacts for a vendor with the given source."""
        from sqlalchemy import delete

        stmt = delete(VendorContactModel).where(
            and_(
                VendorContactModel.vendor_id == vendor_id,
                VendorContactModel.source == source,
            )
        )
        await self._session.execute(stmt)
        await self._session.flush()

    async def get_contacts(self, vendor_id: UUID) -> list[VendorContactModel]:
        """Get all contacts for a vendor."""
        stmt = select(VendorContactModel).where(
            VendorContactModel.vendor_id == vendor_id
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
