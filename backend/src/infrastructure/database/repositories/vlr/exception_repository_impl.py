"""
Exception repository implementation (Adapter).
Implements IExceptionRepository using async SQLAlchemy with company_code scoping
and pagination support.
"""

from uuid import UUID

from sqlalchemy import and_, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.repositories.vlr.exception_repository import (
    ExceptionFilters,
    IExceptionRepository,
)
from src.domain.repositories.vlr.vendor_repository import PaginatedResult, PaginationParams
from src.infrastructure.database.models.vlr.reco_exception_model import RecoExceptionModel
from src.infrastructure.database.models.vlr.reconciliation_case_model import ReconciliationCaseModel
from src.infrastructure.database.models.vlr.reconciliation_request_model import ReconciliationRequestModel


class ExceptionRepositoryImpl(IExceptionRepository):
    """Concrete implementation of exception persistence using async SQLAlchemy."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, exception_id: UUID) -> RecoExceptionModel | None:
        stmt = select(RecoExceptionModel).where(RecoExceptionModel.id == exception_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def create(self, exception_data: dict) -> RecoExceptionModel:
        model = RecoExceptionModel(**exception_data)
        self._session.add(model)
        await self._session.flush()
        return model

    async def bulk_create(self, exceptions_data: list[dict]) -> list[RecoExceptionModel]:
        models = [RecoExceptionModel(**data) for data in exceptions_data]
        self._session.add_all(models)
        await self._session.flush()
        return models

    async def update(self, exception_id: UUID, update_data: dict) -> RecoExceptionModel:
        stmt = select(RecoExceptionModel).where(RecoExceptionModel.id == exception_id)
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        if model is None:
            raise ValueError(f"Exception with id {exception_id} not found")

        for key, value in update_data.items():
            setattr(model, key, value)

        await self._session.flush()
        return model

    async def list_exceptions(
        self,
        company_code: str,
        filters: ExceptionFilters | None = None,
        pagination: PaginationParams | None = None,
    ) -> PaginatedResult:
        pagination = pagination or PaginationParams()

        # Join through case -> request for company_code scoping
        base_stmt = (
            select(RecoExceptionModel)
            .join(
                ReconciliationCaseModel,
                RecoExceptionModel.case_id == ReconciliationCaseModel.id,
            )
            .join(
                ReconciliationRequestModel,
                ReconciliationCaseModel.request_id == ReconciliationRequestModel.id,
            )
            .where(
                and_(
                    ReconciliationRequestModel.company_code == company_code,
                    ReconciliationCaseModel.is_deleted == False,  # noqa: E712
                )
            )
        )

        filter_conditions = self._build_filter_conditions(filters)
        if filter_conditions:
            base_stmt = base_stmt.where(and_(*filter_conditions))

        # Count query
        count_stmt = select(func.count()).select_from(base_stmt.subquery())
        total = (await self._session.execute(count_stmt)).scalar_one()

        # Data query
        data_stmt = (
            base_stmt.order_by(RecoExceptionModel.created_date.desc())
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

    async def list_by_case(
        self,
        case_id: UUID,
        filters: ExceptionFilters | None = None,
        pagination: PaginationParams | None = None,
    ) -> PaginatedResult:
        pagination = pagination or PaginationParams()

        base_condition = RecoExceptionModel.case_id == case_id
        filter_conditions = self._build_filter_conditions(filters)

        # Count query
        count_stmt = select(func.count(RecoExceptionModel.id)).where(
            and_(base_condition, *filter_conditions)
        )
        total = (await self._session.execute(count_stmt)).scalar_one()

        # Data query
        data_stmt = (
            select(RecoExceptionModel)
            .where(and_(base_condition, *filter_conditions))
            .order_by(RecoExceptionModel.created_date.desc())
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

    async def get_open_by_case(self, case_id: UUID) -> list[RecoExceptionModel]:
        stmt = select(RecoExceptionModel).where(
            and_(
                RecoExceptionModel.case_id == case_id,
                RecoExceptionModel.status == "open",
            )
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_critical_open_by_case(self, case_id: UUID) -> list[RecoExceptionModel]:
        stmt = select(RecoExceptionModel).where(
            and_(
                RecoExceptionModel.case_id == case_id,
                RecoExceptionModel.status == "open",
                RecoExceptionModel.severity == "critical",
            )
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def delete_by_case(self, case_id: UUID) -> int:
        stmt = delete(RecoExceptionModel).where(RecoExceptionModel.case_id == case_id)
        result = await self._session.execute(stmt)
        await self._session.flush()
        return result.rowcount

    async def count_by_case(self, case_id: UUID, status: str | None = None) -> int:
        conditions = [RecoExceptionModel.case_id == case_id]
        if status:
            conditions.append(RecoExceptionModel.status == status)

        stmt = select(func.count(RecoExceptionModel.id)).where(and_(*conditions))
        result = await self._session.execute(stmt)
        return result.scalar_one()

    async def count_by_severity(self, case_id: UUID) -> dict[str, int]:
        stmt = (
            select(
                RecoExceptionModel.severity,
                func.count(RecoExceptionModel.id).label("count"),
            )
            .where(RecoExceptionModel.case_id == case_id)
            .group_by(RecoExceptionModel.severity)
        )
        result = await self._session.execute(stmt)
        return {row.severity: row.count for row in result.all()}

    @staticmethod
    def _build_filter_conditions(filters: ExceptionFilters | None) -> list:
        """Build SQLAlchemy filter conditions from ExceptionFilters."""
        conditions = []
        if filters is None:
            return conditions

        if filters.case_id:
            conditions.append(RecoExceptionModel.case_id == filters.case_id)
        if filters.severity:
            conditions.append(RecoExceptionModel.severity == filters.severity)
        if filters.category:
            conditions.append(RecoExceptionModel.category == filters.category)
        if filters.status:
            conditions.append(RecoExceptionModel.status == filters.status)

        return conditions
