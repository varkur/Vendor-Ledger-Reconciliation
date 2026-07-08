"""
Recovery repository implementation (Adapter).
Implements IRecoveryRepository using async SQLAlchemy.
"""

from datetime import date, timezone
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.repositories.vlr.recovery_repository import (
    IRecoveryRepository,
    RecoveryFilters,
)
from src.domain.repositories.vlr.vendor_repository import PaginatedResult, PaginationParams
from src.infrastructure.database.models.vlr.recovery_follow_up_model import RecoveryFollowUpModel
from src.infrastructure.database.models.vlr.recovery_item_model import RecoveryItemModel


class RecoveryRepositoryImpl(IRecoveryRepository):
    """Concrete implementation of recovery persistence using async SQLAlchemy."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, data: dict) -> RecoveryItemModel:
        model = RecoveryItemModel(**data)
        self._session.add(model)
        await self._session.flush()
        return model

    async def get_by_id(self, item_id: UUID) -> RecoveryItemModel | None:
        stmt = select(RecoveryItemModel).where(RecoveryItemModel.id == item_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def update(self, item_id: UUID, data: dict) -> RecoveryItemModel:
        stmt = select(RecoveryItemModel).where(RecoveryItemModel.id == item_id)
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        if model is None:
            raise ValueError(f"Recovery item with id {item_id} not found")

        for key, value in data.items():
            setattr(model, key, value)

        await self._session.flush()
        return model

    async def list_items(
        self,
        filters: RecoveryFilters | None = None,
        pagination: PaginationParams | None = None,
    ) -> PaginatedResult:
        pagination = pagination or PaginationParams()

        base_stmt = select(RecoveryItemModel)

        filter_conditions = self._build_filter_conditions(filters)
        if filter_conditions:
            base_stmt = base_stmt.where(and_(*filter_conditions))

        # Count query
        count_stmt = select(func.count()).select_from(base_stmt.subquery())
        total = (await self._session.execute(count_stmt)).scalar_one()

        # Data query with pagination
        data_stmt = (
            base_stmt.order_by(RecoveryItemModel.created_date.desc())
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

    async def list_overdue(self, as_of_date: date | None = None) -> list[RecoveryItemModel]:
        reference_date = as_of_date or date.today()
        stmt = select(RecoveryItemModel).where(
            and_(
                RecoveryItemModel.status.in_(["open", "in_progress"]),
                RecoveryItemModel.next_follow_up_date <= reference_date,
                RecoveryItemModel.next_follow_up_date.isnot(None),
            )
        ).order_by(RecoveryItemModel.next_follow_up_date.asc())

        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def add_follow_up(self, item_id: UUID, follow_up_data: dict) -> RecoveryFollowUpModel:
        follow_up_data["recovery_item_id"] = item_id
        model = RecoveryFollowUpModel(**follow_up_data)
        self._session.add(model)
        await self._session.flush()
        return model

    async def get_follow_ups(self, item_id: UUID) -> list[RecoveryFollowUpModel]:
        stmt = (
            select(RecoveryFollowUpModel)
            .where(RecoveryFollowUpModel.recovery_item_id == item_id)
            .order_by(RecoveryFollowUpModel.action_date.desc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    def _build_filter_conditions(filters: RecoveryFilters | None) -> list:
        """Build SQLAlchemy filter conditions from RecoveryFilters."""
        conditions = []
        if filters is None:
            return conditions

        if filters.status:
            conditions.append(RecoveryItemModel.status == filters.status)
        if filters.vendor_id:
            conditions.append(RecoveryItemModel.vendor_id == filters.vendor_id)
        if filters.case_id:
            conditions.append(RecoveryItemModel.case_id == filters.case_id)

        return conditions
