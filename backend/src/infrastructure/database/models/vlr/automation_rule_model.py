"""Automation rule model for scheduled/recurring reconciliation tasks."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Index, String
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.database.models.base_model import BaseModel


class AutomationRuleModel(BaseModel):
    """
    Automation rule defining scheduled reconciliation or escalation logic.

    Rules can be enabled/disabled without deletion and track execution history.
    """

    __tablename__ = "vlr_automation_rules"

    company_code: Mapped[str] = mapped_column(String(20), nullable=False)
    rule_type: Mapped[str] = mapped_column(String(50), nullable=False)
    frequency: Mapped[str] = mapped_column(String(30), nullable=False)
    configuration: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_executed: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    next_execution: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships
    executions = relationship("AutomationExecutionModel", back_populates="rule", lazy="noload")

    __table_args__ = (
        Index("ix_vlr_automation_rules_company_code", "company_code"),
        Index("ix_vlr_automation_rules_is_active", "is_active"),
    )
