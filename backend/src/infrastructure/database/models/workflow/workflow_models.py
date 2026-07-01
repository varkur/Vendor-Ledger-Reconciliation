"""SQLAlchemy ORM models for the Workflow Engine."""
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.database.models.base_model import BaseModel, Base


class WorkflowDefinitionModel(BaseModel):
    __tablename__ = "workflow_definitions"
    code: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    entity_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class WorkflowStatusModel(BaseModel):
    __tablename__ = "workflow_statuses"
    workflow_definition_id: Mapped[str] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    is_initial: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_terminal: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class WorkflowTransitionModel(BaseModel):
    __tablename__ = "workflow_transitions"
    workflow_definition_id: Mapped[str] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    from_status_id: Mapped[str] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    to_status_id: Mapped[str] = mapped_column(UUID(as_uuid=True), nullable=False)
    action_code: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    guard_expression: Mapped[str | None] = mapped_column(Text, nullable=True)
    requires_comment: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    auto_execute: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class WorkflowActionModel(BaseModel):
    __tablename__ = "workflow_actions"
    workflow_definition_id: Mapped[str] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    action_type: Mapped[str] = mapped_column(String(20), nullable=False)


class WorkflowStepModel(BaseModel):
    __tablename__ = "workflow_steps"
    workflow_definition_id: Mapped[str] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    from_status_id: Mapped[str] = mapped_column(UUID(as_uuid=True), nullable=False)
    to_status_id: Mapped[str] = mapped_column(UUID(as_uuid=True), nullable=False)
    action_code: Mapped[str] = mapped_column(String(50), nullable=False)
    step_type: Mapped[str] = mapped_column(String(20), default="APPROVAL", nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_parallel: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    sla_hours: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class WorkflowAssignmentRuleModel(BaseModel):
    __tablename__ = "workflow_assignment_rules"
    workflow_step_id: Mapped[str] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    assignment_type: Mapped[str] = mapped_column(String(20), nullable=False)
    role_id: Mapped[str | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    user_id: Mapped[str | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    matrix_rule_id: Mapped[str | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    expression: Mapped[str | None] = mapped_column(Text, nullable=True)


class WorkflowInstanceModel(BaseModel):
    __tablename__ = "workflow_instances"
    workflow_definition_id: Mapped[str] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    entity_id: Mapped[str] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    current_status_id: Mapped[str] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    initiated_by: Mapped[str] = mapped_column(UUID(as_uuid=True), nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    due_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    extra_data: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)


class WorkflowInstanceStepModel(BaseModel):
    __tablename__ = "workflow_instance_steps"
    instance_id: Mapped[str] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    step_id: Mapped[str] = mapped_column(UUID(as_uuid=True), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="PENDING", nullable=False)
    assigned_to_id: Mapped[str | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    assigned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    action_taken: Mapped[str | None] = mapped_column(String(50), nullable=True)
    comments: Mapped[str | None] = mapped_column(Text, nullable=True)
    sla_due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_escalated: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class WorkflowHistoryModel(Base):
    """Immutable workflow history — append-only."""
    __tablename__ = "workflow_history"
    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4, nullable=False)
    instance_id: Mapped[str] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    from_status_id: Mapped[str | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    to_status_id: Mapped[str] = mapped_column(UUID(as_uuid=True), nullable=False)
    action_code: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    actor_id: Mapped[str | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    actor_username: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    comments: Mapped[str] = mapped_column(Text, default="", nullable=False)
    extra_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    ip_address: Mapped[str] = mapped_column(String(45), default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), index=True)
