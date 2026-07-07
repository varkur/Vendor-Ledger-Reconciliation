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
    tolerance_amount: Decimal = Field(default=Decimal("0"), ge=0, description="Tolerance amount for matching")
    tds_percentage: Decimal = Field(default=Decimal("0"), ge=0, le=100, description="TDS percentage")
    gst_percentage: Decimal = Field(default=Decimal("0"), ge=0, le=100, description="GST percentage")
    matching_preferences: MatchingPreferencesSchema | None = Field(
        default=None, description="Matching pass configuration"
    )
    assigned_manager_id: UUID | None = Field(default=None, description="Assigned manager user ID")

    @model_validator(mode="after")
    def validate_date_range(self) -> Self:
        """Ensure period_start < period_end and period_end is not in the future."""
        if self.period_start >= self.period_end:
            raise ValueError("period_start must be before period_end")
        if self.period_end > date.today():
            raise ValueError("period_end cannot be in the future")
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
    tolerance_amount: Decimal | None = None
    tds_percentage: Decimal | None = None
    gst_percentage: Decimal | None = None
    matching_preferences: dict | None = None
    assigned_manager_id: UUID | None = None
    created_by: str | None = None
    created_date: datetime | None = None

    model_config = {"from_attributes": True}


class RequestListResponse(BaseModel):
    """Paginated reconciliation request list response."""

    items: list[ReconciliationRequestResponse]
    total: int = Field(default=0, description="Total matching records")
    page: int = Field(default=1, description="Current page number")
    page_size: int = Field(default=50, description="Items per page")
    total_pages: int = Field(default=0, description="Total pages available")


class RequestStatisticsResponse(BaseModel):
    """Statistics for a reconciliation request (case counts by status)."""

    request_id: UUID
    total_cases: int = Field(default=0, description="Total number of cases")
    cases_by_status: dict[str, int] = Field(
        default_factory=dict, description="Case count per status"
    )
