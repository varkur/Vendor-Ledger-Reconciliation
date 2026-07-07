"""
Unit tests for ExceptionManagerService domain logic.

Tests exception categorization, resolution actions, Row_10 calculation,
manual edit limit enforcement, write-off threshold checks, and bulk resolution.
"""

import pytest
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

from src.domain.exceptions.vlr import (
    CaseClosedException,
    EditLimitExceededException,
    WriteOffThresholdExceededException,
)
from src.domain.repositories.vlr.exception_repository import ExceptionFilters
from src.domain.repositories.vlr.vendor_repository import PaginatedResult
from src.domain.services.vlr.exception_manager_service import (
    DEFAULT_WRITE_OFF_THRESHOLD,
    ExceptionManagerService,
    ExceptionSeverity,
    ExceptionStatus,
    MAX_MANUAL_EDITS_PER_CASE,
    ResolutionAction,
    SeverityThresholds,
)


# ─── Test Helpers ─────────────────────────────────────────────────────────────


@dataclass
class FakeCase:
    """Fake case object for testing."""

    id: UUID = field(default_factory=uuid4)
    status: str = "matched"
    edit_count: int = 0


@dataclass
class FakeLedgerEntry:
    """Fake ledger entry object for testing."""

    id: UUID = field(default_factory=uuid4)
    case_id: UUID = field(default_factory=uuid4)
    amount: Decimal = Decimal("5000.00")
    side: str = "company"
    reference_number: str = "REF001"


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
class FakeSetting:
    """Fake setting object for testing."""

    id: UUID = field(default_factory=uuid4)
    key: str = "write_off_threshold"
    value: str = "50000"


# ─── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_exception_repo() -> AsyncMock:
    """Create a mock exception repository."""
    repo = AsyncMock()
    repo.get_by_id = AsyncMock(return_value=None)
    repo.create = AsyncMock()
    repo.bulk_create = AsyncMock(return_value=[])
    repo.update = AsyncMock()
    repo.list_by_case = AsyncMock(
        return_value=PaginatedResult(items=[], total=0, page=1, page_size=50)
    )
    repo.get_open_by_case = AsyncMock(return_value=[])
    repo.get_critical_open_by_case = AsyncMock(return_value=[])
    repo.delete_by_case = AsyncMock(return_value=0)
    repo.count_by_case = AsyncMock(return_value=0)
    return repo


@pytest.fixture
def mock_case_repo() -> AsyncMock:
    """Create a mock case repository."""
    repo = AsyncMock()
    repo.get_by_id = AsyncMock(return_value=FakeCase())
    repo.increment_edit_count = AsyncMock(return_value=1)
    return repo


@pytest.fixture
def mock_ledger_repo() -> AsyncMock:
    """Create a mock ledger entry repository."""
    repo = AsyncMock()
    repo.get_by_id = AsyncMock(return_value=FakeLedgerEntry())
    repo.sum_amount_by_case = AsyncMock(return_value=0.0)
    return repo


@pytest.fixture
def mock_setting_repo() -> AsyncMock:
    """Create a mock setting repository."""
    repo = AsyncMock()
    repo.get_by_key = AsyncMock(return_value=None)
    return repo


@pytest.fixture
def exception_service(
    mock_exception_repo: AsyncMock,
    mock_case_repo: AsyncMock,
    mock_ledger_repo: AsyncMock,
    mock_setting_repo: AsyncMock,
) -> ExceptionManagerService:
    """Create ExceptionManagerService with mocked repositories."""
    return ExceptionManagerService(
        exception_repository=mock_exception_repo,
        case_repository=mock_case_repo,
        ledger_entry_repository=mock_ledger_repo,
        setting_repository=mock_setting_repo,
    )


# ─── Severity Classification Tests ───────────────────────────────────────────


class TestSeverityClassification:
    """Tests for exception severity categorization."""

    def test_critical_by_amount(self, exception_service: ExceptionManagerService):
        """Should classify as critical when amount >= 100,000."""
        thresholds = SeverityThresholds()
        result = exception_service._classify_severity(
            Decimal("100000"), 0, thresholds
        )
        assert result == ExceptionSeverity.CRITICAL.value

    def test_critical_by_age(self, exception_service: ExceptionManagerService):
        """Should classify as critical when age >= 90 days."""
        thresholds = SeverityThresholds()
        result = exception_service._classify_severity(
            Decimal("100"), 90, thresholds
        )
        assert result == ExceptionSeverity.CRITICAL.value

    def test_high_by_amount(self, exception_service: ExceptionManagerService):
        """Should classify as high when amount >= 50,000."""
        thresholds = SeverityThresholds()
        result = exception_service._classify_severity(
            Decimal("50000"), 0, thresholds
        )
        assert result == ExceptionSeverity.HIGH.value

    def test_high_by_age(self, exception_service: ExceptionManagerService):
        """Should classify as high when age >= 60 days."""
        thresholds = SeverityThresholds()
        result = exception_service._classify_severity(
            Decimal("100"), 60, thresholds
        )
        assert result == ExceptionSeverity.HIGH.value

    def test_medium_by_amount(self, exception_service: ExceptionManagerService):
        """Should classify as medium when amount >= 10,000."""
        thresholds = SeverityThresholds()
        result = exception_service._classify_severity(
            Decimal("10000"), 0, thresholds
        )
        assert result == ExceptionSeverity.MEDIUM.value

    def test_medium_by_age(self, exception_service: ExceptionManagerService):
        """Should classify as medium when age >= 30 days."""
        thresholds = SeverityThresholds()
        result = exception_service._classify_severity(
            Decimal("100"), 30, thresholds
        )
        assert result == ExceptionSeverity.MEDIUM.value

    def test_low_severity(self, exception_service: ExceptionManagerService):
        """Should classify as low when below all thresholds."""
        thresholds = SeverityThresholds()
        result = exception_service._classify_severity(
            Decimal("5000"), 10, thresholds
        )
        assert result == ExceptionSeverity.LOW.value

    def test_higher_severity_wins(self, exception_service: ExceptionManagerService):
        """Amount qualifies for critical but age only for medium."""
        thresholds = SeverityThresholds()
        result = exception_service._classify_severity(
            Decimal("150000"), 35, thresholds
        )
        assert result == ExceptionSeverity.CRITICAL.value


# ─── Categorize Exceptions Tests ─────────────────────────────────────────────


class TestCategorizeExceptions:
    """Tests for categorize_exceptions method."""

    async def test_categorize_empty_list(
        self, exception_service: ExceptionManagerService
    ):
        """Should return empty list for empty input."""
        result = await exception_service.categorize_exceptions(uuid4(), [])
        assert result == []

    async def test_categorize_creates_exceptions(
        self,
        exception_service: ExceptionManagerService,
        mock_ledger_repo: AsyncMock,
        mock_exception_repo: AsyncMock,
    ):
        """Should create exception records for each unmatched entry."""
        entry = FakeLedgerEntry(amount=Decimal("75000"))
        mock_ledger_repo.get_by_id.return_value = entry
        case_id = uuid4()

        result = await exception_service.categorize_exceptions(
            case_id, [entry.id]
        )

        assert len(result) == 1
        assert result[0].severity == ExceptionSeverity.HIGH.value
        assert result[0].amount == Decimal("75000")
        mock_exception_repo.create.assert_called_once()

    async def test_categorize_skips_missing_entries(
        self,
        exception_service: ExceptionManagerService,
        mock_ledger_repo: AsyncMock,
    ):
        """Should skip entries that cannot be found."""
        mock_ledger_repo.get_by_id.return_value = None

        result = await exception_service.categorize_exceptions(
            uuid4(), [uuid4()]
        )
        assert result == []


# ─── Resolve Exception Tests ─────────────────────────────────────────────────


class TestResolveException:
    """Tests for single exception resolution."""

    async def test_resolve_exception_success(
        self,
        exception_service: ExceptionManagerService,
        mock_exception_repo: AsyncMock,
        mock_case_repo: AsyncMock,
    ):
        """Should resolve exception and increment edit count."""
        case_id = uuid4()
        fake_exc = FakeException(case_id=case_id, amount=Decimal("5000"))
        mock_exception_repo.get_by_id.return_value = fake_exc
        mock_case_repo.get_by_id.return_value = FakeCase(
            id=case_id, status="matched", edit_count=0
        )

        result = await exception_service.resolve_exception(
            exception_id=fake_exc.id,
            action=ResolutionAction.ACM,
            resolved_by=uuid4(),
            comment="Accepted match",
        )

        assert result.action == ResolutionAction.ACM.value
        assert result.status == ExceptionStatus.RESOLVED.value
        assert result.comments == "Accepted match"
        mock_exception_repo.update.assert_called_once()
        mock_case_repo.increment_edit_count.assert_called_once_with(case_id)

    async def test_resolve_escalation_sets_escalated_status(
        self,
        exception_service: ExceptionManagerService,
        mock_exception_repo: AsyncMock,
        mock_case_repo: AsyncMock,
    ):
        """Should set status to escalated when action is ESC."""
        case_id = uuid4()
        fake_exc = FakeException(case_id=case_id)
        mock_exception_repo.get_by_id.return_value = fake_exc
        mock_case_repo.get_by_id.return_value = FakeCase(
            id=case_id, status="matched"
        )

        result = await exception_service.resolve_exception(
            exception_id=fake_exc.id,
            action=ResolutionAction.ESC,
            resolved_by=uuid4(),
        )

        assert result.status == ExceptionStatus.ESCALATED.value

    async def test_resolve_exception_not_found_raises(
        self,
        exception_service: ExceptionManagerService,
        mock_exception_repo: AsyncMock,
    ):
        """Should raise ValueError when exception not found."""
        mock_exception_repo.get_by_id.return_value = None

        with pytest.raises(ValueError, match="not found"):
            await exception_service.resolve_exception(
                exception_id=uuid4(),
                action=ResolutionAction.ACM,
                resolved_by=uuid4(),
            )

    async def test_resolve_on_closed_case_raises(
        self,
        exception_service: ExceptionManagerService,
        mock_exception_repo: AsyncMock,
        mock_case_repo: AsyncMock,
    ):
        """Should raise CaseClosedException when case is closed."""
        case_id = uuid4()
        fake_exc = FakeException(case_id=case_id)
        mock_exception_repo.get_by_id.return_value = fake_exc
        mock_case_repo.get_by_id.return_value = FakeCase(
            id=case_id, status="closed"
        )

        with pytest.raises(CaseClosedException):
            await exception_service.resolve_exception(
                exception_id=fake_exc.id,
                action=ResolutionAction.ACM,
                resolved_by=uuid4(),
            )

    async def test_resolve_all_resolution_actions(
        self,
        exception_service: ExceptionManagerService,
        mock_exception_repo: AsyncMock,
        mock_case_repo: AsyncMock,
    ):
        """Should support all resolution actions."""
        case_id = uuid4()
        # Use small amount so WOF doesn't trigger threshold
        fake_exc = FakeException(case_id=case_id, amount=Decimal("100"))
        mock_exception_repo.get_by_id.return_value = fake_exc
        mock_case_repo.get_by_id.return_value = FakeCase(
            id=case_id, status="matched", edit_count=0
        )

        for action in ResolutionAction:
            mock_case_repo.increment_edit_count.return_value = 1
            result = await exception_service.resolve_exception(
                exception_id=fake_exc.id,
                action=action,
                resolved_by=uuid4(),
            )
            assert result.action == action.value


# ─── Edit Limit Tests ─────────────────────────────────────────────────────────


class TestEditLimit:
    """Tests for manual edit limit enforcement."""

    async def test_edit_limit_at_max_raises(
        self,
        exception_service: ExceptionManagerService,
        mock_exception_repo: AsyncMock,
        mock_case_repo: AsyncMock,
    ):
        """Should raise EditLimitExceededException at limit."""
        case_id = uuid4()
        fake_exc = FakeException(case_id=case_id)
        mock_exception_repo.get_by_id.return_value = fake_exc
        mock_case_repo.get_by_id.return_value = FakeCase(
            id=case_id, status="matched", edit_count=MAX_MANUAL_EDITS_PER_CASE
        )

        with pytest.raises(EditLimitExceededException):
            await exception_service.resolve_exception(
                exception_id=fake_exc.id,
                action=ResolutionAction.ACM,
                resolved_by=uuid4(),
            )

    async def test_edit_limit_below_max_passes(
        self,
        exception_service: ExceptionManagerService,
        mock_exception_repo: AsyncMock,
        mock_case_repo: AsyncMock,
    ):
        """Should allow resolution when below edit limit."""
        case_id = uuid4()
        fake_exc = FakeException(case_id=case_id, amount=Decimal("100"))
        mock_exception_repo.get_by_id.return_value = fake_exc
        mock_case_repo.get_by_id.return_value = FakeCase(
            id=case_id, status="matched", edit_count=9
        )

        # Should not raise
        result = await exception_service.resolve_exception(
            exception_id=fake_exc.id,
            action=ResolutionAction.ACM,
            resolved_by=uuid4(),
        )
        assert result.status == ExceptionStatus.RESOLVED.value

    async def test_get_edit_count(
        self,
        exception_service: ExceptionManagerService,
        mock_case_repo: AsyncMock,
    ):
        """Should return current edit count from case."""
        case_id = uuid4()
        mock_case_repo.get_by_id.return_value = FakeCase(
            id=case_id, edit_count=5
        )

        count = await exception_service.get_edit_count(case_id)
        assert count == 5

    async def test_get_remaining_edits(
        self,
        exception_service: ExceptionManagerService,
        mock_case_repo: AsyncMock,
    ):
        """Should return remaining edits correctly."""
        case_id = uuid4()
        mock_case_repo.get_by_id.return_value = FakeCase(
            id=case_id, edit_count=7
        )

        remaining = await exception_service.get_remaining_edits(case_id)
        assert remaining == 3


# ─── Write-Off Threshold Tests ────────────────────────────────────────────────


class TestWriteOffThreshold:
    """Tests for write-off threshold enforcement."""

    async def test_write_off_exceeds_threshold_raises(
        self,
        exception_service: ExceptionManagerService,
        mock_exception_repo: AsyncMock,
        mock_case_repo: AsyncMock,
    ):
        """Should raise WriteOffThresholdExceededException for large write-offs."""
        case_id = uuid4()
        # Amount exceeds default threshold of 50,000
        fake_exc = FakeException(case_id=case_id, amount=Decimal("60000"))
        mock_exception_repo.get_by_id.return_value = fake_exc
        mock_case_repo.get_by_id.return_value = FakeCase(
            id=case_id, status="matched", edit_count=0
        )

        with pytest.raises(WriteOffThresholdExceededException):
            await exception_service.resolve_exception(
                exception_id=fake_exc.id,
                action=ResolutionAction.WOF,
                resolved_by=uuid4(),
            )

    async def test_write_off_below_threshold_passes(
        self,
        exception_service: ExceptionManagerService,
        mock_exception_repo: AsyncMock,
        mock_case_repo: AsyncMock,
    ):
        """Should allow write-off when below threshold."""
        case_id = uuid4()
        fake_exc = FakeException(case_id=case_id, amount=Decimal("1000"))
        mock_exception_repo.get_by_id.return_value = fake_exc
        mock_case_repo.get_by_id.return_value = FakeCase(
            id=case_id, status="matched", edit_count=0
        )

        result = await exception_service.resolve_exception(
            exception_id=fake_exc.id,
            action=ResolutionAction.WOF,
            resolved_by=uuid4(),
        )
        assert result.action == ResolutionAction.WOF.value

    async def test_write_off_at_threshold_passes(
        self,
        exception_service: ExceptionManagerService,
        mock_exception_repo: AsyncMock,
        mock_case_repo: AsyncMock,
    ):
        """Should allow write-off at exactly the threshold amount."""
        case_id = uuid4()
        fake_exc = FakeException(
            case_id=case_id, amount=DEFAULT_WRITE_OFF_THRESHOLD
        )
        mock_exception_repo.get_by_id.return_value = fake_exc
        mock_case_repo.get_by_id.return_value = FakeCase(
            id=case_id, status="matched", edit_count=0
        )

        result = await exception_service.resolve_exception(
            exception_id=fake_exc.id,
            action=ResolutionAction.WOF,
            resolved_by=uuid4(),
        )
        assert result.action == ResolutionAction.WOF.value

    async def test_check_write_off_requires_approval(
        self,
        exception_service: ExceptionManagerService,
        mock_exception_repo: AsyncMock,
    ):
        """Should return True when amount exceeds threshold."""
        fake_exc = FakeException(amount=Decimal("75000"))
        mock_exception_repo.get_by_id.return_value = fake_exc

        requires = await exception_service.check_write_off_requires_approval(
            fake_exc.id
        )
        assert requires is True

    async def test_check_write_off_no_approval_needed(
        self,
        exception_service: ExceptionManagerService,
        mock_exception_repo: AsyncMock,
    ):
        """Should return False when amount is within threshold."""
        fake_exc = FakeException(amount=Decimal("1000"))
        mock_exception_repo.get_by_id.return_value = fake_exc

        requires = await exception_service.check_write_off_requires_approval(
            fake_exc.id
        )
        assert requires is False

    async def test_non_write_off_actions_skip_threshold_check(
        self,
        exception_service: ExceptionManagerService,
        mock_exception_repo: AsyncMock,
        mock_case_repo: AsyncMock,
    ):
        """Should not check threshold for non-WOF actions even with large amounts."""
        case_id = uuid4()
        fake_exc = FakeException(case_id=case_id, amount=Decimal("200000"))
        mock_exception_repo.get_by_id.return_value = fake_exc
        mock_case_repo.get_by_id.return_value = FakeCase(
            id=case_id, status="matched", edit_count=0
        )

        # ACM should succeed regardless of amount
        result = await exception_service.resolve_exception(
            exception_id=fake_exc.id,
            action=ResolutionAction.ACM,
            resolved_by=uuid4(),
        )
        assert result.action == ResolutionAction.ACM.value


# ─── Row 10 Calculation Tests ─────────────────────────────────────────────────


class TestRow10Calculation:
    """Tests for Row_10 balance calculation."""

    async def test_row_10_zero_when_balanced(
        self,
        exception_service: ExceptionManagerService,
        mock_ledger_repo: AsyncMock,
        mock_exception_repo: AsyncMock,
    ):
        """Should return zero when company = vendor + adjustments."""
        case_id = uuid4()
        mock_ledger_repo.sum_amount_by_case.side_effect = [
            100000.0,  # company total
            100000.0,  # vendor total
        ]
        mock_exception_repo.list_by_case.return_value = PaginatedResult(
            items=[], total=0, page=1, page_size=50
        )

        result = await exception_service.calculate_row_10(case_id)

        assert result.net_difference == Decimal("0")
        assert result.company_total == Decimal("100000.0")
        assert result.vendor_total == Decimal("100000.0")

    async def test_row_10_positive_difference(
        self,
        exception_service: ExceptionManagerService,
        mock_ledger_repo: AsyncMock,
        mock_exception_repo: AsyncMock,
    ):
        """Should return positive difference when company > vendor."""
        case_id = uuid4()
        mock_ledger_repo.sum_amount_by_case.side_effect = [
            150000.0,  # company total
            100000.0,  # vendor total
        ]
        mock_exception_repo.list_by_case.return_value = PaginatedResult(
            items=[], total=0, page=1, page_size=50
        )

        result = await exception_service.calculate_row_10(case_id)

        assert result.net_difference == Decimal("50000.0")

    async def test_row_10_with_resolved_adjustments(
        self,
        exception_service: ExceptionManagerService,
        mock_ledger_repo: AsyncMock,
        mock_exception_repo: AsyncMock,
    ):
        """Should subtract resolved adjustments from difference."""
        case_id = uuid4()
        mock_ledger_repo.sum_amount_by_case.side_effect = [
            150000.0,  # company total
            100000.0,  # vendor total
        ]
        # One resolved exception of 50,000
        resolved_exc = FakeException(amount=Decimal("50000"), status="resolved")
        mock_exception_repo.list_by_case.return_value = PaginatedResult(
            items=[resolved_exc], total=1, page=1, page_size=50
        )

        result = await exception_service.calculate_row_10(case_id)

        assert result.resolved_adjustments == Decimal("50000")
        assert result.net_difference == Decimal("0")


# ─── Bulk Resolution Tests ────────────────────────────────────────────────────


class TestBulkResolution:
    """Tests for bulk exception resolution."""

    async def test_bulk_resolve_success(
        self,
        exception_service: ExceptionManagerService,
        mock_exception_repo: AsyncMock,
        mock_case_repo: AsyncMock,
    ):
        """Should resolve all exceptions in a batch."""
        case_id = uuid4()
        exc1 = FakeException(case_id=case_id, amount=Decimal("100"))
        exc2 = FakeException(case_id=case_id, amount=Decimal("200"))
        mock_exception_repo.get_by_id.side_effect = [
            exc1, exc2,  # For category validation
            exc1,  # For resolve_exception call 1
            exc2,  # For resolve_exception call 2
        ]
        mock_case_repo.get_by_id.return_value = FakeCase(
            id=case_id, status="matched", edit_count=0
        )

        result = await exception_service.bulk_resolve(
            exception_ids=[exc1.id, exc2.id],
            action=ResolutionAction.ACM,
            resolved_by=uuid4(),
            comment="Bulk resolved",
        )

        assert result.total == 2
        assert result.resolved == 2
        assert result.failed == 0

    async def test_bulk_resolve_empty_list(
        self,
        exception_service: ExceptionManagerService,
    ):
        """Should return zero result for empty list."""
        result = await exception_service.bulk_resolve(
            exception_ids=[],
            action=ResolutionAction.ACM,
            resolved_by=uuid4(),
        )

        assert result.total == 0
        assert result.resolved == 0
        assert result.failed == 0

    async def test_bulk_resolve_mixed_categories_rejected(
        self,
        exception_service: ExceptionManagerService,
        mock_exception_repo: AsyncMock,
    ):
        """Should reject bulk resolve with mixed categories."""
        exc1 = FakeException(category="unmatched")
        exc2 = FakeException(category="disputed")
        mock_exception_repo.get_by_id.side_effect = [exc1, exc2]

        result = await exception_service.bulk_resolve(
            exception_ids=[exc1.id, exc2.id],
            action=ResolutionAction.ACM,
            resolved_by=uuid4(),
        )

        assert result.failed == 2
        assert result.resolved == 0
        assert "same category" in result.errors[0]

    async def test_bulk_resolve_stops_at_edit_limit(
        self,
        exception_service: ExceptionManagerService,
        mock_exception_repo: AsyncMock,
        mock_case_repo: AsyncMock,
    ):
        """Should stop processing when edit limit is hit."""
        case_id = uuid4()
        exc1 = FakeException(case_id=case_id, amount=Decimal("100"))
        exc2 = FakeException(case_id=case_id, amount=Decimal("200"))

        # First two calls for category validation, then calls for resolution
        mock_exception_repo.get_by_id.side_effect = [
            exc1, exc2,  # Category validation
            exc1,  # First resolve attempt
        ]
        # Case at edit limit
        mock_case_repo.get_by_id.return_value = FakeCase(
            id=case_id, status="matched", edit_count=MAX_MANUAL_EDITS_PER_CASE
        )

        result = await exception_service.bulk_resolve(
            exception_ids=[exc1.id, exc2.id],
            action=ResolutionAction.ACM,
            resolved_by=uuid4(),
        )

        assert result.resolved == 0
        assert "Edit limit" in result.errors[0]


# ─── Unresolved Critical Exceptions Tests ─────────────────────────────────────


class TestUnresolvedCritical:
    """Tests for checking unresolved critical exceptions."""

    async def test_has_unresolved_critical_true(
        self,
        exception_service: ExceptionManagerService,
        mock_exception_repo: AsyncMock,
    ):
        """Should return True when critical open exceptions exist."""
        mock_exception_repo.get_critical_open_by_case.return_value = [
            FakeException(severity="critical")
        ]

        result = await exception_service.has_unresolved_critical(uuid4())
        assert result is True

    async def test_has_unresolved_critical_false(
        self,
        exception_service: ExceptionManagerService,
        mock_exception_repo: AsyncMock,
    ):
        """Should return False when no critical open exceptions."""
        mock_exception_repo.get_critical_open_by_case.return_value = []

        result = await exception_service.has_unresolved_critical(uuid4())
        assert result is False

    async def test_get_unresolved_critical(
        self,
        exception_service: ExceptionManagerService,
        mock_exception_repo: AsyncMock,
    ):
        """Should return list of critical open exceptions."""
        critical_excs = [
            FakeException(severity="critical"),
            FakeException(severity="critical"),
        ]
        mock_exception_repo.get_critical_open_by_case.return_value = critical_excs

        result = await exception_service.get_unresolved_critical(uuid4())
        assert len(result) == 2


# ─── Configuration Loading Tests ──────────────────────────────────────────────


class TestConfigurationLoading:
    """Tests for loading thresholds from settings."""

    async def test_default_thresholds_when_no_company_code(
        self,
        exception_service: ExceptionManagerService,
    ):
        """Should use defaults when company_code is None."""
        thresholds = await exception_service._load_severity_thresholds(None)

        assert thresholds.critical_amount == Decimal("100000")
        assert thresholds.high_amount == Decimal("50000")
        assert thresholds.medium_amount == Decimal("10000")
        assert thresholds.critical_age_days == 90
        assert thresholds.high_age_days == 60
        assert thresholds.medium_age_days == 30

    async def test_custom_thresholds_from_settings(
        self,
        exception_service: ExceptionManagerService,
        mock_setting_repo: AsyncMock,
    ):
        """Should load thresholds from settings when available."""
        mock_setting_repo.get_by_key.side_effect = [
            FakeSetting(key="exception_critical_amount", value="200000"),
            FakeSetting(key="exception_high_amount", value="80000"),
            FakeSetting(key="exception_medium_amount", value="20000"),
            FakeSetting(key="exception_critical_age_days", value="120"),
            FakeSetting(key="exception_high_age_days", value="90"),
            FakeSetting(key="exception_medium_age_days", value="45"),
        ]

        thresholds = await exception_service._load_severity_thresholds("CC01")

        assert thresholds.critical_amount == Decimal("200000")
        assert thresholds.high_amount == Decimal("80000")
        assert thresholds.medium_amount == Decimal("20000")
        assert thresholds.critical_age_days == 120
        assert thresholds.high_age_days == 90
        assert thresholds.medium_age_days == 45

    async def test_default_write_off_threshold_when_no_setting(
        self,
        exception_service: ExceptionManagerService,
        mock_setting_repo: AsyncMock,
    ):
        """Should use default write-off threshold when not configured."""
        mock_setting_repo.get_by_key.return_value = None

        threshold = await exception_service._load_write_off_threshold("CC01")
        assert threshold == DEFAULT_WRITE_OFF_THRESHOLD

    async def test_custom_write_off_threshold_from_settings(
        self,
        exception_service: ExceptionManagerService,
        mock_setting_repo: AsyncMock,
    ):
        """Should load write-off threshold from settings."""
        mock_setting_repo.get_by_key.return_value = FakeSetting(
            key="write_off_threshold", value="75000"
        )

        threshold = await exception_service._load_write_off_threshold("CC01")
        assert threshold == Decimal("75000")
