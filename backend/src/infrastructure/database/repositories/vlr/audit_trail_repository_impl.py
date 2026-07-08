"""
Audit trail repository implementation (Adapter).
Implements IAuditTrailRepository using async SQLAlchemy.

This repository is APPEND-ONLY — no update or delete operations are exposed.

Requirements: 38.1, 38.4
"""

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.repositories.vlr.audit_trail_repository import (
    AuditSearchFilters,
    IAuditTrailRepository,
)
from src.domain.repositories.vlr.vendor_repository import PaginatedResult, PaginationParams
from src.infrastructure.database.models.vlr.audit_event_model import AuditEventModel


class AuditTrailRepositoryImpl(IAuditTrailRepository):
    """
    Concrete implementation of audit trail persistence using async SQLAlchemy.

    Only supports append() and search() — no update or delete operations.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def append(self, event_data: dict) -> AuditEventModel:
        """Persist a new audit event (append-only)."""
        model = AuditEventModel(**event_data)
        self._session.add(model)
        await self._session.flush()
        return model

    async def search(
        self,
        filters: AuditSearchFilters | None = None,
        pagination: PaginationParams | None = None,
    ) -> PaginatedResult:
        """Search audit events with filters and pagination."""
        pagination = pagination or PaginationParams()

        base_stmt = select(AuditEventModel)

        filter_conditions = self._build_filter_conditions(filters)
        if filter_conditions:
            base_stmt = base_stmt.where(and_(*filter_conditions))

        # Count query
        count_stmt = select(func.count()).select_from(base_stmt.subquery())
        total = (await self._session.execute(count_stmt)).scalar_one()

        # Data query with pagination, ordered by most recent first
        data_stmt = (
            base_stmt.order_by(AuditEventModel.timestamp.desc())
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

    @staticmethod
    def _build_filter_conditions(filters: AuditSearchFilters | None) -> list:
        """Build SQLAlchemy filter conditions from AuditSearchFilters."""
        conditions = []
        if filters is None:
            return conditions

        if filters.actor_username:
            conditions.append(
                AuditEventModel.actor_username.ilike(f"%{filters.actor_username}%")
            )
        if filters.event_type:
            conditions.append(AuditEventModel.event_type == filters.event_type)
        if filters.case_id:
            conditions.append(AuditEventModel.case_id == str(filters.case_id))
        if filters.date_from:
            conditions.append(AuditEventModel.timestamp >= filters.date_from)
        if filters.date_to:
            conditions.append(AuditEventModel.timestamp <= filters.date_to)

        return conditions
