"""Workflow Application Service."""

from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.application.services.workflow.workflow_engine import WorkflowEngine
from src.infrastructure.database.models.workflow.workflow_models import (
    WorkflowDefinitionModel,
    WorkflowHistoryModel,
    WorkflowInstanceModel,
    WorkflowStatusModel,
    WorkflowTransitionModel,
)
from src.infrastructure.database.models.workflow.approval_matrix_models import (
    ApprovalAssignmentModel,
    ApprovalMatrixModel,
    ApprovalRuleModel,
)


class WorkflowService:
    """Application service for workflow definition management and runtime."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._engine = WorkflowEngine(session)

    # ═══════════════════════════════════════════════════════════════════
    # WORKFLOW DEFINITIONS
    # ═══════════════════════════════════════════════════════════════════

    async def list_definitions(self) -> dict:
        """List all workflow definitions. Returns dict with definitions and total."""
        stmt = select(WorkflowDefinitionModel).order_by(WorkflowDefinitionModel.code)
        result = await self._session.execute(stmt)
        definitions = list(result.scalars().all())
        return {"definitions": definitions, "total": len(definitions)}

    async def create_definition(
        self,
        *,
        code: str,
        name: str,
        description: str | None,
        entity_type: str,
        created_by: str,
    ) -> WorkflowDefinitionModel:
        """Create a new workflow definition."""
        existing = await self._session.execute(
            select(WorkflowDefinitionModel).where(WorkflowDefinitionModel.code == code)
        )
        if existing.scalar_one_or_none():
            raise ValueError(f"Workflow '{code}' already exists")

        definition = WorkflowDefinitionModel(
            id=uuid4(),
            code=code,
            name=name,
            description=description,
            entity_type=entity_type,
            version=1,
            is_active=True,
            created_by=created_by,
            modified_by=created_by,
        )
        self._session.add(definition)
        await self._session.flush()
        return definition

    async def get_definition(self, definition_id: UUID) -> dict:
        """Get workflow definition with statuses and transitions."""
        definition = await self._session.get(WorkflowDefinitionModel, str(definition_id))
        if not definition:
            raise ValueError("Definition not found")

        # Load statuses
        statuses_stmt = (
            select(WorkflowStatusModel)
            .where(WorkflowStatusModel.workflow_definition_id == str(definition_id))
            .order_by(WorkflowStatusModel.sequence)
        )
        statuses = (await self._session.execute(statuses_stmt)).scalars().all()

        # Load transitions
        transitions_stmt = select(WorkflowTransitionModel).where(
            WorkflowTransitionModel.workflow_definition_id == str(definition_id)
        )
        transitions = (await self._session.execute(transitions_stmt)).scalars().all()

        return {
            "definition": definition,
            "statuses": list(statuses),
            "transitions": list(transitions),
        }

    # ═══════════════════════════════════════════════════════════════════
    # WORKFLOW STATUSES
    # ═══════════════════════════════════════════════════════════════════

    async def create_status(
        self,
        *,
        definition_id: UUID,
        code: str,
        name: str,
        is_initial: bool,
        is_terminal: bool,
        sequence: int,
        created_by: str,
    ) -> WorkflowStatusModel:
        """Add a status to a workflow definition."""
        definition = await self._session.get(WorkflowDefinitionModel, str(definition_id))
        if not definition:
            raise ValueError("Definition not found")

        wf_status = WorkflowStatusModel(
            id=uuid4(),
            workflow_definition_id=str(definition_id),
            code=code,
            name=name,
            is_initial=is_initial,
            is_terminal=is_terminal,
            sequence=sequence,
            created_by=created_by,
            modified_by=created_by,
        )
        self._session.add(wf_status)
        await self._session.flush()
        return wf_status

    async def list_statuses(self, definition_id: UUID) -> list[WorkflowStatusModel]:
        """List statuses for a workflow definition."""
        stmt = (
            select(WorkflowStatusModel)
            .where(WorkflowStatusModel.workflow_definition_id == str(definition_id))
            .order_by(WorkflowStatusModel.sequence)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    # ═══════════════════════════════════════════════════════════════════
    # WORKFLOW TRANSITIONS
    # ═══════════════════════════════════════════════════════════════════

    async def create_transition(
        self,
        *,
        definition_id: UUID,
        from_status_id: UUID,
        to_status_id: UUID,
        action_code: str,
        guard_expression: str | None = None,
        requires_comment: bool = False,
        auto_execute: bool = False,
        priority: int = 0,
        created_by: str,
    ) -> WorkflowTransitionModel:
        """Add a transition to a workflow definition."""
        transition = WorkflowTransitionModel(
            id=uuid4(),
            workflow_definition_id=str(definition_id),
            from_status_id=str(from_status_id),
            to_status_id=str(to_status_id),
            action_code=action_code,
            guard_expression=guard_expression,
            requires_comment=requires_comment,
            auto_execute=auto_execute,
            priority=priority,
            created_by=created_by,
            modified_by=created_by,
        )
        self._session.add(transition)
        await self._session.flush()
        return transition

    async def delete_transition(self, transition_id: UUID) -> None:
        """Delete a transition."""
        transition = await self._session.get(WorkflowTransitionModel, str(transition_id))
        if not transition:
            raise ValueError("Transition not found")
        await self._session.delete(transition)

    # ═══════════════════════════════════════════════════════════════════
    # WORKFLOW RUNTIME
    # ═══════════════════════════════════════════════════════════════════

    async def start_workflow(
        self,
        *,
        definition_code: str,
        entity_type: str,
        entity_id: str,
        initiated_by: UUID,
        metadata: dict | None = None,
    ) -> dict:
        """Start a workflow instance."""
        result = await self._engine.start_workflow(
            definition_code=definition_code,
            entity_type=entity_type,
            entity_id=entity_id,
            initiated_by=initiated_by,
            metadata=metadata,
        )
        return result

    async def execute_action(
        self,
        *,
        instance_id: UUID,
        action_code: str,
        actor_id: UUID,
        actor_username: str,
        comments: str | None = None,
    ) -> dict:
        """Execute an action on a workflow instance."""
        result = await self._engine.execute_action(
            instance_id=instance_id,
            action_code=action_code,
            actor_id=actor_id,
            actor_username=actor_username,
            comments=comments,
        )
        return result

    async def get_instance_status(self, instance_id: UUID) -> dict:
        """Get workflow instance status."""
        return await self._engine.get_workflow_status(instance_id)

    async def get_instance_actions(self, instance_id: UUID) -> list[dict]:
        """Get available actions for a workflow instance."""
        return await self._engine.get_available_actions(instance_id)

    async def get_instance_history(self, instance_id: UUID) -> list[WorkflowHistoryModel]:
        """Get workflow instance history."""
        stmt = (
            select(WorkflowHistoryModel)
            .where(WorkflowHistoryModel.instance_id == str(instance_id))
            .order_by(WorkflowHistoryModel.created_at.desc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_my_tasks(self, user_id: UUID) -> list[dict]:
        """Get pending approval tasks for a user."""
        return await self._engine.get_pending_tasks(user_id)

    # ═══════════════════════════════════════════════════════════════════
    # APPROVAL MATRIX
    # ═══════════════════════════════════════════════════════════════════

    async def list_approval_matrices(self) -> list[dict]:
        """List approval matrices with their rules and assignments."""
        stmt = select(ApprovalMatrixModel).order_by(ApprovalMatrixModel.priority)
        result = await self._session.execute(stmt)
        matrices = result.scalars().all()

        response = []
        for matrix in matrices:
            # Load rules
            rules_stmt = select(ApprovalRuleModel).where(
                ApprovalRuleModel.matrix_id == str(matrix.id)
            )
            rules = (await self._session.execute(rules_stmt)).scalars().all()

            # Load assignments
            assign_stmt = (
                select(ApprovalAssignmentModel)
                .where(ApprovalAssignmentModel.matrix_id == str(matrix.id))
                .order_by(ApprovalAssignmentModel.level)
            )
            assignments = (await self._session.execute(assign_stmt)).scalars().all()

            response.append({
                "id": matrix.id,
                "code": matrix.code,
                "name": matrix.name,
                "entity_type": matrix.entity_type,
                "priority": matrix.priority,
                "is_active": matrix.is_active,
                "rules": [
                    {
                        "field": r.field,
                        "operator": r.operator,
                        "value": r.value,
                        "data_type": r.data_type,
                        "logical_group": r.logical_group,
                    }
                    for r in rules
                ],
                "assignments": [
                    {
                        "level": a.level,
                        "assignment_type": a.assignment_type,
                        "user_id": str(a.user_id) if a.user_id else None,
                        "role_id": str(a.role_id) if a.role_id else None,
                    }
                    for a in assignments
                ],
            })

        return response

    async def create_approval_matrix(
        self,
        *,
        code: str,
        name: str,
        entity_type: str,
        priority: int,
        rules: list,
        assignments: list,
        created_by: str,
    ) -> dict:
        """Create an approval matrix with rules and assignments."""
        existing = await self._session.execute(
            select(ApprovalMatrixModel).where(ApprovalMatrixModel.code == code)
        )
        if existing.scalar_one_or_none():
            raise ValueError(f"Matrix '{code}' already exists")

        matrix = ApprovalMatrixModel(
            id=uuid4(),
            code=code,
            name=name,
            entity_type=entity_type,
            priority=priority,
            is_active=True,
            created_by=created_by,
            modified_by=created_by,
        )
        self._session.add(matrix)
        await self._session.flush()

        # Create rules
        for rule in rules:
            r = ApprovalRuleModel(
                id=uuid4(),
                matrix_id=str(matrix.id),
                field=rule.field,
                operator=rule.operator,
                value=rule.value,
                data_type=rule.data_type,
                logical_group=rule.logical_group,
                created_by=created_by,
                modified_by=created_by,
            )
            self._session.add(r)

        # Create assignments
        for assignment in assignments:
            a = ApprovalAssignmentModel(
                id=uuid4(),
                matrix_id=str(matrix.id),
                assignment_type=assignment.assignment_type,
                user_id=str(assignment.user_id) if assignment.user_id else None,
                role_id=str(assignment.role_id) if assignment.role_id else None,
                level=assignment.level,
                created_by=created_by,
                modified_by=created_by,
            )
            self._session.add(a)

        return {
            "id": matrix.id,
            "code": matrix.code,
            "name": matrix.name,
            "entity_type": entity_type,
            "priority": priority,
            "is_active": matrix.is_active,
            "rules": [
                {
                    "field": r.field,
                    "operator": r.operator,
                    "value": r.value,
                    "data_type": r.data_type,
                    "logical_group": r.logical_group,
                }
                for r in rules
            ],
            "assignments": [
                {
                    "level": a.level,
                    "assignment_type": a.assignment_type,
                    "user_id": str(a.user_id) if a.user_id else None,
                    "role_id": str(a.role_id) if a.role_id else None,
                }
                for a in assignments
            ],
        }

    async def update_approval_matrix(
        self,
        *,
        matrix_id: UUID,
        name: str,
        entity_type: str,
        priority: int,
        rules: list,
        assignments: list,
        modified_by: str,
    ) -> dict:
        """Update approval matrix (replaces rules and assignments)."""
        matrix = await self._session.get(ApprovalMatrixModel, str(matrix_id))
        if not matrix:
            raise ValueError("Approval matrix not found")

        # Update basic fields
        matrix.name = name
        matrix.entity_type = entity_type
        matrix.priority = priority
        matrix.modified_by = modified_by

        # Delete existing rules
        existing_rules = await self._session.execute(
            select(ApprovalRuleModel).where(ApprovalRuleModel.matrix_id == str(matrix_id))
        )
        for r in existing_rules.scalars().all():
            await self._session.delete(r)

        # Delete existing assignments
        existing_assigns = await self._session.execute(
            select(ApprovalAssignmentModel).where(
                ApprovalAssignmentModel.matrix_id == str(matrix_id)
            )
        )
        for a in existing_assigns.scalars().all():
            await self._session.delete(a)

        await self._session.flush()

        # Create new rules
        for rule in rules:
            r = ApprovalRuleModel(
                id=uuid4(),
                matrix_id=str(matrix_id),
                field=rule.field,
                operator=rule.operator,
                value=rule.value,
                data_type=rule.data_type,
                logical_group=rule.logical_group,
                created_by=modified_by,
                modified_by=modified_by,
            )
            self._session.add(r)

        # Create new assignments
        for assignment in assignments:
            a = ApprovalAssignmentModel(
                id=uuid4(),
                matrix_id=str(matrix_id),
                assignment_type=assignment.assignment_type,
                user_id=str(assignment.user_id) if assignment.user_id else None,
                role_id=str(assignment.role_id) if assignment.role_id else None,
                level=assignment.level,
                created_by=modified_by,
                modified_by=modified_by,
            )
            self._session.add(a)

        return {
            "id": matrix.id,
            "code": matrix.code,
            "name": name,
            "entity_type": entity_type,
            "priority": priority,
            "is_active": matrix.is_active,
            "rules": [
                {
                    "field": r.field,
                    "operator": r.operator,
                    "value": r.value,
                    "data_type": r.data_type,
                    "logical_group": r.logical_group,
                }
                for r in rules
            ],
            "assignments": [
                {
                    "level": a.level,
                    "assignment_type": a.assignment_type,
                    "user_id": str(a.user_id) if a.user_id else None,
                    "role_id": str(a.role_id) if a.role_id else None,
                }
                for a in assignments
            ],
        }
