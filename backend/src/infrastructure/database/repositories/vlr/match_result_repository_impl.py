"""
Match Result repository implementation (Adapter).
Implements IMatchResultRepository using async SQLAlchemy with pagination support.
"""

from uuid import UUID

from sqlalchemy import and_, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.repositories.vlr.match_result_repository import IMatchResultRepository
from src.domain.repositories.vlr.vendor_repository import PaginatedResult, PaginationParams
from src.infrastructure.database.models.vlr.match_result_model import MatchResultModel


class MatchResultRepositoryImpl(IMatchResultRepository):
    """Concrete implementation of match result persistence using async SQLAlchemy."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, match_id: UUID) -> MatchResultModel | None:
        stmt = select(MatchResultModel).where(MatchResultModel.id == match_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def create(self, match_data: dict) -> MatchResultModel:
        model = MatchResultModel(**match_data)
        self._session.add(model)
        await self._session.flush()
        return model

    async def bulk_create(self, matches_data: list[dict]) -> list[MatchResultModel]:
        models = [MatchResultModel(**data) for data in matches_data]
        self._session.add_all(models)
        await self._session.flush()
        return models

    async def list_by_case(
        self,
        case_id: UUID,
        pagination: PaginationParams | None = None,
    ) -> PaginatedResult:
        pagination = pagination or PaginationParams()

        base_condition = MatchResultModel.case_id == case_id

        # Count query
        count_stmt = select(func.count(MatchResultModel.id)).where(base_condition)
        total = (await self._session.execute(count_stmt)).scalar_one()

        # Data query
        data_stmt = (
            select(MatchResultModel)
            .where(base_condition)
            .order_by(MatchResultModel.pass_number, MatchResultModel.created_date)
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

    async def get_by_case_and_pass(self, case_id: UUID, pass_number: int) -> list[MatchResultModel]:
        stmt = select(MatchResultModel).where(
            and_(
                MatchResultModel.case_id == case_id,
                MatchResultModel.pass_number == pass_number,
            )
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def delete_by_case(self, case_id: UUID) -> int:
        stmt = delete(MatchResultModel).where(MatchResultModel.case_id == case_id)
        result = await self._session.execute(stmt)
        await self._session.flush()
        return result.rowcount

    async def get_statistics_by_case(self, case_id: UUID) -> dict:
        """
        Get match statistics per pass for a case.
        Returns dict with pass_number -> {match_count, matched_amount}.
        """
        stmt = (
            select(
                MatchResultModel.pass_number,
                func.count(MatchResultModel.id).label("match_count"),
                func.sum(MatchResultModel.matched_amount).label("matched_amount"),
            )
            .where(MatchResultModel.case_id == case_id)
            .group_by(MatchResultModel.pass_number)
        )
        result = await self._session.execute(stmt)
        return {
            row.pass_number: {
                "match_count": row.match_count,
                "matched_amount": float(row.matched_amount) if row.matched_amount else 0.0,
            }
            for row in result.all()
        }

    async def get_unconfirmed_by_case(self, case_id: UUID) -> list[MatchResultModel]:
        stmt = select(MatchResultModel).where(
            and_(
                MatchResultModel.case_id == case_id,
                MatchResultModel.is_confirmed == False,  # noqa: E712
            )
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def confirm_match(self, match_id: UUID) -> MatchResultModel:
        stmt = select(MatchResultModel).where(MatchResultModel.id == match_id)
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        if model is None:
            raise ValueError(f"Match result with id {match_id} not found")

        model.is_confirmed = True
        await self._session.flush()
        return model

    async def count_by_case(self, case_id: UUID) -> int:
        stmt = select(func.count(MatchResultModel.id)).where(
            MatchResultModel.case_id == case_id
        )
        result = await self._session.execute(stmt)
        return result.scalar_one()
