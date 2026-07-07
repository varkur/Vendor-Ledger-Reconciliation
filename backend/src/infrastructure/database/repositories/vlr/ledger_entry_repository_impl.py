"""
Ledger Entry repository implementation (Adapter).
Implements ILedgerEntryRepository using async SQLAlchemy with pagination support.
"""

from uuid import UUID

from sqlalchemy import and_, delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.repositories.vlr.ledger_entry_repository import (
    ILedgerEntryRepository,
    LedgerEntryFilters,
)
from src.domain.repositories.vlr.vendor_repository import PaginatedResult, PaginationParams
from src.infrastructure.database.models.vlr.ledger_entry_model import LedgerEntryModel


class LedgerEntryRepositoryImpl(ILedgerEntryRepository):
    """Concrete implementation of ledger entry persistence using async SQLAlchemy."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, entry_id: UUID) -> LedgerEntryModel | None:
        stmt = select(LedgerEntryModel).where(LedgerEntryModel.id == entry_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def create(self, entry_data: dict) -> LedgerEntryModel:
        model = LedgerEntryModel(**entry_data)
        self._session.add(model)
        await self._session.flush()
        return model

    async def bulk_create(self, entries_data: list[dict]) -> list[LedgerEntryModel]:
        models = [LedgerEntryModel(**data) for data in entries_data]
        self._session.add_all(models)
        await self._session.flush()
        return models

    async def update(self, entry_id: UUID, update_data: dict) -> LedgerEntryModel:
        stmt = select(LedgerEntryModel).where(LedgerEntryModel.id == entry_id)
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        if model is None:
            raise ValueError(f"Ledger entry with id {entry_id} not found")

        for key, value in update_data.items():
            setattr(model, key, value)

        await self._session.flush()
        return model

    async def bulk_update_match(
        self, entry_ids: list[UUID], match_id: UUID, pass_number: int, confidence_score: float
    ) -> None:
        if not entry_ids:
            return

        stmt = (
            update(LedgerEntryModel)
            .where(LedgerEntryModel.id.in_(entry_ids))
            .values(
                match_id=match_id,
                pass_number=pass_number,
                confidence_score=confidence_score,
            )
        )
        await self._session.execute(stmt)
        await self._session.flush()

    async def list_by_case(
        self,
        case_id: UUID,
        filters: LedgerEntryFilters | None = None,
        pagination: PaginationParams | None = None,
    ) -> PaginatedResult:
        pagination = pagination or PaginationParams()

        base_condition = LedgerEntryModel.case_id == case_id
        filter_conditions = self._build_filter_conditions(filters)

        # Count query
        count_stmt = select(func.count(LedgerEntryModel.id)).where(
            and_(base_condition, *filter_conditions)
        )
        total = (await self._session.execute(count_stmt)).scalar_one()

        # Data query
        data_stmt = (
            select(LedgerEntryModel)
            .where(and_(base_condition, *filter_conditions))
            .order_by(LedgerEntryModel.posting_date.desc())
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

    async def get_unmatched_by_case(self, case_id: UUID, side: str | None = None) -> list[LedgerEntryModel]:
        conditions = [
            LedgerEntryModel.case_id == case_id,
            LedgerEntryModel.match_id.is_(None),
        ]
        if side:
            conditions.append(LedgerEntryModel.side == side)

        stmt = select(LedgerEntryModel).where(and_(*conditions))
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_case_and_side(self, case_id: UUID, side: str) -> list[LedgerEntryModel]:
        stmt = select(LedgerEntryModel).where(
            and_(
                LedgerEntryModel.case_id == case_id,
                LedgerEntryModel.side == side,
            )
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def delete_by_case(self, case_id: UUID) -> int:
        stmt = delete(LedgerEntryModel).where(LedgerEntryModel.case_id == case_id)
        result = await self._session.execute(stmt)
        await self._session.flush()
        return result.rowcount

    async def delete_unmatched_by_case_and_side(self, case_id: UUID, side: str) -> int:
        stmt = delete(LedgerEntryModel).where(
            and_(
                LedgerEntryModel.case_id == case_id,
                LedgerEntryModel.side == side,
                LedgerEntryModel.match_id.is_(None),
            )
        )
        result = await self._session.execute(stmt)
        await self._session.flush()
        return result.rowcount

    async def clear_match_data_by_case(self, case_id: UUID) -> int:
        stmt = (
            update(LedgerEntryModel)
            .where(LedgerEntryModel.case_id == case_id)
            .values(match_id=None, pass_number=None, confidence_score=None)
        )
        result = await self._session.execute(stmt)
        await self._session.flush()
        return result.rowcount

    async def count_by_case(self, case_id: UUID, side: str | None = None) -> int:
        conditions = [LedgerEntryModel.case_id == case_id]
        if side:
            conditions.append(LedgerEntryModel.side == side)

        stmt = select(func.count(LedgerEntryModel.id)).where(and_(*conditions))
        result = await self._session.execute(stmt)
        return result.scalar_one()

    async def sum_amount_by_case(self, case_id: UUID, side: str) -> float:
        stmt = select(func.coalesce(func.sum(LedgerEntryModel.amount), 0)).where(
            and_(
                LedgerEntryModel.case_id == case_id,
                LedgerEntryModel.side == side,
            )
        )
        result = await self._session.execute(stmt)
        return float(result.scalar_one())

    @staticmethod
    def _build_filter_conditions(filters: LedgerEntryFilters | None) -> list:
        """Build SQLAlchemy filter conditions from LedgerEntryFilters."""
        conditions = []
        if filters is None:
            return conditions

        if filters.side:
            conditions.append(LedgerEntryModel.side == filters.side)
        if filters.match_id:
            conditions.append(LedgerEntryModel.match_id == filters.match_id)
        if filters.is_matched is True:
            conditions.append(LedgerEntryModel.match_id.isnot(None))
        elif filters.is_matched is False:
            conditions.append(LedgerEntryModel.match_id.is_(None))
        if filters.document_type:
            conditions.append(LedgerEntryModel.document_type == filters.document_type)

        return conditions
