"""
Approval Matrix Service.
Resolves approvers based on configurable rules and creates approval tasks.
"""
import logging
from uuid import UUID, uuid4
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.application.services.workflow.rule_evaluator import RuleEvaluator

logger = logging.getLogger(__name__)


class ApprovalMatrixService:
    """Resolves approvers and creates approval tasks based on configurable matrix rules."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._rule_evaluator = RuleEvaluator()

    async def resolve_approvers(self, entity_type: str, entity_data: dict) -> list[dict]:
        """
        Find matching approval matrix and return ordered list of approvers.

        Returns list of dicts: [{"level": 1, "assignment_type": "ROLE", "role_id": ..., "user_id": ...}]
        """
        from src.infrastructure.database.models.workflow.approval_matrix_models import (
            ApprovalMatrixModel,
            ApprovalRuleModel,
            ApprovalAssignmentModel,
        )

        # Find all active matrices for this entity type
        stmt = (
            select(ApprovalMatrixModel)
            .where(
                ApprovalMatrixModel.entity_type == entity_type,
                ApprovalMatrixModel.is_active == True,
            )
            .order_by(ApprovalMatrixModel.priority)
        )
        result = await self._session.execute(stmt)
        matrices = result.scalars().all()

        for matrix in matrices:
            # Load rules for this matrix
            rules_stmt = select(ApprovalRuleModel).where(
                ApprovalRuleModel.matrix_id == str(matrix.id)
            )
            rules_result = await self._session.execute(rules_stmt)
            rules = [
                {
                    "field": r.field,
                    "operator": r.operator,
                    "value": r.value,
                    "data_type": r.data_type,
                    "logical_group": r.logical_group,
                }
                for r in rules_result.scalars().all()
            ]

            # Evaluate rules
            if self._rule_evaluator.evaluate_rules(rules, entity_data):
                # Match found — load assignments
                assign_stmt = (
                    select(ApprovalAssignmentModel)
                    .where(ApprovalAssignmentModel.matrix_id == str(matrix.id))
                    .order_by(ApprovalAssignmentModel.level)
                )
                assign_result = await self._session.execute(assign_stmt)
                assignments = assign_result.scalars().all()

                logger.info("Matrix '%s' matched for entity_type=%s", matrix.code, entity_type)

                return [
                    {
                        "level": a.level,
                        "assignment_type": a.assignment_type,
                        "user_id": a.user_id,
                        "role_id": a.role_id,
                    }
                    for a in assignments
                ]

        logger.warning("No approval matrix matched for entity_type=%s", entity_type)
        return []

    async def create_approval_task(
        self,
        instance_id: UUID,
        assignee_id: UUID,
        level: int,
        matrix_id: UUID | None = None,
        due_date: datetime | None = None,
    ) -> dict:
        """Create an approval task for a specific assignee."""
        from src.infrastructure.database.models.workflow.approval_matrix_models import ApprovalTaskModel

        task = ApprovalTaskModel(
            id=uuid4(),
            instance_id=str(instance_id),
            matrix_id=str(matrix_id) if matrix_id else None,
            assignee_id=str(assignee_id),
            level=level,
            status="PENDING",
            action_taken=None,
            due_date=due_date,
            comments=None,
            created_by="system",
            modified_by="system",
        )
        self._session.add(task)

        logger.info("Approval task created: instance=%s assignee=%s level=%d", instance_id, assignee_id, level)

        return {
            "task_id": str(task.id),
            "instance_id": str(instance_id),
            "assignee_id": str(assignee_id),
            "level": level,
            "status": "PENDING",
        }
