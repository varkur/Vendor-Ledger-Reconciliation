"""Automation execution history model."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.database.models.base_model import BaseModel


class AutomationExecutionModel(BaseModel):
    """
    Record of an automation rule execution.

    Tracks trigger time, status (success/failure), outcome description, and errors.
    """

    __tablename__ = "vlr_automation_executions"

    rule_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("vlr_automation_rules.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    triggered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    outcome: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_details: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Relationships
    rule = relationship("AutomationRuleModel", back_populates="executions")
