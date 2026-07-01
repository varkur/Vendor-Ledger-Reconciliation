"""
Workflow Engine — Orchestration Service.
Coordinates state machine, approval matrix, events, and audit trail.
This is the primary entry point for business modules to interact with the workflow system.
"""
import logging
from uuid import UUID, uuid4
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.application.services.workflow.state_machine_service import StateMachineService
from src.application.services.workflow.approval_matrix_service import ApprovalMatrixService

logger = logging.getLogger(__name__)


class WorkflowEngine:
    """
    Central orchestrator for workflow execution.

    Business modules call this service to:
    - Start a workflow
    - Execute actions (approve, reject, refer back, etc.)
    - Query pending tasks
    - Cancel workflows

    No workflow logic should exist in business modules.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._state_machine = StateMachineService(session)
        self._approval_matrix = ApprovalMatrixService(session)

    async def start_workflow(
        self,
        definition_code: str,
        entity_type: str,
        entity_id: UUID,
        initiated_by: UUID,
        metadata: dict[str, Any] | None = None,
    ) -> dict:
        """
        Start a new workflow instance.

        1. Looks up workflow definition by code
        2. Creates instance in initial state
        3. Returns instance info
        """
        from src.infrastructure.database.models.workflow.workflow_models import (
            WorkflowDefinitionModel,
            WorkflowStatusModel,
            WorkflowInstanceModel,
        )

        # Find active definition
        stmt = select(WorkflowDefinitionModel).where(
            WorkflowDefinitionModel.code == definition_code,
            WorkflowDefinitionModel.is_active == True,
        )
        result = await self._session.execute(stmt)
        definition = result.scalar_one_or_none()

        if not definition:
            raise ValueError(f"Workflow definition '{definition_code}' not found or inactive")

        # Find initial status
        status_stmt = select(WorkflowStatusModel).where(
            WorkflowStatusModel.workflow_definition_id == str(definition.id),
            WorkflowStatusModel.is_initial == True,
        )
        status_result = await self._session.execute(status_stmt)
        initial_status = status_result.scalar_one_or_none()

        if not initial_status:
            raise ValueError(f"No initial status defined for workflow '{definition_code}'")

        # Create instance
        instance = WorkflowInstanceModel(
            id=uuid4(),
            workflow_definition_id=str(definition.id),
            entity_type=entity_type,
            entity_id=str(entity_id),
            current_status_id=str(initial_status.id),
            initiated_by=str(initiated_by),
            priority=0,
            started_at=datetime.now(timezone.utc),
            extra_data=metadata or {},
            created_by="system",
            modified_by="system",
        )
        self._session.add(instance)

        logger.info(
            "Workflow started: definition=%s entity=%s/%s instance=%s",
            definition_code, entity_type, entity_id, instance.id,
        )

        return {
            "instance_id": str(instance.id),
            "definition_code": definition_code,
            "current_status": initial_status.code,
            "started_at": instance.started_at.isoformat(),
        }

    async def execute_action(
        self,
        instance_id: UUID,
        action_code: str,
        actor_id: UUID,
        actor_username: str,
        comments: str = "",
        ip_address: str = "",
    ) -> dict:
        """
        Execute a workflow action (approve, reject, refer back, etc.).

        1. Validates the transition is allowed
        2. Executes state transition
        3. Resolves next approver if needed
        4. Creates approval task
        5. Returns new state
        """
        # Execute state transition
        transition_result = await self._state_machine.execute_transition(
            instance_id=instance_id,
            action_code=action_code,
            actor_id=actor_id,
            actor_username=actor_username,
            comments=comments,
            ip_address=ip_address,
        )

        logger.info(
            "Action executed: instance=%s action=%s new_status=%s",
            instance_id, action_code, transition_result["current_status_code"],
        )

        return transition_result

    async def get_available_actions(self, instance_id: UUID) -> list[dict]:
        """Get actions available for the current state of a workflow instance."""
        return await self._state_machine.get_available_actions(instance_id)

    async def get_workflow_status(self, instance_id: UUID) -> dict:
        """Get current status of a workflow instance."""
        return await self._state_machine.get_current_state(instance_id)

    async def get_pending_tasks(self, user_id: UUID) -> list[dict]:
        """Get all pending approval tasks assigned to a user."""
        from src.infrastructure.database.models.workflow.approval_matrix_models import ApprovalTaskModel
        from src.infrastructure.database.models.workflow.workflow_models import WorkflowInstanceModel

        stmt = select(ApprovalTaskModel).where(
            ApprovalTaskModel.assignee_id == str(user_id),
            ApprovalTaskModel.status == "PENDING",
        )
        result = await self._session.execute(stmt)
        tasks = result.scalars().all()

        return [
            {
                "task_id": str(t.id),
                "instance_id": str(t.instance_id),
                "level": t.level,
                "status": t.status,
                "due_date": t.due_date.isoformat() if t.due_date else None,
            }
            for t in tasks
        ]
