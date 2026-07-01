"""Pydantic schemas for Workflow API."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


# ─── Workflow Definition ───

class WorkflowDefinitionCreate(BaseModel):
    code: str = Field(..., min_length=2, max_length=100)
    name: str = Field(..., min_length=2, max_length=255)
    description: str = Field(default="")
    entity_type: str = Field(..., min_length=2, max_length=100)


class WorkflowDefinitionResponse(BaseModel):
    id: UUID
    code: str
    name: str
    description: str
    entity_type: str
    version: int
    is_active: bool
    created_date: datetime

    model_config = {"from_attributes": True}


class WorkflowDefinitionListResponse(BaseModel):
    definitions: list[WorkflowDefinitionResponse]
    total: int


# ─── Workflow Status ───

class WorkflowStatusCreate(BaseModel):
    code: str = Field(..., min_length=2, max_length=50)
    name: str = Field(..., min_length=2, max_length=255)
    is_initial: bool = False
    is_terminal: bool = False
    sequence: int = 0


class WorkflowStatusResponse(BaseModel):
    id: UUID
    workflow_definition_id: UUID
    code: str
    name: str
    is_initial: bool
    is_terminal: bool
    sequence: int

    model_config = {"from_attributes": True}


# ─── Workflow Transition ───

class WorkflowTransitionCreate(BaseModel):
    from_status_id: UUID
    to_status_id: UUID
    action_code: str = Field(..., min_length=2, max_length=50)
    guard_expression: str | None = None
    requires_comment: bool = False
    auto_execute: bool = False
    priority: int = 0


class WorkflowTransitionResponse(BaseModel):
    id: UUID
    workflow_definition_id: UUID
    from_status_id: UUID
    to_status_id: UUID
    action_code: str
    guard_expression: str | None
    requires_comment: bool
    auto_execute: bool
    priority: int

    model_config = {"from_attributes": True}


# ─── Workflow Instance ───

class WorkflowStartRequest(BaseModel):
    definition_code: str
    entity_type: str
    entity_id: UUID
    metadata: dict = Field(default_factory=dict)


class WorkflowActionRequest(BaseModel):
    action_code: str
    comments: str = ""


class WorkflowInstanceResponse(BaseModel):
    id: UUID
    workflow_definition_id: UUID
    entity_type: str
    entity_id: UUID
    current_status_id: UUID
    current_status_code: str | None = None
    initiated_by: UUID
    priority: int
    started_at: datetime
    completed_at: datetime | None
    extra_data: dict = Field(default_factory=dict)

    model_config = {"from_attributes": True}


class WorkflowHistoryResponse(BaseModel):
    id: UUID
    instance_id: UUID
    from_status_id: UUID | None
    to_status_id: UUID
    action_code: str
    actor_id: UUID | None
    actor_username: str
    comments: str
    created_at: datetime

    model_config = {"from_attributes": True}


# ─── Approval Matrix ───

class ApprovalRuleCreate(BaseModel):
    field: str
    operator: str
    value: str
    data_type: str = "STRING"
    logical_group: str = "default"


class ApprovalAssignmentCreate(BaseModel):
    assignment_type: str  # ROLE, USER
    user_id: UUID | None = None
    role_id: UUID | None = None
    level: int = 1


class ApprovalMatrixCreate(BaseModel):
    code: str = Field(..., min_length=2, max_length=100)
    name: str = Field(..., min_length=2, max_length=255)
    entity_type: str = Field(..., min_length=2, max_length=100)
    priority: int = 0
    rules: list[ApprovalRuleCreate] = []
    assignments: list[ApprovalAssignmentCreate] = []


class ApprovalMatrixResponse(BaseModel):
    id: UUID
    code: str
    name: str
    entity_type: str
    priority: int
    is_active: bool
    rules: list[dict] = []
    assignments: list[dict] = []

    model_config = {"from_attributes": True}


class ApprovalTaskResponse(BaseModel):
    id: UUID
    instance_id: UUID
    assignee_id: UUID
    level: int
    status: str
    action_taken: str | None
    due_date: datetime | None
    comments: str | None

    model_config = {"from_attributes": True}
