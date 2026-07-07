"""
Notification repository implementation (Adapter).
Implements INotificationRepository using async SQLAlchemy with pagination support.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.repositories.vlr.notification_repository import INotificationRepository
from src.domain.repositories.vlr.vendor_repository import PaginatedResult, PaginationParams
from src.infrastructure.database.models.vlr.notification_model import NotificationModel


class NotificationRepositoryImpl(INotificationRepository):
    """Concrete implementation of notification persistence using async SQLAlchemy."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, notification_id: UUID) -> NotificationModel | None:
        stmt = select(NotificationModel).where(NotificationModel.id == notification_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def create(self, notification_data: dict) -> NotificationModel:
        model = NotificationModel(**notification_data)
        self._session.add(model)
        await self._session.flush()
        return model

    async def update(self, notification_id: UUID, update_data: dict) -> NotificationModel:
        stmt = select(NotificationModel).where(NotificationModel.id == notification_id)
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        if model is None:
            raise ValueError(f"Notification with id {notification_id} not found")

        for key, value in update_data.items():
            setattr(model, key, value)

        await self._session.flush()
        return model

    async def list_by_case(
        self,
        case_id: UUID,
        pagination: PaginationParams | None = None,
    ) -> PaginatedResult:
        pagination = pagination or PaginationParams()

        base_condition = NotificationModel.case_id == case_id

        # Count query
        count_stmt = select(func.count(NotificationModel.id)).where(base_condition)
        total = (await self._session.execute(count_stmt)).scalar_one()

        # Data query
        data_stmt = (
            select(NotificationModel)
            .where(base_condition)
            .order_by(NotificationModel.created_date.desc())
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

    async def get_pending_retries(self, before: datetime) -> list[NotificationModel]:
        stmt = select(NotificationModel).where(
            and_(
                NotificationModel.status == "failed",
                NotificationModel.next_retry_date <= before,
                NotificationModel.retry_count < 3,
            )
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_reminders_for_case(self, case_id: UUID) -> list[NotificationModel]:
        stmt = select(NotificationModel).where(
            and_(
                NotificationModel.case_id == case_id,
                NotificationModel.type == "reminder",
            )
        ).order_by(NotificationModel.created_date.desc())
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count_reminders_for_case(self, case_id: UUID) -> int:
        stmt = select(func.count(NotificationModel.id)).where(
            and_(
                NotificationModel.case_id == case_id,
                NotificationModel.type == "reminder",
            )
        )
        result = await self._session.execute(stmt)
        return result.scalar_one()

    async def count_by_case(self, case_id: UUID) -> int:
        stmt = select(func.count(NotificationModel.id)).where(
            NotificationModel.case_id == case_id
        )
        result = await self._session.execute(stmt)
        return result.scalar_one()
