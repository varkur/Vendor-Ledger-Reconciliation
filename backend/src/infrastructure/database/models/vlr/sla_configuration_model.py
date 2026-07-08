"""SLA configuration model for workflow step time limits."""

from sqlalchemy import Boolean, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.database.models.base_model import BaseModel


class SLAConfigurationModel(BaseModel):
    """
    Configurable SLA durations per workflow step.

    Each workflow step can have a defined SLA (in hours) after which the case
    is flagged as overdue. An escalation email can be specified for notifications.
    """

    __tablename__ = "vlr_sla_configurations"

    step_name: Mapped[str] = mapped_column(
        String(30),
        unique=True,
        nullable=False,
        comment="Workflow step name matching WorkflowStep enum values",
    )
    sla_hours: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Maximum allowed hours for this step before flagging as overdue",
    )
    escalation_email: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="Email address for SLA violation escalation notifications",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        comment="Whether this SLA configuration is active",
    )
