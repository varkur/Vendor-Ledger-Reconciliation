"""
State Machine Service.
Manages state transitions for workflow instances.
Validates transitions against configured rules and executes them atomically.
"""
import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.entities.workflow.value_objects import StateType

logger = logging.getLogger(__name__)


class StateMachineService:
    """Core state machine — validates and executes state transitions."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_current_state(self, instance_id: UUID) -> dict:
        """Get the current state of a workflow instance."""
        from src.infrastructure.database.models.workflow.workflow_models import (
            WorkflowInstanceModel,
            WorkflowStatusModel,
        )
        stmt = select(WorkflowInstanceModel).where(WorkflowInstanceModel.id == str(instance_id))
        result = await self._session.execute(stmt)
        instance = result.scalar_one_or_none()
        if not instance:
            raise ValueError(f"Instance {instance_id} not found")

        status_stmt = select(WorkflowStatusModel).where(
            WorkflowStatusModel.id == instance.current_status_id
        )
        status_result = await self._session.execute(status_stmt)
        status = status_result.scalar_one_or_none()

        return {
            "instance_id": str(instance.id),
            "status_id": str(status.id) if status else None,
            "status_code": status.code if status else None,
            "status_name": status.name if status else None,
            "is_terminal": status.is_terminal if status else False,
        }

    async def get_available_actions(self, instance_id: UUID) -> list[dict]:
        """Get actions available from the current state."""
        from src.infrastructure.database.models.workflow.workflow_models import (
            WorkflowInstanceModel,
            WorkflowTransitionModel,
        )
        stmt = select(WorkflowInstanceModel).where(WorkflowInstanceModel.id == str(instance_id))
        result = await self._session.execute(stmt)
        instance = result.scalar_one_or_none()
        if not instance:
            return []

        trans_stmt = select(WorkflowTransitionModel).where(
            WorkflowTransitionModel.workflow_definition_id == instance.workflow_definition_id,
            WorkflowTransitionModel.from_status_id == instance.current_status_id,
        ).order_by(WorkflowTransitionModel.priority)

        trans_result = await self._session.execute(trans_stmt)
        transitions = trans_result.scalars().all()

        return [
            {
                "action_code": t.action_code,
                "requires_comment": t.requires_comment,
            }
            for t in transitions
        ]

    async def validate_transition(self, instance_id: UUID, action_code: str) -> dict | None:
        """Validate if a transition is allowed. Returns the transition or None."""
        from src.infrastructure.database.models.workflow.workflow_models import (
            WorkflowInstanceModel,
            WorkflowTransitionModel,
        )
        stmt = select(WorkflowInstanceModel).where(WorkflowInstanceModel.id == str(instance_id))
        result = await self._session.execute(stmt)
        instance = result.scalar_one_or_none()
        if not instance:
            return None

        trans_stmt = select(WorkflowTransitionModel).where(
            WorkflowTransitionModel.workflow_definition_id == instance.workflow_definition_id,
            WorkflowTransitionModel.from_status_id == instance.current_status_id,
            WorkflowTransitionModel.action_code == action_code,
        )
        trans_result = await self._session.execute(trans_stmt)
        transition = trans_result.scalar_one_or_none()

        if not transition:
            return None

        return {
            "transition_id": str(transition.id),
            "from_status_id": str(transition.from_status_id),
            "to_status_id": str(transition.to_status_id),
            "action_code": transition.action_code,
            "requires_comment": transition.requires_comment,
        }

    async def execute_transition(
        self,
        instance_id: UUID,
        action_code: str,
        actor_id: UUID,
        actor_username: str,
        comments: str = "",
        ip_address: str = "",
    ) -> dict:
        """Execute a state transition. Updates instance and creates history entry."""
        from src.infrastructure.database.models.workflow.workflow_models import (
            WorkflowInstanceModel,
            WorkflowTransitionModel,
            WorkflowHistoryModel,
            WorkflowStatusModel,
        )
        from uuid import uuid4
        from datetime import datetime, timezone

        # Validate transition exists
        transition_data = await self.validate_transition(instance_id, action_code)
        if not transition_data:
            raise ValueError(
                f"Invalid transition: action '{action_code}' not allowed from current state"
            )

        # Get instance
        stmt = select(WorkflowInstanceModel).where(WorkflowInstanceModel.id == str(instance_id))
        result = await self._session.execute(stmt)
        instance = result.scalar_one()

        old_status_id = instance.current_status_id

        # Update instance state
        instance.current_status_id = transition_data["to_status_id"]

        # Check if new state is terminal
        new_status_stmt = select(WorkflowStatusModel).where(
            WorkflowStatusModel.id == transition_data["to_status_id"]
        )
        new_status_result = await self._session.execute(new_status_stmt)
        new_status = new_status_result.scalar_one()

        if new_status.is_terminal:
            instance.completed_at = datetime.now(timezone.utc)

        # Create history entry
        history = WorkflowHistoryModel(
            id=uuid4(),
            instance_id=str(instance_id),
            from_status_id=old_status_id,
            to_status_id=transition_data["to_status_id"],
            action_code=action_code,
            actor_id=str(actor_id),
            actor_username=actor_username,
            comments=comments,
            ip_address=ip_address,
            created_at=datetime.now(timezone.utc),
        )
        self._session.add(history)

        logger.info(
            "State transition executed: instance=%s action=%s to=%s",
            instance_id, action_code, new_status.code,
        )

        return {
            "instance_id": str(instance_id),
            "previous_status": old_status_id,
            "current_status_id": str(new_status.id),
            "current_status_code": new_status.code,
            "is_completed": new_status.is_terminal,
        }
