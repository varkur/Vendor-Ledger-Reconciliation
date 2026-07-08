"""
Unit tests for ReportService domain logic.

Tests reconciliation statement generation, exception reports,
vendor status tracking, monthly MIS reports, and session caching.
"""

import pytest
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

from src.domain.repositories.vlr.vendor_repository import PaginatedResult
from src.domain.services.vlr.report_service import (
    AgeingBucket,
    ExceptionReportData,
    MonthlyMISReport,
    ReconciliationStatementReport,
    ReconciliationSummaryReport,
    ReconciliationSummaryRow,
    ReportService,
    ReportType,
    VendorStatusReport,
)


# ─── Test Helpers ─────────────────────────────────────────────────────────────


@dataclass
class FakeLedgerEntry:
    """Fake ledger entry object for testing."""

    id: UUID = field(default_factory=uuid4)
    case_id: UUID = field(default_factory=uuid4)
    amount: Decimal = Decimal("5000.00")
    side: str = "company"
    reference_number: str = "REF001"
    posting_date: date = field(default_factory=date.today)
    match_id: UUID | None = None
    pass_number: int | None = None
    confidence_score: float | None = None


@dataclass
class FakeException:
    """Fake exception object for testing."""

    id: UUID = field(default_factory=uuid4)
    case_id: UUID = field(default_factory=uuid4)
    ledger_entry_id: UUID = field(default_factory=uuid4)
    category: str = "unmatched"
    severity: str = "medium"
    amount: Decimal = Decimal("5000.00")
    first_flagged_date: date = field(default_factory=date.today)
    status: str = "open"


@dataclass
class FakeCase:
    """Fake case object for testing."""

    id: UUID = field(default_factory=uuid4)
    status: str = "matched"
    vendor_id: UUID = field(default_factory=uuid4)
    upload_count: int = 1
    edit_count: int = 0
    updated_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


@dataclass
class FakeVendor:
    """Fake vendor object for testing."""

    id: UUID = field(default_factory=uuid4)
    name: str = "Test Vendor"
    vendor_code: str = "V001"
    status: str = "active"


# ─── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_case_repo() -> AsyncMock:
    """Create a mock case repository."""
    repo = AsyncMock()
    repo.get_by_id = AsyncMock(return_value=None)
    repo.list_by_request = AsyncMock(
        return_value=PaginatedResult(items=[], total=0, page=1, page_size=50)
    )
    repo.list_cases = AsyncMock(
        return_value=PaginatedResult(items=[], total=0, page=1, page_size=50)
    )
    repo.count_by_status = AsyncMock(return_value={})
    return repo


@pytest.fixture
def mock_exception_repo() -> AsyncMock:
    """Create a mock exception repository."""
    repo = AsyncMock()
    repo.get_by_id = AsyncMock(return_value=None)
    repo.list_by_case = AsyncMock(
        return_value=PaginatedResult(items=[], total=0, page=1, page_size=50)
    )
    repo.count_by_severity = AsyncMock(return_value={})
    repo.count_by_case = AsyncMock(return_value=0)
    return repo


@pytest.fixture
def mock_ledger_repo() -> AsyncMock:
    """Create a mock ledger entry repository."""
    repo = AsyncMock()
    repo.get_by_case_and_side = AsyncMock(return_value=[])
    repo.sum_amount_by_case = AsyncMock(return_value=0.0)
    repo.count_by_case = AsyncMock(return_value=0)
    repo.get_unmatched_by_case = AsyncMock(return_value=[])
    return repo


@pytest.fixture
def mock_match_repo() -> AsyncMock:
    """Create a mock match result repository."""
    repo = AsyncMock()
    repo.get_statistics_by_case = AsyncMock(return_value={})
    repo.count_by_case = AsyncMock(return_value=0)
    return repo


@pytest.fixture
def mock_request_repo() -> AsyncMock:
    """Create a mock request repository."""
    repo = AsyncMock()
    repo.count = AsyncMock(return_value=0)
    repo.list_requests = AsyncMock(
        return_value=PaginatedResult(items=[], total=0, page=1, page_size=50)
    )
    return repo


@pytest.fixture
def mock_vendor_repo() -> AsyncMock:
    """Create a mock vendor repository."""
    repo = AsyncMock()
    repo.get_by_id = AsyncMock(return_value=None)
    return repo


@pytest.fixture
def report_service(
    mock_case_repo: AsyncMock,
    mock_exception_repo: AsyncMock,
    mock_ledger_repo: AsyncMock,
    mock_match_repo: AsyncMock,
    mock_request_repo: AsyncMock,
    mock_vendor_repo: AsyncMock,
) -> ReportService:
    """Create ReportService with mocked repositories."""
    return ReportService(
        case_repository=mock_case_repo,
        exception_repository=mock_exception_repo,
        ledger_entry_repository=mock_ledger_repo,
        match_result_repository=mock_match_repo,
        request_repository=mock_request_repo,
        vendor_repository=mock_vendor_repo,
    )


# ─── Reconciliation Statement Tests ──────────────────────────────────────────


class TestReconciliationStatement:
    """Tests for reconciliation statement generation."""

    async def test_generate_empty_case(
        self,
        report_service: ReportService,
        mock_ledger_repo: AsyncMock,
        mock_match_repo: AsyncMock,
        mock_exception_repo: AsyncMock,
    ):
        """Should generate an empty statement for a case with no entries."""
        case_id = uuid4()
        mock_ledger_repo.get_by_case_and_side.return_value = []
        mock_ledger_repo.sum_amount_by_case.return_value = 0.0
        mock_match_repo.get_statistics_by_case.return_value = {}
        mock_match_repo.count_by_case.return_value = 0
        mock_exception_repo.list_by_case.return_value = PaginatedResult(
            items=[], total=0, page=1, page_size=50
        )
        mock_exception_repo.count_by_severity.return_value = {}

        result = await report_service.generate_reconciliation_statement(case_id)

        assert result.case_id == case_id
        assert result.company_entries == []
        assert result.vendor_entries == []
        assert result.row_10_balance == Decimal("0")
        assert result.matched_pairs_count == 0

    async def test_generate_with_entries(
        self,
        report_service: ReportService,
        mock_ledger_repo: AsyncMock,
        mock_match_repo: AsyncMock,
        mock_exception_repo: AsyncMock,
    ):
        """Should include all company and vendor entries in the statement."""
        case_id = uuid4()
        match_id = uuid4()

        company_entries = [
            FakeLedgerEntry(
                amount=Decimal("10000"), side="company",
                match_id=match_id, pass_number=1, confidence_score=1.0,
            ),
            FakeLedgerEntry(
                amount=Decimal("5000"), side="company",
            ),
        ]
        vendor_entries = [
            FakeLedgerEntry(
                amount=Decimal("10000"), side="vendor",
                match_id=match_id, pass_number=1, confidence_score=1.0,
            ),
        ]

        mock_ledger_repo.get_by_case_and_side.side_effect = [
            company_entries, vendor_entries
        ]
        mock_ledger_repo.sum_amount_by_case.side_effect = [15000.0, 10000.0]
        mock_match_repo.get_statistics_by_case.return_value = {
            1: {"match_count": 1, "matched_amount": 10000}
        }
        mock_match_repo.count_by_case.return_value = 1
        mock_exception_repo.list_by_case.return_value = PaginatedResult(
            items=[], total=0, page=1, page_size=50
        )
        mock_exception_repo.count_by_severity.return_value = {"medium": 1}

        result = await report_service.generate_reconciliation_statement(case_id)

        assert len(result.company_entries) == 2
        assert len(result.vendor_entries) == 1
        assert result.company_entries[0].match_status == "matched"
        assert result.company_entries[1].match_status == "unmatched"
        assert result.unmatched_company_count == 1
        assert result.unmatched_vendor_count == 0
        assert result.matched_pairs_count == 1

    async def test_row_10_calculation(
        self,
        report_service: ReportService,
        mock_ledger_repo: AsyncMock,
        mock_match_repo: AsyncMock,
        mock_exception_repo: AsyncMock,
    ):
        """Should calculate Row_10 = company - vendor - resolved adjustments."""
        case_id = uuid4()
        mock_ledger_repo.get_by_case_and_side.return_value = []
        mock_ledger_repo.sum_amount_by_case.side_effect = [150000.0, 100000.0]
        mock_match_repo.get_statistics_by_case.return_value = {}
        mock_match_repo.count_by_case.return_value = 0
        mock_exception_repo.count_by_severity.return_value = {}

        # One resolved exception with amount 50000
        resolved_exc = FakeException(amount=Decimal("50000"), status="resolved")
        mock_exception_repo.list_by_case.return_value = PaginatedResult(
            items=[resolved_exc], total=1, page=1, page_size=50
        )

        result = await report_service.generate_reconciliation_statement(case_id)

        assert result.company_total == Decimal("150000.0")
        assert result.vendor_total == Decimal("100000.0")
        assert result.resolved_adjustments == Decimal("50000")
        assert result.row_10_balance == Decimal("0")

    async def test_match_statistics_included(
        self,
        report_service: ReportService,
        mock_ledger_repo: AsyncMock,
        mock_match_repo: AsyncMock,
        mock_exception_repo: AsyncMock,
    ):
        """Should include match statistics per pass in the report."""
        case_id = uuid4()
        mock_ledger_repo.get_by_case_and_side.return_value = []
        mock_ledger_repo.sum_amount_by_case.return_value = 0.0
        expected_stats = {
            1: {"match_count": 5, "matched_amount": 50000, "percentage": 50.0},
            2: {"match_count": 2, "matched_amount": 20000, "percentage": 20.0},
        }
        mock_match_repo.get_statistics_by_case.return_value = expected_stats
        mock_match_repo.count_by_case.return_value = 7
        mock_exception_repo.list_by_case.return_value = PaginatedResult(
            items=[], total=0, page=1, page_size=50
        )
        mock_exception_repo.count_by_severity.return_value = {}

        result = await report_service.generate_reconciliation_statement(case_id)

        assert result.match_statistics == expected_stats


# ─── Exception Report Tests ───────────────────────────────────────────────────


class TestExceptionReport:
    """Tests for exception report generation."""

    async def test_generate_empty_exceptions(
        self,
        report_service: ReportService,
        mock_exception_repo: AsyncMock,
    ):
        """Should generate report with zero counts for no exceptions."""
        case_id = uuid4()
        mock_exception_repo.list_by_case.return_value = PaginatedResult(
            items=[], total=0, page=1, page_size=10000
        )

        result = await report_service.generate_exception_report(case_id)

        assert result.case_id == case_id
        assert result.total_exceptions == 0
        assert result.total_exception_amount == Decimal("0")
        assert result.entries == []

    async def test_ageing_bucket_classification(
        self,
        report_service: ReportService,
        mock_exception_repo: AsyncMock,
    ):
        """Should correctly classify exceptions into ageing buckets."""
        case_id = uuid4()
        today = date.today()

        exceptions = [
            FakeException(
                amount=Decimal("1000"),
                first_flagged_date=today - timedelta(days=10),
                severity="low",
            ),
            FakeException(
                amount=Decimal("2000"),
                first_flagged_date=today - timedelta(days=45),
                severity="medium",
            ),
            FakeException(
                amount=Decimal("3000"),
                first_flagged_date=today - timedelta(days=75),
                severity="high",
            ),
            FakeException(
                amount=Decimal("4000"),
                first_flagged_date=today - timedelta(days=120),
                severity="critical",
            ),
        ]
        mock_exception_repo.list_by_case.return_value = PaginatedResult(
            items=exceptions, total=4, page=1, page_size=10000
        )

        result = await report_service.generate_exception_report(case_id)

        assert result.total_exceptions == 4
        assert result.ageing_buckets[AgeingBucket.CURRENT.value] == 1
        assert result.ageing_buckets[AgeingBucket.DAYS_31_60.value] == 1
        assert result.ageing_buckets[AgeingBucket.DAYS_61_90.value] == 1
        assert result.ageing_buckets[AgeingBucket.OVER_90.value] == 1

    async def test_severity_and_category_breakdown(
        self,
        report_service: ReportService,
        mock_exception_repo: AsyncMock,
    ):
        """Should correctly count exceptions by severity and category."""
        case_id = uuid4()
        today = date.today()

        exceptions = [
            FakeException(severity="critical", category="unmatched"),
            FakeException(severity="critical", category="unmatched"),
            FakeException(severity="high", category="disputed"),
            FakeException(severity="medium", category="unmatched"),
        ]
        mock_exception_repo.list_by_case.return_value = PaginatedResult(
            items=exceptions, total=4, page=1, page_size=10000
        )

        result = await report_service.generate_exception_report(case_id)

        assert result.exceptions_by_severity["critical"] == 2
        assert result.exceptions_by_severity["high"] == 1
        assert result.exceptions_by_severity["medium"] == 1
        assert result.exceptions_by_category["unmatched"] == 3
        assert result.exceptions_by_category["disputed"] == 1

    async def test_resolution_status_breakdown(
        self,
        report_service: ReportService,
        mock_exception_repo: AsyncMock,
    ):
        """Should correctly count exceptions by resolution status."""
        case_id = uuid4()

        exceptions = [
            FakeException(status="open"),
            FakeException(status="open"),
            FakeException(status="resolved"),
            FakeException(status="escalated"),
        ]
        mock_exception_repo.list_by_case.return_value = PaginatedResult(
            items=exceptions, total=4, page=1, page_size=10000
        )

        result = await report_service.generate_exception_report(case_id)

        assert result.exceptions_by_status["open"] == 2
        assert result.exceptions_by_status["resolved"] == 1
        assert result.exceptions_by_status["escalated"] == 1

    async def test_total_exception_amount(
        self,
        report_service: ReportService,
        mock_exception_repo: AsyncMock,
    ):
        """Should sum all exception amounts correctly."""
        case_id = uuid4()

        exceptions = [
            FakeException(amount=Decimal("10000")),
            FakeException(amount=Decimal("-5000")),  # Negative amounts use abs
            FakeException(amount=Decimal("3000")),
        ]
        mock_exception_repo.list_by_case.return_value = PaginatedResult(
            items=exceptions, total=3, page=1, page_size=10000
        )

        result = await report_service.generate_exception_report(case_id)

        # Uses abs(amount): 10000 + 5000 + 3000 = 18000
        assert result.total_exception_amount == Decimal("18000")

    async def test_ageing_amounts(
        self,
        report_service: ReportService,
        mock_exception_repo: AsyncMock,
    ):
        """Should aggregate amounts per ageing bucket."""
        case_id = uuid4()
        today = date.today()

        exceptions = [
            FakeException(
                amount=Decimal("1000"),
                first_flagged_date=today - timedelta(days=5),
            ),
            FakeException(
                amount=Decimal("2000"),
                first_flagged_date=today - timedelta(days=15),
            ),
        ]
        mock_exception_repo.list_by_case.return_value = PaginatedResult(
            items=exceptions, total=2, page=1, page_size=10000
        )

        result = await report_service.generate_exception_report(case_id)

        assert result.ageing_amounts[AgeingBucket.CURRENT.value] == Decimal("3000")


# ─── Vendor Status Report Tests ───────────────────────────────────────────────


class TestVendorStatusReport:
    """Tests for vendor status tracking report."""

    async def test_generate_empty_request(
        self,
        report_service: ReportService,
        mock_case_repo: AsyncMock,
    ):
        """Should return zero counts for a request with no cases."""
        request_id = uuid4()
        mock_case_repo.list_by_request.return_value = PaginatedResult(
            items=[], total=0, page=1, page_size=10000
        )

        result = await report_service.generate_vendor_status_report(
            request_id, "COMP01"
        )

        assert result.total_vendors == 0
        assert result.response_rate == 0.0
        assert result.upload_rate == 0.0
        assert result.sign_off_rate == 0.0

    async def test_response_rate_calculation(
        self,
        report_service: ReportService,
        mock_case_repo: AsyncMock,
        mock_vendor_repo: AsyncMock,
    ):
        """Should correctly calculate vendor response rate."""
        request_id = uuid4()
        vendor = FakeVendor()
        mock_vendor_repo.get_by_id.return_value = vendor

        cases = [
            FakeCase(status="data_received", vendor_id=vendor.id),
            FakeCase(status="invited", vendor_id=vendor.id),
            FakeCase(status="matched", vendor_id=vendor.id),
            FakeCase(status="created", vendor_id=vendor.id),
        ]
        mock_case_repo.list_by_request.return_value = PaginatedResult(
            items=cases, total=4, page=1, page_size=10000
        )

        result = await report_service.generate_vendor_status_report(
            request_id, "COMP01"
        )

        assert result.total_vendors == 4
        assert result.responded_count == 2  # data_received, matched
        assert result.response_rate == 50.0

    async def test_upload_tracking(
        self,
        report_service: ReportService,
        mock_case_repo: AsyncMock,
        mock_vendor_repo: AsyncMock,
    ):
        """Should track upload counts correctly."""
        request_id = uuid4()
        mock_vendor_repo.get_by_id.return_value = FakeVendor()

        cases = [
            FakeCase(status="data_received", upload_count=2),
            FakeCase(status="invited", upload_count=0),
            FakeCase(status="matched", upload_count=1),
        ]
        mock_case_repo.list_by_request.return_value = PaginatedResult(
            items=cases, total=3, page=1, page_size=10000
        )

        result = await report_service.generate_vendor_status_report(
            request_id, "COMP01"
        )

        assert result.uploaded_count == 2  # upload_count > 0
        assert result.upload_rate == pytest.approx(66.67, rel=0.01)

    async def test_sign_off_tracking(
        self,
        report_service: ReportService,
        mock_case_repo: AsyncMock,
        mock_vendor_repo: AsyncMock,
    ):
        """Should track sign-off status correctly."""
        request_id = uuid4()
        mock_vendor_repo.get_by_id.return_value = FakeVendor()

        cases = [
            FakeCase(status="signed_off"),
            FakeCase(status="closed"),
            FakeCase(status="pending_approval"),
            FakeCase(status="matched"),
        ]
        mock_case_repo.list_by_request.return_value = PaginatedResult(
            items=cases, total=4, page=1, page_size=10000
        )

        result = await report_service.generate_vendor_status_report(
            request_id, "COMP01"
        )

        assert result.signed_off_count == 2  # signed_off + closed
        assert result.sign_off_rate == 50.0

    async def test_vendor_name_resolved(
        self,
        report_service: ReportService,
        mock_case_repo: AsyncMock,
        mock_vendor_repo: AsyncMock,
    ):
        """Should resolve vendor names from vendor repository."""
        request_id = uuid4()
        vendor = FakeVendor(name="Acme Corp")
        mock_vendor_repo.get_by_id.return_value = vendor

        cases = [FakeCase(status="matched", vendor_id=vendor.id)]
        mock_case_repo.list_by_request.return_value = PaginatedResult(
            items=cases, total=1, page=1, page_size=10000
        )

        result = await report_service.generate_vendor_status_report(
            request_id, "COMP01"
        )

        assert result.vendor_entries[0].vendor_name == "Acme Corp"

    async def test_has_responded_statuses(self, report_service: ReportService):
        """Should recognize all responded statuses."""
        responded_statuses = [
            "data_received", "matching", "matched", "review",
            "pending_approval", "approved", "signed_off", "closed",
        ]
        not_responded = ["created", "ledger_confirmed", "invited"]

        for status in responded_statuses:
            assert report_service._has_vendor_responded(status) is True

        for status in not_responded:
            assert report_service._has_vendor_responded(status) is False


# ─── Monthly MIS Report Tests ─────────────────────────────────────────────────


class TestMonthlyMISReport:
    """Tests for monthly MIS report generation."""

    async def test_generate_empty_period(
        self,
        report_service: ReportService,
        mock_request_repo: AsyncMock,
        mock_case_repo: AsyncMock,
    ):
        """Should return zero counts for an empty period."""
        mock_request_repo.count.return_value = 0
        mock_case_repo.list_cases.return_value = PaginatedResult(
            items=[], total=0, page=1, page_size=10000
        )

        result = await report_service.generate_monthly_mis_report(
            company_code="COMP01",
            period_start=date(2024, 1, 1),
            period_end=date(2024, 1, 31),
        )

        assert result.company_code == "COMP01"
        assert result.total_requests == 0
        assert result.total_cases == 0
        assert result.overall_match_rate == 0.0

    async def test_match_rate_calculation(
        self,
        report_service: ReportService,
        mock_request_repo: AsyncMock,
        mock_case_repo: AsyncMock,
        mock_ledger_repo: AsyncMock,
        mock_match_repo: AsyncMock,
        mock_exception_repo: AsyncMock,
    ):
        """Should calculate overall match rate correctly."""
        case = FakeCase(status="matched")
        mock_request_repo.count.return_value = 1
        mock_case_repo.list_cases.return_value = PaginatedResult(
            items=[case], total=1, page=1, page_size=10000
        )
        # 100 entries, 80 matched
        mock_ledger_repo.count_by_case.return_value = 100
        mock_match_repo.get_statistics_by_case.return_value = {
            1: {"match_count": 60, "matched_amount": 600000},
            2: {"match_count": 20, "matched_amount": 200000},
        }
        mock_ledger_repo.get_unmatched_by_case.return_value = [
            FakeLedgerEntry() for _ in range(20)
        ]
        mock_exception_repo.list_by_case.return_value = PaginatedResult(
            items=[], total=0, page=1, page_size=10000
        )

        result = await report_service.generate_monthly_mis_report(
            company_code="COMP01",
            period_start=date(2024, 1, 1),
            period_end=date(2024, 1, 31),
        )

        assert result.total_entries_processed == 100
        assert result.total_matched == 80
        assert result.overall_match_rate == 80.0

    async def test_exception_trends(
        self,
        report_service: ReportService,
        mock_request_repo: AsyncMock,
        mock_case_repo: AsyncMock,
        mock_ledger_repo: AsyncMock,
        mock_match_repo: AsyncMock,
        mock_exception_repo: AsyncMock,
    ):
        """Should track exception severity trends across cases."""
        case = FakeCase(status="matched")
        mock_request_repo.count.return_value = 1
        mock_case_repo.list_cases.return_value = PaginatedResult(
            items=[case], total=1, page=1, page_size=10000
        )
        mock_ledger_repo.count_by_case.return_value = 10
        mock_match_repo.get_statistics_by_case.return_value = {}
        mock_ledger_repo.get_unmatched_by_case.return_value = []

        exceptions = [
            FakeException(severity="critical", status="open"),
            FakeException(severity="high", status="resolved"),
            FakeException(severity="high", status="open"),
        ]
        mock_exception_repo.list_by_case.return_value = PaginatedResult(
            items=exceptions, total=3, page=1, page_size=10000
        )

        result = await report_service.generate_monthly_mis_report(
            company_code="COMP01",
            period_start=date(2024, 1, 1),
            period_end=date(2024, 1, 31),
        )

        assert result.total_exceptions == 3
        assert result.exceptions_resolved == 1
        assert result.exceptions_open == 2
        assert result.exception_trends["critical"] == 1
        assert result.exception_trends["high"] == 2
        assert result.resolution_rate == pytest.approx(33.33, rel=0.01)

    async def test_cases_by_status(
        self,
        report_service: ReportService,
        mock_request_repo: AsyncMock,
        mock_case_repo: AsyncMock,
        mock_ledger_repo: AsyncMock,
        mock_match_repo: AsyncMock,
        mock_exception_repo: AsyncMock,
    ):
        """Should track cases by status distribution."""
        cases = [
            FakeCase(status="matched"),
            FakeCase(status="matched"),
            FakeCase(status="closed"),
            FakeCase(status="review"),
        ]
        mock_request_repo.count.return_value = 1
        mock_case_repo.list_cases.return_value = PaginatedResult(
            items=cases, total=4, page=1, page_size=10000
        )
        mock_ledger_repo.count_by_case.return_value = 0
        mock_match_repo.get_statistics_by_case.return_value = {}
        mock_ledger_repo.get_unmatched_by_case.return_value = []
        mock_exception_repo.list_by_case.return_value = PaginatedResult(
            items=[], total=0, page=1, page_size=10000
        )

        result = await report_service.generate_monthly_mis_report(
            company_code="COMP01",
            period_start=date(2024, 1, 1),
            period_end=date(2024, 1, 31),
        )

        assert result.cases_by_status["matched"] == 2
        assert result.cases_by_status["closed"] == 1
        assert result.cases_by_status["review"] == 1


# ─── Cache Tests ──────────────────────────────────────────────────────────────


class TestReportCaching:
    """Tests for session-level report caching."""

    async def test_cache_returns_cached_result(
        self,
        report_service: ReportService,
        mock_ledger_repo: AsyncMock,
        mock_match_repo: AsyncMock,
        mock_exception_repo: AsyncMock,
    ):
        """Should return cached result on second call without hitting repos."""
        case_id = uuid4()
        mock_ledger_repo.get_by_case_and_side.return_value = []
        mock_ledger_repo.sum_amount_by_case.return_value = 0.0
        mock_match_repo.get_statistics_by_case.return_value = {}
        mock_match_repo.count_by_case.return_value = 0
        mock_exception_repo.list_by_case.return_value = PaginatedResult(
            items=[], total=0, page=1, page_size=50
        )
        mock_exception_repo.count_by_severity.return_value = {}

        # First call - hits repos
        result1 = await report_service.generate_reconciliation_statement(case_id)

        # Reset call counts
        mock_ledger_repo.get_by_case_and_side.reset_mock()
        mock_match_repo.get_statistics_by_case.reset_mock()

        # Second call - should use cache
        result2 = await report_service.generate_reconciliation_statement(case_id)

        assert result1 is result2
        mock_ledger_repo.get_by_case_and_side.assert_not_called()
        mock_match_repo.get_statistics_by_case.assert_not_called()

    async def test_bypass_cache_with_flag(
        self,
        report_service: ReportService,
        mock_ledger_repo: AsyncMock,
        mock_match_repo: AsyncMock,
        mock_exception_repo: AsyncMock,
    ):
        """Should bypass cache when use_cache=False."""
        case_id = uuid4()
        mock_ledger_repo.get_by_case_and_side.return_value = []
        mock_ledger_repo.sum_amount_by_case.return_value = 0.0
        mock_match_repo.get_statistics_by_case.return_value = {}
        mock_match_repo.count_by_case.return_value = 0
        mock_exception_repo.list_by_case.return_value = PaginatedResult(
            items=[], total=0, page=1, page_size=50
        )
        mock_exception_repo.count_by_severity.return_value = {}

        # First call
        await report_service.generate_reconciliation_statement(case_id)

        # Reset mocks
        mock_ledger_repo.get_by_case_and_side.reset_mock()

        # Second call with cache bypass
        await report_service.generate_reconciliation_statement(
            case_id, use_cache=False
        )

        # Should have hit repos again
        assert mock_ledger_repo.get_by_case_and_side.call_count == 2

    async def test_clear_cache(
        self,
        report_service: ReportService,
        mock_ledger_repo: AsyncMock,
        mock_match_repo: AsyncMock,
        mock_exception_repo: AsyncMock,
    ):
        """Should clear all cached reports."""
        case_id = uuid4()
        mock_ledger_repo.get_by_case_and_side.return_value = []
        mock_ledger_repo.sum_amount_by_case.return_value = 0.0
        mock_match_repo.get_statistics_by_case.return_value = {}
        mock_match_repo.count_by_case.return_value = 0
        mock_exception_repo.list_by_case.return_value = PaginatedResult(
            items=[], total=0, page=1, page_size=50
        )
        mock_exception_repo.count_by_severity.return_value = {}

        # First call caches the result
        await report_service.generate_reconciliation_statement(case_id)

        # Clear cache
        report_service.clear_cache()

        # Reset mocks
        mock_ledger_repo.get_by_case_and_side.reset_mock()

        # Should hit repos again after cache clear
        await report_service.generate_reconciliation_statement(case_id)
        assert mock_ledger_repo.get_by_case_and_side.call_count == 2

    async def test_invalidate_cache_for_case(
        self,
        report_service: ReportService,
        mock_ledger_repo: AsyncMock,
        mock_match_repo: AsyncMock,
        mock_exception_repo: AsyncMock,
    ):
        """Should invalidate only cache entries related to a specific case."""
        case_id_1 = uuid4()
        case_id_2 = uuid4()
        mock_ledger_repo.get_by_case_and_side.return_value = []
        mock_ledger_repo.sum_amount_by_case.return_value = 0.0
        mock_match_repo.get_statistics_by_case.return_value = {}
        mock_match_repo.count_by_case.return_value = 0
        mock_exception_repo.list_by_case.return_value = PaginatedResult(
            items=[], total=0, page=1, page_size=50
        )
        mock_exception_repo.count_by_severity.return_value = {}

        # Cache both cases
        await report_service.generate_reconciliation_statement(case_id_1)
        await report_service.generate_reconciliation_statement(case_id_2)

        # Invalidate only case 1
        report_service.invalidate_cache_for_case(case_id_1)

        # Reset mocks
        mock_ledger_repo.get_by_case_and_side.reset_mock()

        # Case 2 should still be cached
        await report_service.generate_reconciliation_statement(case_id_2)
        mock_ledger_repo.get_by_case_and_side.assert_not_called()

        # Case 1 should need re-fetch
        await report_service.generate_reconciliation_statement(case_id_1)
        assert mock_ledger_repo.get_by_case_and_side.call_count == 2


# ─── Ageing Bucket Helper Tests ──────────────────────────────────────────────


class TestAgeingBucketHelper:
    """Tests for the ageing bucket classification helper."""

    def test_current_bucket(self, report_service: ReportService):
        """0-30 days should be CURRENT."""
        assert report_service._get_ageing_bucket(0) == AgeingBucket.CURRENT.value
        assert report_service._get_ageing_bucket(15) == AgeingBucket.CURRENT.value
        assert report_service._get_ageing_bucket(30) == AgeingBucket.CURRENT.value

    def test_31_60_bucket(self, report_service: ReportService):
        """31-60 days should be DAYS_31_60."""
        assert report_service._get_ageing_bucket(31) == AgeingBucket.DAYS_31_60.value
        assert report_service._get_ageing_bucket(45) == AgeingBucket.DAYS_31_60.value
        assert report_service._get_ageing_bucket(60) == AgeingBucket.DAYS_31_60.value

    def test_61_90_bucket(self, report_service: ReportService):
        """61-90 days should be DAYS_61_90."""
        assert report_service._get_ageing_bucket(61) == AgeingBucket.DAYS_61_90.value
        assert report_service._get_ageing_bucket(75) == AgeingBucket.DAYS_61_90.value
        assert report_service._get_ageing_bucket(90) == AgeingBucket.DAYS_61_90.value

    def test_over_90_bucket(self, report_service: ReportService):
        """Over 90 days should be OVER_90."""
        assert report_service._get_ageing_bucket(91) == AgeingBucket.OVER_90.value
        assert report_service._get_ageing_bucket(120) == AgeingBucket.OVER_90.value
        assert report_service._get_ageing_bucket(365) == AgeingBucket.OVER_90.value


# ─── Reconciliation Summary Report Tests (Requirements 27.1, 27.2) ────────────


@dataclass
class FakeCaseWithBalances:
    """Fake case with balance fields for reconciliation summary tests."""

    id: UUID = field(default_factory=uuid4)
    status: str = "matched"
    vendor_id: UUID = field(default_factory=uuid4)
    company_closing_balance: Decimal = Decimal("0.00")
    vendor_closing_balance: Decimal = Decimal("0.00")
    upload_count: int = 1
    edit_count: int = 0
    updated_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


@dataclass
class FakeLedgerEntryWithTDS:
    """Fake ledger entry with TDS and amount fields for summary tests."""

    id: UUID = field(default_factory=uuid4)
    case_id: UUID = field(default_factory=uuid4)
    amount: Decimal = Decimal("5000.00")
    side: str = "company"
    reference_number: str = "REF001"
    posting_date: date = field(default_factory=date.today)
    match_id: UUID | None = None
    pass_number: int | None = None
    confidence_score: float | None = None
    is_tds: bool = False
    document_category: str | None = None


@dataclass
class FakeMatchResult:
    """Fake match result for tolerance/date-proximity matches."""

    id: UUID = field(default_factory=uuid4)
    case_id: UUID = field(default_factory=uuid4)
    pass_number: int = 2
    match_type: str = "tolerance"
    confidence_score: float = 0.90
    matched_amount: Decimal = Decimal("10000.00")
    difference_amount: Decimal | None = None
    company_entry_ids: list = field(default_factory=list)
    vendor_entry_ids: list = field(default_factory=list)


class TestReconciliationSummaryReport:
    """Tests for the 10-row reconciliation summary report (Requirements 27.1, 27.2)."""

    async def test_generate_empty_case_all_zeros(
        self,
        report_service: ReportService,
        mock_case_repo: AsyncMock,
        mock_ledger_repo: AsyncMock,
        mock_match_repo: AsyncMock,
    ):
        """Should generate a report with all zeros for a case with no data."""
        case_id = uuid4()
        case = FakeCaseWithBalances(id=case_id)
        mock_case_repo.get_by_id.return_value = case
        mock_ledger_repo.get_unmatched_by_case.return_value = []
        mock_match_repo.get_by_case_and_pass.return_value = []

        result = await report_service.generate_reconciliation_summary(case_id)

        assert result.case_id == case_id
        assert len(result.rows) == 10
        assert result.net_difference == Decimal("0.00")
        assert result.company_closing_balance == Decimal("0.00")
        assert result.vendor_closing_balance == Decimal("0.00")

    async def test_row_10_zero_for_fully_reconciled(
        self,
        report_service: ReportService,
        mock_case_repo: AsyncMock,
        mock_ledger_repo: AsyncMock,
        mock_match_repo: AsyncMock,
    ):
        """
        Row 10 (Net Difference) must be 0 for a fully reconciled case
        where all entries are matched and balances agree.

        Requirement 27.2: Net Difference = 0 for fully reconciled cases.
        """
        case_id = uuid4()
        case = FakeCaseWithBalances(
            id=case_id,
            company_closing_balance=Decimal("100000.00"),
            vendor_closing_balance=Decimal("100000.00"),
        )
        mock_case_repo.get_by_id.return_value = case
        # No unmatched entries (fully reconciled)
        mock_ledger_repo.get_unmatched_by_case.return_value = []
        # No tolerance or date-proximity matches with differences
        mock_match_repo.get_by_case_and_pass.return_value = []

        result = await report_service.generate_reconciliation_summary(case_id)

        assert result.net_difference == Decimal("0.00")
        assert result.rows[9].row_number == 10
        assert result.rows[9].amount == Decimal("0.00")

    async def test_row_10_zero_with_adjustments_explaining_difference(
        self,
        report_service: ReportService,
        mock_case_repo: AsyncMock,
        mock_ledger_repo: AsyncMock,
        mock_match_repo: AsyncMock,
    ):
        """
        Row 10 should be 0 when unmatched entries fully explain
        the difference between company and vendor closing balances.

        Example: Company Closing = 150,000; Vendor Closing = 100,000
        Gap = 50,000 (company higher)
        Unmatched company credit = +50,000 (our payment vendor hasn't recorded)
        Net Diff = 150,000 - 100,000 - (50,000) = 0
        """
        case_id = uuid4()
        case = FakeCaseWithBalances(
            id=case_id,
            company_closing_balance=Decimal("150000.00"),
            vendor_closing_balance=Decimal("100000.00"),
        )
        mock_case_repo.get_by_id.return_value = case

        # Unmatched company credit (positive amount) explaining the gap
        unmatched_company = [
            FakeLedgerEntryWithTDS(
                amount=Decimal("50000.00"),
                side="company",
                is_tds=False,
            ),
        ]
        mock_ledger_repo.get_unmatched_by_case.side_effect = [
            unmatched_company,  # company side
            [],  # vendor side
        ]
        mock_match_repo.get_by_case_and_pass.return_value = []

        result = await report_service.generate_reconciliation_summary(case_id)

        assert result.company_closing_balance == Decimal("150000.00")
        assert result.vendor_closing_balance == Decimal("100000.00")
        assert result.unmatched_company_credit == Decimal("50000.00")
        assert result.net_difference == Decimal("0.00")

    async def test_unmatched_entries_split_by_debit_credit(
        self,
        report_service: ReportService,
        mock_case_repo: AsyncMock,
        mock_ledger_repo: AsyncMock,
        mock_match_repo: AsyncMock,
    ):
        """Should split unmatched entries into debit (negative) and credit (positive)."""
        case_id = uuid4()
        case = FakeCaseWithBalances(
            id=case_id,
            company_closing_balance=Decimal("200000.00"),
            vendor_closing_balance=Decimal("150000.00"),
        )
        mock_case_repo.get_by_id.return_value = case

        # Company: mix of debit and credit unmatched entries
        unmatched_company = [
            FakeLedgerEntryWithTDS(amount=Decimal("-30000.00"), side="company"),
            FakeLedgerEntryWithTDS(amount=Decimal("10000.00"), side="company"),
        ]
        # Vendor: mix of debit and credit unmatched entries
        unmatched_vendor = [
            FakeLedgerEntryWithTDS(amount=Decimal("-5000.00"), side="vendor"),
            FakeLedgerEntryWithTDS(amount=Decimal("15000.00"), side="vendor"),
        ]
        mock_ledger_repo.get_unmatched_by_case.side_effect = [
            unmatched_company,
            unmatched_vendor,
        ]
        mock_match_repo.get_by_case_and_pass.return_value = []

        result = await report_service.generate_reconciliation_summary(case_id)

        # Row 3: Unmatched company debit
        assert result.unmatched_company_debit == Decimal("-30000.00")
        assert result.rows[2].amount == Decimal("-30000.00")
        # Row 4: Unmatched company credit
        assert result.unmatched_company_credit == Decimal("10000.00")
        assert result.rows[3].amount == Decimal("10000.00")
        # Row 5: Unmatched vendor debit
        assert result.unmatched_vendor_debit == Decimal("-5000.00")
        assert result.rows[4].amount == Decimal("-5000.00")
        # Row 6: Unmatched vendor credit
        assert result.unmatched_vendor_credit == Decimal("15000.00")
        assert result.rows[5].amount == Decimal("15000.00")

    async def test_tds_entries_counted_separately(
        self,
        report_service: ReportService,
        mock_case_repo: AsyncMock,
        mock_ledger_repo: AsyncMock,
        mock_match_repo: AsyncMock,
    ):
        """TDS entries should be counted in Row 7, not in Rows 3/4."""
        case_id = uuid4()
        case = FakeCaseWithBalances(
            id=case_id,
            company_closing_balance=Decimal("100000.00"),
            vendor_closing_balance=Decimal("80000.00"),
        )
        mock_case_repo.get_by_id.return_value = case

        # Company unmatched: one regular credit and one TDS credit
        # Gap = 20,000 explained by: credit 15,000 + TDS 5,000 = 20,000
        unmatched_company = [
            FakeLedgerEntryWithTDS(
                amount=Decimal("15000.00"), side="company", is_tds=False
            ),
            FakeLedgerEntryWithTDS(
                amount=Decimal("5000.00"), side="company", is_tds=True
            ),
        ]
        mock_ledger_repo.get_unmatched_by_case.side_effect = [
            unmatched_company,
            [],  # vendor side
        ]
        mock_match_repo.get_by_case_and_pass.return_value = []

        result = await report_service.generate_reconciliation_summary(case_id)

        # TDS entry should be in Row 7, not Row 4
        assert result.unmatched_company_credit == Decimal("15000.00")
        assert result.tds_difference == Decimal("5000.00")
        assert result.rows[6].amount == Decimal("5000.00")  # Row 7
        # Net diff: 100000 - 80000 - (15000 + 5000) = 20000 - 20000 = 0
        assert result.net_difference == Decimal("0.00")

    async def test_tolerance_match_differences_in_row_8(
        self,
        report_service: ReportService,
        mock_case_repo: AsyncMock,
        mock_ledger_repo: AsyncMock,
        mock_match_repo: AsyncMock,
    ):
        """Row 8 should contain the sum of difference_amount from tolerance matches."""
        case_id = uuid4()
        case = FakeCaseWithBalances(
            id=case_id,
            company_closing_balance=Decimal("100000.00"),
            vendor_closing_balance=Decimal("99700.00"),
        )
        mock_case_repo.get_by_id.return_value = case
        mock_ledger_repo.get_unmatched_by_case.return_value = []

        # Tolerance matches with small differences
        tolerance_matches = [
            FakeMatchResult(pass_number=2, difference_amount=Decimal("150.00")),
            FakeMatchResult(pass_number=2, difference_amount=Decimal("150.00")),
        ]

        # Return tolerance matches for pass 2, empty for pass 6
        mock_match_repo.get_by_case_and_pass.side_effect = [
            tolerance_matches,  # pass 2 (tolerance)
            [],  # pass 6 (date proximity)
        ]

        result = await report_service.generate_reconciliation_summary(case_id)

        assert result.amount_difference == Decimal("300.00")
        assert result.rows[7].amount == Decimal("300.00")
        # Net diff: 100000 - 99700 - 300 = 0
        assert result.net_difference == Decimal("0.00")

    async def test_date_proximity_differences_in_row_9(
        self,
        report_service: ReportService,
        mock_case_repo: AsyncMock,
        mock_ledger_repo: AsyncMock,
        mock_match_repo: AsyncMock,
    ):
        """Row 9 should contain the sum of difference_amount from date-proximity matches."""
        case_id = uuid4()
        case = FakeCaseWithBalances(
            id=case_id,
            company_closing_balance=Decimal("50000.00"),
            vendor_closing_balance=Decimal("49500.00"),
        )
        mock_case_repo.get_by_id.return_value = case
        mock_ledger_repo.get_unmatched_by_case.return_value = []

        date_prox_matches = [
            FakeMatchResult(pass_number=6, match_type="date_proximity", difference_amount=Decimal("500.00")),
        ]

        mock_match_repo.get_by_case_and_pass.side_effect = [
            [],  # pass 2 (tolerance)
            date_prox_matches,  # pass 6 (date proximity)
        ]

        result = await report_service.generate_reconciliation_summary(case_id)

        assert result.timing_difference == Decimal("500.00")
        assert result.rows[8].amount == Decimal("500.00")
        # Net diff: 50000 - 49500 - 500 = 0
        assert result.net_difference == Decimal("0.00")

    async def test_report_has_exactly_10_rows(
        self,
        report_service: ReportService,
        mock_case_repo: AsyncMock,
        mock_ledger_repo: AsyncMock,
        mock_match_repo: AsyncMock,
    ):
        """The report must contain exactly 10 rows."""
        case_id = uuid4()
        case = FakeCaseWithBalances(id=case_id)
        mock_case_repo.get_by_id.return_value = case
        mock_ledger_repo.get_unmatched_by_case.return_value = []
        mock_match_repo.get_by_case_and_pass.return_value = []

        result = await report_service.generate_reconciliation_summary(case_id)

        assert len(result.rows) == 10
        for i, row in enumerate(result.rows, start=1):
            assert row.row_number == i

    async def test_row_descriptions_match_brd(
        self,
        report_service: ReportService,
        mock_case_repo: AsyncMock,
        mock_ledger_repo: AsyncMock,
        mock_match_repo: AsyncMock,
    ):
        """Row descriptions should match BRD Section 10.2 format."""
        case_id = uuid4()
        case = FakeCaseWithBalances(id=case_id)
        mock_case_repo.get_by_id.return_value = case
        mock_ledger_repo.get_unmatched_by_case.return_value = []
        mock_match_repo.get_by_case_and_pass.return_value = []

        result = await report_service.generate_reconciliation_summary(case_id)

        expected_descriptions = [
            "Closing Balance as per Emcure Books",
            "Closing Balance as per Vendor Books",
            "Amounts not reflected in Vendor Books (Debit)",
            "Amounts not reflected in Vendor Books (Credit)",
            "Amounts not reflected in Emcure Books (Debit)",
            "Amounts not reflected in Emcure Books (Credit)",
            "TDS Deducted by Emcure",
            "Amount Difference",
            "Timing Differences",
            "Net Difference",
        ]
        for i, desc in enumerate(expected_descriptions):
            assert result.rows[i].description == desc

    async def test_non_zero_net_difference_for_partial_reconciliation(
        self,
        report_service: ReportService,
        mock_case_repo: AsyncMock,
        mock_ledger_repo: AsyncMock,
        mock_match_repo: AsyncMock,
    ):
        """Net Difference should be non-zero when adjustments don't fully explain the gap."""
        case_id = uuid4()
        case = FakeCaseWithBalances(
            id=case_id,
            company_closing_balance=Decimal("200000.00"),
            vendor_closing_balance=Decimal("150000.00"),
        )
        mock_case_repo.get_by_id.return_value = case

        # Only partial unmatched entries (explaining 30000 of the 50000 gap)
        unmatched_company = [
            FakeLedgerEntryWithTDS(amount=Decimal("-30000.00"), side="company"),
        ]
        mock_ledger_repo.get_unmatched_by_case.side_effect = [
            unmatched_company,
            [],
        ]
        mock_match_repo.get_by_case_and_pass.return_value = []

        result = await report_service.generate_reconciliation_summary(case_id)

        # Net diff: 200000 - 150000 - (-30000) = 80000 (not fully reconciled)
        assert result.net_difference == Decimal("80000.00")
        assert result.rows[9].amount == Decimal("80000.00")

    async def test_case_not_found_returns_zeros(
        self,
        report_service: ReportService,
        mock_case_repo: AsyncMock,
        mock_ledger_repo: AsyncMock,
        mock_match_repo: AsyncMock,
    ):
        """Should return zeros when the case is not found."""
        case_id = uuid4()
        mock_case_repo.get_by_id.return_value = None
        mock_ledger_repo.get_unmatched_by_case.return_value = []
        mock_match_repo.get_by_case_and_pass.return_value = []

        result = await report_service.generate_reconciliation_summary(case_id)

        assert result.company_closing_balance == Decimal("0.00")
        assert result.vendor_closing_balance == Decimal("0.00")
        assert result.net_difference == Decimal("0.00")

    async def test_caching_works_for_summary(
        self,
        report_service: ReportService,
        mock_case_repo: AsyncMock,
        mock_ledger_repo: AsyncMock,
        mock_match_repo: AsyncMock,
    ):
        """Should return cached result on second call."""
        case_id = uuid4()
        case = FakeCaseWithBalances(id=case_id)
        mock_case_repo.get_by_id.return_value = case
        mock_ledger_repo.get_unmatched_by_case.return_value = []
        mock_match_repo.get_by_case_and_pass.return_value = []

        # First call
        result1 = await report_service.generate_reconciliation_summary(case_id)

        # Reset mocks
        mock_case_repo.get_by_id.reset_mock()

        # Second call should use cache
        result2 = await report_service.generate_reconciliation_summary(case_id)

        assert result1 is result2
        mock_case_repo.get_by_id.assert_not_called()

    async def test_full_reconciliation_scenario_with_all_adjustment_types(
        self,
        report_service: ReportService,
        mock_case_repo: AsyncMock,
        mock_ledger_repo: AsyncMock,
        mock_match_repo: AsyncMock,
    ):
        """
        Complete scenario: company closing 500,000 vs vendor closing 450,000.
        Gap of 50,000 is explained by adjustments that sum to 50,000:
        - Unmatched company debit: -30,000 (Row 3)
        - Unmatched company credit: 5,000 (Row 4)
        - Unmatched vendor debit: -3,000 (Row 5)
        - Unmatched vendor credit: 8,000 (Row 6)
        - TDS: -40,000 (Row 7)
        - Tolerance diff: 5,000 (Row 8)
        - Timing diff: 5,000 (Row 9)
        Adjustments = -30000 + 5000 + (-3000) + 8000 + (-40000) + 5000 + 5000 = -50000
        Net Diff = 500000 - 450000 - (-50000) = 500000 - 450000 + 50000 = 100000
        Wait, let me use values that yield 0:
        Adjustments must equal company - vendor = 50000
        -30000 + 5000 + (-3000) + 8000 + 60000 + 5000 + 5000 = 50000

        Requirement 27.2: Row 10 = 0 when fully reconciled.
        """
        case_id = uuid4()
        case = FakeCaseWithBalances(
            id=case_id,
            company_closing_balance=Decimal("500000.00"),
            vendor_closing_balance=Decimal("450000.00"),
        )
        mock_case_repo.get_by_id.return_value = case

        # Adjustments that sum to 50,000 (matching the gap):
        # company_debit(-30000) + company_credit(15000) + vendor_debit(-5000) +
        # vendor_credit(20000) + tds(40000) + tolerance(5000) + timing(5000) = 50000
        unmatched_company = [
            FakeLedgerEntryWithTDS(amount=Decimal("-30000.00"), side="company", is_tds=False),
            FakeLedgerEntryWithTDS(amount=Decimal("15000.00"), side="company", is_tds=False),
            FakeLedgerEntryWithTDS(amount=Decimal("40000.00"), side="company", is_tds=True),
        ]
        unmatched_vendor = [
            FakeLedgerEntryWithTDS(amount=Decimal("-5000.00"), side="vendor"),
            FakeLedgerEntryWithTDS(amount=Decimal("20000.00"), side="vendor"),
        ]
        mock_ledger_repo.get_unmatched_by_case.side_effect = [
            unmatched_company,
            unmatched_vendor,
        ]

        tolerance_matches = [
            FakeMatchResult(pass_number=2, difference_amount=Decimal("5000.00")),
        ]
        date_prox_matches = [
            FakeMatchResult(pass_number=6, difference_amount=Decimal("5000.00")),
        ]
        mock_match_repo.get_by_case_and_pass.side_effect = [
            tolerance_matches,
            date_prox_matches,
        ]

        result = await report_service.generate_reconciliation_summary(case_id)

        assert result.company_closing_balance == Decimal("500000.00")
        assert result.vendor_closing_balance == Decimal("450000.00")
        assert result.unmatched_company_debit == Decimal("-30000.00")
        assert result.unmatched_company_credit == Decimal("15000.00")
        assert result.unmatched_vendor_debit == Decimal("-5000.00")
        assert result.unmatched_vendor_credit == Decimal("20000.00")
        assert result.tds_difference == Decimal("40000.00")
        assert result.amount_difference == Decimal("5000.00")
        assert result.timing_difference == Decimal("5000.00")
        # Adjustments = -30000 + 15000 + (-5000) + 20000 + 40000 + 5000 + 5000 = 50000
        # Net Diff = 500000 - 450000 - 50000 = 0
        assert result.net_difference == Decimal("0.00")


# ─── Aging Analysis Report Tests (Requirements 28.1, 28.2) ────────────────────


class TestAgingBucketHelper:
    """Tests for the new 5-bucket aging bucket classification."""

    def test_0_30_days(self, report_service: ReportService):
        """0-30 days should be DAYS_0_30."""
        from src.domain.services.vlr.report_service import AgingBucket
        assert report_service._get_aging_bucket(0) == AgingBucket.DAYS_0_30.value
        assert report_service._get_aging_bucket(15) == AgingBucket.DAYS_0_30.value
        assert report_service._get_aging_bucket(30) == AgingBucket.DAYS_0_30.value

    def test_31_60_days(self, report_service: ReportService):
        """31-60 days should be DAYS_31_60."""
        from src.domain.services.vlr.report_service import AgingBucket
        assert report_service._get_aging_bucket(31) == AgingBucket.DAYS_31_60.value
        assert report_service._get_aging_bucket(45) == AgingBucket.DAYS_31_60.value
        assert report_service._get_aging_bucket(60) == AgingBucket.DAYS_31_60.value

    def test_61_90_days(self, report_service: ReportService):
        """61-90 days should be DAYS_61_90."""
        from src.domain.services.vlr.report_service import AgingBucket
        assert report_service._get_aging_bucket(61) == AgingBucket.DAYS_61_90.value
        assert report_service._get_aging_bucket(75) == AgingBucket.DAYS_61_90.value
        assert report_service._get_aging_bucket(90) == AgingBucket.DAYS_61_90.value

    def test_91_180_days(self, report_service: ReportService):
        """91-180 days should be DAYS_91_180."""
        from src.domain.services.vlr.report_service import AgingBucket
        assert report_service._get_aging_bucket(91) == AgingBucket.DAYS_91_180.value
        assert report_service._get_aging_bucket(120) == AgingBucket.DAYS_91_180.value
        assert report_service._get_aging_bucket(180) == AgingBucket.DAYS_91_180.value

    def test_180_plus_days(self, report_service: ReportService):
        """Over 180 days should be DAYS_180_PLUS."""
        from src.domain.services.vlr.report_service import AgingBucket
        assert report_service._get_aging_bucket(181) == AgingBucket.DAYS_180_PLUS.value
        assert report_service._get_aging_bucket(365) == AgingBucket.DAYS_180_PLUS.value
        assert report_service._get_aging_bucket(1000) == AgingBucket.DAYS_180_PLUS.value


class TestAgingAnalysisReport:
    """Tests for aging analysis report generation."""

    async def test_generate_empty_company(
        self,
        report_service: ReportService,
        mock_case_repo: AsyncMock,
    ):
        """Should return empty report when no cases exist."""
        mock_case_repo.list_cases.return_value = PaginatedResult(
            items=[], total=0, page=1, page_size=10000
        )

        result = await report_service.generate_aging_analysis(
            company_code="EMCURE"
        )

        assert result.total_items == 0
        assert result.total_amount == Decimal("0.00")
        assert len(result.bucket_summaries) == 5
        assert result.items == []

    async def test_aging_buckets_with_entries(
        self,
        report_service: ReportService,
        mock_case_repo: AsyncMock,
        mock_ledger_repo: AsyncMock,
        mock_vendor_repo: AsyncMock,
    ):
        """Should correctly classify entries into aging buckets."""
        from src.domain.services.vlr.report_service import AgingBucket

        case_id = uuid4()
        vendor_id = uuid4()
        today = date.today()

        case = FakeCase(id=case_id, vendor_id=vendor_id, status="matching")
        mock_case_repo.list_cases.return_value = PaginatedResult(
            items=[case], total=1, page=1, page_size=10000
        )

        vendor = FakeVendor(id=vendor_id, name="Acme Corp")
        mock_vendor_repo.get_by_id.return_value = vendor

        # Create entries with various ages
        entries = [
            FakeLedgerEntry(
                amount=Decimal("1000.00"),
                posting_date=today - timedelta(days=10),
            ),
            FakeLedgerEntry(
                amount=Decimal("2000.00"),
                posting_date=today - timedelta(days=45),
            ),
            FakeLedgerEntry(
                amount=Decimal("3000.00"),
                posting_date=today - timedelta(days=100),
            ),
            FakeLedgerEntry(
                amount=Decimal("4000.00"),
                posting_date=today - timedelta(days=200),
            ),
        ]
        mock_ledger_repo.get_unmatched_by_case.return_value = entries

        result = await report_service.generate_aging_analysis(
            company_code="EMCURE"
        )

        assert result.total_items == 4
        assert result.total_amount == Decimal("10000.00")

        # Check bucket distribution
        bucket_map = {s.bucket: s for s in result.bucket_summaries}
        assert bucket_map[AgingBucket.DAYS_0_30.value].count == 1
        assert bucket_map[AgingBucket.DAYS_0_30.value].total_amount == Decimal("1000.00")
        assert bucket_map[AgingBucket.DAYS_31_60.value].count == 1
        assert bucket_map[AgingBucket.DAYS_31_60.value].total_amount == Decimal("2000.00")
        assert bucket_map[AgingBucket.DAYS_91_180.value].count == 1
        assert bucket_map[AgingBucket.DAYS_91_180.value].total_amount == Decimal("3000.00")
        assert bucket_map[AgingBucket.DAYS_180_PLUS.value].count == 1
        assert bucket_map[AgingBucket.DAYS_180_PLUS.value].total_amount == Decimal("4000.00")

    async def test_aging_groups_by_vendor(
        self,
        report_service: ReportService,
        mock_case_repo: AsyncMock,
        mock_ledger_repo: AsyncMock,
        mock_vendor_repo: AsyncMock,
    ):
        """Should group aging entries by vendor name."""
        case_id = uuid4()
        vendor_id = uuid4()
        today = date.today()

        case = FakeCase(id=case_id, vendor_id=vendor_id, status="open")
        mock_case_repo.list_cases.return_value = PaginatedResult(
            items=[case], total=1, page=1, page_size=10000
        )

        vendor = FakeVendor(id=vendor_id, name="TestVendor")
        mock_vendor_repo.get_by_id.return_value = vendor

        entries = [
            FakeLedgerEntry(
                amount=Decimal("5000.00"),
                posting_date=today - timedelta(days=20),
            ),
        ]
        mock_ledger_repo.get_unmatched_by_case.return_value = entries

        result = await report_service.generate_aging_analysis(
            company_code="EMCURE"
        )

        assert "TestVendor" in result.by_vendor
        assert len(result.by_vendor["TestVendor"]) == 5  # All 5 buckets


# ─── Enhanced Exception Report Tests (Requirement 29.1) ──────────────────────


class TestEnhancedExceptionReport:
    """Tests for exception report with resolution history."""

    async def test_empty_report(
        self,
        report_service: ReportService,
        mock_case_repo: AsyncMock,
    ):
        """Should return empty report when no cases exist."""
        mock_case_repo.list_cases.return_value = PaginatedResult(
            items=[], total=0, page=1, page_size=10000
        )

        result = await report_service.generate_enhanced_exception_report(
            company_code="EMCURE"
        )

        assert result.total_exceptions == 0
        assert result.items == []

    async def test_exception_with_resolution_history(
        self,
        report_service: ReportService,
        mock_case_repo: AsyncMock,
        mock_exception_repo: AsyncMock,
    ):
        """Should include resolution history for resolved exceptions."""
        case_id = uuid4()
        now = datetime.now(timezone.utc)

        case = FakeCase(id=case_id)
        mock_case_repo.list_cases.return_value = PaginatedResult(
            items=[case], total=1, page=1, page_size=10000
        )

        exc = FakeException(
            case_id=case_id,
            status="resolved",
            severity="high",
            category="amount_mismatch",
            amount=Decimal("10000.00"),
        )
        # Add resolution attributes
        exc.resolved_at = now
        exc.resolved_by = "finance_user@emcure.com"
        exc.resolution_notes = "Matched after correction"
        exc.created_at = now - timedelta(days=5)

        mock_exception_repo.list_by_case.return_value = PaginatedResult(
            items=[exc], total=1, page=1, page_size=10000
        )

        result = await report_service.generate_enhanced_exception_report(
            company_code="EMCURE"
        )

        assert result.total_exceptions == 1
        item = result.items[0]
        assert item.status == "resolved"
        assert len(item.resolution_history) == 2  # flagged + resolved
        assert item.resolution_history[0].action == "flagged"
        assert item.resolution_history[1].action == "resolved"
        assert item.resolution_history[1].action_by == "finance_user@emcure.com"


# ─── Export Tests (Requirements 27.3, 28.3, 29.4) ────────────────────────────


class TestExportMethods:
    """Tests for PDF and Excel export functionality."""

    def test_export_to_excel_produces_bytes(self, report_service: ReportService):
        """Should produce non-empty bytes for Excel export."""
        from src.domain.services.vlr.report_service import ReconciliationSummaryReport

        report = ReconciliationSummaryReport(case_id=uuid4())
        result = report_service.export_to_excel(report, sheet_name="Summary")

        assert isinstance(result, bytes)
        assert len(result) > 0

    def test_export_to_pdf_produces_bytes(self, report_service: ReportService):
        """Should produce non-empty bytes for PDF export."""
        from src.domain.services.vlr.report_service import ReconciliationSummaryReport

        report = ReconciliationSummaryReport(case_id=uuid4())
        result = report_service.export_to_pdf(report, title="Test Report")

        assert isinstance(result, bytes)
        assert len(result) > 0

    def test_export_aging_report_to_excel(self, report_service: ReportService):
        """Should export aging analysis report to Excel."""
        from src.domain.services.vlr.report_service import (
            AgingAnalysisReport,
            AgingBucketSummary,
        )

        report = AgingAnalysisReport(
            total_items=5,
            total_amount=Decimal("50000.00"),
            bucket_summaries=[
                AgingBucketSummary(bucket="0-30_days", count=3, total_amount=Decimal("30000")),
                AgingBucketSummary(bucket="31-60_days", count=2, total_amount=Decimal("20000")),
            ],
        )
        result = report_service.export_to_excel(report, sheet_name="Aging")

        assert isinstance(result, bytes)
        assert len(result) > 0
