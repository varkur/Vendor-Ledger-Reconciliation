"""
Unit tests for ReconciliationEngineService domain logic.

Tests the 6-pass matching algorithm, no-double-match invariant,
statistics calculation, and clear_previous_results for re-reconciliation.

Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 5.9, 5.10, 5.11, 5.12, 5.13
"""

import pytest
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

from src.domain.services.vlr.reconciliation_engine_service import (
    LedgerEntryData,
    MatchPassType,
    ReconciliationEngineService,
)


# ─── Test Helpers ─────────────────────────────────────────────────────────────


@dataclass
class FakeLedgerEntry:
    """Fake ledger entry object for testing."""

    id: UUID = field(default_factory=uuid4)
    case_id: UUID = field(default_factory=uuid4)
    side: str = "company"
    amount: Decimal = Decimal("1000.00")
    posting_date: date = field(default_factory=lambda: date(2024, 3, 15))
    reference_number: str = "REF-001"
    document_number: str = "DOC-001"
    document_type: str = "invoice"
    match_id: UUID | None = None
    pass_number: int | None = None
    confidence_score: float | None = None


def make_entry(
    side: str = "company",
    amount: str = "1000.00",
    posting_date: date | None = None,
    reference_number: str = "REF-001",
) -> FakeLedgerEntry:
    """Helper to create a fake ledger entry with given attributes."""
    return FakeLedgerEntry(
        side=side,
        amount=Decimal(amount),
        posting_date=posting_date or date(2024, 3, 15),
        reference_number=reference_number,
    )


@pytest.fixture
def mock_ledger_repo() -> AsyncMock:
    """Create a mock ledger entry repository."""
    repo = AsyncMock()
    repo.get_by_case_and_side = AsyncMock(return_value=[])
    repo.bulk_update_match = AsyncMock()
    repo.clear_match_data_by_case = AsyncMock(return_value=0)
    return repo


@pytest.fixture
def mock_match_repo() -> AsyncMock:
    """Create a mock match result repository."""
    repo = AsyncMock()
    repo.create = AsyncMock()
    repo.bulk_create = AsyncMock(return_value=[])
    repo.delete_by_case = AsyncMock(return_value=0)
    repo.get_statistics_by_case = AsyncMock(return_value={})
    return repo


@pytest.fixture
def mock_case_repo() -> AsyncMock:
    """Create a mock case repository."""
    repo = AsyncMock()
    repo.update = AsyncMock()
    return repo


@pytest.fixture
def mock_exception_repo() -> AsyncMock:
    """Create a mock exception repository."""
    repo = AsyncMock()
    repo.delete_by_case = AsyncMock(return_value=0)
    repo.bulk_create = AsyncMock(return_value=[])
    return repo


@pytest.fixture
def service(
    mock_ledger_repo: AsyncMock,
    mock_match_repo: AsyncMock,
    mock_case_repo: AsyncMock,
    mock_exception_repo: AsyncMock,
) -> ReconciliationEngineService:
    """Create ReconciliationEngineService with mocked repositories."""
    return ReconciliationEngineService(
        ledger_entry_repository=mock_ledger_repo,
        match_result_repository=mock_match_repo,
        case_repository=mock_case_repo,
        exception_repository=mock_exception_repo,
    )


# ─── Pass 1: Exact Match Tests ────────────────────────────────────────────────


class TestExactMatch:
    """Tests for Pass 1: Exact Match (amount + date + reference identical)."""

    def test_exact_match_identical_entries(
        self, service: ReconciliationEngineService
    ):
        """Should match entries with identical amount, date, and reference."""
        company = [
            LedgerEntryData(
                id=uuid4(), amount=Decimal("1000"),
                posting_date=date(2024, 3, 15), reference_number="REF-001"
            )
        ]
        vendor = [
            LedgerEntryData(
                id=uuid4(), amount=Decimal("1000"),
                posting_date=date(2024, 3, 15), reference_number="REF-001"
            )
        ]

        pairs = service._exact_match(company, vendor)

        assert len(pairs) == 1
        assert pairs[0].company_entry_id == company[0].id
        assert pairs[0].vendor_entry_id == vendor[0].id
        assert pairs[0].confidence_score == 1.0
        assert pairs[0].pass_number == MatchPassType.EXACT
        assert pairs[0].difference_amount == Decimal("0")

    def test_exact_match_different_amount_no_match(
        self, service: ReconciliationEngineService
    ):
        """Should not match entries with different amounts."""
        company = [
            LedgerEntryData(
                id=uuid4(), amount=Decimal("1000"),
                posting_date=date(2024, 3, 15), reference_number="REF-001"
            )
        ]
        vendor = [
            LedgerEntryData(
                id=uuid4(), amount=Decimal("999"),
                posting_date=date(2024, 3, 15), reference_number="REF-001"
            )
        ]

        pairs = service._exact_match(company, vendor)
        assert len(pairs) == 0

    def test_exact_match_different_date_no_match(
        self, service: ReconciliationEngineService
    ):
        """Should not match entries with different dates."""
        company = [
            LedgerEntryData(
                id=uuid4(), amount=Decimal("1000"),
                posting_date=date(2024, 3, 15), reference_number="REF-001"
            )
        ]
        vendor = [
            LedgerEntryData(
                id=uuid4(), amount=Decimal("1000"),
                posting_date=date(2024, 3, 16), reference_number="REF-001"
            )
        ]

        pairs = service._exact_match(company, vendor)
        assert len(pairs) == 0

    def test_exact_match_different_reference_no_match(
        self, service: ReconciliationEngineService
    ):
        """Should not match entries with different reference numbers."""
        company = [
            LedgerEntryData(
                id=uuid4(), amount=Decimal("1000"),
                posting_date=date(2024, 3, 15), reference_number="REF-001"
            )
        ]
        vendor = [
            LedgerEntryData(
                id=uuid4(), amount=Decimal("1000"),
                posting_date=date(2024, 3, 15), reference_number="REF-002"
            )
        ]

        pairs = service._exact_match(company, vendor)
        assert len(pairs) == 0

    def test_exact_match_multiple_entries(
        self, service: ReconciliationEngineService
    ):
        """Should match multiple exact pairs correctly."""
        c1 = LedgerEntryData(
            id=uuid4(), amount=Decimal("500"),
            posting_date=date(2024, 1, 1), reference_number="A"
        )
        c2 = LedgerEntryData(
            id=uuid4(), amount=Decimal("750"),
            posting_date=date(2024, 2, 1), reference_number="B"
        )
        v1 = LedgerEntryData(
            id=uuid4(), amount=Decimal("500"),
            posting_date=date(2024, 1, 1), reference_number="A"
        )
        v2 = LedgerEntryData(
            id=uuid4(), amount=Decimal("750"),
            posting_date=date(2024, 2, 1), reference_number="B"
        )

        pairs = service._exact_match([c1, c2], [v1, v2])

        assert len(pairs) == 2
        matched_vendor_ids = {p.vendor_entry_id for p in pairs}
        assert v1.id in matched_vendor_ids
        assert v2.id in matched_vendor_ids

    def test_exact_match_no_double_vendor_match(
        self, service: ReconciliationEngineService
    ):
        """Each vendor entry should be matched at most once."""
        c1 = LedgerEntryData(
            id=uuid4(), amount=Decimal("1000"),
            posting_date=date(2024, 3, 15), reference_number="REF-001"
        )
        c2 = LedgerEntryData(
            id=uuid4(), amount=Decimal("1000"),
            posting_date=date(2024, 3, 15), reference_number="REF-001"
        )
        v1 = LedgerEntryData(
            id=uuid4(), amount=Decimal("1000"),
            posting_date=date(2024, 3, 15), reference_number="REF-001"
        )

        pairs = service._exact_match([c1, c2], [v1])

        assert len(pairs) == 1


# ─── Pass 2: Tolerance Match Tests ────────────────────────────────────────────


class TestToleranceMatch:
    """Tests for Pass 2: Tolerance Match (within tolerance, reference matches)."""

    def test_tolerance_match_within_threshold(
        self, service: ReconciliationEngineService
    ):
        """Should match when amount diff <= tolerance and reference matches."""
        company = [
            LedgerEntryData(
                id=uuid4(), amount=Decimal("1005"),
                posting_date=date(2024, 3, 15), reference_number="REF-001"
            )
        ]
        vendor = [
            LedgerEntryData(
                id=uuid4(), amount=Decimal("1000"),
                posting_date=date(2024, 3, 15), reference_number="REF-001"
            )
        ]

        pairs = service._tolerance_match(company, vendor, Decimal("10"))

        assert len(pairs) == 1
        assert pairs[0].pass_number == MatchPassType.TOLERANCE
        assert pairs[0].difference_amount == Decimal("5")

    def test_tolerance_match_exceeds_threshold(
        self, service: ReconciliationEngineService
    ):
        """Should not match when amount diff > tolerance."""
        company = [
            LedgerEntryData(
                id=uuid4(), amount=Decimal("1015"),
                posting_date=date(2024, 3, 15), reference_number="REF-001"
            )
        ]
        vendor = [
            LedgerEntryData(
                id=uuid4(), amount=Decimal("1000"),
                posting_date=date(2024, 3, 15), reference_number="REF-001"
            )
        ]

        pairs = service._tolerance_match(company, vendor, Decimal("10"))
        assert len(pairs) == 0

    def test_tolerance_match_different_reference_no_match(
        self, service: ReconciliationEngineService
    ):
        """Should not match when reference numbers differ even if within tolerance."""
        company = [
            LedgerEntryData(
                id=uuid4(), amount=Decimal("1005"),
                posting_date=date(2024, 3, 15), reference_number="REF-001"
            )
        ]
        vendor = [
            LedgerEntryData(
                id=uuid4(), amount=Decimal("1000"),
                posting_date=date(2024, 3, 15), reference_number="REF-002"
            )
        ]

        pairs = service._tolerance_match(company, vendor, Decimal("10"))
        assert len(pairs) == 0

    def test_tolerance_match_zero_tolerance_returns_empty(
        self, service: ReconciliationEngineService
    ):
        """Should return no matches when tolerance is zero."""
        company = [
            LedgerEntryData(
                id=uuid4(), amount=Decimal("1000"),
                posting_date=date(2024, 3, 15), reference_number="REF-001"
            )
        ]
        vendor = [
            LedgerEntryData(
                id=uuid4(), amount=Decimal("999"),
                posting_date=date(2024, 3, 15), reference_number="REF-001"
            )
        ]

        pairs = service._tolerance_match(company, vendor, Decimal("0"))
        assert len(pairs) == 0

    def test_tolerance_match_exact_boundary(
        self, service: ReconciliationEngineService
    ):
        """Should match when difference equals exactly the tolerance."""
        company = [
            LedgerEntryData(
                id=uuid4(), amount=Decimal("1010"),
                posting_date=date(2024, 3, 15), reference_number="REF-001"
            )
        ]
        vendor = [
            LedgerEntryData(
                id=uuid4(), amount=Decimal("1000"),
                posting_date=date(2024, 3, 15), reference_number="REF-001"
            )
        ]

        pairs = service._tolerance_match(company, vendor, Decimal("10"))
        assert len(pairs) == 1


# ─── Pass 3: Fuzzy Reference Match Tests ──────────────────────────────────────


class TestFuzzyReferenceMatch:
    """Tests for Pass 3: Fuzzy Reference Match (amounts equal, ref similarity > 0.8)."""

    def test_fuzzy_match_similar_references(
        self, service: ReconciliationEngineService
    ):
        """Should match entries with similar reference numbers and equal amounts."""
        company = [
            LedgerEntryData(
                id=uuid4(), amount=Decimal("1000"),
                posting_date=date(2024, 3, 15), reference_number="INV-2024-001"
            )
        ]
        vendor = [
            LedgerEntryData(
                id=uuid4(), amount=Decimal("1000"),
                posting_date=date(2024, 3, 15), reference_number="INV-2024-0O1"
            )
        ]

        pairs = service._fuzzy_reference_match(company, vendor, 0.8)

        assert len(pairs) == 1
        assert pairs[0].pass_number == MatchPassType.FUZZY_REFERENCE
        assert pairs[0].confidence_score > 0.8

    def test_fuzzy_match_very_different_references(
        self, service: ReconciliationEngineService
    ):
        """Should not match entries with very different reference numbers."""
        company = [
            LedgerEntryData(
                id=uuid4(), amount=Decimal("1000"),
                posting_date=date(2024, 3, 15), reference_number="ABC-123"
            )
        ]
        vendor = [
            LedgerEntryData(
                id=uuid4(), amount=Decimal("1000"),
                posting_date=date(2024, 3, 15), reference_number="XYZ-999"
            )
        ]

        pairs = service._fuzzy_reference_match(company, vendor, 0.8)
        assert len(pairs) == 0

    def test_fuzzy_match_different_amounts_no_match(
        self, service: ReconciliationEngineService
    ):
        """Should not match entries with different amounts even if refs are similar."""
        company = [
            LedgerEntryData(
                id=uuid4(), amount=Decimal("1000"),
                posting_date=date(2024, 3, 15), reference_number="REF-001"
            )
        ]
        vendor = [
            LedgerEntryData(
                id=uuid4(), amount=Decimal("999"),
                posting_date=date(2024, 3, 15), reference_number="REF-001"
            )
        ]

        pairs = service._fuzzy_reference_match(company, vendor, 0.8)
        assert len(pairs) == 0

    def test_fuzzy_match_picks_best_candidate(
        self, service: ReconciliationEngineService
    ):
        """Should pick the vendor entry with highest similarity score."""
        c1 = LedgerEntryData(
            id=uuid4(), amount=Decimal("1000"),
            posting_date=date(2024, 3, 15), reference_number="INV-2024-001"
        )
        v1 = LedgerEntryData(
            id=uuid4(), amount=Decimal("1000"),
            posting_date=date(2024, 3, 15), reference_number="INV-2024-0X1"
        )
        v2 = LedgerEntryData(
            id=uuid4(), amount=Decimal("1000"),
            posting_date=date(2024, 3, 15), reference_number="INV-2024-001X"
        )

        pairs = service._fuzzy_reference_match([c1], [v1, v2], 0.8)

        assert len(pairs) == 1
        # v2 has higher similarity ("INV-2024-001X" vs "INV-2024-001")
        assert pairs[0].vendor_entry_id == v2.id


# ─── Pass 4: One-to-Many Match Tests ──────────────────────────────────────────


class TestOneToManyMatch:
    """Tests for Pass 4: One-to-Many (one company = sum of multiple vendor entries)."""

    def test_one_to_many_basic_match(
        self, service: ReconciliationEngineService
    ):
        """Should match one company entry to multiple vendor entries summing to same amount."""
        c1 = LedgerEntryData(
            id=uuid4(), amount=Decimal("1000"),
            posting_date=date(2024, 3, 15), reference_number="REF-001"
        )
        v1 = LedgerEntryData(
            id=uuid4(), amount=Decimal("600"),
            posting_date=date(2024, 3, 15), reference_number="REF-A"
        )
        v2 = LedgerEntryData(
            id=uuid4(), amount=Decimal("400"),
            posting_date=date(2024, 3, 15), reference_number="REF-B"
        )

        groups = service._one_to_many_match([c1], [v1, v2])

        assert len(groups) == 1
        assert groups[0].company_entry_ids == [c1.id]
        assert set(groups[0].vendor_entry_ids) == {v1.id, v2.id}
        assert groups[0].pass_number == MatchPassType.ONE_TO_MANY
        assert groups[0].matched_amount == Decimal("1000")

    def test_one_to_many_no_match_when_sums_differ(
        self, service: ReconciliationEngineService
    ):
        """Should not match if no combination of vendor entries sums to company amount."""
        c1 = LedgerEntryData(
            id=uuid4(), amount=Decimal("1000"),
            posting_date=date(2024, 3, 15), reference_number="REF-001"
        )
        v1 = LedgerEntryData(
            id=uuid4(), amount=Decimal("600"),
            posting_date=date(2024, 3, 15), reference_number="REF-A"
        )
        v2 = LedgerEntryData(
            id=uuid4(), amount=Decimal("300"),
            posting_date=date(2024, 3, 15), reference_number="REF-B"
        )

        groups = service._one_to_many_match([c1], [v1, v2])
        assert len(groups) == 0

    def test_one_to_many_requires_at_least_two_vendor_entries(
        self, service: ReconciliationEngineService
    ):
        """Should not match with only one vendor entry (that's exact match territory)."""
        c1 = LedgerEntryData(
            id=uuid4(), amount=Decimal("1000"),
            posting_date=date(2024, 3, 15), reference_number="REF-001"
        )
        v1 = LedgerEntryData(
            id=uuid4(), amount=Decimal("1000"),
            posting_date=date(2024, 3, 15), reference_number="REF-A"
        )

        groups = service._one_to_many_match([c1], [v1])
        assert len(groups) == 0


# ─── Pass 5: Many-to-One Match Tests ──────────────────────────────────────────


class TestManyToOneMatch:
    """Tests for Pass 5: Many-to-One (multiple company entries sum to one vendor)."""

    def test_many_to_one_basic_match(
        self, service: ReconciliationEngineService
    ):
        """Should match multiple company entries summing to one vendor entry."""
        c1 = LedgerEntryData(
            id=uuid4(), amount=Decimal("400"),
            posting_date=date(2024, 3, 15), reference_number="REF-A"
        )
        c2 = LedgerEntryData(
            id=uuid4(), amount=Decimal("600"),
            posting_date=date(2024, 3, 15), reference_number="REF-B"
        )
        v1 = LedgerEntryData(
            id=uuid4(), amount=Decimal("1000"),
            posting_date=date(2024, 3, 15), reference_number="REF-001"
        )

        groups = service._many_to_one_match([c1, c2], [v1])

        assert len(groups) == 1
        assert set(groups[0].company_entry_ids) == {c1.id, c2.id}
        assert groups[0].vendor_entry_ids == [v1.id]
        assert groups[0].pass_number == MatchPassType.MANY_TO_ONE
        assert groups[0].matched_amount == Decimal("1000")

    def test_many_to_one_no_match_when_sums_differ(
        self, service: ReconciliationEngineService
    ):
        """Should not match if no combination of company entries sums to vendor amount."""
        c1 = LedgerEntryData(
            id=uuid4(), amount=Decimal("400"),
            posting_date=date(2024, 3, 15), reference_number="REF-A"
        )
        c2 = LedgerEntryData(
            id=uuid4(), amount=Decimal("500"),
            posting_date=date(2024, 3, 15), reference_number="REF-B"
        )
        v1 = LedgerEntryData(
            id=uuid4(), amount=Decimal("1000"),
            posting_date=date(2024, 3, 15), reference_number="REF-001"
        )

        groups = service._many_to_one_match([c1, c2], [v1])
        assert len(groups) == 0


# ─── Reference Similarity Tests ───────────────────────────────────────────────


class TestReferenceSimilarity:
    """Tests for the reference similarity helper."""

    def test_identical_references(self, service: ReconciliationEngineService):
        """Identical references should have similarity 1.0."""
        assert service._reference_similarity("REF-001", "REF-001") == 1.0

    def test_empty_reference(self, service: ReconciliationEngineService):
        """Empty references should have similarity 0.0."""
        assert service._reference_similarity("", "REF-001") == 0.0
        assert service._reference_similarity("REF-001", "") == 0.0
        assert service._reference_similarity("", "") == 0.0

    def test_similar_references(self, service: ReconciliationEngineService):
        """Similar references should have high similarity."""
        score = service._reference_similarity("INV-2024-001", "INV-2024-0O1")
        assert score > 0.8

    def test_very_different_references(self, service: ReconciliationEngineService):
        """Very different references should have low similarity."""
        score = service._reference_similarity("ABC", "XYZ")
        assert score < 0.5


# ─── Full Execution Tests ─────────────────────────────────────────────────────


class TestFullExecution:
    """Tests for the full 6-pass reconciliation engine execution."""

    async def test_execute_clears_previous_results(
        self,
        service: ReconciliationEngineService,
        mock_ledger_repo: AsyncMock,
        mock_match_repo: AsyncMock,
        mock_exception_repo: AsyncMock,
    ):
        """Should clear previous results before re-reconciliation (Req 5.13)."""
        case_id = uuid4()
        mock_ledger_repo.get_by_case_and_side.return_value = []

        await service.execute(case_id)

        mock_match_repo.delete_by_case.assert_called_once_with(case_id)
        mock_exception_repo.delete_by_case.assert_called_once_with(case_id)
        mock_ledger_repo.clear_match_data_by_case.assert_called_once_with(case_id)

    async def test_execute_no_entries_returns_empty_result(
        self,
        service: ReconciliationEngineService,
        mock_ledger_repo: AsyncMock,
    ):
        """Should return empty result when no entries exist."""
        case_id = uuid4()
        mock_ledger_repo.get_by_case_and_side.return_value = []

        result = await service.execute(case_id)

        assert result.case_id == case_id
        assert result.match_pairs == []
        assert result.match_groups == []
        assert result.unmatched_company_ids == []
        assert result.unmatched_vendor_ids == []

    async def test_execute_exact_matches_processed_first(
        self,
        service: ReconciliationEngineService,
        mock_ledger_repo: AsyncMock,
    ):
        """Exact matches should be found in Pass 1."""
        case_id = uuid4()
        c1 = make_entry("company", "1000.00", date(2024, 3, 15), "REF-001")
        v1 = make_entry("vendor", "1000.00", date(2024, 3, 15), "REF-001")

        def side_effect(cid, side):
            if side == "company":
                return [c1]
            return [v1]

        mock_ledger_repo.get_by_case_and_side.side_effect = side_effect

        result = await service.execute(case_id)

        assert len(result.match_pairs) == 1
        assert result.match_pairs[0].pass_number == MatchPassType.EXACT
        assert result.unmatched_company_ids == []
        assert result.unmatched_vendor_ids == []

    async def test_execute_unmatched_entries_become_exceptions(
        self,
        service: ReconciliationEngineService,
        mock_ledger_repo: AsyncMock,
        mock_exception_repo: AsyncMock,
    ):
        """Unmatched entries should be marked as exceptions (Pass 6)."""
        case_id = uuid4()
        c1 = make_entry("company", "1000.00", date(2024, 3, 15), "REF-001")
        v1 = make_entry("vendor", "2000.00", date(2024, 4, 1), "REF-999")

        def side_effect(cid, side):
            if side == "company":
                return [c1]
            return [v1]

        mock_ledger_repo.get_by_case_and_side.side_effect = side_effect

        result = await service.execute(case_id)

        assert c1.id in result.unmatched_company_ids
        assert v1.id in result.unmatched_vendor_ids
        mock_exception_repo.bulk_create.assert_called_once()
        exceptions_data = mock_exception_repo.bulk_create.call_args[0][0]
        assert len(exceptions_data) == 2

    async def test_execute_no_double_match_across_passes(
        self,
        service: ReconciliationEngineService,
        mock_ledger_repo: AsyncMock,
    ):
        """No entry should be matched more than once across passes (Req 5.10)."""
        case_id = uuid4()
        # Entry matches exactly in pass 1 - should not appear in later passes
        c1 = make_entry("company", "1000.00", date(2024, 3, 15), "REF-001")
        c2 = make_entry("company", "500.00", date(2024, 3, 20), "REF-002")
        v1 = make_entry("vendor", "1000.00", date(2024, 3, 15), "REF-001")
        v2 = make_entry("vendor", "500.00", date(2024, 3, 20), "REF-002")

        def side_effect(cid, side):
            if side == "company":
                return [c1, c2]
            return [v1, v2]

        mock_ledger_repo.get_by_case_and_side.side_effect = side_effect

        result = await service.execute(case_id)

        # All matched via exact match
        assert len(result.match_pairs) == 2
        # No unmatched
        assert result.unmatched_company_ids == []
        assert result.unmatched_vendor_ids == []
        # Verify no duplicate entry IDs across all match results
        all_company_ids = [p.company_entry_id for p in result.match_pairs]
        all_vendor_ids = [p.vendor_entry_id for p in result.match_pairs]
        assert len(all_company_ids) == len(set(all_company_ids))
        assert len(all_vendor_ids) == len(set(all_vendor_ids))

    async def test_execute_needs_confirmation_for_fuzzy_matches(
        self,
        service: ReconciliationEngineService,
        mock_ledger_repo: AsyncMock,
    ):
        """Fuzzy/combination matches should flag needs_confirmation (Req 5.11)."""
        case_id = uuid4()
        # Amounts equal but reference slightly different (fuzzy match)
        c1 = make_entry("company", "1000.00", date(2024, 3, 15), "INV-2024-001")
        v1 = make_entry("vendor", "1000.00", date(2024, 3, 15), "INV-2024-0O1")

        def side_effect(cid, side):
            if side == "company":
                return [c1]
            return [v1]

        mock_ledger_repo.get_by_case_and_side.side_effect = side_effect

        result = await service.execute(case_id)

        # Should find a fuzzy match (not exact because reference differs)
        assert len(result.match_pairs) == 1
        assert result.match_pairs[0].pass_number == MatchPassType.FUZZY_REFERENCE
        assert result.needs_confirmation is True

    async def test_execute_statistics_calculated_correctly(
        self,
        service: ReconciliationEngineService,
        mock_ledger_repo: AsyncMock,
    ):
        """Match statistics should accurately reflect the results (Req 5.12)."""
        case_id = uuid4()
        c1 = make_entry("company", "1000.00", date(2024, 3, 15), "REF-001")
        c2 = make_entry("company", "500.00", date(2024, 3, 20), "REF-002")
        v1 = make_entry("vendor", "1000.00", date(2024, 3, 15), "REF-001")
        # v2 has different amount - won't match c2
        v2 = make_entry("vendor", "9999.00", date(2024, 4, 1), "REF-999")

        def side_effect(cid, side):
            if side == "company":
                return [c1, c2]
            return [v1, v2]

        mock_ledger_repo.get_by_case_and_side.side_effect = side_effect

        result = await service.execute(case_id)

        assert result.statistics.total_company_entries == 2
        assert result.statistics.total_vendor_entries == 2
        assert result.statistics.total_matched_company == 1
        assert result.statistics.total_matched_vendor == 1

        # Check that pass 1 stats are correct
        pass1_stats = next(
            (ps for ps in result.statistics.pass_statistics if ps.pass_number == 1),
            None,
        )
        assert pass1_stats is not None
        assert pass1_stats.match_count == 1
        assert pass1_stats.matched_amount == Decimal("1000.00")


# ─── Clear Previous Results Tests ─────────────────────────────────────────────


class TestClearPreviousResults:
    """Tests for clear_previous_results method."""

    async def test_clear_deletes_matches_exceptions_and_clears_entry_metadata(
        self,
        service: ReconciliationEngineService,
        mock_match_repo: AsyncMock,
        mock_exception_repo: AsyncMock,
        mock_ledger_repo: AsyncMock,
    ):
        """Should clear all match results, exceptions, and entry match metadata."""
        case_id = uuid4()

        await service.clear_previous_results(case_id)

        mock_match_repo.delete_by_case.assert_called_once_with(case_id)
        mock_exception_repo.delete_by_case.assert_called_once_with(case_id)
        mock_ledger_repo.clear_match_data_by_case.assert_called_once_with(case_id)


# ─── Partition Invariant Tests ────────────────────────────────────────────────


class TestPartitionInvariant:
    """Tests verifying matched + unmatched = total for both sides."""

    async def test_partition_invariant_holds(
        self,
        service: ReconciliationEngineService,
        mock_ledger_repo: AsyncMock,
    ):
        """Matched entries + unmatched entries = total entries (Req 5.7)."""
        case_id = uuid4()
        company = [
            make_entry("company", "1000.00", date(2024, 3, 15), "REF-001"),
            make_entry("company", "2000.00", date(2024, 3, 16), "REF-002"),
            make_entry("company", "3000.00", date(2024, 3, 17), "REF-003"),
        ]
        vendor = [
            make_entry("vendor", "1000.00", date(2024, 3, 15), "REF-001"),
            make_entry("vendor", "5000.00", date(2024, 4, 1), "REF-999"),
        ]

        def side_effect(cid, side):
            if side == "company":
                return company
            return vendor

        mock_ledger_repo.get_by_case_and_side.side_effect = side_effect

        result = await service.execute(case_id)

        # Count matched company entries from pairs and groups
        matched_company_ids = set()
        for pair in result.match_pairs:
            matched_company_ids.add(pair.company_entry_id)
        for group in result.match_groups:
            matched_company_ids.update(group.company_entry_ids)

        matched_vendor_ids = set()
        for pair in result.match_pairs:
            matched_vendor_ids.add(pair.vendor_entry_id)
        for group in result.match_groups:
            matched_vendor_ids.update(group.vendor_entry_ids)

        # Partition invariant: matched + unmatched = total
        assert (
            len(matched_company_ids) + len(result.unmatched_company_ids)
            == len(company)
        )
        assert (
            len(matched_vendor_ids) + len(result.unmatched_vendor_ids)
            == len(vendor)
        )
