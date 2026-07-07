"""
Setting repository implementation (Adapter).
Implements ISettingRepository using async SQLAlchemy with company_code scoping
and pagination support.
"""

from uuid import UUID

from sqlalchemy import and_, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.repositories.vlr.setting_repository import ISettingRepository
from src.domain.repositories.vlr.vendor_repository import PaginatedResult, PaginationParams
from src.infrastructure.database.models.vlr.setting_model import SettingModel


class SettingRepositoryImpl(ISettingRepository):
    """Concrete implementation of setting persistence using async SQLAlchemy."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, setting_id: UUID) -> SettingModel | None:
        stmt = select(SettingModel).where(SettingModel.id == setting_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_key(self, company_code: str, key: str) -> SettingModel | None:
        stmt = select(SettingModel).where(
            and_(
                SettingModel.company_code == company_code,
                SettingModel.key == key,
            )
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def create(self, setting_data: dict) -> SettingModel:
        model = SettingModel(**setting_data)
        self._session.add(model)
        await self._session.flush()
        return model

    async def update(self, setting_id: UUID, update_data: dict) -> SettingModel:
        stmt = select(SettingModel).where(SettingModel.id == setting_id)
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        if model is None:
            raise ValueError(f"Setting with id {setting_id} not found")

        for key, value in update_data.items():
            setattr(model, key, value)

        await self._session.flush()
        return model

    async def upsert(self, company_code: str, key: str, value: str, **kwargs) -> SettingModel:
        """Create or update a setting by company_code and key."""
        existing = await self.get_by_key(company_code, key)
        if existing:
            existing.value = value
            for k, v in kwargs.items():
                if hasattr(existing, k):
                    setattr(existing, k, v)
            await self._session.flush()
            return existing
        else:
            setting_data = {
                "company_code": company_code,
                "key": key,
                "value": value,
                **kwargs,
            }
            return await self.create(setting_data)

    async def list_by_company(
        self,
        company_code: str,
        pagination: PaginationParams | None = None,
    ) -> PaginatedResult:
        pagination = pagination or PaginationParams()

        base_condition = SettingModel.company_code == company_code

        # Count query
        count_stmt = select(func.count(SettingModel.id)).where(base_condition)
        total = (await self._session.execute(count_stmt)).scalar_one()

        # Data query
        data_stmt = (
            select(SettingModel)
            .where(base_condition)
            .order_by(SettingModel.key)
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

    async def get_all_by_company(self, company_code: str) -> list[SettingModel]:
        stmt = (
            select(SettingModel)
            .where(SettingModel.company_code == company_code)
            .order_by(SettingModel.key)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def delete_by_key(self, company_code: str, key: str) -> bool:
        stmt = delete(SettingModel).where(
            and_(
                SettingModel.company_code == company_code,
                SettingModel.key == key,
            )
        )
        result = await self._session.execute(stmt)
        await self._session.flush()
        return result.rowcount > 0
