"""
Unit tests for ReconciliationEngineService domain logic.

Tests the 7-pass matching algorithm, no-double-match invariant,
statistics calculation, and clear_previous_results for re-reconciliation.

Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 5.9, 5.10, 5.11, 5.12, 5.13, 17.1
"""

import pytest
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

from src.domain.services.vlr.reconciliation_engine_service import (
    CONFIDENCE_SCORES,
    LedgerEntryData,
    MatchPassType,
    ReconciliationEngineService,
    _is_reversal,
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
    # NOTE: document_number is derived from reference_number by default (see
    # make_entry) rather than a fixed literal — the engine's invoice-number
    # matching key (LedgerEntryData.invoice_number) is computed from
    # derived_invoice_number/document_number, NOT reference_number, in the
    # real _to_entry_data_list conversion path used by execute(). A shared
    # literal default here would make every fake entry resolve to the same
    # invoice_number regardless of reference_number, causing false matches
    # in full-execution tests.
    document_number: str = "DOC-001"
    document_type: str = "invoice"
    derived_invoice_number: str = ""
    match_id: UUID | None = None
    pass_number: int | None = None
    confidence_score: float | None = None


def make_entry(
    side: str = "company",
    amount: str = "1000.00",
    posting_date: date | None = None,
    reference_number: str = "REF-001",
) -> FakeLedgerEntry:
    """Helper to create a fake ledger entry with given attributes.

    document_number is derived from reference_number (not a fixed literal)
    so that entries with different reference_number values also get
    different invoice-matching keys once converted via _to_entry_data_list —
    matching this test file's existing convention of using reference_number
    as the per-test matchable identifier.
    """
    return FakeLedgerEntry(
        side=side,
        amount=Decimal(amount),
        posting_date=posting_date or date(2024, 3, 15),
        reference_number=reference_number,
        document_number=f"DOC-{reference_number}",
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
        """Should match when amount diff <= tolerance and reference matches.

        Company records payables as negative, vendor records sales as
        positive for the same invoice (confirmed on real data) — the diff
        check must compare magnitudes, not the raw signed difference.
        """
        company = [
            LedgerEntryData(
                id=uuid4(), amount=Decimal("-1005"),
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
        assert pairs[0].difference_amount == Decimal("-5")

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

    def test_tolerance_match_widened_for_tds_gap(
        self, service: ReconciliationEngineService
    ):
        """
        Bug fix: an invoice-number-exact, date-exact pair with a real TDS/GST-
        sized amount gap must still match on invoice number (Pass 2), not
        fall through to the weaker _tolerance_date_match (which doesn't
        check invoice number and reported this as "Date Range and Amount
        Matched" instead of "Invoice Number Matched" — the client's exact
        complaint: "classification is showing Date Range and Amount Matched
        even though the invoice number and invoice date are the same").
        A plain (non-TDS) tolerance of 10 is far too small for this gap, so
        this only passes because of the TDS-percentage widening.
        """
        company = [
            LedgerEntryData(
                id=uuid4(), amount=Decimal("-29729.22"),
                posting_date=date(2025, 8, 29), reference_number="GST/0863/2025-26"
            )
        ]
        vendor = [
            LedgerEntryData(
                id=uuid4(), amount=Decimal("31524"),
                posting_date=date(2025, 8, 29), reference_number="GST/0863/2025-26"
            )
        ]

        pairs = service._tolerance_match(
            company, vendor, Decimal("10"),
            tds_percentage=Decimal("0"), gst_percentage=Decimal("6"),
        )
        assert len(pairs) == 1
        assert pairs[0].pass_number == MatchPassType.TOLERANCE

    def test_tolerance_match_no_tds_gst_still_gates_on_plain_tolerance(
        self, service: ReconciliationEngineService
    ):
        """Without a TDS/GST percentage configured, a large gap must still
        NOT match — the widening only applies when tds/gst % is actually set."""
        company = [
            LedgerEntryData(
                id=uuid4(), amount=Decimal("-29729.22"),
                posting_date=date(2025, 8, 29), reference_number="GST/0863/2025-26"
            )
        ]
        vendor = [
            LedgerEntryData(
                id=uuid4(), amount=Decimal("31524"),
                posting_date=date(2025, 8, 29), reference_number="GST/0863/2025-26"
            )
        ]

        pairs = service._tolerance_match(company, vendor, Decimal("10"))
        assert len(pairs) == 0


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
        # BRD: Pass 3 confidence = 0.70 (normalized from MatchScore 70)
        assert pairs[0].confidence_score == 0.70

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


# ─── Pass 6: Date-proximity Match Tests ────────────────────────────────────────


class TestDateProximityMatch:
    """Tests for Pass 6: Date-proximity Match (amount matches + date within N days)."""

    def test_date_proximity_match_same_amount_within_tolerance(
        self, service: ReconciliationEngineService
    ):
        """Should match entries with same absolute amount and dates within tolerance."""
        company = [
            LedgerEntryData(
                id=uuid4(), amount=Decimal("1000"),
                posting_date=date(2024, 3, 15), reference_number="REF-001"
            )
        ]
        vendor = [
            LedgerEntryData(
                id=uuid4(), amount=Decimal("1000"),
                posting_date=date(2024, 3, 17), reference_number="VENDOR-XYZ"
            )
        ]

        pairs = service._date_proximity_match(company, vendor, date_tolerance_days=3)

        assert len(pairs) == 1
        assert pairs[0].company_entry_id == company[0].id
        assert pairs[0].vendor_entry_id == vendor[0].id
        assert pairs[0].confidence_score == 0.70
        assert pairs[0].pass_number == MatchPassType.DATE_PROXIMITY
        assert pairs[0].difference_amount == Decimal("0")

    def test_date_proximity_match_date_exceeds_tolerance(
        self, service: ReconciliationEngineService
    ):
        """Should not match when date difference exceeds tolerance."""
        company = [
            LedgerEntryData(
                id=uuid4(), amount=Decimal("1000"),
                posting_date=date(2024, 3, 15), reference_number="REF-001"
            )
        ]
        vendor = [
            LedgerEntryData(
                id=uuid4(), amount=Decimal("1000"),
                posting_date=date(2024, 3, 20), reference_number="VENDOR-XYZ"
            )
        ]

        pairs = service._date_proximity_match(company, vendor, date_tolerance_days=3)
        assert len(pairs) == 0

    def test_date_proximity_match_different_amounts_no_match(
        self, service: ReconciliationEngineService
    ):
        """Should not match when amounts differ even if dates are close."""
        company = [
            LedgerEntryData(
                id=uuid4(), amount=Decimal("1000"),
                posting_date=date(2024, 3, 15), reference_number="REF-001"
            )
        ]
        vendor = [
            LedgerEntryData(
                id=uuid4(), amount=Decimal("999"),
                posting_date=date(2024, 3, 16), reference_number="VENDOR-XYZ"
            )
        ]

        pairs = service._date_proximity_match(company, vendor, date_tolerance_days=3)
        assert len(pairs) == 0

    def test_date_proximity_match_exact_boundary(
        self, service: ReconciliationEngineService
    ):
        """Should match when date difference is exactly at the tolerance boundary."""
        company = [
            LedgerEntryData(
                id=uuid4(), amount=Decimal("500"),
                posting_date=date(2024, 3, 15), reference_number="REF-001"
            )
        ]
        vendor = [
            LedgerEntryData(
                id=uuid4(), amount=Decimal("500"),
                posting_date=date(2024, 3, 18), reference_number="VENDOR-ABC"
            )
        ]

        pairs = service._date_proximity_match(company, vendor, date_tolerance_days=3)
        assert len(pairs) == 1

    def test_date_proximity_match_vendor_date_before_company(
        self, service: ReconciliationEngineService
    ):
        """Should match when vendor date is before company date (within tolerance)."""
        company = [
            LedgerEntryData(
                id=uuid4(), amount=Decimal("2000"),
                posting_date=date(2024, 3, 15), reference_number="REF-001"
            )
        ]
        vendor = [
            LedgerEntryData(
                id=uuid4(), amount=Decimal("2000"),
                posting_date=date(2024, 3, 13), reference_number="VENDOR-XYZ"
            )
        ]

        pairs = service._date_proximity_match(company, vendor, date_tolerance_days=3)
        assert len(pairs) == 1

    def test_date_proximity_match_picks_closest_date(
        self, service: ReconciliationEngineService
    ):
        """Should prefer the vendor entry with the closest date when multiple candidates exist."""
        c1 = LedgerEntryData(
            id=uuid4(), amount=Decimal("1000"),
            posting_date=date(2024, 3, 15), reference_number="REF-001"
        )
        v1 = LedgerEntryData(
            id=uuid4(), amount=Decimal("1000"),
            posting_date=date(2024, 3, 18), reference_number="VENDOR-A"
        )
        v2 = LedgerEntryData(
            id=uuid4(), amount=Decimal("1000"),
            posting_date=date(2024, 3, 16), reference_number="VENDOR-B"
        )

        pairs = service._date_proximity_match([c1], [v1, v2], date_tolerance_days=3)

        assert len(pairs) == 1
        assert pairs[0].vendor_entry_id == v2.id  # closer date

    def test_date_proximity_match_no_double_vendor_match(
        self, service: ReconciliationEngineService
    ):
        """Each vendor entry should be matched at most once."""
        c1 = LedgerEntryData(
            id=uuid4(), amount=Decimal("1000"),
            posting_date=date(2024, 3, 15), reference_number="REF-001"
        )
        c2 = LedgerEntryData(
            id=uuid4(), amount=Decimal("1000"),
            posting_date=date(2024, 3, 16), reference_number="REF-002"
        )
        v1 = LedgerEntryData(
            id=uuid4(), amount=Decimal("1000"),
            posting_date=date(2024, 3, 15), reference_number="VENDOR-XYZ"
        )

        pairs = service._date_proximity_match([c1, c2], [v1], date_tolerance_days=3)
        assert len(pairs) == 1

    def test_date_proximity_match_configurable_tolerance(
        self, service: ReconciliationEngineService
    ):
        """Should respect the configurable date tolerance parameter."""
        company = [
            LedgerEntryData(
                id=uuid4(), amount=Decimal("1000"),
                posting_date=date(2024, 3, 15), reference_number="REF-001"
            )
        ]
        vendor = [
            LedgerEntryData(
                id=uuid4(), amount=Decimal("1000"),
                posting_date=date(2024, 3, 20), reference_number="VENDOR-XYZ"
            )
        ]

        # 5 days apart - should not match with 3-day tolerance
        pairs_3 = service._date_proximity_match(company, vendor, date_tolerance_days=3)
        assert len(pairs_3) == 0

        # 5 days apart - should match with 5-day tolerance
        pairs_5 = service._date_proximity_match(company, vendor, date_tolerance_days=5)
        assert len(pairs_5) == 1

    def test_date_proximity_match_uses_absolute_amount(
        self, service: ReconciliationEngineService
    ):
        """Should compare absolute amounts (handles negative amounts for credits)."""
        company = [
            LedgerEntryData(
                id=uuid4(), amount=Decimal("-1000"),
                posting_date=date(2024, 3, 15), reference_number="REF-001"
            )
        ]
        vendor = [
            LedgerEntryData(
                id=uuid4(), amount=Decimal("-1000"),
                posting_date=date(2024, 3, 16), reference_number="VENDOR-XYZ"
            )
        ]

        pairs = service._date_proximity_match(company, vendor, date_tolerance_days=3)
        assert len(pairs) == 1

    def test_date_proximity_match_zero_tolerance_only_same_date(
        self, service: ReconciliationEngineService
    ):
        """With zero day tolerance, should only match if dates are identical."""
        company = [
            LedgerEntryData(
                id=uuid4(), amount=Decimal("1000"),
                posting_date=date(2024, 3, 15), reference_number="REF-001"
            )
        ]
        vendor_same_date = [
            LedgerEntryData(
                id=uuid4(), amount=Decimal("1000"),
                posting_date=date(2024, 3, 15), reference_number="VENDOR-XYZ"
            )
        ]
        vendor_diff_date = [
            LedgerEntryData(
                id=uuid4(), amount=Decimal("1000"),
                posting_date=date(2024, 3, 16), reference_number="VENDOR-ABC"
            )
        ]

        pairs_same = service._date_proximity_match(company, vendor_same_date, date_tolerance_days=0)
        assert len(pairs_same) == 1

        pairs_diff = service._date_proximity_match(company, vendor_diff_date, date_tolerance_days=0)
        assert len(pairs_diff) == 0

    def test_date_proximity_match_multiple_matches(
        self, service: ReconciliationEngineService
    ):
        """Should match multiple distinct pairs correctly."""
        c1 = LedgerEntryData(
            id=uuid4(), amount=Decimal("500"),
            posting_date=date(2024, 3, 10), reference_number="REF-A"
        )
        c2 = LedgerEntryData(
            id=uuid4(), amount=Decimal("750"),
            posting_date=date(2024, 3, 20), reference_number="REF-B"
        )
        v1 = LedgerEntryData(
            id=uuid4(), amount=Decimal("500"),
            posting_date=date(2024, 3, 12), reference_number="VENDOR-1"
        )
        v2 = LedgerEntryData(
            id=uuid4(), amount=Decimal("750"),
            posting_date=date(2024, 3, 21), reference_number="VENDOR-2"
        )

        pairs = service._date_proximity_match([c1, c2], [v1, v2], date_tolerance_days=3)

        assert len(pairs) == 2
        matched_vendor_ids = {p.vendor_entry_id for p in pairs}
        assert v1.id in matched_vendor_ids
        assert v2.id in matched_vendor_ids


class TestDateProximityMatchInFullExecution:
    """Tests verifying Pass 6 is correctly wired into the full execution pipeline."""

    @pytest.fixture
    def service(
        self,
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

    @pytest.mark.asyncio
    async def test_date_proximity_match_in_pipeline(
        self,
        service: ReconciliationEngineService,
        mock_ledger_repo: AsyncMock,
    ):
        """
        Same amount, close dates, different references: caught by the
        higher-confidence Pass 1.5 (Amount+Date, 0.90) before Pass 6
        (Date-proximity, 0.70) ever runs — Pass 1.5 has always executed
        before Pass 6 in the pipeline and shares the same "amount equal +
        date within N days" criteria, so it wins for any entry pair this
        simple. Pass 6 only fires for pairs Pass 1.5 could not claim (e.g.
        already consumed by an earlier reference-aware pass on one side).
        """
        case_id = uuid4()
        c1 = make_entry("company", "1000.00", date(2024, 3, 15), "REF-001")
        v1 = make_entry("vendor", "1000.00", date(2024, 3, 17), "COMPLETELY-DIFFERENT")

        def side_effect(cid, side):
            if side == "company":
                return [c1]
            return [v1]

        mock_ledger_repo.get_by_case_and_side.side_effect = side_effect

        result = await service.execute(case_id, date_tolerance_days=3)

        assert len(result.match_pairs) == 1
        assert result.match_pairs[0].pass_number == MatchPassType.AMOUNT_DATE
        assert result.match_pairs[0].confidence_score == 0.90
        assert result.unmatched_company_ids == []
        assert result.unmatched_vendor_ids == []

    @pytest.mark.asyncio
    async def test_exact_match_takes_priority_over_date_proximity(
        self,
        service: ReconciliationEngineService,
        mock_ledger_repo: AsyncMock,
    ):
        """Entries matched in Pass 1 (exact) should not be available for Pass 6."""
        case_id = uuid4()
        # This should match exactly in Pass 1
        c1 = make_entry("company", "1000.00", date(2024, 3, 15), "REF-001")
        v1 = make_entry("vendor", "1000.00", date(2024, 3, 15), "REF-001")

        def side_effect(cid, side):
            if side == "company":
                return [c1]
            return [v1]

        mock_ledger_repo.get_by_case_and_side.side_effect = side_effect

        result = await service.execute(case_id, date_tolerance_days=3)

        # Should be exact match, not date-proximity
        assert len(result.match_pairs) == 1
        assert result.match_pairs[0].pass_number == MatchPassType.EXACT

    @pytest.mark.asyncio
    async def test_amount_date_match_is_auto_accepted(
        self,
        service: ReconciliationEngineService,
        mock_ledger_repo: AsyncMock,
    ):
        """
        Amount+Date matches (0.90 confidence) are high-confidence and
        auto-accepted, unlike the genuinely weak Date-proximity (Pass 6) and
        Tolerance+Date (Pass 6.5) tiers which always need Finance review.
        """
        case_id = uuid4()
        c1 = make_entry("company", "1000.00", date(2024, 3, 15), "REF-001")
        v1 = make_entry("vendor", "1000.00", date(2024, 3, 17), "COMPLETELY-DIFFERENT")

        def side_effect(cid, side):
            if side == "company":
                return [c1]
            return [v1]

        mock_ledger_repo.get_by_case_and_side.side_effect = side_effect

        result = await service.execute(case_id, date_tolerance_days=3)

        assert result.needs_confirmation is False

# ─── Confidence Scoring Tests ─────────────────────────────────────────────────


class TestConfidenceScoring:
    """Tests verifying correct confidence scores per BRD Section 5.6.10.

    Requirements: 17.2 - Assign confidence score to each match result.
    """

    def test_exact_match_confidence_is_1_0(
        self, service: ReconciliationEngineService
    ):
        """Pass 1 (Exact): BRD MatchScore = 100 → confidence = 1.0."""
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
        assert pairs[0].confidence_score == 1.0
        assert pairs[0].confidence_score == CONFIDENCE_SCORES[MatchPassType.EXACT]

    def test_tolerance_match_confidence_is_0_85(
        self, service: ReconciliationEngineService
    ):
        """Pass 2 (Tolerance): BRD MatchScore = 85 → confidence = 0.85."""
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
        assert pairs[0].confidence_score == 0.85
        assert pairs[0].confidence_score == CONFIDENCE_SCORES[MatchPassType.TOLERANCE]

    def test_fuzzy_reference_match_confidence_is_0_70(
        self, service: ReconciliationEngineService
    ):
        """Pass 3 (Fuzzy Reference): BRD MatchScore = 70 → confidence = 0.70."""
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
        assert pairs[0].confidence_score == 0.70
        assert pairs[0].confidence_score == CONFIDENCE_SCORES[MatchPassType.FUZZY_REFERENCE]

    def test_one_to_many_confidence_is_0_80(
        self, service: ReconciliationEngineService
    ):
        """Pass 4 (One-to-Many): BRD MatchScore = 80 → confidence = 0.80."""
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
        assert groups[0].confidence_score == 0.80
        assert groups[0].confidence_score == CONFIDENCE_SCORES[MatchPassType.ONE_TO_MANY]

    def test_many_to_one_confidence_is_0_75(
        self, service: ReconciliationEngineService
    ):
        """Pass 5 (Many-to-One): BRD MatchScore = 75 → confidence = 0.75."""
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
        assert groups[0].confidence_score == 0.75
        assert groups[0].confidence_score == CONFIDENCE_SCORES[MatchPassType.MANY_TO_ONE]

    def test_date_proximity_match_confidence_is_0_70(
        self, service: ReconciliationEngineService
    ):
        """Pass 6 (Date-proximity): BRD MatchScore = 70 → confidence = 0.70."""
        company = [
            LedgerEntryData(
                id=uuid4(), amount=Decimal("1000"),
                posting_date=date(2024, 3, 15), reference_number="REF-001"
            )
        ]
        vendor = [
            LedgerEntryData(
                id=uuid4(), amount=Decimal("1000"),
                posting_date=date(2024, 3, 17), reference_number="REF-999"
            )
        ]

        pairs = service._date_proximity_match(company, vendor, date_tolerance_days=3)

        assert len(pairs) == 1
        assert pairs[0].confidence_score == 0.70
        assert pairs[0].confidence_score == CONFIDENCE_SCORES[MatchPassType.DATE_PROXIMITY]

    def test_confidence_scores_all_in_valid_range(
        self, service: ReconciliationEngineService
    ):
        """All confidence scores must be in [0.0, 1.0] range."""
        for pass_type, score in CONFIDENCE_SCORES.items():
            assert 0.0 <= score <= 1.0, (
                f"Pass {pass_type}: confidence {score} not in [0.0, 1.0]"
            )

    def test_confidence_score_constant_values_match_brd(self):
        """Verify CONFIDENCE_SCORES constant matches BRD Section 5.6.10."""
        assert CONFIDENCE_SCORES[MatchPassType.EXACT] == 1.0
        assert CONFIDENCE_SCORES[MatchPassType.TOLERANCE] == 0.85
        assert CONFIDENCE_SCORES[MatchPassType.FUZZY_REFERENCE] == 0.70
        assert CONFIDENCE_SCORES[MatchPassType.ONE_TO_MANY] == 0.80
        assert CONFIDENCE_SCORES[MatchPassType.MANY_TO_ONE] == 0.75
        assert CONFIDENCE_SCORES[MatchPassType.DATE_PROXIMITY] == 0.70
        assert CONFIDENCE_SCORES[MatchPassType.UNMATCHED] == 0.0


# ─── No-Double-Match Invariant Tests ──────────────────────────────────────────


class TestNoDoubleMatchInvariant:
    """Tests verifying the no-double-match invariant (MR-001, MR-002).

    Requirements: 17.3, 17.4, 36.1, 36.2, 36.3
    - MR-001: A transaction can only be matched to one counterpart.
    - MR-002: Once matched in Pass N, excluded from Pass N+1 onward.
    """

    async def test_entries_matched_in_pass1_excluded_from_pass2(
        self,
        service: ReconciliationEngineService,
        mock_ledger_repo: AsyncMock,
    ):
        """Entries matched in Pass 1 (Exact) must be excluded from Pass 2 (Tolerance).

        Requirement 36.1: Mark all matched entries as consumed after Pass 1.
        Requirement 36.2: Exclude consumed entries from Pass 2 through Pass 7.
        """
        case_id = uuid4()
        # c1/v1 will match exactly in Pass 1
        # c1 should NOT be re-matched in Pass 2 even if it would also match
        # within tolerance against v2
        c1 = make_entry("company", "1000.00", date(2024, 3, 15), "REF-001")
        v1 = make_entry("vendor", "1000.00", date(2024, 3, 15), "REF-001")
        # v2 is close to c1's amount and has same reference - would match in Pass 2
        v2 = make_entry("vendor", "1002.00", date(2024, 3, 15), "REF-001")

        def side_effect(cid, side):
            if side == "company":
                return [c1]
            return [v1, v2]

        mock_ledger_repo.get_by_case_and_side.side_effect = side_effect

        result = await service.execute(case_id, tolerance=Decimal("5"))

        # c1 should be matched exactly once (in Pass 1)
        c1_matches = [p for p in result.match_pairs if p.company_entry_id == c1.id]
        assert len(c1_matches) == 1
        assert c1_matches[0].pass_number == MatchPassType.EXACT
        # v1 should be matched exactly once
        v1_matches = [p for p in result.match_pairs if p.vendor_entry_id == v1.id]
        assert len(v1_matches) == 1

    async def test_entries_matched_in_pass2_excluded_from_pass3(
        self,
        service: ReconciliationEngineService,
        mock_ledger_repo: AsyncMock,
    ):
        """Entries matched in Pass 2 (Tolerance) must be excluded from Pass 3 (Fuzzy).

        Requirement 36.3: Exclusion rule applies after each subsequent pass.
        """
        case_id = uuid4()
        # c1/v1 will match in Pass 2 (tolerance) because refs match and amounts within tolerance
        c1 = make_entry("company", "1005.00", date(2024, 3, 15), "REF-001")
        v1 = make_entry("vendor", "1000.00", date(2024, 3, 15), "REF-001")
        # v2 has same amount as c1 and similar ref - could match in Pass 3
        v2 = make_entry("vendor", "1005.00", date(2024, 3, 15), "REF-0O1")

        def side_effect(cid, side):
            if side == "company":
                return [c1]
            return [v1, v2]

        mock_ledger_repo.get_by_case_and_side.side_effect = side_effect

        result = await service.execute(case_id, tolerance=Decimal("10"))

        # c1 should only appear once across all matches
        c1_matches = [p for p in result.match_pairs if p.company_entry_id == c1.id]
        assert len(c1_matches) == 1
        # Should be matched in Pass 2 (not Pass 3)
        assert c1_matches[0].pass_number == MatchPassType.TOLERANCE

    async def test_no_entry_appears_in_multiple_match_results(
        self,
        service: ReconciliationEngineService,
        mock_ledger_repo: AsyncMock,
    ):
        """No single entry should appear in more than one match result.

        Requirement 17.3: No-double-match invariant.
        """
        case_id = uuid4()
        # Create entries that could potentially match across multiple passes
        c1 = make_entry("company", "1000.00", date(2024, 3, 15), "REF-001")
        c2 = make_entry("company", "500.00", date(2024, 3, 16), "REF-002")
        c3 = make_entry("company", "750.00", date(2024, 3, 17), "REF-003")
        v1 = make_entry("vendor", "1000.00", date(2024, 3, 15), "REF-001")
        v2 = make_entry("vendor", "500.00", date(2024, 3, 16), "REF-002")
        v3 = make_entry("vendor", "750.00", date(2024, 3, 18), "REF-003")

        def side_effect(cid, side):
            if side == "company":
                return [c1, c2, c3]
            return [v1, v2, v3]

        mock_ledger_repo.get_by_case_and_side.side_effect = side_effect

        result = await service.execute(case_id, tolerance=Decimal("5"))

        # Collect all matched entry IDs from pairs
        all_company_ids = [p.company_entry_id for p in result.match_pairs]
        all_vendor_ids = [p.vendor_entry_id for p in result.match_pairs]
        # Also from groups
        for group in result.match_groups:
            all_company_ids.extend(group.company_entry_ids)
            all_vendor_ids.extend(group.vendor_entry_ids)

        # No duplicates allowed (MR-001)
        assert len(all_company_ids) == len(set(all_company_ids)), \
            "Company entry matched more than once"
        assert len(all_vendor_ids) == len(set(all_vendor_ids)), \
            "Vendor entry matched more than once"

    async def test_consumed_entries_excluded_from_all_subsequent_passes(
        self,
        service: ReconciliationEngineService,
        mock_ledger_repo: AsyncMock,
    ):
        """Once matched, entries must not appear in any subsequent pass results.

        Requirement 17.4: When Pass 1 produces matches, exclude from subsequent passes.
        Requirement 36.3: Entries matched in Pass N excluded from Pass N+1 onward.
        """
        case_id = uuid4()
        # c1/v1: exact match (Pass 1)
        # c2/v2: only amount within tolerance, different ref would NOT match
        # c3/v3: same amount, close dates, different refs → date proximity
        c1 = make_entry("company", "1000.00", date(2024, 3, 15), "REF-001")
        c2 = make_entry("company", "2000.00", date(2024, 3, 20), "REF-002")
        c3 = make_entry("company", "3000.00", date(2024, 3, 25), "REF-003")
        v1 = make_entry("vendor", "1000.00", date(2024, 3, 15), "REF-001")
        v2 = make_entry("vendor", "2000.00", date(2024, 3, 20), "REF-002")
        v3 = make_entry("vendor", "3000.00", date(2024, 3, 27), "XYZ-999")

        def side_effect(cid, side):
            if side == "company":
                return [c1, c2, c3]
            return [v1, v2, v3]

        mock_ledger_repo.get_by_case_and_side.side_effect = side_effect

        result = await service.execute(
            case_id, tolerance=Decimal("5"), date_tolerance_days=3
        )

        # c1 and c2 matched exactly in Pass 1
        # c3/v3: same amount, dates 2 days apart, different refs → date proximity pass
        all_company_ids = []
        all_vendor_ids = []
        for pair in result.match_pairs:
            all_company_ids.append(pair.company_entry_id)
            all_vendor_ids.append(pair.vendor_entry_id)
        for group in result.match_groups:
            all_company_ids.extend(group.company_entry_ids)
            all_vendor_ids.extend(group.vendor_entry_ids)

        # Verify no duplicates
        assert len(all_company_ids) == len(set(all_company_ids))
        assert len(all_vendor_ids) == len(set(all_vendor_ids))

        # c1/v1, c2/v2 should be exact matches
        exact_pairs = [p for p in result.match_pairs if p.pass_number == MatchPassType.EXACT]
        exact_company_ids = {p.company_entry_id for p in exact_pairs}
        assert c1.id in exact_company_ids
        assert c2.id in exact_company_ids

    async def test_matched_entries_not_in_unmatched_lists(
        self,
        service: ReconciliationEngineService,
        mock_ledger_repo: AsyncMock,
    ):
        """Entries that are matched must not appear in unmatched lists (Pass 7).

        Requirement 36.2: Exclude consumed entries from Pass 7 (Unmatched).
        """
        case_id = uuid4()
        c1 = make_entry("company", "1000.00", date(2024, 3, 15), "REF-001")
        c2 = make_entry("company", "9999.00", date(2024, 3, 20), "UNIQUE-XYZ")
        v1 = make_entry("vendor", "1000.00", date(2024, 3, 15), "REF-001")

        def side_effect(cid, side):
            if side == "company":
                return [c1, c2]
            return [v1]

        mock_ledger_repo.get_by_case_and_side.side_effect = side_effect

        result = await service.execute(case_id)

        # c1/v1 match exactly → should NOT be in unmatched
        assert c1.id not in result.unmatched_company_ids
        assert v1.id not in result.unmatched_vendor_ids
        # c2 is unmatched
        assert c2.id in result.unmatched_company_ids


# ─── Pass 6: Date-proximity Match Tests ───────────────────────────────────────


class TestDateProximityMatch:
    """Tests for Pass 6: Date-proximity Match (amount equal, date within N days).

    Requirement 17.1: Match by amount + date within configurable N days.
    """

    def test_date_proximity_match_within_tolerance(
        self, service: ReconciliationEngineService
    ):
        """Should match when amounts are equal and dates within tolerance days."""
        company = [
            LedgerEntryData(
                id=uuid4(), amount=Decimal("1000"),
                posting_date=date(2024, 3, 15), reference_number="REF-001"
            )
        ]
        vendor = [
            LedgerEntryData(
                id=uuid4(), amount=Decimal("1000"),
                posting_date=date(2024, 3, 17), reference_number="VENDOR-XYZ"
            )
        ]

        pairs = service._date_proximity_match(company, vendor, date_tolerance_days=3)

        assert len(pairs) == 1
        assert pairs[0].pass_number == MatchPassType.DATE_PROXIMITY
        assert pairs[0].matched_amount == Decimal("1000")
        assert pairs[0].difference_amount == Decimal("0")

    def test_date_proximity_match_exact_boundary(
        self, service: ReconciliationEngineService
    ):
        """Should match when date difference equals exactly the tolerance."""
        company = [
            LedgerEntryData(
                id=uuid4(), amount=Decimal("500"),
                posting_date=date(2024, 3, 15), reference_number="REF-001"
            )
        ]
        vendor = [
            LedgerEntryData(
                id=uuid4(), amount=Decimal("500"),
                posting_date=date(2024, 3, 18), reference_number="VENDOR-A"
            )
        ]

        pairs = service._date_proximity_match(company, vendor, date_tolerance_days=3)
        assert len(pairs) == 1

    def test_date_proximity_no_match_exceeds_tolerance(
        self, service: ReconciliationEngineService
    ):
        """Should not match when date difference exceeds tolerance."""
        company = [
            LedgerEntryData(
                id=uuid4(), amount=Decimal("1000"),
                posting_date=date(2024, 3, 15), reference_number="REF-001"
            )
        ]
        vendor = [
            LedgerEntryData(
                id=uuid4(), amount=Decimal("1000"),
                posting_date=date(2024, 3, 20), reference_number="VENDOR-XYZ"
            )
        ]

        pairs = service._date_proximity_match(company, vendor, date_tolerance_days=3)
        assert len(pairs) == 0

    def test_date_proximity_no_match_different_amounts(
        self, service: ReconciliationEngineService
    ):
        """Should not match when amounts differ even if dates are close."""
        company = [
            LedgerEntryData(
                id=uuid4(), amount=Decimal("1000"),
                posting_date=date(2024, 3, 15), reference_number="REF-001"
            )
        ]
        vendor = [
            LedgerEntryData(
                id=uuid4(), amount=Decimal("999"),
                posting_date=date(2024, 3, 15), reference_number="VENDOR-XYZ"
            )
        ]

        pairs = service._date_proximity_match(company, vendor, date_tolerance_days=3)
        assert len(pairs) == 0

    def test_date_proximity_picks_closest_date(
        self, service: ReconciliationEngineService
    ):
        """Should pick the vendor entry with the closest date."""
        c1 = LedgerEntryData(
            id=uuid4(), amount=Decimal("1000"),
            posting_date=date(2024, 3, 15), reference_number="REF-001"
        )
        v1 = LedgerEntryData(
            id=uuid4(), amount=Decimal("1000"),
            posting_date=date(2024, 3, 17), reference_number="VENDOR-A"
        )
        v2 = LedgerEntryData(
            id=uuid4(), amount=Decimal("1000"),
            posting_date=date(2024, 3, 16), reference_number="VENDOR-B"
        )

        pairs = service._date_proximity_match([c1], [v1, v2], date_tolerance_days=3)

        assert len(pairs) == 1
        # v2 is closer (1 day vs 2 days)
        assert pairs[0].vendor_entry_id == v2.id

    def test_date_proximity_no_double_vendor_match(
        self, service: ReconciliationEngineService
    ):
        """Each vendor entry should be matched at most once in date-proximity pass."""
        c1 = LedgerEntryData(
            id=uuid4(), amount=Decimal("1000"),
            posting_date=date(2024, 3, 15), reference_number="REF-A"
        )
        c2 = LedgerEntryData(
            id=uuid4(), amount=Decimal("1000"),
            posting_date=date(2024, 3, 16), reference_number="REF-B"
        )
        v1 = LedgerEntryData(
            id=uuid4(), amount=Decimal("1000"),
            posting_date=date(2024, 3, 15), reference_number="VENDOR-X"
        )

        pairs = service._date_proximity_match([c1, c2], [v1], date_tolerance_days=3)

        assert len(pairs) == 1
        # v1 should only be matched once

    def test_date_proximity_with_none_posting_date_skipped(
        self, service: ReconciliationEngineService
    ):
        """Entries with None posting_date should be skipped."""
        company = [
            LedgerEntryData(
                id=uuid4(), amount=Decimal("1000"),
                posting_date=None, reference_number="REF-001"
            )
        ]
        vendor = [
            LedgerEntryData(
                id=uuid4(), amount=Decimal("1000"),
                posting_date=date(2024, 3, 15), reference_number="VENDOR-A"
            )
        ]

        pairs = service._date_proximity_match(company, vendor, date_tolerance_days=3)
        assert len(pairs) == 0


# ─── Category Gating Tests (Vendor Ledger Mapping Rules doc compliance) ──────


def _cat_entry(
    amount: str,
    category: str = "",
    posting_date: date | None = None,
    reference_number: str = "REF-001",
    document_type: str = "",
    assignment_number: str = "",
    document_number: str = "",
    derived_invoice_number: str = "",
) -> LedgerEntryData:
    """Helper to build a LedgerEntryData with a document category set."""
    return LedgerEntryData(
        id=uuid4(),
        amount=Decimal(amount),
        posting_date=posting_date or date(2024, 3, 15),
        reference_number=reference_number,
        document_type=document_type,
        category=category,
        assignment_number=assignment_number,
        document_number=document_number,
        derived_invoice_number=derived_invoice_number,
    )


class TestCategoryGating:
    """
    Cross-side matching must respect the Vendor Ledger Mapping Rules doc:
      - Invoice only matches Invoice
      - Debit Note only matches Credit Note (and vice versa)
      - Payment only matches Receipt (and vice versa)
      - TDS Adjusted only matches TDS Adjusted
      - Knocking Off (AB) and Adjusted (SA) never cross-match at all
    """

    def test_invoice_does_not_match_receipt_on_amount_date(
        self, service: ReconciliationEngineService
    ):
        company = [_cat_entry("1000", "Invoice", date(2024, 3, 15))]
        vendor = [_cat_entry("-1000", "Receipt", date(2024, 3, 15))]
        pairs = service._amount_date_match(company, vendor, date_tolerance_days=5)
        assert len(pairs) == 0

    def test_invoice_matches_invoice_on_amount_date(
        self, service: ReconciliationEngineService
    ):
        company = [_cat_entry("1000", "Invoice", date(2024, 3, 15))]
        vendor = [_cat_entry("-1000", "Invoice", date(2024, 3, 16))]
        pairs = service._amount_date_match(company, vendor, date_tolerance_days=5)
        assert len(pairs) == 1

    def test_payment_matches_receipt(self, service: ReconciliationEngineService):
        company = [_cat_entry("500", "Payment", date(2024, 3, 15))]
        vendor = [_cat_entry("-500", "Receipt", date(2024, 3, 15))]
        pairs = service._amount_date_match(company, vendor, date_tolerance_days=5)
        assert len(pairs) == 1

    def test_debit_note_matches_credit_note_only(
        self, service: ReconciliationEngineService
    ):
        company = [_cat_entry("1000", "Debit Note", date(2024, 3, 15), "REF-1")]
        vendor_credit = [_cat_entry("1000", "Credit Note", date(2024, 3, 15), "REF-1")]
        vendor_invoice = [_cat_entry("1000", "Invoice", date(2024, 3, 15), "REF-1")]
        assert len(service._exact_match(company, vendor_credit)) == 1
        assert len(service._exact_match(company, vendor_invoice)) == 0

    def test_debit_note_does_not_match_invoice_on_amount_date(
        self, service: ReconciliationEngineService
    ):
        company = [_cat_entry("1000", "Debit Note", date(2024, 3, 15))]
        vendor = [_cat_entry("-1000", "Invoice", date(2024, 3, 15))]
        pairs = service._amount_date_match(company, vendor, date_tolerance_days=5)
        assert len(pairs) == 0

    def test_date_proximity_gates_on_category(
        self, service: ReconciliationEngineService
    ):
        company = [_cat_entry("1000", "Invoice", date(2024, 3, 15))]
        vendor = [_cat_entry("1000", "Payment", date(2024, 3, 16))]
        pairs = service._date_proximity_match(company, vendor, date_tolerance_days=3)
        assert len(pairs) == 0

    def test_knockoff_excluded_from_matching(
        self, service: ReconciliationEngineService
    ):
        company = [_cat_entry("1000", "Invoice", date(2024, 3, 15))]
        vendor = [_cat_entry("-1000", "Knocking Off", date(2024, 3, 15))]
        pairs = service._amount_date_match(company, vendor, date_tolerance_days=5)
        assert len(pairs) == 0

    def test_adjusted_sa_excluded_from_cross_matching(
        self, service: ReconciliationEngineService
    ):
        """Bug fix: 'Other entry' (SA/Adjusted) must never cross-match a real
        invoice/payment — per doc, it only nets with its own side's SA entries."""
        company = [_cat_entry("1000", "Adjusted", date(2024, 3, 15))]
        vendor = [_cat_entry("-1000", "Invoice", date(2024, 3, 15))]
        pairs = service._amount_date_match(company, vendor, date_tolerance_days=5)
        assert len(pairs) == 0

    def test_tds_gst_gates_on_category(self, service: ReconciliationEngineService):
        company = [_cat_entry("100000", "Invoice", date(2024, 3, 15), "INV-1")]
        vendor = [_cat_entry("90000", "Knocking Off", date(2024, 3, 15), "INV-1")]
        pairs = service._tds_gst_match(company, vendor, Decimal("10"), Decimal("0"))
        assert len(pairs) == 0

    def test_exact_match_gates_on_category(
        self, service: ReconciliationEngineService
    ):
        company = [_cat_entry("1000", "Invoice", date(2024, 3, 15), "REF-1")]
        vendor = [_cat_entry("1000", "Receipt", date(2024, 3, 15), "REF-1")]
        pairs = service._exact_match(company, vendor)
        assert len(pairs) == 0

    def test_wildcard_category_still_matches(
        self, service: ReconciliationEngineService
    ):
        """Unrecognized/uncategorized entries (wildcard) must remain matchable
        so users aren't blocked before mapping a doc type."""
        company = [_cat_entry("1000", "", date(2024, 3, 15))]
        vendor = [_cat_entry("-1000", "Invoice", date(2024, 3, 15))]
        pairs = service._amount_date_match(company, vendor, date_tolerance_days=5)
        assert len(pairs) == 1


class TestReversalBothSides:
    """
    Reversal (knock-off, AB) netting must run on BOTH ledger sides
    independently — per doc: "Knocking entries are internal entries for both
    Emcure and vendor; it should only map with their internal entries."
    """

    def test_company_reversal_pairs_matched(
        self, service: ReconciliationEngineService
    ):
        d = _cat_entry("5000", document_type="AB")
        cr = _cat_entry("-5000", document_type="AB")
        pairs = service._reversal_match([d, cr], side="company")
        assert len(pairs) == 1
        assert pairs[0].reversal_side == "company"

    def test_vendor_reversal_pairs_matched(
        self, service: ReconciliationEngineService
    ):
        """Bug fix: vendor-side knock-off entries were never netted before —
        they fell into the general matching pool and could match real invoices."""
        d = _cat_entry("5000", category="Knocking Off")
        cr = _cat_entry("-5000", category="Knocking Off")
        pairs = service._reversal_match([d, cr], side="vendor")
        assert len(pairs) == 1
        assert pairs[0].reversal_side == "vendor"

    def test_unpaired_reversal_not_matched(
        self, service: ReconciliationEngineService
    ):
        d = _cat_entry("5000", document_type="AB")
        pairs = service._reversal_match([d], side="company")
        assert len(pairs) == 0

    @pytest.mark.asyncio
    async def test_vendor_reversal_wired_into_full_execution(
        self,
        service: ReconciliationEngineService,
        mock_ledger_repo: AsyncMock,
    ):
        """Vendor-side AB entries must net within the vendor ledger during a
        full execute() run, not leak into cross-side matching or unmatched."""
        case_id = uuid4()
        v1 = _cat_entry("8000", document_type="AB", posting_date=date(2024, 3, 10))
        v2 = _cat_entry("-8000", document_type="AB", posting_date=date(2024, 3, 10))

        def side_effect(cid, side):
            if side == "company":
                return []
            return [v1, v2]

        mock_ledger_repo.get_by_case_and_side.side_effect = side_effect
        result = await service.execute(case_id)

        assert len(result.unmatched_vendor_ids) == 0
        reversal_pairs = [p for p in result.match_pairs if p.pass_number == 9]
        assert len(reversal_pairs) == 1
        assert reversal_pairs[0].reversal_side == "vendor"


class TestSuffixedInvoiceReversal:
    """
    Bug fix: Emcure reposts a reclassed/reversed invoice under the SAME base
    invoice number with a "-R", "-RE", or "-Rev" suffix and the opposite sign
    (e.g. "GJ2501027881-R" = -16755.62 paired with "GJ2501027881-RE" =
    +16755.62). Confirmed against real DB data pulled from a live case.

    Critically, on real data this suffix lives on `derived_invoice_number`
    (the CLEAN-derived value from ZUONR/XBLNR/BELNR) — NOT on
    `document_number`, which is a plain SAP document number with no suffix
    at all (e.g. "6000009613"). An earlier version of this fix checked
    document_number/reference_number only, which never matched real data —
    it only passed against hand-built test fixtures that put the suffix on
    document_number directly. The real bug this caused: the genuine,
    un-suffixed invoice sat unmatched while its "-RE" reversal counterpart
    stole the vendor's match instead.
    """

    def test_suffixed_pair_nets_within_company_side(
        self, service: ReconciliationEngineService
    ):
        d = _cat_entry(
            "16755.62", "Invoice", document_number="6000009613",
            derived_invoice_number="GJ2501027881-RE",
        )
        cr = _cat_entry(
            "-16755.62", "Invoice", document_number="6000009614",
            derived_invoice_number="GJ2501027881-R",
        )
        pairs = service._reversal_match([d, cr], side="company")
        assert len(pairs) == 1
        assert pairs[0].reversal_side == "company"

    def test_suffix_detection_via_reference_number_too(
        self, service: ReconciliationEngineService
    ):
        d = _cat_entry("11519", "Invoice", reference_number="GJ2501018033-R")
        cr = _cat_entry("-11519", "Invoice", reference_number="GJ2501018033-R")
        pairs = service._reversal_match([d, cr], side="company")
        assert len(pairs) == 1

    def test_unsuffixed_invoice_not_treated_as_reversal(
        self, service: ReconciliationEngineService
    ):
        """The plain, un-suffixed invoice (e.g. "GJ2501027881") must NOT be
        swept into same-side netting — it keeps matching cross-side as usual."""
        plain = _cat_entry(
            "-16755.62", "Invoice", document_number="7043047546",
            derived_invoice_number="GJ2501027881",
        )
        assert _is_reversal(plain) is False

    def test_unpaired_suffixed_entry_falls_through(
        self, service: ReconciliationEngineService
    ):
        """An unpaired suffixed entry (no opposite-sign counterpart) is left
        alone by the reversal pass and falls through to normal matching."""
        lone = _cat_entry(
            "-17174.51", "Invoice", document_number="6000009613",
            derived_invoice_number="GJ2501024670-RE",
        )
        pairs = service._reversal_match([lone], side="company")
        assert len(pairs) == 0

    def test_different_base_invoice_not_netted_despite_equal_amount(
        self, service: ReconciliationEngineService
    ):
        """Two DIFFERENT invoices' suffixed legs that happen to cancel out in
        amount (e.g. a Debit Note leg of one invoice and a TDS leg of an
        unrelated invoice) must NOT be netted against each other — only
        same-base-invoice suffix pairs may net. Reproduces the real DB shape:
        both entries carry a "-Rev" suffix but on different base invoices."""
        d = _cat_entry(
            "17174.51", "Debit Note", document_number="7031002318",
            derived_invoice_number="GJ2501024670-Rev",
        )
        unrelated = _cat_entry(
            "-17174.51", "TDS Adjusted", document_number="9999999999",
            derived_invoice_number="GJ2501099999-Rev",
        )
        pairs = service._reversal_match([d, unrelated], side="company")
        assert len(pairs) == 0

    @pytest.mark.asyncio
    async def test_suffixed_reversal_wired_into_full_execution(
        self,
        service: ReconciliationEngineService,
        mock_ledger_repo: AsyncMock,
    ):
        """Full execute() run: the suffixed pair nets out and never reaches
        cross-side matching, so it can't steal an unrelated vendor invoice
        tied on amount/date. Also proves the genuine un-suffixed invoice is
        the one that ends up matched, not a reversal leg."""
        case_id = uuid4()
        c1 = _cat_entry(
            "16755.62", "Invoice", document_number="6000009613",
            derived_invoice_number="GJ2501027881-RE",
            posting_date=date(2024, 3, 10),
        )
        c2 = _cat_entry(
            "-16755.62", "Invoice", document_number="6000009614",
            derived_invoice_number="GJ2501027881-R",
            posting_date=date(2024, 3, 10),
        )
        genuine = _cat_entry(
            "-16755.62", "Invoice", document_number="7043047546",
            derived_invoice_number="GJ2501027881",
            posting_date=date(2024, 3, 10),
        )
        v1 = _cat_entry(
            "16755.62", "Invoice", document_number="201193",
            reference_number="GJ2501027881",
            posting_date=date(2024, 3, 10),
        )

        def side_effect(cid, side):
            if side == "company":
                return [c1, c2, genuine]
            return [v1]

        mock_ledger_repo.get_by_case_and_side.side_effect = side_effect
        result = await service.execute(case_id)

        reversal_pairs = [p for p in result.match_pairs if p.pass_number == 9]
        assert len(reversal_pairs) == 1
        assert reversal_pairs[0].reversal_side == "company"
        assert {reversal_pairs[0].company_entry_id, reversal_pairs[0].vendor_entry_id} == {c1.id, c2.id}
        # The vendor entry must be matched against the GENUINE invoice, not
        # consumed by a reversal leg.
        genuine_pairs = [p for p in result.match_pairs if p.company_entry_id == genuine.id]
        assert len(genuine_pairs) == 1
        assert genuine_pairs[0].vendor_entry_id == v1.id


class TestOtherEntrySameSideNetting:
    """
    "Other entry" (SA/Adjusted) rows net only against other SA entries on
    the SAME side — per doc: "Other entry like SA from both side... therefore
    that only map with each other in both side."
    """

    def test_company_sa_entries_net_within_company_side(
        self, service: ReconciliationEngineService
    ):
        d = _cat_entry("3000", document_type="SA")
        cr = _cat_entry("-3000", document_type="SA")
        pairs = service._other_entry_match([d, cr], side="company")
        assert len(pairs) == 1

    def test_vendor_sa_entries_net_within_vendor_side(
        self, service: ReconciliationEngineService
    ):
        d = _cat_entry("3000", category="Adjusted")
        cr = _cat_entry("-3000", category="Adjusted")
        pairs = service._other_entry_match([d, cr], side="vendor")
        assert len(pairs) == 1


class TestUTRPaymentGrouping:
    """
    Per doc: "If Emcure has made the payment in multiple split entries under
    the same UTR, then combine all those entries and match them with the
    vendor's entry based on the payment date and total amount."
    """

    def test_split_payments_same_utr_combine_and_match(
        self, service: ReconciliationEngineService
    ):
        c1 = _cat_entry("600", "Payment", date(2024, 3, 10), assignment_number="UTR123")
        c2 = _cat_entry("400", "Payment", date(2024, 3, 12), assignment_number="UTR123")
        v1 = _cat_entry("-1000", "Receipt", date(2024, 3, 15))
        groups = service._utr_payment_match([c1, c2], [v1], date_tolerance_days=15)
        assert len(groups) == 1
        assert set(groups[0].company_entry_ids) == {c1.id, c2.id}
        assert groups[0].vendor_entry_ids == [v1.id]

    def test_single_entry_utr_not_grouped(self, service: ReconciliationEngineService):
        """A UTR with only one entry doesn't need combining — leave it to the
        normal 1:1 passes."""
        c1 = _cat_entry("600", "Payment", date(2024, 3, 10), assignment_number="UTR123")
        v1 = _cat_entry("-600", "Receipt", date(2024, 3, 10))
        groups = service._utr_payment_match([c1], [v1], date_tolerance_days=15)
        assert len(groups) == 0

    def test_utr_grouping_respects_date_tolerance(
        self, service: ReconciliationEngineService
    ):
        c1 = _cat_entry("600", "Payment", date(2024, 1, 1), assignment_number="UTR9")
        c2 = _cat_entry("400", "Payment", date(2024, 1, 1), assignment_number="UTR9")
        v1 = _cat_entry("-1000", "Receipt", date(2024, 6, 1))  # far outside window
        groups = service._utr_payment_match([c1, c2], [v1], date_tolerance_days=15)
        assert len(groups) == 0


# ─── Payment Date-Range Directionality (Vendor Ledger Mapping Rules doc) ────


class TestPaymentDateDirectionality:
    """
    Per doc: "map with date range mapping, from the date of payment made
    from Emcure to after 15 days of receipt amount of vendor" — the vendor's
    receipt date must be ON OR AFTER the company payment date, within N days
    forward. This is directional, NOT a symmetric ± window.
    """

    def test_vendor_receipt_after_payment_date_matches(
        self, service: ReconciliationEngineService
    ):
        company = [_cat_entry("1000", "Payment", date(2024, 3, 1))]
        vendor = [_cat_entry("-1000", "Receipt", date(2024, 3, 10))]  # +9 days
        pairs = service._amount_date_match(company, vendor, date_tolerance_days=15)
        assert len(pairs) == 1

    def test_vendor_receipt_before_payment_date_does_not_match(
        self, service: ReconciliationEngineService
    ):
        """Bug fix: previously used abs(date_diff), which incorrectly allowed
        a vendor receipt dated BEFORE the company payment to match."""
        company = [_cat_entry("1000", "Payment", date(2024, 3, 10))]
        vendor = [_cat_entry("-1000", "Receipt", date(2024, 3, 1))]  # -9 days (before)
        pairs = service._amount_date_match(company, vendor, date_tolerance_days=15)
        assert len(pairs) == 0

    def test_vendor_receipt_beyond_window_forward_does_not_match(
        self, service: ReconciliationEngineService
    ):
        company = [_cat_entry("1000", "Payment", date(2024, 3, 1))]
        vendor = [_cat_entry("-1000", "Receipt", date(2024, 4, 1))]  # +31 days, beyond 15
        pairs = service._amount_date_match(company, vendor, date_tolerance_days=15)
        assert len(pairs) == 0

    def test_non_payment_category_stays_symmetric(
        self, service: ReconciliationEngineService
    ):
        """Invoice matching is unaffected — still a symmetric ± window."""
        company = [_cat_entry("1000", "Invoice", date(2024, 3, 10))]
        vendor = [_cat_entry("-1000", "Invoice", date(2024, 3, 1))]  # -9 days
        pairs = service._amount_date_match(company, vendor, date_tolerance_days=15)
        assert len(pairs) == 1

    def test_utr_grouping_rejects_vendor_receipt_before_payment(
        self, service: ReconciliationEngineService
    ):
        c1 = _cat_entry("600", "Payment", date(2024, 3, 10), assignment_number="UTR1")
        c2 = _cat_entry("400", "Payment", date(2024, 3, 12), assignment_number="UTR1")
        v1 = _cat_entry("-1000", "Receipt", date(2024, 3, 1))  # before the payments
        groups = service._utr_payment_match([c1, c2], [v1], date_tolerance_days=15)
        assert len(groups) == 0


# ─── Regression: "Other" category must be wildcard, not a real category ────


class TestOtherCategoryIsWildcard:
    """
    DataTransformationService.classify_document_type persists
    document_category="Other" for any doc type outside its narrow hardcoded
    set (RE/KR/DR/ZP/KZ/ZV/KG/RV), BEFORE the reconciliation engine runs.
    If "Other" were treated as a real, mutually-exclusive category (like
    "Adjusted"), an Invoice entry could never match an "Other"-categorized
    entry even when they're the same real invoice — this collapsed match
    counts from ~340 to ~18 on a real case.
    """

    def test_invoice_matches_other_categorized_entry(
        self, service: ReconciliationEngineService
    ):
        company = [_cat_entry("1000", "Invoice", date(2024, 3, 15), "REF-1")]
        vendor = [_cat_entry("1000", "Other", date(2024, 3, 15), "REF-1")]
        pairs = service._exact_match(company, vendor)
        assert len(pairs) == 1

    def test_other_matches_other(self, service: ReconciliationEngineService):
        company = [_cat_entry("1000", "Other", date(2024, 3, 15), "REF-1")]
        vendor = [_cat_entry("1000", "Other", date(2024, 3, 15), "REF-1")]
        pairs = service._exact_match(company, vendor)
        assert len(pairs) == 1

    def test_other_still_excludes_knockoff(
        self, service: ReconciliationEngineService
    ):
        """"Other" being wildcard doesn't override the hard exclusions —
        knock-off entries must still never cross-match."""
        company = [_cat_entry("1000", "Other", date(2024, 3, 15))]
        vendor = [_cat_entry("-1000", "Knocking Off", date(2024, 3, 15))]
        pairs = service._amount_date_match(company, vendor, date_tolerance_days=5)
        assert len(pairs) == 0
