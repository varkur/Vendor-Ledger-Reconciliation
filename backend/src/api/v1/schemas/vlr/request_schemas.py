"""
Reconciliation Request Pydantic schemas (request/response).

Provides validation for request creation, cloning, listing, and statistics.
Requirements: 3.1, 3.2, 3.10, 11.2, 11.6
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Self
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


# ──────────────────────────────────────────────────────────────────────
# Request Schemas
# ──────────────────────────────────────────────────────────────────────


class MatchingPreferencesSchema(BaseModel):
    """Configuration for matching passes."""

    exact_match_enabled: bool = Field(default=True, description="Enable exact match pass")
    tolerance_match_enabled: bool = Field(default=True, description="Enable tolerance match pass")
    fuzzy_reference_enabled: bool = Field(default=True, description="Enable fuzzy reference match pass")
    one_to_many_enabled: bool = Field(default=True, description="Enable one-to-many match pass")
    many_to_one_enabled: bool = Field(default=True, description="Enable many-to-one match pass")


class CreateRequestRequest(BaseModel):
    """Request body for creating a new reconciliation request."""

    company_code: str = Field(..., min_length=1, max_length=20, description="Company code")
    fiscal_year: str = Field(..., min_length=1, max_length=10, description="Fiscal year (e.g., '2024-25')")
    period_start: date = Field(..., description="Start of reconciliation period")
    period_end: date = Field(..., description="End of reconciliation period")
    vendor_ids: list[UUID] = Field(..., min_length=1, description="List of vendor IDs to include")
    title: str | None = Field(default=None, max_length=255, description="Request title/name")
    tolerance_amount: Decimal = Field(default=Decimal("0"), ge=0, description="Tolerance amount for matching")
    tds_percentage: Decimal = Field(default=Decimal("0"), ge=0, le=100, description="TDS percentage (upper bound of the configured range)")
    tds_percentage_min: Decimal = Field(default=Decimal("0"), ge=0, le=100, description="TDS percentage (lower bound of the configured range)")
    gst_percentage: Decimal = Field(default=Decimal("0"), ge=0, le=100, description="GST percentage")
    date_tolerance_days_min: int = Field(default=0, ge=0, description="Minimum days for date-proximity/date-range matching")
    date_tolerance_days_max: int = Field(default=15, ge=0, description="Maximum days for date-proximity/date-range matching")
    matching_preferences: MatchingPreferencesSchema | None = Field(
        default=None, description="Matching pass configuration"
    )
    assigned_manager_id: UUID | None = Field(default=None, description="Assigned manager user ID")
    email_template_id: str | None = Field(
        default=None,
        description="Email template ID (Settings > Email Templates) to render the auto-sent vendor invite from",
    )

    @model_validator(mode="after")
    def validate_date_range(self) -> Self:
        """Ensure period_start < period_end, period_end is not in the future,
        and every configured range (TDS%, date tolerance) has min <= max."""
        if self.period_start >= self.period_end:
            raise ValueError("period_start must be before period_end")
        if self.period_end > date.today():
            raise ValueError("period_end cannot be in the future")
        if self.tds_percentage_min > self.tds_percentage:
            raise ValueError("tds_percentage_min must be <= tds_percentage (max)")
        if self.date_tolerance_days_min > self.date_tolerance_days_max:
            raise ValueError("date_tolerance_days_min must be <= date_tolerance_days_max")
        return self


class CloneRequestRequest(BaseModel):
    """Request body for cloning a request to a new period."""

    period_start: date = Field(..., description="New period start date")
    period_end: date = Field(..., description="New period end date")

    @model_validator(mode="after")
    def validate_date_range(self) -> Self:
        """Ensure period_start < period_end and period_end is not in the future."""
        if self.period_start >= self.period_end:
            raise ValueError("period_start must be before period_end")
        if self.period_end > date.today():
            raise ValueError("period_end cannot be in the future")
        return self


# ──────────────────────────────────────────────────────────────────────
# Response Schemas
# ──────────────────────────────────────────────────────────────────────


class ReconciliationRequestResponse(BaseModel):
    """Response schema for a single reconciliation request."""

    id: UUID
    company_code: str
    fiscal_year: str
    period_start: date
    period_end: date
    status: str
    request_number: str | None = None
    title: str | None = None
    sent_date: datetime | None = None
    tolerance_amount: Decimal | None = None
    tds_percentage: Decimal | None = None
    tds_percentage_min: Decimal | None = None
    gst_percentage: Decimal | None = None
    date_tolerance_days_min: int | None = None
    date_tolerance_days_max: int | None = None
    matching_preferences: dict | None = None
    assigned_manager_id: UUID | None = None
    created_by: str | None = None
    created_date: datetime | None = None
    party_count: int = Field(default=0, description="Number of vendor cases (parties) in this request")

    model_config = {"from_attributes": True}


class RequestListResponse(BaseModel):
    """Paginated reconciliation request list response."""

    items: list[ReconciliationRequestResponse]
    total: int = Field(default=0, description="Total matching records")
    page: int = Field(default=1, description="Current page number")
    page_size: int = Field(default=50, description="Items per page")
    total_pages: int = Field(default=0, description="Total pages available")


class AmountEntry(BaseModel):
    """Amount and entry count for a difference or action row."""

    amount: float = Field(default=0.0, description="Aggregated amount")
    entry_count: int = Field(default=0, description="Number of entries")


class AmountCategoryRow(BaseModel):
    """Amount statistics row for a specific category (e.g., Vendor Payable)."""

    category: str = Field(..., description="Category name")
    total_company_amount: float = Field(default=0.0)
    company_amount_responded: float = Field(default=0.0)
    party_amount_responded: float = Field(default=0.0)
    net_difference: float = Field(default=0.0)


class ReminderInfo(BaseModel):
    """Reminder summary for the request."""

    reminders_sent: int = Field(default=0, description="Total reminders sent for this request")
    max_reminders: int = Field(default=5, description="Maximum reminders allowed")
    last_reminder_date: str | None = Field(default=None, description="Last reminder date (ISO)")


class StatementStatusCounts(BaseModel):
    """Statement status counts."""

    total: int = Field(default=0)
    responded: int = Field(default=0)
    not_responded: int = Field(default=0)
    rejected: int = Field(default=0)
    failed: int = Field(default=0)


class ReconciliationStatusCounts(BaseModel):
    """Reconciliation status counts per sub-status."""

    in_progress: int = Field(default=0)
    statement_received: int = Field(default=0)
    mapping_pending: int = Field(default=0)
    statement_mapped: int = Field(default=0)
    auto_completed: int = Field(default=0)
    review_pending: int = Field(default=0)
    reviewed: int = Field(default=0)
    signoff_requested: int = Field(default=0)
    signoff_completed: int = Field(default=0)
    reco_rejected: int = Field(default=0)


class RequestStatisticsResponse(BaseModel):
    """Enriched statistics for a reconciliation request."""

    request_id: UUID
    total_cases: int = Field(default=0, description="Total number of cases")
    cases_by_status: dict[str, int] = Field(
        default_factory=dict, description="Case count per status (raw)"
    )

    # Structured sections
    statement_status: StatementStatusCounts = Field(default_factory=StatementStatusCounts)
    reconciliation_status: ReconciliationStatusCounts = Field(
        default_factory=ReconciliationStatusCounts
    )
    amount_statistics: list[AmountCategoryRow] = Field(default_factory=list)
    reason_for_difference: dict[str, AmountEntry] = Field(default_factory=dict)
    action_summary: dict[str, AmountEntry] = Field(default_factory=dict)
    reminder_info: ReminderInfo = Field(default_factory=ReminderInfo)
