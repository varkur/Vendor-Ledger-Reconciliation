"""
Reconciliation Case Pydantic schemas (request/response).

Provides validation for case detail, actions, and statistics.
Requirements: 3.4, 3.5, 3.6, 3.7, 11.2, 11.6
"""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field


# ──────────────────────────────────────────────────────────────────────
# Response Schemas
# ──────────────────────────────────────────────────────────────────────


class ReconciliationCaseResponse(BaseModel):
    """Response schema for a single reconciliation case."""

    id: UUID
    request_id: UUID
    vendor_id: UUID
    case_type: str
    status: str
    upload_count: int = 0
    edit_count: int = 0
    row_10_balance: Decimal | None = None
    match_statistics: dict | None = None
    created_date: datetime | None = None

    model_config = {"from_attributes": True}


class CaseActionResponse(BaseModel):
    """Response for case state-transition actions (confirm, invite, etc.)."""

    id: UUID
    status: str
    message: str = Field(description="Human-readable action result")


class CaseStatisticsResponse(BaseModel):
    """Match statistics for a reconciliation case."""

    case_id: UUID
    status: str
    total_company_entries: int = 0
    total_vendor_entries: int = 0
    matched_count: int = 0
    unmatched_count: int = 0
    match_percentage: float = 0.0
    matched_amount: Decimal = Decimal("0")
    row_10_balance: Decimal | None = None
    statistics_by_pass: dict | None = None


class ReconciliationStatementResponse(BaseModel):
    """Full reconciliation statement for a case."""

    case_id: UUID
    status: str
    company_entries: list[dict] = Field(default_factory=list)
    vendor_entries: list[dict] = Field(default_factory=list)
    match_results: list[dict] = Field(default_factory=list)
    exceptions: list[dict] = Field(default_factory=list)
    row_10_balance: Decimal | None = None


class ReconcileResponse(BaseModel):
    """Response for triggering reconciliation."""

    case_id: UUID
    task_id: str | None = Field(default=None, description="Celery task ID if async")
    status: str
    message: str
