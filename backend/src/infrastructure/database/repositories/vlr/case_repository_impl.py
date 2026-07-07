"""
Reconciliation Case repository implementation (Adapter).
Implements ICaseRepository using async SQLAlchemy with soft-delete filtering
and pagination support.
"""

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.repositories.vlr.case_repository import (
    CaseFilters,
    ICaseRepository,
)
from src.domain.repositories.vlr.vendor_repository import PaginatedResult, PaginationParams
from src.infrastructure.database.models.vlr.reconciliation_case_model import ReconciliationCaseModel
from src.infrastructure.database.models.vlr.reconciliation_request_model import ReconciliationRequestModel


class CaseRepositoryImpl(ICaseRepository):
    """Concrete implementation of case persistence using async SQLAlchemy."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, case_id: UUID, company_code: str | None = None) -> ReconciliationCaseModel | None:
        conditions = [
            ReconciliationCaseModel.id == case_id,
            ReconciliationCaseModel.is_deleted == False,  # noqa: E712
        ]

        if company_code:
            stmt = (
                select(ReconciliationCaseModel)
                .join(
                    ReconciliationRequestModel,
                    ReconciliationCaseModel.request_id == ReconciliationRequestModel.id,
                )
                .where(
                    and_(
                        *conditions,
                        ReconciliationRequestModel.company_code == company_code,
                    )
                )
            )
        else:
            stmt = select(ReconciliationCaseModel).where(and_(*conditions))

        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_token(self, portal_token: str) -> ReconciliationCaseModel | None:
        stmt = select(ReconciliationCaseModel).where(
            and_(
                ReconciliationCaseModel.portal_token == portal_token,
                ReconciliationCaseModel.is_deleted == False,  # noqa: E712
            )
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def create(self, case_data: dict) -> ReconciliationCaseModel:
        model = ReconciliationCaseModel(**case_data)
        self._session.add(model)
        await self._session.flush()
        return model

    async def bulk_create(self, cases_data: list[dict]) -> list[ReconciliationCaseModel]:
        models = [ReconciliationCaseModel(**data) for data in cases_data]
        self._session.add_all(models)
        await self._session.flush()
        return models

    async def update(self, case_id: UUID, update_data: dict) -> ReconciliationCaseModel:
        stmt = select(ReconciliationCaseModel).where(
            and_(
                ReconciliationCaseModel.id == case_id,
                ReconciliationCaseModel.is_deleted == False,  # noqa: E712
            )
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        if model is None:
            raise ValueError(f"Case with id {case_id} not found")

        for key, value in update_data.items():
            setattr(model, key, value)

        await self._session.flush()
        return model

    async def soft_delete(self, case_id: UUID) -> None:
        stmt = select(ReconciliationCaseModel).where(
            and_(
                ReconciliationCaseModel.id == case_id,
                ReconciliationCaseModel.is_deleted == False,  # noqa: E712
            )
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        if model is None:
            raise ValueError(f"Case with id {case_id} not found")

        model.is_deleted = True
        model.deleted_at = datetime.now(timezone.utc)
        await self._session.flush()

    async def list_cases(
        self,
        company_code: str,
        filters: CaseFilters | None = None,
        pagination: PaginationParams | None = None,
    ) -> PaginatedResult:
        pagination = pagination or PaginationParams()

        base_stmt = (
            select(ReconciliationCaseModel)
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

        # Data query with pagination
        data_stmt = (
            base_stmt.order_by(ReconciliationCaseModel.created_date.desc())
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

    async def list_by_request(
        self,
        request_id: UUID,
        pagination: PaginationParams | None = None,
    ) -> PaginatedResult:
        pagination = pagination or PaginationParams()

        base_conditions = and_(
            ReconciliationCaseModel.request_id == request_id,
            ReconciliationCaseModel.is_deleted == False,  # noqa: E712
        )

        # Count query
        count_stmt = select(func.count(ReconciliationCaseModel.id)).where(base_conditions)
        total = (await self._session.execute(count_stmt)).scalar_one()

        # Data query
        data_stmt = (
            select(ReconciliationCaseModel)
            .where(base_conditions)
            .order_by(ReconciliationCaseModel.created_date.desc())
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

    async def get_active_cases_for_vendor(self, vendor_id: UUID) -> list[ReconciliationCaseModel]:
        stmt = select(ReconciliationCaseModel).where(
            and_(
                ReconciliationCaseModel.vendor_id == vendor_id,
                ReconciliationCaseModel.is_deleted == False,  # noqa: E712
                ReconciliationCaseModel.status != "closed",
            )
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def increment_upload_count(self, case_id: UUID) -> int:
        stmt = select(ReconciliationCaseModel).where(
            and_(
                ReconciliationCaseModel.id == case_id,
                ReconciliationCaseModel.is_deleted == False,  # noqa: E712
            )
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        if model is None:
            raise ValueError(f"Case with id {case_id} not found")

        model.upload_count = model.upload_count + 1
        await self._session.flush()
        return model.upload_count

    async def increment_edit_count(self, case_id: UUID) -> int:
        stmt = select(ReconciliationCaseModel).where(
            and_(
                ReconciliationCaseModel.id == case_id,
                ReconciliationCaseModel.is_deleted == False,  # noqa: E712
            )
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        if model is None:
            raise ValueError(f"Case with id {case_id} not found")

        model.edit_count = model.edit_count + 1
        await self._session.flush()
        return model.edit_count

    async def count_by_request(self, request_id: UUID) -> int:
        stmt = select(func.count(ReconciliationCaseModel.id)).where(
            and_(
                ReconciliationCaseModel.request_id == request_id,
                ReconciliationCaseModel.is_deleted == False,  # noqa: E712
            )
        )
        result = await self._session.execute(stmt)
        return result.scalar_one()

    async def count_by_status(self, request_id: UUID) -> dict[str, int]:
        stmt = (
            select(
                ReconciliationCaseModel.status,
                func.count(ReconciliationCaseModel.id).label("count"),
            )
            .where(
                and_(
                    ReconciliationCaseModel.request_id == request_id,
                    ReconciliationCaseModel.is_deleted == False,  # noqa: E712
                )
            )
            .group_by(ReconciliationCaseModel.status)
        )
        result = await self._session.execute(stmt)
        return {row.status: row.count for row in result.all()}

    @staticmethod
    def _build_filter_conditions(filters: CaseFilters | None) -> list:
        """Build SQLAlchemy filter conditions from CaseFilters."""
        conditions = []
        if filters is None:
            return conditions

        if filters.status:
            conditions.append(ReconciliationCaseModel.status == filters.status)
        if filters.vendor_id:
            conditions.append(ReconciliationCaseModel.vendor_id == filters.vendor_id)
        if filters.request_id:
            conditions.append(ReconciliationCaseModel.request_id == filters.request_id)
        if filters.case_type:
            conditions.append(ReconciliationCaseModel.case_type == filters.case_type)

        return conditions
