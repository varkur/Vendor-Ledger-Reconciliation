"""
Reconciliation Request repository implementation (Adapter).
Implements IRequestRepository using async SQLAlchemy with company_code scoping
and pagination support.
"""

from datetime import date
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.repositories.vlr.request_repository import (
    IRequestRepository,
    RequestFilters,
)
from src.domain.repositories.vlr.vendor_repository import PaginatedResult, PaginationParams
from src.infrastructure.database.models.vlr.reconciliation_case_model import ReconciliationCaseModel
from src.infrastructure.database.models.vlr.reconciliation_request_model import ReconciliationRequestModel


class RequestRepositoryImpl(IRequestRepository):
    """Concrete implementation of request persistence using async SQLAlchemy."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, request_id: UUID, company_code: str) -> ReconciliationRequestModel | None:
        stmt = select(ReconciliationRequestModel).where(
            and_(
                ReconciliationRequestModel.id == request_id,
                ReconciliationRequestModel.company_code == company_code,
            )
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def create(self, request_data: dict) -> ReconciliationRequestModel:
        model = ReconciliationRequestModel(**request_data)
        self._session.add(model)
        await self._session.flush()
        return model

    async def update(
        self, request_id: UUID, company_code: str, update_data: dict
    ) -> ReconciliationRequestModel:
        stmt = select(ReconciliationRequestModel).where(
            and_(
                ReconciliationRequestModel.id == request_id,
                ReconciliationRequestModel.company_code == company_code,
            )
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        if model is None:
            raise ValueError(
                f"Request with id {request_id} not found in company {company_code}"
            )

        for key, value in update_data.items():
            setattr(model, key, value)

        await self._session.flush()
        return model

    async def list_requests(
        self,
        company_code: str,
        filters: RequestFilters | None = None,
        pagination: PaginationParams | None = None,
    ) -> PaginatedResult:
        pagination = pagination or PaginationParams()

        base_condition = ReconciliationRequestModel.company_code == company_code
        filter_conditions = self._build_filter_conditions(filters)

        # Count query
        count_stmt = select(func.count(ReconciliationRequestModel.id)).where(
            and_(base_condition, *filter_conditions)
        )
        total = (await self._session.execute(count_stmt)).scalar_one()

        # Data query
        data_stmt = (
            select(ReconciliationRequestModel)
            .where(and_(base_condition, *filter_conditions))
            .order_by(ReconciliationRequestModel.created_date.desc())
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

    async def has_overlapping_period(
        self,
        vendor_id: UUID,
        company_code: str,
        period_start: date,
        period_end: date,
        exclude_request_id: UUID | None = None,
    ) -> bool:
        """
        Check for overlapping periods using the range overlap condition:
        start1 <= end2 AND start2 <= end1
        """
        # Join with cases to check vendor-specific overlap
        stmt = (
            select(func.count(ReconciliationCaseModel.id))
            .join(
                ReconciliationRequestModel,
                ReconciliationCaseModel.request_id == ReconciliationRequestModel.id,
            )
            .where(
                and_(
                    ReconciliationCaseModel.vendor_id == vendor_id,
                    ReconciliationCaseModel.is_deleted == False,  # noqa: E712
                    ReconciliationRequestModel.company_code == company_code,
                    ReconciliationRequestModel.period_start <= period_end,
                    ReconciliationRequestModel.period_end >= period_start,
                )
            )
        )

        if exclude_request_id:
            stmt = stmt.where(ReconciliationRequestModel.id != exclude_request_id)

        result = await self._session.execute(stmt)
        return result.scalar_one() > 0

    async def get_statistics(self, request_id: UUID, company_code: str) -> dict:
        """Get case counts by status for a request."""
        stmt = (
            select(
                ReconciliationCaseModel.status,
                func.count(ReconciliationCaseModel.id).label("count"),
            )
            .join(
                ReconciliationRequestModel,
                ReconciliationCaseModel.request_id == ReconciliationRequestModel.id,
            )
            .where(
                and_(
                    ReconciliationCaseModel.request_id == request_id,
                    ReconciliationCaseModel.is_deleted == False,  # noqa: E712
                    ReconciliationRequestModel.company_code == company_code,
                )
            )
            .group_by(ReconciliationCaseModel.status)
        )
        result = await self._session.execute(stmt)
        return {row.status: row.count for row in result.all()}

    async def count(self, company_code: str, filters: RequestFilters | None = None) -> int:
        base_condition = ReconciliationRequestModel.company_code == company_code
        filter_conditions = self._build_filter_conditions(filters)

        stmt = select(func.count(ReconciliationRequestModel.id)).where(
            and_(base_condition, *filter_conditions)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one()

    async def get_max_request_serial(self, code_prefix: str) -> int:
        """
        Return the highest numeric serial used in request_number values that
        start with "{code_prefix}-". Used to generate the next sequential
        request number per entity. Returns 0 if none exist.
        """
        like_pattern = f"{code_prefix}-%"
        stmt = select(ReconciliationRequestModel.request_number).where(
            ReconciliationRequestModel.request_number.like(like_pattern)
        )
        result = await self._session.execute(stmt)
        max_serial = 0
        for (rn,) in result.all():
            if not rn:
                continue
            tail = rn.rsplit("-", 1)[-1]
            try:
                val = int(tail)
                if val > max_serial:
                    max_serial = val
            except ValueError:
                continue
        return max_serial

    @staticmethod
    def _build_filter_conditions(filters: RequestFilters | None) -> list:
        """Build SQLAlchemy filter conditions from RequestFilters."""
        conditions = []
        if filters is None:
            return conditions

        if filters.status:
            conditions.append(ReconciliationRequestModel.status == filters.status)
        if filters.date_from:
            conditions.append(ReconciliationRequestModel.created_date >= filters.date_from)
        if filters.date_to:
            conditions.append(ReconciliationRequestModel.created_date <= filters.date_to)
        if filters.assigned_manager_id:
            conditions.append(
                ReconciliationRequestModel.assigned_manager_id == filters.assigned_manager_id
            )
        if filters.fiscal_year:
            conditions.append(ReconciliationRequestModel.fiscal_year == filters.fiscal_year)
        if filters.reco_type:
            conditions.append(ReconciliationRequestModel.reco_type == filters.reco_type)

        return conditions
