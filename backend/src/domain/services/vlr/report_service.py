"""
Report Generation Domain Service.

Implements reconciliation statement generation, exception reports,
vendor status tracking, aging analysis, and monthly MIS reports
with session-level caching and PDF/Excel export capabilities.

Requirements: 9.1, 9.2, 9.3, 9.4, 9.7, 9.9, 9.10, 27.1, 27.2, 27.3,
              28.1, 28.2, 28.3, 29.1, 29.2, 29.3, 29.4
"""

import io
import json
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal
from enum import Enum
from uuid import UUID

from src.domain.repositories.vlr.case_repository import CaseFilters, ICaseRepository
from src.domain.repositories.vlr.exception_repository import (
    ExceptionFilters,
    IExceptionRepository,
)
from src.domain.repositories.vlr.ledger_entry_repository import ILedgerEntryRepository
from src.domain.repositories.vlr.match_result_repository import IMatchResultRepository
from src.domain.repositories.vlr.request_repository import IRequestRepository, RequestFilters
from src.domain.repositories.vlr.vendor_repository import (
    IVendorRepository,
    PaginationParams,
)


# ─── Enumerations ─────────────────────────────────────────────────────────────


class ReportType(str, Enum):
    """Available report types."""

    RECONCILIATION_STATEMENT = "reconciliation_statement"
    RECONCILIATION_SUMMARY = "reconciliation_summary"
    EXCEPTION_REPORT = "exception_report"
    VENDOR_STATUS = "vendor_status"
    MONTHLY_MIS = "monthly_mis"
    AGING_ANALYSIS = "aging_analysis"


class AgeingBucket(str, Enum):
    """Exception ageing buckets for reporting."""

    CURRENT = "0-30_days"
    DAYS_31_60 = "31-60_days"
    DAYS_61_90 = "61-90_days"
    OVER_90 = "over_90_days"


class AgingBucket(str, Enum):
    """
    Aging analysis buckets per Requirement 28.2.

    Defines: 0-30 days, 31-60 days, 61-90 days, 91-180 days, 180+ days.
    """

    DAYS_0_30 = "0-30_days"
    DAYS_31_60 = "31-60_days"
    DAYS_61_90 = "61-90_days"
    DAYS_91_180 = "91-180_days"
    DAYS_180_PLUS = "180+_days"


class ExportFormat(str, Enum):
    """Supported export formats for reports."""

    PDF = "pdf"
    EXCEL = "excel"


# ─── Data Transfer Objects ────────────────────────────────────────────────────


@dataclass
class ReconciliationSummaryRow:
    """A single row in the 10-row reconciliation summary report."""

    row_number: int
    description: str
    amount: Decimal = Decimal("0.00")


@dataclass
class ReconciliationSummaryReport:
    """
    10-row reconciliation summary report per BRD Section 10.2 (Table 37).

    Row 1: Closing Balance as per Emcure Books
    Row 2: Closing Balance as per Vendor Books
    Row 3: Amounts not reflected in Vendor Books (Debit)
    Row 4: Amounts not reflected in Vendor Books (Credit)
    Row 5: Amounts not reflected in Emcure Books (Debit)
    Row 6: Amounts not reflected in Emcure Books (Credit)
    Row 7: TDS Deducted by Emcure (not reflected in vendor)
    Row 8: Amount Difference (tolerance-matched items)
    Row 9: Timing Differences (date-proximity matched items)
    Row 10: Net Difference (MUST be 0.00 for approved cases)

    Requirements: 27.1, 27.2
    """

    case_id: UUID
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    rows: list[ReconciliationSummaryRow] = field(default_factory=list)
    company_closing_balance: Decimal = Decimal("0.00")
    vendor_closing_balance: Decimal = Decimal("0.00")
    unmatched_company_debit: Decimal = Decimal("0.00")
    unmatched_company_credit: Decimal = Decimal("0.00")
    unmatched_vendor_debit: Decimal = Decimal("0.00")
    unmatched_vendor_credit: Decimal = Decimal("0.00")
    tds_difference: Decimal = Decimal("0.00")
    amount_difference: Decimal = Decimal("0.00")
    timing_difference: Decimal = Decimal("0.00")
    net_difference: Decimal = Decimal("0.00")


@dataclass
class ReconciliationStatementEntry:
    """A single line in the reconciliation statement."""

    entry_id: UUID
    side: str
    amount: Decimal
    reference_number: str
    posting_date: date | None = None
    match_status: str = "unmatched"
    match_id: UUID | None = None
    pass_number: int | None = None
    confidence_score: float | None = None


@dataclass
class ReconciliationStatementReport:
    """
    Complete reconciliation statement for a case.

    Requirement 9.1: Generate statement with entries, matches, exceptions, Row_10.
    """

    case_id: UUID
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    company_entries: list[ReconciliationStatementEntry] = field(default_factory=list)
    vendor_entries: list[ReconciliationStatementEntry] = field(default_factory=list)
    matched_pairs_count: int = 0
    matched_groups_count: int = 0
    unmatched_company_count: int = 0
    unmatched_vendor_count: int = 0
    company_total: Decimal = Decimal("0")
    vendor_total: Decimal = Decimal("0")
    resolved_adjustments: Decimal = Decimal("0")
    row_10_balance: Decimal = Decimal("0")
    exceptions_summary: dict[str, int] = field(default_factory=dict)
    match_statistics: dict[int, dict] = field(default_factory=dict)


@dataclass
class AgeingEntry:
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


@dataclass
class ExceptionReportData:
    """
    Exception report with ageing, category, and resolution status.

    Requirement 9.2: Ageing analysis, category breakdown, resolution status.
    """

    case_id: UUID | None = None
    request_id: UUID | None = None
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    total_exceptions: int = 0
    exceptions_by_severity: dict[str, int] = field(default_factory=dict)
    exceptions_by_category: dict[str, int] = field(default_factory=dict)
    exceptions_by_status: dict[str, int] = field(default_factory=dict)
    ageing_buckets: dict[str, int] = field(default_factory=dict)
    ageing_amounts: dict[str, Decimal] = field(default_factory=dict)
    entries: list[AgeingEntry] = field(default_factory=list)
    total_exception_amount: Decimal = Decimal("0")


@dataclass
class VendorStatusEntry:
    """Status tracking for a single vendor case."""

    vendor_id: UUID
    vendor_name: str
    case_id: UUID
    case_status: str
    upload_count: int = 0
    has_responded: bool = False
    sign_off_status: str = "pending"
    last_activity_date: datetime | None = None


@dataclass
class VendorStatusReport:
    """
    Vendor status tracking report.

    Requirement 9.3: Response rates, upload status, sign-off tracking.
    """

    request_id: UUID | None = None
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    total_vendors: int = 0
    responded_count: int = 0
    response_rate: float = 0.0
    uploaded_count: int = 0
    upload_rate: float = 0.0
    signed_off_count: int = 0
    sign_off_rate: float = 0.0
    vendor_entries: list[VendorStatusEntry] = field(default_factory=list)


@dataclass
class MonthlyMISReport:
    """
    Monthly Management Information System report.

    Requirement 9.4: Volumes, match rates, exception trends, ageing analysis.
    """

    company_code: str = ""
    period_start: date | None = None
    period_end: date | None = None
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    total_requests: int = 0
    total_cases: int = 0
    total_entries_processed: int = 0
    total_matched: int = 0
    total_unmatched: int = 0
    overall_match_rate: float = 0.0
    match_rate_by_pass: dict[int, float] = field(default_factory=dict)
    total_exceptions: int = 0
    exceptions_resolved: int = 0
    exceptions_open: int = 0
    resolution_rate: float = 0.0
    exception_trends: dict[str, int] = field(default_factory=dict)
    ageing_analysis: dict[str, int] = field(default_factory=dict)
    ageing_amounts: dict[str, Decimal] = field(default_factory=dict)
    average_resolution_days: float = 0.0
    cases_by_status: dict[str, int] = field(default_factory=dict)


# ─── Aging Analysis DTOs (Requirements 28.1, 28.2) ───────────────────────────


@dataclass
class AgingFilters:
    """Filter criteria for aging analysis report."""

    vendor_id: UUID | None = None
    company_code: str | None = None
    status: str | None = None
    as_of_date: date | None = None  # defaults to today


@dataclass
class AgingItem:
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
    aging_bucket: str = AgingBucket.DAYS_0_30.value


@dataclass
class AgingBucketSummary:
    """Summary for a single aging bucket."""

    bucket: str
    count: int = 0
    total_amount: Decimal = Decimal("0.00")


@dataclass
class AgingAnalysisReport:
    """
    Aging analysis report groupable by vendor, bucket, and status.

    Requirements: 28.1, 28.2
    """

    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    as_of_date: date = field(default_factory=date.today)
    total_items: int = 0
    total_amount: Decimal = Decimal("0.00")
    bucket_summaries: list[AgingBucketSummary] = field(default_factory=list)
    by_vendor: dict[str, list[AgingBucketSummary]] = field(default_factory=dict)
    by_status: dict[str, list[AgingBucketSummary]] = field(default_factory=dict)
    items: list[AgingItem] = field(default_factory=list)


# ─── Enhanced Exception Report DTOs (Requirement 29.1) ───────────────────────


@dataclass
class ResolutionHistoryEntry:
    """A single resolution action for an exception."""

    action: str
    action_by: str = ""
    action_date: datetime | None = None
    notes: str = ""


@dataclass
class ExceptionWithHistory:
    """Exception item with its full resolution history."""

    exception_id: UUID
    case_id: UUID
    amount: Decimal = Decimal("0.00")
    severity: str = ""
    category: str = ""
    status: str = ""
    first_flagged_date: date | None = None
    resolution_history: list[ResolutionHistoryEntry] = field(default_factory=list)


@dataclass
class EnhancedExceptionReport:
    """
    Exception report with resolution history per Requirement 29.1.

    Lists all unmatched and disputed items with their resolution history.
    """

    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    total_exceptions: int = 0
    exceptions_by_status: dict[str, int] = field(default_factory=dict)
    exceptions_by_category: dict[str, int] = field(default_factory=dict)
    items: list[ExceptionWithHistory] = field(default_factory=list)
    total_amount: Decimal = Decimal("0.00")


# ─── Aggregate Reconciliation Summary ────────────────────────────────────────


@dataclass
class AggregateRecoSummaryRow:
    """A single row in the aggregate reconciliation summary across all cases."""

    id: str = ""
    vendor_name: str = ""
    opening_balance: Decimal = Decimal("0.00")
    invoices: Decimal = Decimal("0.00")
    payments: Decimal = Decimal("0.00")
    adjustments: Decimal = Decimal("0.00")
    closing_balance: Decimal = Decimal("0.00")
    difference: Decimal = Decimal("0.00")
    status: str = ""


@dataclass
class AggregateReconciliationSummaryResult:
    """Paginated aggregate reconciliation summary result."""

    items: list[AggregateRecoSummaryRow] = field(default_factory=list)
    total: int = 0
    page: int = 1
    page_size: int = 20


# ─── Export Report Record ─────────────────────────────────────────────────────


@dataclass
class GeneratedReport:
    """Record of a generated report for download."""

    report_id: str
    report_type: str
    format: str  # "pdf" or "excel"
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    content: bytes = b""
    filename: str = ""


# ─── Service ──────────────────────────────────────────────────────────────────


class ReportService:
    """
    Domain service for report generation.

    Generates reconciliation statements, exception reports, vendor status
    tracking, and monthly MIS reports. Implements session-level caching
    to avoid redundant computation within the same session.

    Requirement 9.7: Cache report data within the session.
    """

    def __init__(
        self,
        case_repository: ICaseRepository,
        exception_repository: IExceptionRepository,
        ledger_entry_repository: ILedgerEntryRepository,
        match_result_repository: IMatchResultRepository,
        request_repository: IRequestRepository,
        vendor_repository: IVendorRepository,
    ) -> None:
        self._case_repo = case_repository
        self._exception_repo = exception_repository
        self._ledger_repo = ledger_entry_repository
        self._match_repo = match_result_repository
        self._request_repo = request_repository
        self._vendor_repo = vendor_repository

        # Session-level cache (Requirement 9.7)
        self._cache: dict[str, object] = {}


    # ──────────────────────────────────────────────────────────────────────
    # Cache Management (Requirement 9.7)
    # ──────────────────────────────────────────────────────────────────────

    def _cache_key(self, report_type: str, identifier: str) -> str:
        """Generate a cache key for a report."""
        return f"{report_type}:{identifier}"

    def _get_cached(self, cache_key: str) -> object | None:
        """Retrieve a cached report if available."""
        return self._cache.get(cache_key)

    def _set_cached(self, cache_key: str, report: object) -> None:
        """Store a report in the session cache."""
        self._cache[cache_key] = report

    def clear_cache(self) -> None:
        """Clear all cached reports. Call when underlying data changes."""
        self._cache.clear()

    def invalidate_cache_for_case(self, case_id: UUID) -> None:
        """Invalidate cached reports related to a specific case."""
        keys_to_remove = [
            k for k in self._cache
            if str(case_id) in k
        ]
        for key in keys_to_remove:
            del self._cache[key]


    # ──────────────────────────────────────────────────────────────────────
    # Aggregate Reconciliation Summary (Requirement 16)
    # ──────────────────────────────────────────────────────────────────────

    async def generate_aggregate_reconciliation_summary(
        self,
        company_code: str,
        page: int = 1,
        page_size: int = 20,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> AggregateReconciliationSummaryResult:
        """
        Generate an aggregate reconciliation summary across all cases
        for the specified company_code.

        Returns paginated rows with vendor_name, opening_balance, invoices,
        payments, adjustments, closing_balance, difference, and status.

        Requirement 16: Reports Page — Reconciliation Summary.
        """
        from src.infrastructure.database.models.vlr.reconciliation_case_model import (
            ReconciliationCaseModel,
        )
        from src.infrastructure.database.models.vlr.vendor_model import VendorModel
        from src.infrastructure.database.models.vlr.reconciliation_request_model import (
            ReconciliationRequestModel,
        )

        # Use the case repository's underlying session for the custom query
        session = self._case_repo._session  # type: ignore[attr-defined]

        from sqlalchemy import select, func, and_

        # Build base query joining cases with vendors and requests
        base_conditions = [
            ReconciliationRequestModel.company_code == company_code,
            ReconciliationCaseModel.is_deleted == False,  # noqa: E712
        ]

        if date_from:
            base_conditions.append(
                func.date(ReconciliationCaseModel.created_date) >= date_from
            )
        if date_to:
            base_conditions.append(
                func.date(ReconciliationCaseModel.created_date) <= date_to
            )

        base_stmt = (
            select(ReconciliationCaseModel, VendorModel.name.label("vendor_name"))
            .join(
                ReconciliationRequestModel,
                ReconciliationCaseModel.request_id == ReconciliationRequestModel.id,
            )
            .join(
                VendorModel,
                ReconciliationCaseModel.vendor_id == VendorModel.id,
            )
            .where(and_(*base_conditions))
        )

        # Count total
        count_stmt = select(func.count()).select_from(base_stmt.subquery())
        total = (await session.execute(count_stmt)).scalar_one()

        # Paginated data query
        offset = (page - 1) * page_size
        data_stmt = (
            base_stmt.order_by(ReconciliationCaseModel.created_date.desc())
            .offset(offset)
            .limit(page_size)
        )
        result = await session.execute(data_stmt)
        rows = result.all()

        items: list[AggregateRecoSummaryRow] = []
        for row in rows:
            case = row[0]  # ReconciliationCaseModel
            vendor_name = row[1]  # vendor_name from join

            # Compute balances from the case model fields
            opening_balance = Decimal(str(case.company_opening_balance or 0))
            closing_balance = Decimal(str(case.company_closing_balance or 0))
            difference = Decimal(str(case.net_difference or 0))

            # Invoices, payments, adjustments are derived from the balance difference
            # (opening → closing). Without separate tracked columns, approximate from
            # closing - opening. In production, these would come from ledger aggregates.
            balance_change = closing_balance - opening_balance
            invoices = balance_change if balance_change > 0 else Decimal("0.00")
            payments = abs(balance_change) if balance_change < 0 else Decimal("0.00")
            adjustments = Decimal("0.00")  # Adjustments tracked separately if available

            items.append(
                AggregateRecoSummaryRow(
                    id=str(case.id),
                    vendor_name=vendor_name,
                    opening_balance=opening_balance,
                    invoices=invoices,
                    payments=payments,
                    adjustments=adjustments,
                    closing_balance=closing_balance,
                    difference=difference,
                    status=case.status or "",
                )
            )

        return AggregateReconciliationSummaryResult(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
        )

    # ──────────────────────────────────────────────────────────────────────
    # Reconciliation Summary Report (Requirements 27.1, 27.2)
    # ──────────────────────────────────────────────────────────────────────

    async def generate_reconciliation_summary(
        self,
        case_id: UUID,
        use_cache: bool = True,
    ) -> ReconciliationSummaryReport:
        """
        Generate the 10-row reconciliation summary report per BRD Section 10.2.

        Row 1: Closing Balance as per Emcure Books (from case.company_closing_balance)
        Row 2: Closing Balance as per Vendor Books (from case.vendor_closing_balance)
        Row 3: Amounts not reflected in Vendor Books (Debit - unmatched company debits)
        Row 4: Amounts not reflected in Vendor Books (Credit - unmatched company credits)
        Row 5: Amounts not reflected in Emcure Books (Debit - unmatched vendor debits)
        Row 6: Amounts not reflected in Emcure Books (Credit - unmatched vendor credits)
        Row 7: TDS Deducted by Emcure (TDS entries not in vendor)
        Row 8: Amount Difference (tolerance-matched items with differences)
        Row 9: Timing Differences (date-proximity matched items)
        Row 10: Net Difference = Row 1 - Row 2 - (Row 3 + Row 4 + Row 5 + Row 6 + Row 7 + Row 8 + Row 9)

        Requirements: 27.1, 27.2
        System Validation: Row 10 must equal 0.00 for approved cases.
        """
        cache_key = self._cache_key("recon_summary", str(case_id))
        if use_cache:
            cached = self._get_cached(cache_key)
            if cached is not None:
                return cached  # type: ignore[return-value]

        report = ReconciliationSummaryReport(case_id=case_id)

        # Get case data for closing balances
        case = await self._case_repo.get_by_id(case_id)

        # Row 1: Closing Balance as per Emcure Books
        company_closing = Decimal("0.00")
        if case is not None:
            raw_val = getattr(case, "company_closing_balance", None)
            if raw_val is not None:
                company_closing = Decimal(str(raw_val))
        report.company_closing_balance = company_closing

        # Row 2: Closing Balance as per Vendor Books
        vendor_closing = Decimal("0.00")
        if case is not None:
            raw_val = getattr(case, "vendor_closing_balance", None)
            if raw_val is not None:
                vendor_closing = Decimal(str(raw_val))
        report.vendor_closing_balance = vendor_closing

        # Get unmatched company entries (Rows 3 & 4)
        unmatched_company = await self._ledger_repo.get_unmatched_by_case(
            case_id, side="company"
        )
        unmatched_company_debit = Decimal("0.00")
        unmatched_company_credit = Decimal("0.00")
        for entry in unmatched_company:
            amount = Decimal(str(getattr(entry, "amount", 0)))
            is_tds = getattr(entry, "is_tds", False)
            # TDS entries are counted separately in Row 7
            if is_tds:
                continue
            if amount < 0:
                # Negative amount = debit (our invoices vendor hasn't recorded)
                unmatched_company_debit += amount
            else:
                # Positive amount = credit (our payments vendor hasn't recorded)
                unmatched_company_credit += amount
        report.unmatched_company_debit = unmatched_company_debit
        report.unmatched_company_credit = unmatched_company_credit

        # Get unmatched vendor entries (Rows 5 & 6)
        unmatched_vendor = await self._ledger_repo.get_unmatched_by_case(
            case_id, side="vendor"
        )
        unmatched_vendor_debit = Decimal("0.00")
        unmatched_vendor_credit = Decimal("0.00")
        for entry in unmatched_vendor:
            amount = Decimal(str(getattr(entry, "amount", 0)))
            if amount < 0:
                # Negative = vendor's debit notes we haven't recorded
                unmatched_vendor_debit += amount
            else:
                # Positive = vendor's invoices we haven't recorded
                unmatched_vendor_credit += amount
        report.unmatched_vendor_debit = unmatched_vendor_debit
        report.unmatched_vendor_credit = unmatched_vendor_credit

        # Row 7: TDS Deducted by Emcure (TDS-tagged entries not reflected in vendor)
        tds_difference = Decimal("0.00")
        for entry in unmatched_company:
            is_tds = getattr(entry, "is_tds", False)
            if is_tds:
                amount = Decimal(str(getattr(entry, "amount", 0)))
                tds_difference += amount
        report.tds_difference = tds_difference

        # Row 8: Amount Difference (tolerance-matched items with differences)
        # Pass 2 (TOLERANCE) match results have difference_amount
        tolerance_matches = await self._match_repo.get_by_case_and_pass(
            case_id, pass_number=2
        )
        amount_difference = Decimal("0.00")
        for match in tolerance_matches:
            diff = getattr(match, "difference_amount", None)
            if diff is not None:
                amount_difference += Decimal(str(diff))
        report.amount_difference = amount_difference

        # Row 9: Timing Differences (date-proximity matched items)
        # Pass 6 (DATE_PROXIMITY) match results
        date_proximity_matches = await self._match_repo.get_by_case_and_pass(
            case_id, pass_number=6
        )
        timing_difference = Decimal("0.00")
        for match in date_proximity_matches:
            diff = getattr(match, "difference_amount", None)
            if diff is not None:
                timing_difference += Decimal(str(diff))
        report.timing_difference = timing_difference

        # Row 10: Net Difference
        # Formula: Row 1 - Row 2 - (all adjustment rows)
        # Adjustments explain the gap between company and vendor closing balances
        total_adjustments = (
            unmatched_company_debit
            + unmatched_company_credit
            + unmatched_vendor_debit
            + unmatched_vendor_credit
            + tds_difference
            + amount_difference
            + timing_difference
        )
        net_difference = company_closing - vendor_closing - total_adjustments
        report.net_difference = net_difference

        # Build the 10 rows for structured output
        report.rows = [
            ReconciliationSummaryRow(
                row_number=1,
                description="Closing Balance as per Emcure Books",
                amount=company_closing,
            ),
            ReconciliationSummaryRow(
                row_number=2,
                description="Closing Balance as per Vendor Books",
                amount=vendor_closing,
            ),
            ReconciliationSummaryRow(
                row_number=3,
                description="Amounts not reflected in Vendor Books (Debit)",
                amount=unmatched_company_debit,
            ),
            ReconciliationSummaryRow(
                row_number=4,
                description="Amounts not reflected in Vendor Books (Credit)",
                amount=unmatched_company_credit,
            ),
            ReconciliationSummaryRow(
                row_number=5,
                description="Amounts not reflected in Emcure Books (Debit)",
                amount=unmatched_vendor_debit,
            ),
            ReconciliationSummaryRow(
                row_number=6,
                description="Amounts not reflected in Emcure Books (Credit)",
                amount=unmatched_vendor_credit,
            ),
            ReconciliationSummaryRow(
                row_number=7,
                description="TDS Deducted by Emcure",
                amount=tds_difference,
            ),
            ReconciliationSummaryRow(
                row_number=8,
                description="Amount Difference",
                amount=amount_difference,
            ),
            ReconciliationSummaryRow(
                row_number=9,
                description="Timing Differences",
                amount=timing_difference,
            ),
            ReconciliationSummaryRow(
                row_number=10,
                description="Net Difference",
                amount=net_difference,
            ),
        ]

        self._set_cached(cache_key, report)
        return report


    # ──────────────────────────────────────────────────────────────────────
    # Reconciliation Statement (Requirement 9.1)
    # ──────────────────────────────────────────────────────────────────────

    async def generate_reconciliation_statement(
        self,
        case_id: UUID,
        use_cache: bool = True,
    ) -> ReconciliationStatementReport:
        """
        Generate a complete reconciliation statement for a case.

        Includes: all entries (matched/unmatched), match results,
        exception summary, and Row_10 balance.

        Requirement 9.1: Reconciliation statement with entries, matches,
                         exceptions, and Row_10.
        Requirement 9.9: Include pass-level match statistics.
        Requirement 9.10: Include exception counts by severity.
        """
        cache_key = self._cache_key("recon_statement", str(case_id))
        if use_cache:
            cached = self._get_cached(cache_key)
            if cached is not None:
                return cached  # type: ignore[return-value]

        report = ReconciliationStatementReport(case_id=case_id)

        # Load all entries for both sides
        company_entries_raw = await self._ledger_repo.get_by_case_and_side(
            case_id, "company"
        )
        vendor_entries_raw = await self._ledger_repo.get_by_case_and_side(
            case_id, "vendor"
        )

        # Build company entries
        for entry in company_entries_raw:
            stmt_entry = ReconciliationStatementEntry(
                entry_id=getattr(entry, "id"),
                side="company",
                amount=Decimal(str(getattr(entry, "amount", 0))),
                reference_number=getattr(entry, "reference_number", ""),
                posting_date=getattr(entry, "posting_date", None),
                match_status="matched" if getattr(entry, "match_id", None) else "unmatched",
                match_id=getattr(entry, "match_id", None),
                pass_number=getattr(entry, "pass_number", None),
                confidence_score=getattr(entry, "confidence_score", None),
            )
            report.company_entries.append(stmt_entry)

        # Build vendor entries
        for entry in vendor_entries_raw:
            stmt_entry = ReconciliationStatementEntry(
                entry_id=getattr(entry, "id"),
                side="vendor",
                amount=Decimal(str(getattr(entry, "amount", 0))),
                reference_number=getattr(entry, "reference_number", ""),
                posting_date=getattr(entry, "posting_date", None),
                match_status="matched" if getattr(entry, "match_id", None) else "unmatched",
                match_id=getattr(entry, "match_id", None),
                pass_number=getattr(entry, "pass_number", None),
                confidence_score=getattr(entry, "confidence_score", None),
            )
            report.vendor_entries.append(stmt_entry)

        # Count matched/unmatched
        report.unmatched_company_count = sum(
            1 for e in report.company_entries if e.match_status == "unmatched"
        )
        report.unmatched_vendor_count = sum(
            1 for e in report.vendor_entries if e.match_status == "unmatched"
        )

        # Get match statistics (Requirement 9.9)
        match_stats = await self._match_repo.get_statistics_by_case(case_id)
        report.match_statistics = match_stats

        # Count matches
        match_count = await self._match_repo.count_by_case(case_id)
        report.matched_pairs_count = match_count

        # Calculate totals for Row_10
        company_total = Decimal(
            str(await self._ledger_repo.sum_amount_by_case(case_id, "company"))
        )
        vendor_total = Decimal(
            str(await self._ledger_repo.sum_amount_by_case(case_id, "vendor"))
        )
        report.company_total = company_total
        report.vendor_total = vendor_total

        # Get resolved adjustments for Row_10
        resolved_filters = ExceptionFilters(case_id=case_id, status="resolved")
        resolved_result = await self._exception_repo.list_by_case(
            case_id, filters=resolved_filters
        )
        resolved_adjustments = Decimal("0")
        for exc in resolved_result.items:
            resolved_adjustments += Decimal(str(getattr(exc, "amount", 0)))
        report.resolved_adjustments = resolved_adjustments

        # Row_10 = company - vendor - resolved adjustments
        report.row_10_balance = company_total - vendor_total - resolved_adjustments

        # Exception summary by severity (Requirement 9.10)
        severity_counts = await self._exception_repo.count_by_severity(case_id)
        report.exceptions_summary = severity_counts

        # Cache the result
        self._set_cached(cache_key, report)

        return report


    # ──────────────────────────────────────────────────────────────────────
    # Exception Report (Requirement 9.2)
    # ──────────────────────────────────────────────────────────────────────

    async def generate_exception_report(
        self,
        case_id: UUID,
        use_cache: bool = True,
    ) -> ExceptionReportData:
        """
        Generate an exception report with ageing, category breakdown,
        and resolution status.

        Requirement 9.2: Exception report with ageing analysis,
                         category breakdown, resolution status.
        """
        cache_key = self._cache_key("exception_report", str(case_id))
        if use_cache:
            cached = self._get_cached(cache_key)
            if cached is not None:
                return cached  # type: ignore[return-value]

        report = ExceptionReportData(case_id=case_id)
        today = date.today()

        # Get all exceptions for the case
        all_exceptions_result = await self._exception_repo.list_by_case(
            case_id, pagination=PaginationParams(page=1, page_size=10000)
        )
        all_exceptions = all_exceptions_result.items
        report.total_exceptions = len(all_exceptions)

        # Initialize ageing buckets
        ageing_buckets: dict[str, int] = {
            AgeingBucket.CURRENT.value: 0,
            AgeingBucket.DAYS_31_60.value: 0,
            AgeingBucket.DAYS_61_90.value: 0,
            AgeingBucket.OVER_90.value: 0,
        }
        ageing_amounts: dict[str, Decimal] = {
            AgeingBucket.CURRENT.value: Decimal("0"),
            AgeingBucket.DAYS_31_60.value: Decimal("0"),
            AgeingBucket.DAYS_61_90.value: Decimal("0"),
            AgeingBucket.OVER_90.value: Decimal("0"),
        }

        severity_counts: dict[str, int] = {}
        category_counts: dict[str, int] = {}
        status_counts: dict[str, int] = {}
        total_amount = Decimal("0")

        for exc in all_exceptions:
            severity = getattr(exc, "severity", "unknown")
            category = getattr(exc, "category", "unknown")
            status = getattr(exc, "status", "unknown")
            amount = Decimal(str(abs(getattr(exc, "amount", 0))))
            first_flagged = getattr(exc, "first_flagged_date", today)

            # Calculate age
            age_days = (today - first_flagged).days if first_flagged else 0
            bucket = self._get_ageing_bucket(age_days)

            # Update counts
            severity_counts[severity] = severity_counts.get(severity, 0) + 1
            category_counts[category] = category_counts.get(category, 0) + 1
            status_counts[status] = status_counts.get(status, 0) + 1
            ageing_buckets[bucket] = ageing_buckets.get(bucket, 0) + 1
            ageing_amounts[bucket] = ageing_amounts.get(bucket, Decimal("0")) + amount
            total_amount += amount

            # Build entry
            entry = AgeingEntry(
                exception_id=getattr(exc, "id"),
                case_id=case_id,
                amount=amount,
                severity=severity,
                category=category,
                status=status,
                first_flagged_date=first_flagged,
                age_days=age_days,
                ageing_bucket=bucket,
            )
            report.entries.append(entry)

        report.exceptions_by_severity = severity_counts
        report.exceptions_by_category = category_counts
        report.exceptions_by_status = status_counts
        report.ageing_buckets = ageing_buckets
        report.ageing_amounts = ageing_amounts
        report.total_exception_amount = total_amount

        self._set_cached(cache_key, report)
        return report

    @staticmethod
    def _get_ageing_bucket(age_days: int) -> str:
        """Classify age in days into an ageing bucket."""
        if age_days <= 30:
            return AgeingBucket.CURRENT.value
        elif age_days <= 60:
            return AgeingBucket.DAYS_31_60.value
        elif age_days <= 90:
            return AgeingBucket.DAYS_61_90.value
        else:
            return AgeingBucket.OVER_90.value


    # ──────────────────────────────────────────────────────────────────────
    # Vendor Status Report (Requirement 9.3)
    # ──────────────────────────────────────────────────────────────────────

    async def generate_vendor_status_report(
        self,
        request_id: UUID,
        company_code: str,
        use_cache: bool = True,
    ) -> VendorStatusReport:
        """
        Generate vendor status tracking report.

        Tracks response rates, upload status, and sign-off progress
        for all vendors in a reconciliation request.

        Requirement 9.3: Response rates, upload status, sign-off tracking.
        """
        cache_key = self._cache_key("vendor_status", str(request_id))
        if use_cache:
            cached = self._get_cached(cache_key)
            if cached is not None:
                return cached  # type: ignore[return-value]

        report = VendorStatusReport(request_id=request_id)

        # Get all cases for this request
        cases_result = await self._case_repo.list_by_request(
            request_id, pagination=PaginationParams(page=1, page_size=10000)
        )
        cases = cases_result.items
        report.total_vendors = len(cases)

        responded_count = 0
        uploaded_count = 0
        signed_off_count = 0

        for case in cases:
            case_id = getattr(case, "id")
            case_status = getattr(case, "status", "created")
            vendor_id = getattr(case, "vendor_id", None)
            upload_count = int(getattr(case, "upload_count", 0))
            updated_at = getattr(case, "updated_at", None)

            # Determine vendor name
            vendor_name = ""
            if vendor_id:
                vendor = await self._vendor_repo.get_by_id(vendor_id, company_code)
                if vendor:
                    vendor_name = getattr(vendor, "name", "")

            # Determine response status
            has_responded = self._has_vendor_responded(case_status)
            if has_responded:
                responded_count += 1

            # Upload tracking
            if upload_count > 0:
                uploaded_count += 1

            # Sign-off status
            sign_off_status = self._get_sign_off_status(case_status)
            if sign_off_status == "completed":
                signed_off_count += 1

            entry = VendorStatusEntry(
                vendor_id=vendor_id or case_id,
                vendor_name=vendor_name,
                case_id=case_id,
                case_status=case_status,
                upload_count=upload_count,
                has_responded=has_responded,
                sign_off_status=sign_off_status,
                last_activity_date=updated_at,
            )
            report.vendor_entries.append(entry)

        report.responded_count = responded_count
        report.uploaded_count = uploaded_count
        report.signed_off_count = signed_off_count

        # Calculate rates
        if report.total_vendors > 0:
            report.response_rate = round(
                (responded_count / report.total_vendors) * 100, 2
            )
            report.upload_rate = round(
                (uploaded_count / report.total_vendors) * 100, 2
            )
            report.sign_off_rate = round(
                (signed_off_count / report.total_vendors) * 100, 2
            )

        self._set_cached(cache_key, report)
        return report


    @staticmethod
    def _has_vendor_responded(case_status: str) -> bool:
        """
        Determine if a vendor has responded based on case status.

        A vendor is considered to have responded if the case has moved
        beyond the 'invited' stage (i.e., data has been received).
        """
        responded_statuses = {
            "data_received", "matching", "matched", "review",
            "pending_approval", "approved", "signed_off", "closed",
        }
        return case_status in responded_statuses

    @staticmethod
    def _get_sign_off_status(case_status: str) -> str:
        """Determine sign-off status from case status."""
        if case_status in ("signed_off", "closed"):
            return "completed"
        elif case_status in ("approved", "pending_approval"):
            return "in_progress"
        else:
            return "pending"


    # ──────────────────────────────────────────────────────────────────────
    # Monthly MIS Report (Requirement 9.4)
    # ──────────────────────────────────────────────────────────────────────

    async def generate_monthly_mis_report(
        self,
        company_code: str,
        period_start: date,
        period_end: date,
        use_cache: bool = True,
    ) -> MonthlyMISReport:
        """
        Generate a monthly MIS report for a company.

        Includes: volumes, match rates, exception trends, ageing analysis.

        Requirement 9.4: Monthly MIS with volumes, match rates,
                         exception trends, ageing analysis.
        """
        cache_key = self._cache_key(
            "monthly_mis",
            f"{company_code}:{period_start}:{period_end}",
        )
        if use_cache:
            cached = self._get_cached(cache_key)
            if cached is not None:
                return cached  # type: ignore[return-value]

        report = MonthlyMISReport(
            company_code=company_code,
            period_start=period_start,
            period_end=period_end,
        )

        # Get requests for the period
        request_filters = RequestFilters(
            date_from=period_start,
            date_to=period_end,
        )
        request_count = await self._request_repo.count(
            company_code, filters=request_filters
        )
        report.total_requests = request_count

        # Get all cases for this company in the period
        case_filters = CaseFilters()
        cases_result = await self._case_repo.list_cases(
            company_code,
            filters=case_filters,
            pagination=PaginationParams(page=1, page_size=10000),
        )
        cases = cases_result.items
        report.total_cases = len(cases)

        # Track status distribution
        cases_by_status: dict[str, int] = {}
        total_entries = 0
        total_matched = 0
        total_unmatched = 0

        for case in cases:
            case_id = getattr(case, "id")
            status = getattr(case, "status", "created")
            cases_by_status[status] = cases_by_status.get(status, 0) + 1

            # Count entries per case
            case_entry_count = await self._ledger_repo.count_by_case(case_id)
            total_entries += case_entry_count

            # Get match statistics for this case
            case_match_stats = await self._match_repo.get_statistics_by_case(case_id)
            if isinstance(case_match_stats, dict):
                for pass_num, stats in case_match_stats.items():
                    if isinstance(stats, dict):
                        match_count = stats.get("match_count", 0)
                        total_matched += match_count

            # Count unmatched entries
            unmatched = await self._ledger_repo.get_unmatched_by_case(case_id)
            total_unmatched += len(unmatched)

        report.total_entries_processed = total_entries
        report.total_matched = total_matched
        report.total_unmatched = total_unmatched

        # Calculate overall match rate
        if total_entries > 0:
            report.overall_match_rate = round(
                (total_matched / total_entries) * 100, 2
            )

        report.cases_by_status = cases_by_status

        # Exception trends and ageing analysis across all cases
        total_exceptions = 0
        exceptions_resolved = 0
        exceptions_open = 0
        exception_trends: dict[str, int] = {}
        ageing_analysis: dict[str, int] = {
            AgeingBucket.CURRENT.value: 0,
            AgeingBucket.DAYS_31_60.value: 0,
            AgeingBucket.DAYS_61_90.value: 0,
            AgeingBucket.OVER_90.value: 0,
        }
        ageing_amounts: dict[str, Decimal] = {
            AgeingBucket.CURRENT.value: Decimal("0"),
            AgeingBucket.DAYS_31_60.value: Decimal("0"),
            AgeingBucket.DAYS_61_90.value: Decimal("0"),
            AgeingBucket.OVER_90.value: Decimal("0"),
        }
        today = date.today()

        for case in cases:
            case_id = getattr(case, "id")

            # Get all exceptions for this case
            exc_result = await self._exception_repo.list_by_case(
                case_id, pagination=PaginationParams(page=1, page_size=10000)
            )
            case_exceptions = exc_result.items
            total_exceptions += len(case_exceptions)

            for exc in case_exceptions:
                status = getattr(exc, "status", "open")
                severity = getattr(exc, "severity", "unknown")
                amount = Decimal(str(abs(getattr(exc, "amount", 0))))
                first_flagged = getattr(exc, "first_flagged_date", today)

                # Status tracking
                if status == "resolved":
                    exceptions_resolved += 1
                elif status == "open":
                    exceptions_open += 1

                # Severity trends
                exception_trends[severity] = exception_trends.get(severity, 0) + 1

                # Ageing analysis
                age_days = (today - first_flagged).days if first_flagged else 0
                bucket = self._get_ageing_bucket(age_days)
                ageing_analysis[bucket] = ageing_analysis.get(bucket, 0) + 1
                ageing_amounts[bucket] = ageing_amounts.get(bucket, Decimal("0")) + amount

        report.total_exceptions = total_exceptions
        report.exceptions_resolved = exceptions_resolved
        report.exceptions_open = exceptions_open
        report.exception_trends = exception_trends
        report.ageing_analysis = ageing_analysis
        report.ageing_amounts = ageing_amounts

        # Resolution rate
        if total_exceptions > 0:
            report.resolution_rate = round(
                (exceptions_resolved / total_exceptions) * 100, 2
            )

        self._set_cached(cache_key, report)
        return report


    # ──────────────────────────────────────────────────────────────────────
    # Aging Analysis Report (Requirements 28.1, 28.2)
    # ──────────────────────────────────────────────────────────────────────

    async def generate_aging_analysis(
        self,
        company_code: str,
        filters: AgingFilters | None = None,
        use_cache: bool = True,
    ) -> AgingAnalysisReport:
        """
        Generate aging analysis report with grouping by vendor, bucket, status.

        Aging buckets: 0-30 days, 31-60 days, 61-90 days, 91-180 days, 180+ days.
        Groups unmatched ledger entries by their age since posting date.

        Requirements: 28.1, 28.2
        """
        filters = filters or AgingFilters()
        as_of_date = filters.as_of_date or date.today()

        cache_key = self._cache_key(
            "aging_analysis",
            f"{company_code}:{filters.vendor_id}:{filters.status}:{as_of_date}",
        )
        if use_cache:
            cached = self._get_cached(cache_key)
            if cached is not None:
                return cached  # type: ignore[return-value]

        report = AgingAnalysisReport(as_of_date=as_of_date)

        # Initialize bucket summaries
        bucket_counts: dict[str, int] = {b.value: 0 for b in AgingBucket}
        bucket_amounts: dict[str, Decimal] = {b.value: Decimal("0.00") for b in AgingBucket}
        by_vendor: dict[str, dict[str, tuple[int, Decimal]]] = {}
        by_status: dict[str, dict[str, tuple[int, Decimal]]] = {}

        # Get all cases for this company
        case_filters = CaseFilters(vendor_id=filters.vendor_id)
        cases_result = await self._case_repo.list_cases(
            company_code,
            filters=case_filters,
            pagination=PaginationParams(page=1, page_size=10000),
        )
        cases = cases_result.items

        for case in cases:
            case_id = getattr(case, "id")
            vendor_id = getattr(case, "vendor_id", None)
            case_status = getattr(case, "status", "open")

            # Apply status filter if specified
            if filters.status and case_status != filters.status:
                continue

            # Get vendor name
            vendor_name = ""
            if vendor_id:
                vendor = await self._vendor_repo.get_by_id(vendor_id, company_code)
                if vendor:
                    vendor_name = getattr(vendor, "name", str(vendor_id))

            # Get unmatched entries for this case
            unmatched_entries = await self._ledger_repo.get_unmatched_by_case(case_id)

            for entry in unmatched_entries:
                posting_date = getattr(entry, "posting_date", None)
                amount = Decimal(str(abs(getattr(entry, "amount", 0))))
                reference = getattr(entry, "reference_number", "")
                entry_id = getattr(entry, "id")

                # Calculate age
                if posting_date:
                    age_days = (as_of_date - posting_date).days
                else:
                    age_days = 0

                bucket = self._get_aging_bucket(age_days)

                # Build item
                item = AgingItem(
                    entry_id=entry_id,
                    case_id=case_id,
                    vendor_id=vendor_id,
                    vendor_name=vendor_name,
                    amount=amount,
                    posting_date=posting_date,
                    reference_number=reference,
                    status=case_status,
                    age_days=age_days,
                    aging_bucket=bucket,
                )
                report.items.append(item)
                report.total_items += 1
                report.total_amount += amount

                # Aggregate by bucket
                bucket_counts[bucket] = bucket_counts.get(bucket, 0) + 1
                bucket_amounts[bucket] = bucket_amounts.get(bucket, Decimal("0.00")) + amount

                # Aggregate by vendor
                vname = vendor_name or str(vendor_id or "unknown")
                if vname not in by_vendor:
                    by_vendor[vname] = {b.value: (0, Decimal("0.00")) for b in AgingBucket}
                existing = by_vendor[vname].get(bucket, (0, Decimal("0.00")))
                by_vendor[vname][bucket] = (existing[0] + 1, existing[1] + amount)

                # Aggregate by status
                if case_status not in by_status:
                    by_status[case_status] = {b.value: (0, Decimal("0.00")) for b in AgingBucket}
                existing_s = by_status[case_status].get(bucket, (0, Decimal("0.00")))
                by_status[case_status][bucket] = (existing_s[0] + 1, existing_s[1] + amount)

        # Build bucket summaries
        report.bucket_summaries = [
            AgingBucketSummary(
                bucket=b.value,
                count=bucket_counts[b.value],
                total_amount=bucket_amounts[b.value],
            )
            for b in AgingBucket
        ]

        # Build by_vendor grouped summaries
        for vname, buckets in by_vendor.items():
            report.by_vendor[vname] = [
                AgingBucketSummary(bucket=bk, count=cnt, total_amount=amt)
                for bk, (cnt, amt) in buckets.items()
            ]

        # Build by_status grouped summaries
        for st, buckets in by_status.items():
            report.by_status[st] = [
                AgingBucketSummary(bucket=bk, count=cnt, total_amount=amt)
                for bk, (cnt, amt) in buckets.items()
            ]

        self._set_cached(cache_key, report)
        return report

    @staticmethod
    def _get_aging_bucket(age_days: int) -> str:
        """
        Classify age in days into an aging bucket per Requirement 28.2.

        Buckets: 0-30, 31-60, 61-90, 91-180, 180+ days.
        """
        if age_days <= 30:
            return AgingBucket.DAYS_0_30.value
        elif age_days <= 60:
            return AgingBucket.DAYS_31_60.value
        elif age_days <= 90:
            return AgingBucket.DAYS_61_90.value
        elif age_days <= 180:
            return AgingBucket.DAYS_91_180.value
        else:
            return AgingBucket.DAYS_180_PLUS.value

    # ──────────────────────────────────────────────────────────────────────
    # Enhanced Exception Report with Resolution History (Requirement 29.1)
    # ──────────────────────────────────────────────────────────────────────

    async def generate_enhanced_exception_report(
        self,
        company_code: str,
        case_id: UUID | None = None,
        use_cache: bool = True,
    ) -> EnhancedExceptionReport:
        """
        Generate exception report with resolution history.

        Lists all unmatched and disputed items with their full
        resolution history (actions taken, timestamps, etc.).

        Requirement 29.1: Exception report with resolution history.
        """
        cache_key = self._cache_key(
            "enhanced_exception",
            f"{company_code}:{case_id}",
        )
        if use_cache:
            cached = self._get_cached(cache_key)
            if cached is not None:
                return cached  # type: ignore[return-value]

        report = EnhancedExceptionReport()

        # Get cases to process
        if case_id:
            case = await self._case_repo.get_by_id(case_id)
            cases = [case] if case else []
        else:
            case_filters = CaseFilters()
            cases_result = await self._case_repo.list_cases(
                company_code,
                filters=case_filters,
                pagination=PaginationParams(page=1, page_size=10000),
            )
            cases = cases_result.items

        status_counts: dict[str, int] = {}
        category_counts: dict[str, int] = {}
        total_amount = Decimal("0.00")

        for case in cases:
            c_id = getattr(case, "id")

            # Get all exceptions for this case
            exc_result = await self._exception_repo.list_by_case(
                c_id, pagination=PaginationParams(page=1, page_size=10000)
            )

            for exc in exc_result.items:
                exc_id = getattr(exc, "id")
                severity = getattr(exc, "severity", "unknown")
                category = getattr(exc, "category", "unknown")
                exc_status = getattr(exc, "status", "open")
                amount = Decimal(str(abs(getattr(exc, "amount", 0))))
                first_flagged = getattr(exc, "first_flagged_date", None)

                # Build resolution history from available data
                history: list[ResolutionHistoryEntry] = []
                resolved_at = getattr(exc, "resolved_at", None)
                resolved_by = getattr(exc, "resolved_by", "")
                resolution_notes = getattr(exc, "resolution_notes", "")

                # Initial flag entry
                history.append(ResolutionHistoryEntry(
                    action="flagged",
                    action_by="system",
                    action_date=getattr(exc, "created_at", None),
                    notes=f"Exception flagged with severity: {severity}",
                ))

                # Resolution entry if resolved
                if exc_status == "resolved" and resolved_at:
                    history.append(ResolutionHistoryEntry(
                        action="resolved",
                        action_by=resolved_by,
                        action_date=resolved_at,
                        notes=resolution_notes,
                    ))

                item = ExceptionWithHistory(
                    exception_id=exc_id,
                    case_id=c_id,
                    amount=amount,
                    severity=severity,
                    category=category,
                    status=exc_status,
                    first_flagged_date=first_flagged,
                    resolution_history=history,
                )
                report.items.append(item)
                total_amount += amount

                status_counts[exc_status] = status_counts.get(exc_status, 0) + 1
                category_counts[category] = category_counts.get(category, 0) + 1

        report.total_exceptions = len(report.items)
        report.exceptions_by_status = status_counts
        report.exceptions_by_category = category_counts
        report.total_amount = total_amount

        self._set_cached(cache_key, report)
        return report

    # ──────────────────────────────────────────────────────────────────────
    # Vendor Status Tracking Report (Requirement 29.2) — enhanced wrapper
    # ──────────────────────────────────────────────────────────────────────

    async def generate_vendor_status_tracking(
        self,
        company_code: str,
        use_cache: bool = True,
    ) -> VendorStatusReport:
        """
        Generate vendor status tracking report showing each vendor's
        reconciliation progress across all active cases.

        Requirement 29.2: Vendor status tracking report.
        """
        cache_key = self._cache_key("vendor_status_tracking", company_code)
        if use_cache:
            cached = self._get_cached(cache_key)
            if cached is not None:
                return cached  # type: ignore[return-value]

        report = VendorStatusReport()

        # Get all cases for this company
        cases_result = await self._case_repo.list_cases(
            company_code,
            filters=CaseFilters(),
            pagination=PaginationParams(page=1, page_size=10000),
        )
        cases = cases_result.items
        report.total_vendors = len(cases)

        responded_count = 0
        uploaded_count = 0
        signed_off_count = 0

        for case in cases:
            case_id = getattr(case, "id")
            case_status = getattr(case, "status", "created")
            vendor_id = getattr(case, "vendor_id", None)
            upload_count = int(getattr(case, "upload_count", 0))
            updated_at = getattr(case, "updated_at", None)

            vendor_name = ""
            if vendor_id:
                vendor = await self._vendor_repo.get_by_id(vendor_id, company_code)
                if vendor:
                    vendor_name = getattr(vendor, "name", "")

            has_responded = self._has_vendor_responded(case_status)
            if has_responded:
                responded_count += 1

            if upload_count > 0:
                uploaded_count += 1

            sign_off_status = self._get_sign_off_status(case_status)
            if sign_off_status == "completed":
                signed_off_count += 1

            entry = VendorStatusEntry(
                vendor_id=vendor_id or case_id,
                vendor_name=vendor_name,
                case_id=case_id,
                case_status=case_status,
                upload_count=upload_count,
                has_responded=has_responded,
                sign_off_status=sign_off_status,
                last_activity_date=updated_at,
            )
            report.vendor_entries.append(entry)

        report.responded_count = responded_count
        report.uploaded_count = uploaded_count
        report.signed_off_count = signed_off_count

        if report.total_vendors > 0:
            report.response_rate = round(
                (responded_count / report.total_vendors) * 100, 2
            )
            report.upload_rate = round(
                (uploaded_count / report.total_vendors) * 100, 2
            )
            report.sign_off_rate = round(
                (signed_off_count / report.total_vendors) * 100, 2
            )

        self._set_cached(cache_key, report)
        return report

    # ──────────────────────────────────────────────────────────────────────
    # Monthly MIS Report (Requirement 29.3) — enhanced wrapper
    # ──────────────────────────────────────────────────────────────────────

    async def generate_mis_report(
        self,
        company_code: str,
        period_start: date | None = None,
        period_end: date | None = None,
        use_cache: bool = True,
    ) -> MonthlyMISReport:
        """
        Generate monthly MIS report summarizing reconciliation activity.

        Defaults to current month if no dates provided.

        Requirement 29.3: Monthly MIS report.
        """
        today = date.today()
        if period_start is None:
            period_start = today.replace(day=1)
        if period_end is None:
            period_end = today

        return await self.generate_monthly_mis_report(
            company_code=company_code,
            period_start=period_start,
            period_end=period_end,
            use_cache=use_cache,
        )

    # ──────────────────────────────────────────────────────────────────────
    # PDF/Excel Export (Requirements 27.3, 28.3, 29.4)
    # ──────────────────────────────────────────────────────────────────────

    def export_to_excel(self, report: object, sheet_name: str = "Report") -> bytes:
        """
        Export any report dataclass to Excel format using openpyxl.

        Requirements: 27.3, 28.3, 29.4
        """
        report_data = self._report_to_dict(report)
        return self._generate_excel_bytes(report_data, sheet_name=sheet_name)

    def export_to_pdf(self, report: object, title: str = "VLR Report") -> bytes:
        """
        Export any report dataclass to PDF format.

        Uses reportlab if available; falls back to simple text-based PDF.

        Requirements: 27.3, 28.3, 29.4
        """
        report_data = self._report_to_dict(report)
        return self._generate_pdf_bytes(report_data, title=title)

    @staticmethod
    def _report_to_dict(report: object) -> dict:
        """Convert a dataclass report to a JSON-serializable dictionary."""
        raw = asdict(report)  # type: ignore[arg-type]

        class _Encoder(json.JSONEncoder):
            def default(self, obj):
                if isinstance(obj, Decimal):
                    return float(obj)
                if isinstance(obj, (datetime, date)):
                    return obj.isoformat()
                if isinstance(obj, UUID):
                    return str(obj)
                if isinstance(obj, bytes):
                    return "<binary>"
                return super().default(obj)

        return json.loads(json.dumps(raw, cls=_Encoder))

    @staticmethod
    def _generate_excel_bytes(report_data: dict, sheet_name: str = "Report") -> bytes:
        """
        Generate an Excel file from report data using openpyxl.

        Requirement 27.3, 28.3, 29.4: Export to Excel format.
        """
        try:
            from openpyxl import Workbook

            wb = Workbook()
            ws = wb.active
            ws.title = sheet_name

            # Write summary fields as header rows
            row_num = 1
            for key, value in report_data.items():
                if isinstance(value, (list, dict)):
                    continue
                ws.cell(row=row_num, column=1, value=str(key))
                ws.cell(row=row_num, column=2, value=str(value) if value is not None else "")
                row_num += 1

            # Write list data as tables
            list_fields = {k: v for k, v in report_data.items() if isinstance(v, list) and v}
            for field_name, items in list_fields.items():
                row_num += 1
                ws.cell(row=row_num, column=1, value=f"--- {field_name} ---")
                row_num += 1

                if items and isinstance(items[0], dict):
                    headers = list(items[0].keys())
                    for col_num, header in enumerate(headers, 1):
                        ws.cell(row=row_num, column=col_num, value=header)
                    row_num += 1

                    for item in items:
                        for col_num, header in enumerate(headers, 1):
                            val = item.get(header, "")
                            ws.cell(
                                row=row_num, column=col_num,
                                value=str(val) if val is not None else "",
                            )
                        row_num += 1

            buffer = io.BytesIO()
            wb.save(buffer)
            buffer.seek(0)
            return buffer.getvalue()

        except ImportError:
            # Fallback: CSV if openpyxl not available
            import csv

            buffer = io.StringIO()
            writer = csv.writer(buffer)

            for key, value in report_data.items():
                if isinstance(value, (list, dict)):
                    continue
                writer.writerow([key, str(value) if value is not None else ""])

            list_fields = {k: v for k, v in report_data.items() if isinstance(v, list) and v}
            for field_name, items in list_fields.items():
                writer.writerow([])
                writer.writerow([f"--- {field_name} ---"])
                if items and isinstance(items[0], dict):
                    headers = list(items[0].keys())
                    writer.writerow(headers)
                    for item in items:
                        writer.writerow([str(item.get(h, "")) for h in headers])

            return buffer.getvalue().encode("utf-8")

    @staticmethod
    def _generate_pdf_bytes(report_data: dict, title: str = "VLR Report") -> bytes:
        """
        Generate a PDF file from report data.

        Uses reportlab if available; falls back to simple text representation.

        Requirement 27.3, 28.3, 29.4: Export to PDF format.
        """
        try:
            from reportlab.lib import colors
            from reportlab.lib.pagesizes import A4
            from reportlab.lib.styles import getSampleStyleSheet
            from reportlab.platypus import (
                Paragraph,
                SimpleDocTemplate,
                Spacer,
                Table,
                TableStyle,
            )

            buffer = io.BytesIO()
            doc = SimpleDocTemplate(buffer, pagesize=A4)
            styles = getSampleStyleSheet()
            elements = []

            elements.append(Paragraph(title, styles["Title"]))
            elements.append(Spacer(1, 12))

            for key, value in report_data.items():
                if isinstance(value, (list, dict)):
                    continue
                elements.append(
                    Paragraph(f"<b>{key}:</b> {value}", styles["Normal"])
                )

            elements.append(Spacer(1, 12))

            list_fields = {k: v for k, v in report_data.items() if isinstance(v, list) and v}
            for field_name, items in list_fields.items():
                elements.append(Paragraph(f"<b>{field_name}</b>", styles["Heading2"]))
                elements.append(Spacer(1, 6))

                if items and isinstance(items[0], dict):
                    headers = list(items[0].keys())
                    table_data = [headers]
                    for item in items[:100]:
                        table_data.append(
                            [str(item.get(h, ""))[:50] for h in headers]
                        )

                    table = Table(table_data)
                    table.setStyle(TableStyle([
                        ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
                        ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                        ("FONTSIZE", (0, 0), (-1, -1), 7),
                        ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
                    ]))
                    elements.append(table)
                    elements.append(Spacer(1, 12))

            doc.build(elements)
            buffer.seek(0)
            return buffer.getvalue()

        except ImportError:
            # Fallback: plain text as PDF
            lines = [f"=== {title} ===", ""]
            for key, value in report_data.items():
                if isinstance(value, (list, dict)):
                    continue
                lines.append(f"{key}: {value}")

            lines.append("")
            list_fields = {k: v for k, v in report_data.items() if isinstance(v, list) and v}
            for field_name, items in list_fields.items():
                lines.append(f"--- {field_name} ---")
                if items and isinstance(items[0], dict):
                    headers = list(items[0].keys())
                    lines.append("\t".join(headers))
                    for item in items:
                        lines.append("\t".join(str(item.get(h, "")) for h in headers))
                lines.append("")

            return "\n".join(lines).encode("utf-8")
