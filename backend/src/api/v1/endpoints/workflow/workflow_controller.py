"""
Workflow Management API endpoints.
Thin controller — delegates all business logic to WorkflowService.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.v1.dependencies import get_current_active_user
from src.api.v1.endpoints.workflow.schemas import (
    ApprovalMatrixCreate,
    ApprovalMatrixResponse,
    ApprovalTaskResponse,
    WorkflowActionRequest,
    WorkflowDefinitionCreate,
    WorkflowDefinitionListResponse,
    WorkflowDefinitionResponse,
    WorkflowHistoryResponse,
    WorkflowInstanceResponse,
    WorkflowStartRequest,
    WorkflowStatusCreate,
    WorkflowStatusResponse,
    WorkflowTransitionCreate,
    WorkflowTransitionResponse,
)
from src.application.services.workflow_service import WorkflowService
from src.domain.entities.user import User
from src.infrastructure.database.session import get_db_session

router = APIRouter(prefix="/workflow", tags=["Workflow Engine"])


def _get_workflow_service(session: AsyncSession = Depends(get_db_session)) -> WorkflowService:
    return WorkflowService(session=session)


# ═══════════════════════════════════════════════════════════════════
# WORKFLOW DEFINITIONS
# ═══════════════════════════════════════════════════════════════════


@router.get(
    "/definitions",
    response_model=WorkflowDefinitionListResponse,
    summary="List workflow definitions",
)
async def list_definitions(
    current_user: User = Depends(get_current_active_user),
    service: WorkflowService = Depends(_get_workflow_service),
) -> WorkflowDefinitionListResponse:
    data = await service.list_definitions()
    return WorkflowDefinitionListResponse(
        definitions=[WorkflowDefinitionResponse.model_validate(d) for d in data["definitions"]],
        total=data["total"],
    )


@router.post(
    "/definitions",
    response_model=WorkflowDefinitionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create workflow definition",
)
async def create_definition(
    request: WorkflowDefinitionCreate,
    current_user: User = Depends(get_current_active_user),
    service: WorkflowService = Depends(_get_workflow_service),
) -> WorkflowDefinitionResponse:
    try:
        definition = await service.create_definition(
            code=request.code,
            name=request.name,
            description=request.description,
            entity_type=request.entity_type,
            created_by=current_user.username,
        )
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return WorkflowDefinitionResponse.model_validate(definition)


@router.get(
    "/definitions/{definition_id}",
    summary="Get workflow definition with statuses and transitions",
)
async def get_definition(
    definition_id: UUID,
    current_user: User = Depends(get_current_active_user),
    service: WorkflowService = Depends(_get_workflow_service),
) -> dict:
    try:
        data = await service.get_definition(definition_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {
        "definition": WorkflowDefinitionResponse.model_validate(data["definition"]),
        "statuses": [WorkflowStatusResponse.model_validate(s) for s in data["statuses"]],
        "transitions": [WorkflowTransitionResponse.model_validate(t) for t in data["transitions"]],
    }


# ═══════════════════════════════════════════════════════════════════
# WORKFLOW STATUSES
# ═══════════════════════════════════════════════════════════════════


@router.post(
    "/definitions/{definition_id}/statuses",
    response_model=WorkflowStatusResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add status to workflow",
)
async def create_status(
    definition_id: UUID,
    request: WorkflowStatusCreate,
    current_user: User = Depends(get_current_active_user),
    service: WorkflowService = Depends(_get_workflow_service),
) -> WorkflowStatusResponse:
    try:
        wf_status = await service.create_status(
            definition_id=definition_id,
            code=request.code,
            name=request.name,
            is_initial=request.is_initial,
            is_terminal=request.is_terminal,
            sequence=request.sequence,
            created_by=current_user.username,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return WorkflowStatusResponse.model_validate(wf_status)


@router.get(
    "/definitions/{definition_id}/statuses",
    response_model=list[WorkflowStatusResponse],
    summary="List statuses for a workflow",
)
async def list_statuses(
    definition_id: UUID,
    current_user: User = Depends(get_current_active_user),
    service: WorkflowService = Depends(_get_workflow_service),
) -> list[WorkflowStatusResponse]:
    statuses = await service.list_statuses(definition_id)
    return [WorkflowStatusResponse.model_validate(s) for s in statuses]


# ═══════════════════════════════════════════════════════════════════
# WORKFLOW TRANSITIONS
# ═══════════════════════════════════════════════════════════════════


@router.post(
    "/definitions/{definition_id}/transitions",
    response_model=WorkflowTransitionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add transition to workflow",
)
async def create_transition(
    definition_id: UUID,
    request: WorkflowTransitionCreate,
    current_user: User = Depends(get_current_active_user),
    service: WorkflowService = Depends(_get_workflow_service),
) -> WorkflowTransitionResponse:
    transition = await service.create_transition(
        definition_id=definition_id,
        from_status_id=request.from_status_id,
        to_status_id=request.to_status_id,
        action_code=request.action_code,
        guard_expression=request.guard_expression,
        requires_comment=request.requires_comment,
        auto_execute=request.auto_execute,
        priority=request.priority,
        created_by=current_user.username,
    )
    return WorkflowTransitionResponse.model_validate(transition)


@router.delete(
    "/transitions/{transition_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a transition",
)
async def delete_transition(
    transition_id: UUID,
    current_user: User = Depends(get_current_active_user),
    service: WorkflowService = Depends(_get_workflow_service),
) -> None:
    try:
        await service.delete_transition(transition_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ═══════════════════════════════════════════════════════════════════
# WORKFLOW RUNTIME
# ═══════════════════════════════════════════════════════════════════


@router.post(
    "/start",
    status_code=status.HTTP_201_CREATED,
    summary="Start a workflow instance",
)
async def start_workflow(
    request: WorkflowStartRequest,
    current_user: User = Depends(get_current_active_user),
    service: WorkflowService = Depends(_get_workflow_service),
) -> dict:
    return await service.start_workflow(
        definition_code=request.definition_code,
        entity_type=request.entity_type,
        entity_id=request.entity_id,
        initiated_by=current_user.id,
        metadata=request.metadata,
    )


@router.post(
    "/instances/{instance_id}/action",
    summary="Execute action on workflow instance",
)
async def execute_action(
    instance_id: UUID,
    request: WorkflowActionRequest,
    current_user: User = Depends(get_current_active_user),
    service: WorkflowService = Depends(_get_workflow_service),
) -> dict:
    return await service.execute_action(
        instance_id=instance_id,
        action_code=request.action_code,
        actor_id=current_user.id,
        actor_username=current_user.username,
        comments=request.comments,
    )


@router.get(
    "/instances/{instance_id}",
    summary="Get workflow instance status",
)
async def get_instance(
    instance_id: UUID,
    current_user: User = Depends(get_current_active_user),
    service: WorkflowService = Depends(_get_workflow_service),
) -> dict:
    return await service.get_instance_status(instance_id)


@router.get(
    "/instances/{instance_id}/actions",
    summary="Get available actions for instance",
)
async def get_instance_actions(
    instance_id: UUID,
    current_user: User = Depends(get_current_active_user),
    service: WorkflowService = Depends(_get_workflow_service),
) -> list[dict]:
    return await service.get_instance_actions(instance_id)


@router.get(
    "/instances/{instance_id}/history",
    response_model=list[WorkflowHistoryResponse],
    summary="Get workflow instance history",
)
async def get_instance_history(
    instance_id: UUID,
    current_user: User = Depends(get_current_active_user),
    service: WorkflowService = Depends(_get_workflow_service),
) -> list[WorkflowHistoryResponse]:
    history = await service.get_instance_history(instance_id)
    return [WorkflowHistoryResponse.model_validate(h) for h in history]


@router.get(
    "/my-tasks",
    summary="Get pending approval tasks for current user",
)
async def get_my_tasks(
    current_user: User = Depends(get_current_active_user),
    service: WorkflowService = Depends(_get_workflow_service),
) -> list[dict]:
    return await service.get_my_tasks(current_user.id)


# ═══════════════════════════════════════════════════════════════════
# APPROVAL MATRIX
# ═══════════════════════════════════════════════════════════════════


@router.get(
    "/approval-matrices",
    summary="List approval matrices",
)
async def list_approval_matrices(
    current_user: User = Depends(get_current_active_user),
    service: WorkflowService = Depends(_get_workflow_service),
) -> list[ApprovalMatrixResponse]:
    data = await service.list_approval_matrices()
    return [ApprovalMatrixResponse(**item) for item in data]


@router.post(
    "/approval-matrices",
    response_model=ApprovalMatrixResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create approval matrix with rules and assignments",
)
async def create_approval_matrix(
    request: ApprovalMatrixCreate,
    current_user: User = Depends(get_current_active_user),
    service: WorkflowService = Depends(_get_workflow_service),
) -> ApprovalMatrixResponse:
    try:
        data = await service.create_approval_matrix(
            code=request.code,
            name=request.name,
            entity_type=request.entity_type,
            priority=request.priority,
            rules=request.rules,
            assignments=request.assignments,
            created_by=current_user.username,
        )
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return ApprovalMatrixResponse(**data)


@router.put(
    "/approval-matrices/{matrix_id}",
    response_model=ApprovalMatrixResponse,
    summary="Update approval matrix (replaces rules and assignments)",
)
async def update_approval_matrix(
    matrix_id: UUID,
    request: ApprovalMatrixCreate,
    current_user: User = Depends(get_current_active_user),
    service: WorkflowService = Depends(_get_workflow_service),
) -> ApprovalMatrixResponse:
    try:
        data = await service.update_approval_matrix(
            matrix_id=matrix_id,
            name=request.name,
            entity_type=request.entity_type,
            priority=request.priority,
            rules=request.rules,
            assignments=request.assignments,
            modified_by=current_user.username,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return ApprovalMatrixResponse(**data)
