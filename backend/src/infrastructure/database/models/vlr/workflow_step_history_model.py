"""Workflow step history model for tracking reconciliation case step transitions."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.database.models.base_model import BaseModel


class WorkflowStepHistoryModel(BaseModel):
    """
    Records each workflow step transition for a reconciliation case.

    Captures from/to step, who triggered it, when, and the SLA deadline
    for the target step. Supports rollback tracking via is_rollback flag.
    """

    __tablename__ = "vlr_workflow_step_history"

    case_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("vlr_reconciliation_cases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    from_step: Mapped[str | None] = mapped_column(
        String(30),
        nullable=True,
        comment="Previous workflow step (null for initial transition)",
    )
    to_step: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        comment="Target workflow step",
    )
    triggered_by: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="User or system that triggered the transition",
    )
    triggered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="Timestamp when the transition occurred",
    )
    sla_deadline: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="SLA deadline for the target step",
    )
    is_rollback: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment="Whether this transition is a rollback to a previous step",
    )

    # Relationships
    case = relationship("ReconciliationCaseModel", back_populates="workflow_step_history")

    __table_args__ = (
        Index("ix_vlr_wf_history_case_triggered", "case_id", "triggered_at"),
        Index("ix_vlr_wf_history_to_step", "to_step"),
    )
