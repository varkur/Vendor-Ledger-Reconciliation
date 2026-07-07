"""
Report Generation Domain Service.

Implements reconciliation statement generation, exception reports,
vendor status tracking, and monthly MIS reports with session-level caching.

Requirements: 9.1, 9.2, 9.3, 9.4, 9.7, 9.9, 9.10
"""

from dataclasses import dataclass, field
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
    EXCEPTION_REPORT = "exception_report"
    VENDOR_STATUS = "vendor_status"
    MONTHLY_MIS = "monthly_mis"


class AgeingBucket(str, Enum):
    """Exception ageing buckets for reporting."""

    CURRENT = "0-30_days"
    DAYS_31_60 = "31-60_days"
    DAYS_61_90 = "61-90_days"
    OVER_90 = "over_90_days"


# ─── Data Transfer Objects ────────────────────────────────────────────────────


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
