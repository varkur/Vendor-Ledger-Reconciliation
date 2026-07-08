"""
Dashboard Pydantic schemas (response models).

Provides response schemas for the dashboard KPI widgets and recent confirmations endpoints.

Requirements: 26.1, 26.2, 26.3, 26.4, 26.5, 26.6, 26.7, 26.8
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class DashboardWidgetsResponse(BaseModel):
    """Response for GET /api/v1/vlr/dashboard/widgets — all KPI widget data."""

    open_cases: int = Field(
        description="Count of active reconciliation cases (not closed)"
    )
    pending_vendor_upload: int = Field(
        description="Count of cases awaiting vendor ledger upload (vendor_engagement step, upload_count=0)"
    )
    pending_finance_review: int = Field(
        description="Count of cases in finance_review or exception_resolution step"
    )
    overdue_cases: int = Field(
        description="Count of cases where is_overdue=True"
    )
    cases_closed_this_month: int = Field(
        description="Count of cases closed in current calendar month"
    )
    average_cycle_time_days: float | None = Field(
        default=None,
        description="Mean days from case creation to closure (for closed cases). Null if no closed cases.",
    )
    auto_match_rate: float | None = Field(
        default=None,
        description="Percentage of entries matched automatically (Pass 1+2) vs total entries. Null if no entries.",
    )


class RecentConfirmationItem(BaseModel):
    """Single recent confirmation entry for the dashboard table."""

    case_id: UUID = Field(description="Reconciliation case ID")
    vendor_name: str = Field(description="Vendor name who signed off")
    signed_at: datetime = Field(description="Sign-off timestamp")
    statement_version: str = Field(description="Statement version signed")
    confirmation_text: str | None = Field(
        default=None, description="Vendor confirmation text"
    )


class RecentConfirmationsResponse(BaseModel):
    """Response for GET /api/v1/vlr/dashboard/recent-confirmations — last 10 vendor sign-offs."""

    items: list[RecentConfirmationItem] = Field(
        default_factory=list,
        description="Last 10 vendor sign-offs ordered by most recent first",
    )
    total: int = Field(description="Total number of sign-offs available")
