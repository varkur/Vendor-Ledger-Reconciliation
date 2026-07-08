"""
Request/Response schemas for the Workflow Orchestration API endpoints.

Requirements: 12.1, 12.4, 13.2
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from src.domain.services.vlr.workflow_orchestrator_service import WorkflowStep


# ──────────────────────────────────────────────────────────────────────
# Request Schemas
# ──────────────────────────────────────────────────────────────────────


class AdvanceRequest(BaseModel):
    """Request body for advancing a case to the next workflow step."""

    target_step: WorkflowStep = Field(
        ..., description="The target workflow step to advance to"
    )


class RollbackRequest(BaseModel):
    """Request body for rolling back a case to a previous workflow step."""

    target_step: WorkflowStep = Field(
        ..., description="The target workflow step to rollback to"
    )


# ──────────────────────────────────────────────────────────────────────
# Response Schemas
# ──────────────────────────────────────────────────────────────────────


class StatusResponse(BaseModel):
    """Response model for workflow status queries and transitions."""

    case_id: UUID = Field(..., description="The reconciliation case ID")
    current_step: WorkflowStep = Field(
        ..., description="Current workflow step for the case"
    )
    step_entered_at: datetime = Field(
        ..., description="Timestamp when the current step was entered"
    )
    sla_deadline: datetime | None = Field(
        None, description="SLA deadline for the current step"
    )
    is_overdue: bool = Field(
        False, description="Whether the case has exceeded its SLA deadline"
    )

    model_config = {"from_attributes": True}


class SLAViolationResponse(BaseModel):
    """Response model for a single SLA violation."""

    case_id: UUID = Field(..., description="The reconciliation case ID")
    current_step: WorkflowStep = Field(
        ..., description="The workflow step that is overdue"
    )
    step_entered_at: datetime = Field(
        ..., description="Timestamp when the overdue step was entered"
    )
    sla_deadline: datetime = Field(
        ..., description="The SLA deadline that was exceeded"
    )
    hours_overdue: float = Field(
        ..., description="Number of hours past the SLA deadline"
    )

    model_config = {"from_attributes": True}


class SLAViolationsListResponse(BaseModel):
    """Response model for the list of SLA violations."""

    items: list[SLAViolationResponse] = Field(
        default_factory=list, description="List of SLA violations"
    )
    total: int = Field(..., description="Total number of violations")

    model_config = {"from_attributes": True}
