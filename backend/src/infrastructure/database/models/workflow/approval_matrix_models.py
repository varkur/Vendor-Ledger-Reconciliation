"""SQLAlchemy ORM models for the Approval Matrix."""
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.database.models.base_model import BaseModel


class ApprovalMatrixModel(BaseModel):
    __tablename__ = "approval_matrices"
    code: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    priority: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class ApprovalRuleModel(BaseModel):
    __tablename__ = "approval_rules"
    matrix_id: Mapped[str] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    field: Mapped[str] = mapped_column(String(100), nullable=False)
    operator: Mapped[str] = mapped_column(String(20), nullable=False)
    value: Mapped[str] = mapped_column(String(500), nullable=False)
    data_type: Mapped[str] = mapped_column(String(20), default="STRING", nullable=False)
    logical_group: Mapped[str] = mapped_column(String(50), default="default", nullable=False)


class ApprovalConditionModel(BaseModel):
    __tablename__ = "approval_conditions"
    matrix_id: Mapped[str] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    condition_type: Mapped[str] = mapped_column(String(50), nullable=False)
    expression: Mapped[str] = mapped_column(Text, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class ApprovalAssignmentModel(BaseModel):
    __tablename__ = "approval_assignments"
    matrix_id: Mapped[str] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    assignment_type: Mapped[str] = mapped_column(String(20), nullable=False)
    user_id: Mapped[str | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    role_id: Mapped[str | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    level: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


class ApprovalDelegationModel(BaseModel):
    __tablename__ = "approval_delegations"
    delegator_id: Mapped[str] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    delegate_id: Mapped[str] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    from_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    to_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    entity_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class ApprovalTaskModel(BaseModel):
    __tablename__ = "approval_tasks"
    instance_id: Mapped[str] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    matrix_id: Mapped[str | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    assignee_id: Mapped[str] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    level: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="PENDING", nullable=False, index=True)
    action_taken: Mapped[str | None] = mapped_column(String(50), nullable=True)
    due_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    comments: Mapped[str | None] = mapped_column(Text, nullable=True)
