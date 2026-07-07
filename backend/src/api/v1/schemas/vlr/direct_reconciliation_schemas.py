"""
Direct Reconciliation Pydantic schemas (request/response).

Provides validation for the direct reconciliation flow — single-vendor case
creation with inline configuration and dual file upload.

Requirements: 18.1, 18.2, 18.3, 18.4, 18.5, 18.6, 18.7, 18.8
"""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


# ──────────────────────────────────────────────────────────────────────
# Request Schemas
# ──────────────────────────────────────────────────────────────────────


class DirectReconciliationConfig(BaseModel):
    """
    Inline configuration for direct reconciliation case creation.

    Contains vendor selection, period definition, tolerance settings,
    and matching preferences — all specified inline with the dual file upload.
    """

    company_code: str = Field(
        ..., min_length=1, max_length=20, description="Company code"
    )
    vendor_id: UUID = Field(..., description="Single vendor ID for reconciliation")
    fiscal_year: str = Field(
        ..., min_length=1, max_length=10, description="Fiscal year (e.g., '2024-25')"
    )
    period_start: date = Field(..., description="Start of reconciliation period")
    period_end: date = Field(..., description="End of reconciliation period")
    tolerance_amount: Decimal = Field(
        default=Decimal("0"), ge=0, description="Tolerance amount for matching"
    )
    tds_percentage: Decimal = Field(
        default=Decimal("0"), ge=0, le=100, description="TDS percentage"
    )
    gst_percentage: Decimal = Field(
        default=Decimal("0"), ge=0, le=100, description="GST percentage"
    )
    fuzzy_threshold: float = Field(
        default=0.8, ge=0.0, le=1.0, description="Fuzzy matching similarity threshold"
    )

    @model_validator(mode="after")
    def validate_period_range(self) -> "DirectReconciliationConfig":
        """Ensure period_start is before or equal to period_end."""
        if self.period_start > self.period_end:
            raise ValueError(
                "period_start must be on or before period_end."
            )
        return self


# ──────────────────────────────────────────────────────────────────────
# Response Schemas
# ──────────────────────────────────────────────────────────────────────


class DirectReconciliationResponse(BaseModel):
    """Response for direct reconciliation case creation with immediate trigger."""

    case_id: UUID = Field(description="Created reconciliation case ID")
    request_id: UUID = Field(description="Parent reconciliation request ID")
    vendor_id: UUID = Field(description="Vendor ID for this reconciliation")
    case_type: str = Field(default="direct", description="Case type (always 'direct')")
    status: str = Field(description="Current case status after creation")
    company_entries_count: int = Field(
        description="Number of company ledger entries parsed"
    )
    vendor_entries_count: int = Field(
        description="Number of vendor ledger entries parsed"
    )
    reconciliation_triggered: bool = Field(
        description="Whether reconciliation was triggered immediately"
    )
    task_id: str | None = Field(
        default=None, description="Celery task ID if reconciliation was triggered"
    )
    message: str = Field(description="Human-readable result message")
    created_date: datetime | None = Field(
        default=None, description="Case creation timestamp"
    )
