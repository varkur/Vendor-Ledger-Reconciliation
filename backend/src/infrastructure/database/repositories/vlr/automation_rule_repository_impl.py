"""
Automation Rule repository implementation (Adapter).
Implements IAutomationRuleRepository using async SQLAlchemy with company_code scoping
and pagination support.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.repositories.vlr.automation_rule_repository import IAutomationRuleRepository
from src.domain.repositories.vlr.vendor_repository import PaginatedResult, PaginationParams
from src.infrastructure.database.models.vlr.automation_execution_model import AutomationExecutionModel
from src.infrastructure.database.models.vlr.automation_rule_model import AutomationRuleModel


class AutomationRuleRepositoryImpl(IAutomationRuleRepository):
    """Concrete implementation of automation rule persistence using async SQLAlchemy."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, rule_id: UUID) -> AutomationRuleModel | None:
        stmt = select(AutomationRuleModel).where(AutomationRuleModel.id == rule_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def create(self, rule_data: dict) -> AutomationRuleModel:
        model = AutomationRuleModel(**rule_data)
        self._session.add(model)
        await self._session.flush()
        return model

    async def update(self, rule_id: UUID, update_data: dict) -> AutomationRuleModel:
        stmt = select(AutomationRuleModel).where(AutomationRuleModel.id == rule_id)
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        if model is None:
            raise ValueError(f"Automation rule with id {rule_id} not found")

        for key, value in update_data.items():
            setattr(model, key, value)

        await self._session.flush()
        return model

    async def list_by_company(
        self,
        company_code: str,
        pagination: PaginationParams | None = None,
    ) -> PaginatedResult:
        pagination = pagination or PaginationParams()

        base_condition = AutomationRuleModel.company_code == company_code

        # Count query
        count_stmt = select(func.count(AutomationRuleModel.id)).where(base_condition)
        total = (await self._session.execute(count_stmt)).scalar_one()

        # Data query
        data_stmt = (
            select(AutomationRuleModel)
            .where(base_condition)
            .order_by(AutomationRuleModel.created_date.desc())
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

    async def get_active_rules(self, company_code: str) -> list[AutomationRuleModel]:
        stmt = select(AutomationRuleModel).where(
            and_(
                AutomationRuleModel.company_code == company_code,
                AutomationRuleModel.is_active == True,  # noqa: E712
            )
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_due_rules(self, before: datetime) -> list[AutomationRuleModel]:
        stmt = select(AutomationRuleModel).where(
            and_(
                AutomationRuleModel.is_active == True,  # noqa: E712
                AutomationRuleModel.next_execution <= before,
            )
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def record_execution(self, execution_data: dict) -> AutomationExecutionModel:
        model = AutomationExecutionModel(**execution_data)
        self._session.add(model)
        await self._session.flush()
        return model

    async def get_execution_history(
        self,
        rule_id: UUID,
        pagination: PaginationParams | None = None,
    ) -> PaginatedResult:
        pagination = pagination or PaginationParams()

        base_condition = AutomationExecutionModel.rule_id == rule_id

        # Count query
        count_stmt = select(func.count(AutomationExecutionModel.id)).where(base_condition)
        total = (await self._session.execute(count_stmt)).scalar_one()

        # Data query
        data_stmt = (
            select(AutomationExecutionModel)
            .where(base_condition)
            .order_by(AutomationExecutionModel.triggered_at.desc())
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

    async def deactivate(self, rule_id: UUID) -> AutomationRuleModel:
        stmt = select(AutomationRuleModel).where(AutomationRuleModel.id == rule_id)
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        if model is None:
            raise ValueError(f"Automation rule with id {rule_id} not found")

        model.is_active = False
        await self._session.flush()
        return model

    async def activate(self, rule_id: UUID) -> AutomationRuleModel:
        stmt = select(AutomationRuleModel).where(AutomationRuleModel.id == rule_id)
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        if model is None:
            raise ValueError(f"Automation rule with id {rule_id} not found")

        model.is_active = True
        await self._session.flush()
        return model
