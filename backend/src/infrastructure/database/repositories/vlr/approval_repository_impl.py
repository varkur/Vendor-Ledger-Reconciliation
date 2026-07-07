"""
Approval repository implementation (Adapter).
Implements IApprovalRepository using async SQLAlchemy with company_code scoping
and pagination support.
"""

from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.repositories.vlr.approval_repository import IApprovalRepository
from src.domain.repositories.vlr.vendor_repository import PaginatedResult, PaginationParams
from src.infrastructure.database.models.vlr.approval_record_model import ApprovalRecordModel
from src.infrastructure.database.models.vlr.reconciliation_case_model import ReconciliationCaseModel
from src.infrastructure.database.models.vlr.reconciliation_request_model import ReconciliationRequestModel


class ApprovalRepositoryImpl(IApprovalRepository):
    """Concrete implementation of approval persistence using async SQLAlchemy."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, approval_id: UUID) -> ApprovalRecordModel | None:
        stmt = select(ApprovalRecordModel).where(ApprovalRecordModel.id == approval_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def create(self, approval_data: dict) -> ApprovalRecordModel:
        model = ApprovalRecordModel(**approval_data)
        self._session.add(model)
        await self._session.flush()
        return model

    async def list_by_case(
        self,
        case_id: UUID,
        pagination: PaginationParams | None = None,
    ) -> PaginatedResult:
        pagination = pagination or PaginationParams()

        base_condition = ApprovalRecordModel.case_id == case_id

        # Count query
        count_stmt = select(func.count(ApprovalRecordModel.id)).where(base_condition)
        total = (await self._session.execute(count_stmt)).scalar_one()

        # Data query
        data_stmt = (
            select(ApprovalRecordModel)
            .where(base_condition)
            .order_by(ApprovalRecordModel.decision_date.desc())
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

    async def get_pending_approvals(
        self,
        approver_id: UUID,
        company_code: str,
        pagination: PaginationParams | None = None,
    ) -> PaginatedResult:
        """Get cases pending approval by joining through case -> request for company scoping."""
        pagination = pagination or PaginationParams()

        # Cases in pending_approval status assigned to this approver's company
        base_stmt = (
            select(ReconciliationCaseModel)
            .join(
                ReconciliationRequestModel,
                ReconciliationCaseModel.request_id == ReconciliationRequestModel.id,
            )
            .where(
                and_(
                    ReconciliationRequestModel.company_code == company_code,
                    ReconciliationRequestModel.assigned_manager_id == approver_id,
                    ReconciliationCaseModel.status == "pending_approval",
                    ReconciliationCaseModel.is_deleted == False,  # noqa: E712
                )
            )
        )

        # Count query
        count_stmt = select(func.count()).select_from(base_stmt.subquery())
        total = (await self._session.execute(count_stmt)).scalar_one()

        # Data query
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

    async def get_latest_by_case(self, case_id: UUID) -> ApprovalRecordModel | None:
        stmt = (
            select(ApprovalRecordModel)
            .where(ApprovalRecordModel.case_id == case_id)
            .order_by(ApprovalRecordModel.decision_date.desc())
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def count_pending(self, approver_id: UUID, company_code: str) -> int:
        stmt = (
            select(func.count(ReconciliationCaseModel.id))
            .join(
                ReconciliationRequestModel,
                ReconciliationCaseModel.request_id == ReconciliationRequestModel.id,
            )
            .where(
                and_(
                    ReconciliationRequestModel.company_code == company_code,
                    ReconciliationRequestModel.assigned_manager_id == approver_id,
                    ReconciliationCaseModel.status == "pending_approval",
                    ReconciliationCaseModel.is_deleted == False,  # noqa: E712
                )
            )
        )
        result = await self._session.execute(stmt)
        return result.scalar_one()
