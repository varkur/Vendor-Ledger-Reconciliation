"""
Automation Rule Pydantic schemas (request/response).

Provides validation for automation rule CRUD, enable/disable,
and execution history operations.

Requirements: 19.1, 19.5, 19.7
"""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field


# ──────────────────────────────────────────────────────────────────────
# Configuration Schemas
# ──────────────────────────────────────────────────────────────────────


class ScheduleConfigSchema(BaseModel):
    """Configuration for scheduled reconciliation rules."""

    frequency: str = Field(
        ...,
        pattern=r"^(daily|weekly|monthly|quarterly)$",
        description="Schedule frequency",
    )
    day_of_month: int | None = Field(
        default=None, ge=1, le=28, description="Day of month for monthly schedules"
    )
    day_of_week: int | None = Field(
        default=None, ge=0, le=6, description="Day of week (0=Mon, 6=Sun) for weekly schedules"
    )
    quarter_months: list[int] = Field(
        default_factory=lambda: [1, 4, 7, 10],
        description="Starting months for quarterly schedules",
    )
    time_of_day: str = Field(
        default="02:00", pattern=r"^\d{2}:\d{2}$", description="Execution time in UTC (HH:MM)"
    )
    vendor_ids: list[UUID] = Field(
        default_factory=list, description="Specific vendor IDs (empty = all vendors)"
    )


class AutoMatchConfigSchema(BaseModel):
    """Configuration for auto-matching rules."""

    confidence_threshold: float = Field(
        default=0.95, ge=0.80, le=1.0, description="Confidence threshold for auto-accept"
    )
    max_amount: Decimal | None = Field(
        default=None, gt=0, description="Maximum amount for auto-accept (None = no limit)"
    )
    exclude_vendor_ids: list[UUID] = Field(
        default_factory=list, description="Vendor IDs to exclude from auto-matching"
    )


class AutoEscalationConfigSchema(BaseModel):
    """Configuration for auto-escalation rules."""

    days_without_progress: int = Field(
        default=7, ge=1, description="Days without progress before escalation"
    )
    target: str = Field(
        default="manager",
        pattern=r"^(manager|senior_manager|director)$",
        description="Escalation target",
    )
    notify_assignee: bool = Field(default=True, description="Whether to notify the case assignee")
    include_case_statuses: list[str] = Field(
        default_factory=lambda: ["in_progress", "pending_vendor"],
        description="Case statuses to include in escalation checks",
    )


# ──────────────────────────────────────────────────────────────────────
# Request Schemas
# ──────────────────────────────────────────────────────────────────────


class CreateAutomationRuleRequest(BaseModel):
    """Request body for creating a new automation rule."""

    company_code: str = Field(..., min_length=1, max_length=20, description="Company code")
    rule_type: str = Field(
        ...,
        pattern=r"^(scheduled_reconciliation|auto_match|auto_escalation)$",
        description="Type of automation rule",
    )
    name: str = Field(..., min_length=1, max_length=255, description="Rule name")
    description: str | None = Field(default=None, max_length=1000, description="Rule description")
    schedule_config: ScheduleConfigSchema | None = Field(
        default=None, description="Config for scheduled_reconciliation rules"
    )
    auto_match_config: AutoMatchConfigSchema | None = Field(
        default=None, description="Config for auto_match rules"
    )
    auto_escalation_config: AutoEscalationConfigSchema | None = Field(
        default=None, description="Config for auto_escalation rules"
    )


class UpdateAutomationRuleRequest(BaseModel):
    """Request body for updating an existing automation rule."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=1000)
    schedule_config: ScheduleConfigSchema | None = Field(default=None)
    auto_match_config: AutoMatchConfigSchema | None = Field(default=None)
    auto_escalation_config: AutoEscalationConfigSchema | None = Field(default=None)


# ──────────────────────────────────────────────────────────────────────
# Response Schemas
# ──────────────────────────────────────────────────────────────────────


class AutomationRuleResponse(BaseModel):
    """Response schema for a single automation rule."""

    id: UUID
    company_code: str
    rule_type: str
    frequency: str
    configuration: dict | None = None
    is_active: bool = True
    last_executed: datetime | None = None
    next_execution: datetime | None = None
    created_by: str | None = None
    created_date: datetime | None = None
    modified_by: str | None = None
    modified_date: datetime | None = None

    model_config = {"from_attributes": True}


class AutomationRuleListResponse(BaseModel):
    """Paginated automation rule list response."""

    items: list[AutomationRuleResponse]
    total: int = Field(default=0, description="Total matching records")
    page: int = Field(default=1, description="Current page number")
    page_size: int = Field(default=50, description="Items per page")
    total_pages: int = Field(default=0, description="Total pages available")


class ExecutionHistoryResponse(BaseModel):
    """Response schema for a single execution history record."""

    id: UUID
    rule_id: UUID
    triggered_at: datetime
    status: str
    outcome: str | None = None
    error_details: dict | None = None
    created_date: datetime | None = None

    model_config = {"from_attributes": True}


class ExecutionHistoryListResponse(BaseModel):
    """Paginated execution history list response."""

    items: list[ExecutionHistoryResponse]
    total: int = Field(default=0, description="Total matching records")
    page: int = Field(default=1, description="Current page number")
    page_size: int = Field(default=50, description="Items per page")
    total_pages: int = Field(default=0, description="Total pages available")


class ExecuteDueRulesResponse(BaseModel):
    """Response for triggering due rule execution."""

    task_id: str = Field(..., description="Celery task ID for tracking")
    status: str = Field(default="queued", description="Task status")
    message: str = Field(default="Due rules execution has been queued.")
