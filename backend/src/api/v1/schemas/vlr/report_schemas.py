"""
Report API Pydantic schemas (request/response).

Provides validation for reconciliation statement, exception report,
vendor status, monthly MIS, aging analysis, and export operations.
Requirements: 9.5, 9.6, 9.8, 11.2, 11.3, 27.1, 27.3, 28.1, 28.2, 28.3, 29.1, 29.2, 29.3, 29.4
"""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field


# ──────────────────────────────────────────────────────────────────────
# Reconciliation Statement Schemas
# ──────────────────────────────────────────────────────────────────────


class ReconciliationEntryResponse(BaseModel):
    """A single entry in the reconciliation statement."""

    entry_id: UUID
    side: str = Field(description="'company' or 'vendor'")
    amount: Decimal
    reference_number: str
    posting_date: date | None = None
    match_status: str = "unmatched"
    match_id: UUID | None = None
    pass_number: int | None = None
    confidence_score: float | None = None


class MatchStatistics(BaseModel):
    """Match statistics for a specific pass."""

    pass_number: int
    match_count: int = 0
    total_amount: Decimal = Decimal("0")


class ReconciliationStatementResponse(BaseModel):
    """Complete reconciliation statement for a case."""

    case_id: UUID
    generated_at: datetime
    company_entries: list[ReconciliationEntryResponse] = Field(default_factory=list)
    vendor_entries: list[ReconciliationEntryResponse] = Field(default_factory=list)
    matched_pairs_count: int = 0
    matched_groups_count: int = 0
    unmatched_company_count: int = 0
    unmatched_vendor_count: int = 0
    company_total: Decimal = Decimal("0")
    vendor_total: Decimal = Decimal("0")
    resolved_adjustments: Decimal = Decimal("0")
    row_10_balance: Decimal = Decimal("0")
    exceptions_summary: dict[str, int] = Field(default_factory=dict)
    match_statistics: dict[int, dict] = Field(default_factory=dict)


# ──────────────────────────────────────────────────────────────────────
# Reconciliation Summary Schemas (Requirement 27.1, 27.2)
# ──────────────────────────────────────────────────────────────────────


class ReconciliationSummaryRowResponse(BaseModel):
    """A single row in the 10-row reconciliation summary report."""

    row_number: int
    description: str
    amount: Decimal = Decimal("0.00")


class ReconciliationSummaryResponse(BaseModel):
    """10-row reconciliation summary report."""

    case_id: UUID
    generated_at: datetime
    rows: list[ReconciliationSummaryRowResponse] = Field(default_factory=list)
    company_closing_balance: Decimal = Decimal("0.00")
    vendor_closing_balance: Decimal = Decimal("0.00")
    net_difference: Decimal = Decimal("0.00")


# ──────────────────────────────────────────────────────────────────────
# Exception Report Schemas
# ──────────────────────────────────────────────────────────────────────


class AgeingEntryResponse(BaseModel):
    """An exception entry with ageing information."""

    exception_id: UUID
    case_id: UUID
    amount: Decimal
    severity: str
    category: str
    status: str
    first_flagged_date: date
    age_days: int
    ageing_bucket: str


class ExceptionReportResponse(BaseModel):
    """Exception report with ageing, categories, and resolution status."""

    case_id: UUID | None = None
    request_id: UUID | None = None
    generated_at: datetime
    total_exceptions: int = 0
    exceptions_by_severity: dict[str, int] = Field(default_factory=dict)
    exceptions_by_category: dict[str, int] = Field(default_factory=dict)
    exceptions_by_status: dict[str, int] = Field(default_factory=dict)
    ageing_buckets: dict[str, int] = Field(default_factory=dict)
    ageing_amounts: dict[str, Decimal] = Field(default_factory=dict)
    entries: list[AgeingEntryResponse] = Field(default_factory=list)
    total_exception_amount: Decimal = Decimal("0")


# ──────────────────────────────────────────────────────────────────────
# Enhanced Exception Report with Resolution History (Requirement 29.1)
# ──────────────────────────────────────────────────────────────────────


class ResolutionHistoryEntryResponse(BaseModel):
    """A single resolution action for an exception."""

    action: str
    action_by: str = ""
    action_date: datetime | None = None
    notes: str = ""


class ExceptionWithHistoryResponse(BaseModel):
    """Exception item with its full resolution history."""

    exception_id: UUID
    case_id: UUID
    amount: Decimal = Decimal("0.00")
    severity: str = ""
    category: str = ""
    status: str = ""
    first_flagged_date: date | None = None
    resolution_history: list[ResolutionHistoryEntryResponse] = Field(default_factory=list)


class EnhancedExceptionReportResponse(BaseModel):
    """Exception report with resolution history per Requirement 29.1."""

    generated_at: datetime
    total_exceptions: int = 0
    exceptions_by_status: dict[str, int] = Field(default_factory=dict)
    exceptions_by_category: dict[str, int] = Field(default_factory=dict)
    items: list[ExceptionWithHistoryResponse] = Field(default_factory=list)
    total_amount: Decimal = Decimal("0.00")


# ──────────────────────────────────────────────────────────────────────
# Aging Analysis Schemas (Requirements 28.1, 28.2)
# ──────────────────────────────────────────────────────────────────────


class AgingBucketSummaryResponse(BaseModel):
    """Summary for a single aging bucket."""

    bucket: str
    count: int = 0
    total_amount: Decimal = Decimal("0.00")


class AgingItemResponse(BaseModel):
    """A single item in the aging analysis report."""

    entry_id: UUID
    case_id: UUID
    vendor_id: UUID | None = None
    vendor_name: str = ""
    amount: Decimal = Decimal("0.00")
    posting_date: date | None = None
    reference_number: str = ""
    status: str = "unmatched"
    age_days: int = 0
    aging_bucket: str = "0-30_days"


class AgingAnalysisResponse(BaseModel):
    """Aging analysis report groupable by vendor, bucket, and status."""

    generated_at: datetime
    as_of_date: date
    total_items: int = 0
    total_amount: Decimal = Decimal("0.00")
    bucket_summaries: list[AgingBucketSummaryResponse] = Field(default_factory=list)
    by_vendor: dict[str, list[AgingBucketSummaryResponse]] = Field(default_factory=dict)
    by_status: dict[str, list[AgingBucketSummaryResponse]] = Field(default_factory=dict)
    items: list[AgingItemResponse] = Field(default_factory=list)


# ──────────────────────────────────────────────────────────────────────
# Vendor Status Report Schemas
# ──────────────────────────────────────────────────────────────────────


class VendorStatusEntryResponse(BaseModel):
    """Status tracking for a single vendor case."""

    vendor_id: UUID
    vendor_name: str
    case_id: UUID
    case_status: str
    upload_count: int = 0
    has_responded: bool = False
    sign_off_status: str = "pending"
    last_activity_date: datetime | None = None


class VendorStatusReportResponse(BaseModel):
    """Vendor status tracking report."""

    request_id: UUID | None = None
    generated_at: datetime
    total_vendors: int = 0
    responded_count: int = 0
    response_rate: float = 0.0
    uploaded_count: int = 0
    upload_rate: float = 0.0
    signed_off_count: int = 0
    sign_off_rate: float = 0.0
    vendor_entries: list[VendorStatusEntryResponse] = Field(default_factory=list)


# ──────────────────────────────────────────────────────────────────────
# Monthly MIS Report Schemas
# ──────────────────────────────────────────────────────────────────────


class MonthlyMISReportResponse(BaseModel):
    """Monthly Management Information System report."""

    company_code: str
    period_start: date | None = None
    period_end: date | None = None
    generated_at: datetime
    total_requests: int = 0
    total_cases: int = 0
    total_entries_processed: int = 0
    total_matched: int = 0
    total_unmatched: int = 0
    overall_match_rate: float = 0.0
    match_rate_by_pass: dict[int, float] = Field(default_factory=dict)
    total_exceptions: int = 0
    exceptions_resolved: int = 0
    exceptions_open: int = 0
    resolution_rate: float = 0.0
    exception_trends: dict[str, int] = Field(default_factory=dict)
    ageing_analysis: dict[str, int] = Field(default_factory=dict)
    ageing_amounts: dict[str, Decimal] = Field(default_factory=dict)
    average_resolution_days: float = 0.0
    cases_by_status: dict[str, int] = Field(default_factory=dict)


# ──────────────────────────────────────────────────────────────────────
# Export Request/Response Schemas
# ──────────────────────────────────────────────────────────────────────


class GenerateReportRequest(BaseModel):
    """Request to generate and store a report for later download."""

    report_type: str = Field(
        description="One of: reconciliation_summary, aging_analysis, exception_report, vendor_status, monthly_mis"
    )
    format: str = Field(default="excel", description="Export format: pdf or excel")
    case_id: UUID | None = None
    company_code: str | None = None
    period_start: date | None = None
    period_end: date | None = None


class GenerateReportResponse(BaseModel):
    """Response after triggering report generation."""

    report_id: str
    report_type: str
    format: str
    status: str = "generated"
    download_url: str = ""

