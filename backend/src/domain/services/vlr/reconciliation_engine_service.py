"""
Multi-Pass Reconciliation Engine Domain Service.

Implements the 7-pass matching algorithm for reconciling company and vendor
ledger entries. Enforces no-double-match invariant, calculates match statistics,
and supports re-reconciliation by clearing previous results.

Confidence scoring per BRD Section 5.6.10:
- Pass 1 (Exact): 1.0 (Auto-Accept)
- Pass 2 (Tolerance): 0.85 (Auto-Accept)
- Pass 3 (Fuzzy Reference): 0.70 (Finance confirmation required)
- Pass 4 (One-to-Many): 0.80 (Finance confirmation required)
- Pass 5 (Many-to-One): 0.75 (Finance confirmation required)
- Pass 6 (Date-proximity): 0.70 (Finance confirmation required)
- Pass 7 (Unmatched): 0.0

Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 5.8, 5.9, 5.10, 5.11, 5.12, 5.13,
              17.1, 17.2, 17.3, 17.4, 36.1, 36.2, 36.3
"""

import difflib
import time
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from enum import IntEnum
from uuid import UUID, uuid4

from src.domain.repositories.vlr.case_repository import ICaseRepository
from src.domain.repositories.vlr.exception_repository import IExceptionRepository
from src.domain.repositories.vlr.ledger_entry_repository import ILedgerEntryRepository
from src.domain.repositories.vlr.match_result_repository import IMatchResultRepository
from src.infrastructure.logging.structured_logger import get_structured_logger

_structured_logger = get_structured_logger("reconciliation_engine")


class MatchPassType(IntEnum):
    """Matching pass types executed in sequence."""

    EXACT = 1
    TOLERANCE = 2
    FUZZY_REFERENCE = 3
    ONE_TO_MANY = 4
    MANY_TO_ONE = 5
    DATE_PROXIMITY = 6
    UNMATCHED = 7


# BRD Section 5.6.10 - Matching Priority Rules confidence scores (normalized to 0.0-1.0)
# Pass 1 (Exact): 100 → 1.0, Auto-Accept = Yes
# Pass 2 (Tolerance): 85 → 0.85, Auto-Accept = Yes
# Pass 3 (Fuzzy Reference): 70 → 0.70, Auto-Accept = No
# Pass 4 (One-to-Many): 80 → 0.80, Auto-Accept = No
# Pass 5 (Many-to-One): 75 → 0.75, Auto-Accept = No
# Pass 6 (Date-proximity): 70 → 0.70, Auto-Accept = No
# Pass 7 (Unmatched): 0 → 0.0
CONFIDENCE_SCORES: dict[int, float] = {
    MatchPassType.EXACT: 1.0,
    MatchPassType.TOLERANCE: 0.85,
    MatchPassType.FUZZY_REFERENCE: 0.70,
    MatchPassType.ONE_TO_MANY: 0.80,
    MatchPassType.MANY_TO_ONE: 0.75,
    MatchPassType.DATE_PROXIMITY: 0.70,
    MatchPassType.UNMATCHED: 0.0,
}


@dataclass
class LedgerEntryData:
    """Lightweight representation of a ledger entry for matching logic."""

    id: UUID
    amount: Decimal
    posting_date: object  # date
    reference_number: str
    document_number: str = ""
    side: str = ""
    document_type: str = ""


# Pass number for the company-side reversal (knock-off) pass. Kept outside the
# 1–7 MatchPassType range so it doesn't disturb the standard pass statistics.
REVERSAL_PASS = 9


@dataclass
class MatchPair:
    """A matched pair of entries (1:1 match)."""

    company_entry_id: UUID
    vendor_entry_id: UUID
    confidence_score: float
    pass_number: int
    matched_amount: Decimal
    difference_amount: Decimal = Decimal("0")


@dataclass
class MatchGroup:
    """A match group for one-to-many or many-to-one matches."""

    company_entry_ids: list[UUID]
    vendor_entry_ids: list[UUID]
    confidence_score: float
    pass_number: int
    matched_amount: Decimal
    difference_amount: Decimal = Decimal("0")


@dataclass
class PassStatistics:
    """Statistics for a single matching pass."""

    pass_number: int
    match_count: int = 0
    matched_amount: Decimal = Decimal("0")
    percentage: float = 0.0


@dataclass
class MatchStatistics:
    """Aggregate match statistics for a reconciliation case."""

    total_company_entries: int = 0
    total_vendor_entries: int = 0
    total_matched_company: int = 0
    total_matched_vendor: int = 0
    pass_statistics: list[PassStatistics] = field(default_factory=list)


@dataclass
class ReconciliationResult:
    """Result of executing the full reconciliation engine."""

    case_id: UUID
    match_pairs: list[MatchPair] = field(default_factory=list)
    match_groups: list[MatchGroup] = field(default_factory=list)
    unmatched_company_ids: list[UUID] = field(default_factory=list)
    unmatched_vendor_ids: list[UUID] = field(default_factory=list)
    statistics: MatchStatistics = field(default_factory=MatchStatistics)
    needs_confirmation: bool = False


class ReconciliationEngineService:
    """
    Domain service implementing the 7-pass reconciliation matching algorithm.

    Pass 1: Exact Match - amount + date + reference_number identical (confidence=1.0)
    Pass 2: Tolerance Match - amount within tolerance AND reference numbers match (confidence=0.85)
    Pass 3: Fuzzy Reference Match - amounts equal, reference similarity > 0.8 (confidence=0.70)
    Pass 4: One-to-Many - one company entry = sum of multiple vendor entries (confidence=0.80)
    Pass 5: Many-to-One - multiple company entries sum to one vendor entry (confidence=0.75)
    Pass 6: Date-proximity Match - amount matches + date within configurable N days (confidence=0.70)
    Pass 7: Unmatched - mark remaining entries as unmatched exceptions (confidence=0.0)

    Invariant MR-001: No entry is matched more than once across all passes.
    Invariant MR-002: Once matched in Pass N, a row cannot be re-matched in later passes.
    """

    def __init__(
        self,
        ledger_entry_repository: ILedgerEntryRepository,
        match_result_repository: IMatchResultRepository,
        case_repository: ICaseRepository,
        exception_repository: IExceptionRepository,
    ) -> None:
        self._ledger_repo = ledger_entry_repository
        self._match_repo = match_result_repository
        self._case_repo = case_repository
        self._exception_repo = exception_repository

    # ──────────────────────────────────────────────────────────────────────
    # Main Execution
    # ──────────────────────────────────────────────────────────────────────

    async def execute(
        self,
        case_id: UUID,
        tolerance: Decimal = Decimal("0"),
        fuzzy_threshold: float = 0.8,
        date_tolerance_days: int = 3,
        tds_percentage: Decimal = Decimal("0"),
        gst_percentage: Decimal = Decimal("0"),
    ) -> ReconciliationResult:
        """
        Execute the full 7-pass reconciliation engine for a case.

        Requirement 5.1: Execute passes in sequence.
        Requirement 5.8: Complete within 120 seconds for 5,000 entries per side.
        Requirement 5.10: No entry matched more than once.
        Requirement 5.13: Clear previous results before re-reconciliation.
        Requirement 17.1: Pass 6 Date-proximity Match by amount + date within N days.
        """
        start = time.perf_counter()
        # Clear previous results for re-reconciliation (Requirement 5.13)
        await self.clear_previous_results(case_id)

        # Load all entries for both sides
        company_entries_raw = await self._ledger_repo.get_by_case_and_side(
            case_id, "company"
        )
        vendor_entries_raw = await self._ledger_repo.get_by_case_and_side(
            case_id, "vendor"
        )

        # Convert to lightweight data objects
        company_entries = self._to_entry_data_list(company_entries_raw)
        vendor_entries = self._to_entry_data_list(vendor_entries_raw)

        # Track which entries have been matched (no-double-match invariant)
        matched_company_ids: set[UUID] = set()
        matched_vendor_ids: set[UUID] = set()

        result = ReconciliationResult(case_id=case_id)
        result.statistics.total_company_entries = len(company_entries)
        result.statistics.total_vendor_entries = len(vendor_entries)

        # ─── Pass 0: Company-side Reversal (knock-off) ───────────────────
        # Net offsetting AB reversal entries within the company ledger before
        # any cross-side matching, so they don't surface as differences.
        reversal_pairs = self._reversal_match(company_entries)
        for pair in reversal_pairs:
            # Both entries are company-side for reversals.
            matched_company_ids.add(pair.company_entry_id)
            matched_company_ids.add(pair.vendor_entry_id)
            result.match_pairs.append(pair)

        # ─── Pass 1: Exact Match ─────────────────────────────────────────
        available_company = [
            e for e in company_entries if e.id not in matched_company_ids
        ]
        available_vendor = [
            e for e in vendor_entries if e.id not in matched_vendor_ids
        ]
        exact_pairs = self._exact_match(available_company, available_vendor)
        for pair in exact_pairs:
            matched_company_ids.add(pair.company_entry_id)
            matched_vendor_ids.add(pair.vendor_entry_id)
            result.match_pairs.append(pair)

        # ─── Pass 1.5: Amount + Date Match (ignoring doc number) ──────────
        # Most common scenario: company SAP doc numbers don't match vendor invoice numbers
        # but amounts are exactly equal and dates are close
        available_company = [
            e for e in company_entries if e.id not in matched_company_ids
        ]
        available_vendor = [
            e for e in vendor_entries if e.id not in matched_vendor_ids
        ]
        amount_date_pairs = self._amount_date_match(
            available_company, available_vendor, date_tolerance_days
        )
        for pair in amount_date_pairs:
            matched_company_ids.add(pair.company_entry_id)
            matched_vendor_ids.add(pair.vendor_entry_id)
            result.match_pairs.append(pair)

        # ─── Pass 2: Tolerance Match ─────────────────────────────────────
        available_company = [
            e for e in company_entries if e.id not in matched_company_ids
        ]
        available_vendor = [
            e for e in vendor_entries if e.id not in matched_vendor_ids
        ]
        tolerance_pairs = self._tolerance_match(
            available_company, available_vendor, tolerance
        )
        for pair in tolerance_pairs:
            matched_company_ids.add(pair.company_entry_id)
            matched_vendor_ids.add(pair.vendor_entry_id)
            result.match_pairs.append(pair)

        # ─── Pass 2.5: TDS/GST Tolerance Match ─────────────────────────────
        # Match entries where the difference equals TDS% or GST% of the amount
        # (e.g., company booked ₹100 but vendor shows ₹90 because 10% TDS was deducted)
        if tds_percentage > 0 or gst_percentage > 0:
            available_company = [
                e for e in company_entries if e.id not in matched_company_ids
            ]
            available_vendor = [
                e for e in vendor_entries if e.id not in matched_vendor_ids
            ]
            tds_gst_pairs = self._tds_gst_match(
                available_company, available_vendor, tds_percentage, gst_percentage
            )
            for pair in tds_gst_pairs:
                matched_company_ids.add(pair.company_entry_id)
                matched_vendor_ids.add(pair.vendor_entry_id)
                result.match_pairs.append(pair)

        # ─── Pass 3: Fuzzy Reference Match ────────────────────────────────
        available_company = [
            e for e in company_entries if e.id not in matched_company_ids
        ]
        available_vendor = [
            e for e in vendor_entries if e.id not in matched_vendor_ids
        ]
        fuzzy_pairs = self._fuzzy_reference_match(
            available_company, available_vendor, fuzzy_threshold
        )
        for pair in fuzzy_pairs:
            matched_company_ids.add(pair.company_entry_id)
            matched_vendor_ids.add(pair.vendor_entry_id)
            result.match_pairs.append(pair)

        # ─── Pass 4: One-to-Many ──────────────────────────────────────────
        available_company = [
            e for e in company_entries if e.id not in matched_company_ids
        ]
        available_vendor = [
            e for e in vendor_entries if e.id not in matched_vendor_ids
        ]
        one_to_many_groups = self._one_to_many_match(
            available_company, available_vendor
        )
        for group in one_to_many_groups:
            for cid in group.company_entry_ids:
                matched_company_ids.add(cid)
            for vid in group.vendor_entry_ids:
                matched_vendor_ids.add(vid)
            result.match_groups.append(group)

        # ─── Pass 5: Many-to-One ──────────────────────────────────────────
        available_company = [
            e for e in company_entries if e.id not in matched_company_ids
        ]
        available_vendor = [
            e for e in vendor_entries if e.id not in matched_vendor_ids
        ]
        many_to_one_groups = self._many_to_one_match(
            available_company, available_vendor
        )
        for group in many_to_one_groups:
            for cid in group.company_entry_ids:
                matched_company_ids.add(cid)
            for vid in group.vendor_entry_ids:
                matched_vendor_ids.add(vid)
            result.match_groups.append(group)

        # ─── Pass 6: Date-proximity Match ─────────────────────────────────
        available_company = [
            e for e in company_entries if e.id not in matched_company_ids
        ]
        available_vendor = [
            e for e in vendor_entries if e.id not in matched_vendor_ids
        ]
        date_proximity_pairs = self._date_proximity_match(
            available_company, available_vendor, date_tolerance_days
        )
        for pair in date_proximity_pairs:
            matched_company_ids.add(pair.company_entry_id)
            matched_vendor_ids.add(pair.vendor_entry_id)
            result.match_pairs.append(pair)

        # ─── Pass 6.5: Tolerance + Date Match (amounts within tolerance) ──
        # Catches invoices that differ by GST rounding or small journal
        # adjustments (e.g. company 208,683 vs vendor 208,860, diff 177).
        # Only applies when tolerance/tds/gst settings allow a difference.
        if tolerance > 0 or tds_percentage > 0 or gst_percentage > 0:
            available_company = [
                e for e in company_entries if e.id not in matched_company_ids
            ]
            available_vendor = [
                e for e in vendor_entries if e.id not in matched_vendor_ids
            ]
            tol_date_pairs = self._tolerance_date_match(
                available_company, available_vendor,
                tolerance, tds_percentage, gst_percentage, date_tolerance_days,
            )
            for pair in tol_date_pairs:
                matched_company_ids.add(pair.company_entry_id)
                matched_vendor_ids.add(pair.vendor_entry_id)
                result.match_pairs.append(pair)

        # ─── Pass 7: Mark Unmatched ───────────────────────────────────────
        result.unmatched_company_ids = [
            e.id for e in company_entries if e.id not in matched_company_ids
        ]
        result.unmatched_vendor_ids = [
            e.id for e in vendor_entries if e.id not in matched_vendor_ids
        ]

        # Determine if confirmation is needed (fuzzy/combination/date-proximity matches)
        result.needs_confirmation = len(fuzzy_pairs) > 0 or (
            len(one_to_many_groups) > 0 or len(many_to_one_groups) > 0
            or len(date_proximity_pairs) > 0
        )

        # Calculate statistics (Requirement 5.12)
        result.statistics.total_matched_company = len(matched_company_ids)
        result.statistics.total_matched_vendor = len(matched_vendor_ids)
        result.statistics = self._calculate_statistics(
            result, company_entries, vendor_entries
        )

        # Persist results
        await self._persist_results(case_id, result, company_entries, vendor_entries)

        # Compute and store balances, document categories, and net difference
        await self._compute_summary_fields(
            case_id, company_entries_raw, vendor_entries_raw
        )

        duration_ms = (time.perf_counter() - start) * 1000
        _structured_logger.log_success(
            operation="execute_reconciliation",
            duration_ms=duration_ms,
            case_id=str(case_id),
            total_company=result.statistics.total_company_entries,
            total_vendor=result.statistics.total_vendor_entries,
            matched_company=result.statistics.total_matched_company,
            matched_vendor=result.statistics.total_matched_vendor,
            match_pairs=len(result.match_pairs),
            match_groups=len(result.match_groups),
        )

        return result

    # ──────────────────────────────────────────────────────────────────────
    # Summary Field Computation (balances, categories, net difference)
    # ──────────────────────────────────────────────────────────────────────

    async def _compute_summary_fields(
        self,
        case_id: UUID,
        company_entries_raw: list,
        vendor_entries_raw: list,
    ) -> None:
        """
        Compute opening/closing balances, classify document categories, and
        net difference. Stores balances + net_difference on the case and
        updates document_category on each ledger entry.
        """
        from src.domain.services.vlr.doc_type_mapping import classify_document_type

        def _classify_entries(entries: list) -> None:
            """Set document_category on each entry based on its doc type."""
            for e in entries:
                dt = getattr(e, "document_type", None)
                if dt:
                    category = classify_document_type(dt)
                    # If not in the SAP map, use the doc type itself if it's already a category
                    if category == "Unknown":
                        # Vendor ledgers often already have category-like doc types
                        lowered = dt.lower()
                        if "open" in lowered:
                            category = "Opening Balance"
                        elif "clos" in lowered:
                            category = "Closing Balance"
                        elif "sale" in lowered or "invoice" in lowered:
                            category = "Invoice"
                        elif "payment" in lowered or "receipt" in lowered:
                            category = "Payment"
                        elif "journal" in lowered:
                            category = "Journal"
                        else:
                            category = dt
                    e.document_category = category

        _classify_entries(company_entries_raw)
        _classify_entries(vendor_entries_raw)

        def _find_balance(entries: list, keyword: str) -> Decimal | None:
            """Find opening/closing balance from entries by category keyword."""
            for e in entries:
                cat = (getattr(e, "document_category", "") or "").lower()
                if keyword in cat:
                    amt = getattr(e, "amount", None)
                    if amt is not None:
                        return Decimal(str(amt))
            return None

        def _sum_non_balance(entries: list) -> Decimal:
            """Total of a side's transactional entries, excluding opening/closing
            balance rows (used as a closing-balance fallback)."""
            total = Decimal("0")
            for e in entries:
                cat = (getattr(e, "document_category", "") or "").lower()
                if "opening" in cat or "closing" in cat:
                    continue
                amt = getattr(e, "amount", None)
                if amt is not None:
                    total += Decimal(str(amt))
            return total

        company_opening = _find_balance(company_entries_raw, "opening")
        company_closing = _find_balance(company_entries_raw, "closing")
        vendor_opening = _find_balance(vendor_entries_raw, "opening")
        vendor_closing = _find_balance(vendor_entries_raw, "closing")

        # Not every ledger carries an explicit closing-balance row. When it's
        # missing, derive the closing position as opening + sum(entries) so the
        # net difference is still computed instead of being left NULL (which the
        # UI would render as a misleading "0.00 / Reconciled").
        effective_company_closing = company_closing
        if effective_company_closing is None and company_entries_raw:
            effective_company_closing = (company_opening or Decimal("0")) + _sum_non_balance(
                company_entries_raw
            )

        effective_vendor_closing = vendor_closing
        if effective_vendor_closing is None and vendor_entries_raw:
            effective_vendor_closing = (vendor_opening or Decimal("0")) + _sum_non_balance(
                vendor_entries_raw
            )

        # Net difference = company closing - vendor closing. Computed whenever
        # both sides have entries (using derived closings when needed).
        net_difference = None
        if effective_company_closing is not None and effective_vendor_closing is not None:
            net_difference = effective_company_closing - effective_vendor_closing

        # Persist balance/category updates via the ledger repo's session
        await self._ledger_repo._session.flush()

        # Update case with balances and net difference
        update_data: dict = {}
        if company_opening is not None:
            update_data["company_opening_balance"] = company_opening
        if company_closing is not None:
            update_data["company_closing_balance"] = company_closing
        if vendor_opening is not None:
            update_data["vendor_opening_balance"] = vendor_opening
        if vendor_closing is not None:
            update_data["vendor_closing_balance"] = vendor_closing
        if net_difference is not None:
            update_data["net_difference"] = net_difference

        if update_data:
            await self._case_repo.update(case_id, update_data)

    # ──────────────────────────────────────────────────────────────────────
    # Company-side Reversal (knock-off) Match
    # ──────────────────────────────────────────────────────────────────────

    def _reversal_match(
        self, company: list[LedgerEntryData]
    ) -> list[MatchPair]:
        """
        Knock off company-side reversal entries against each other.

        A reversal pair is two COMPANY entries with:
          - document type "AB" (SAP reversal document type), and
          - equal magnitude, opposite sign (they net to zero).

        These offset within the company ledger itself (e.g. an entry posted and
        later reversed), so they should be removed from the reconciliation
        difference rather than reported as unmatched. Each pair is returned as a
        MatchPair whose two entries are both on the company side.
        """
        pairs: list[MatchPair] = []
        used: set[UUID] = set()

        # Only AB-type company entries participate.
        ab_entries = [
            e for e in company
            if (e.document_type or "").strip().upper() == "AB"
        ]

        # Bucket by absolute amount so we can find opposite-sign counterparts.
        by_abs: dict[Decimal, list[LedgerEntryData]] = {}
        for e in ab_entries:
            by_abs.setdefault(abs(e.amount), []).append(e)

        for abs_amt, group in by_abs.items():
            if abs_amt == 0:
                continue
            debits = [e for e in group if e.amount > 0]
            credits = [e for e in group if e.amount < 0]
            # Pair each debit with a credit of the same magnitude.
            for d in debits:
                if d.id in used:
                    continue
                for cr in credits:
                    if cr.id in used:
                        continue
                    used.add(d.id)
                    used.add(cr.id)
                    pairs.append(
                        MatchPair(
                            company_entry_id=d.id,
                            vendor_entry_id=cr.id,  # both are company-side here
                            confidence_score=1.0,
                            pass_number=REVERSAL_PASS,
                            matched_amount=abs_amt,
                            difference_amount=Decimal("0"),
                        )
                    )
                    break

        return pairs

    # ──────────────────────────────────────────────────────────────────────
    # Pass 1: Exact Match
    # ──────────────────────────────────────────────────────────────────────

    def _exact_match(
        self,
        company: list[LedgerEntryData],
        vendor: list[LedgerEntryData],
    ) -> list[MatchPair]:
        """
        Match entries where amount, date, and reference_number are identical.

        Requirement 5.2: confidence_score = 1.0 for exact matches.
        """
        pairs: list[MatchPair] = []
        used_vendor_ids: set[UUID] = set()

        # Build a lookup for vendor entries by (amount, date, reference)
        vendor_lookup: dict[tuple, list[LedgerEntryData]] = {}
        for v_entry in vendor:
            key = (v_entry.amount, v_entry.posting_date, v_entry.reference_number)
            vendor_lookup.setdefault(key, []).append(v_entry)

        for c_entry in company:
            key = (c_entry.amount, c_entry.posting_date, c_entry.reference_number)
            candidates = vendor_lookup.get(key, [])
            for v_entry in candidates:
                if v_entry.id not in used_vendor_ids:
                    pairs.append(
                        MatchPair(
                            company_entry_id=c_entry.id,
                            vendor_entry_id=v_entry.id,
                            confidence_score=1.0,
                            pass_number=MatchPassType.EXACT,
                            matched_amount=c_entry.amount,
                            difference_amount=Decimal("0"),
                        )
                    )
                    used_vendor_ids.add(v_entry.id)
                    break

        return pairs

    # ──────────────────────────────────────────────────────────────────────
    # Pass 1.5: Amount + Date Match (cross-format doc numbers)
    # ──────────────────────────────────────────────────────────────────────

    def _amount_date_match(
        self,
        company: list[LedgerEntryData],
        vendor: list[LedgerEntryData],
        date_tolerance_days: int = 15,
    ) -> list[MatchPair]:
        """
        Match entries where amounts are exactly equal (with sign flip since company
        records payables as negative, vendor records sales as positive) and dates
        are within tolerance days.

        This is the most common matching scenario between SAP company ledgers and
        vendor ledgers where document numbers use different formats.

        Confidence: 0.90 (high confidence since amounts match exactly)
        """
        from datetime import timedelta

        pairs: list[MatchPair] = []
        used_vendor_ids: set[UUID] = set()

        # Build vendor lookup by absolute amount for fast matching
        vendor_by_abs_amount: dict[Decimal, list[LedgerEntryData]] = {}
        for v_entry in vendor:
            abs_amt = abs(v_entry.amount)
            vendor_by_abs_amount.setdefault(abs_amt, []).append(v_entry)

        for c_entry in company:
            abs_c_amount = abs(c_entry.amount)
            candidates = vendor_by_abs_amount.get(abs_c_amount, [])

            best_match: LedgerEntryData | None = None
            best_date_diff: int = date_tolerance_days + 1

            for v_entry in candidates:
                if v_entry.id in used_vendor_ids:
                    continue

                # Check date proximity
                if c_entry.posting_date and v_entry.posting_date:
                    try:
                        c_date = c_entry.posting_date
                        v_date = v_entry.posting_date
                        date_diff = abs((c_date - v_date).days)
                    except (TypeError, AttributeError):
                        date_diff = 0
                else:
                    date_diff = 0

                if date_diff <= date_tolerance_days and date_diff < best_date_diff:
                    best_date_diff = date_diff
                    best_match = v_entry

            if best_match is not None:
                pairs.append(
                    MatchPair(
                        company_entry_id=c_entry.id,
                        vendor_entry_id=best_match.id,
                        confidence_score=0.90,
                        pass_number=MatchPassType.EXACT,  # Categorize under exact for simplicity
                        matched_amount=c_entry.amount,
                        difference_amount=c_entry.amount + best_match.amount,  # sign-aware diff
                    )
                )
                used_vendor_ids.add(best_match.id)

        return pairs

    def _tolerance_date_match(
        self,
        company: list[LedgerEntryData],
        vendor: list[LedgerEntryData],
        tolerance: Decimal,
        tds_percentage: Decimal,
        gst_percentage: Decimal,
        date_tolerance_days: int = 15,
    ) -> list[MatchPair]:
        """
        Match entries whose ABSOLUTE amounts are within an allowed difference
        (tolerance %, TDS %, or GST %) and whose dates are within tolerance days,
        WITHOUT requiring reference numbers to match.

        Catches invoices that differ by GST rounding or small journal adjustments
        (e.g. company 208,683 vs vendor 208,860 → diff 177 within tolerance).
        These are flagged as needing confirmation (Pass 6 confidence).
        """
        pairs: list[MatchPair] = []
        used_vendor_ids: set[UUID] = set()

        # Determine tolerance fraction (tolerance may be percentage < 1 or absolute)
        is_pct = tolerance < Decimal("1")
        tds_frac = tds_percentage / Decimal("100") if tds_percentage > 0 else Decimal("0")
        gst_frac = gst_percentage / Decimal("100") if gst_percentage > 0 else Decimal("0")

        for c_entry in company:
            abs_c = abs(c_entry.amount)
            if abs_c == 0:
                continue

            # Compute the maximum allowed absolute difference for this entry
            allowed = Decimal("0")
            if tolerance > 0:
                allowed = abs_c * tolerance if is_pct else tolerance
            # Also allow up to the larger of TDS/GST portion (some diffs are tax-driven)
            tax_allowed = abs_c * max(tds_frac, gst_frac)
            allowed = max(allowed, tax_allowed)
            # A small floor to absorb rounding (₹5)
            allowed = max(allowed, Decimal("5"))

            best_match: LedgerEntryData | None = None
            best_diff: Decimal | None = None

            for v_entry in vendor:
                if v_entry.id in used_vendor_ids:
                    continue

                diff = abs(abs_c - abs(v_entry.amount))
                if diff > allowed:
                    continue

                # Date proximity check
                if c_entry.posting_date and v_entry.posting_date:
                    try:
                        date_diff = abs((c_entry.posting_date - v_entry.posting_date).days)
                    except (TypeError, AttributeError):
                        date_diff = 0
                else:
                    date_diff = 0
                if date_diff > date_tolerance_days:
                    continue

                if best_diff is None or diff < best_diff:
                    best_diff = diff
                    best_match = v_entry

            if best_match is not None:
                pairs.append(
                    MatchPair(
                        company_entry_id=c_entry.id,
                        vendor_entry_id=best_match.id,
                        confidence_score=CONFIDENCE_SCORES[MatchPassType.TOLERANCE],
                        pass_number=MatchPassType.TOLERANCE,
                        matched_amount=c_entry.amount,
                        difference_amount=c_entry.amount + best_match.amount,
                    )
                )
                used_vendor_ids.add(best_match.id)

        return pairs

    # ──────────────────────────────────────────────────────────────────────
    # Pass 2: Tolerance Match
    # ──────────────────────────────────────────────────────────────────────

    def _tolerance_match(
        self,
        company: list[LedgerEntryData],
        vendor: list[LedgerEntryData],
        tolerance: Decimal,
    ) -> list[MatchPair]:
        """
        Match entries where amount difference is within tolerance
        AND reference numbers match exactly.

        Tolerance can be a percentage (fraction like 0.01 for 1%) applied to
        the company entry amount, or an absolute value if > 1.

        Requirement 5.3: Amount within configured Tolerance_Amount
        and reference numbers match.
        """
        if tolerance <= 0:
            return []

        pairs: list[MatchPair] = []
        used_vendor_ids: set[UUID] = set()

        # Determine if tolerance is percentage-based (< 1) or absolute (>= 1)
        is_percentage = tolerance < Decimal("1")

        # Build reference lookup for vendor entries
        vendor_by_ref: dict[str, list[LedgerEntryData]] = {}
        for v_entry in vendor:
            vendor_by_ref.setdefault(v_entry.reference_number, []).append(v_entry)

        for c_entry in company:
            candidates = vendor_by_ref.get(c_entry.reference_number, [])
            for v_entry in candidates:
                if v_entry.id in used_vendor_ids:
                    continue
                diff = abs(c_entry.amount - v_entry.amount)

                # Calculate allowed tolerance
                if is_percentage:
                    allowed = abs(c_entry.amount) * tolerance
                else:
                    allowed = tolerance

                if diff <= allowed:
                    pairs.append(
                        MatchPair(
                            company_entry_id=c_entry.id,
                            vendor_entry_id=v_entry.id,
                            confidence_score=CONFIDENCE_SCORES[MatchPassType.TOLERANCE],
                            pass_number=MatchPassType.TOLERANCE,
                            matched_amount=c_entry.amount,
                            difference_amount=c_entry.amount - v_entry.amount,
                        )
                    )
                    used_vendor_ids.add(v_entry.id)
                    break

        return pairs

    # ──────────────────────────────────────────────────────────────────────
    # Pass 3: Fuzzy Reference Match
    # ──────────────────────────────────────────────────────────────────────
    # Pass 2.5: TDS/GST Tolerance Match
    # ──────────────────────────────────────────────────────────────────────

    def _tds_gst_match(
        self,
        company: list[LedgerEntryData],
        vendor: list[LedgerEntryData],
        tds_percentage: Decimal,
        gst_percentage: Decimal,
    ) -> list[MatchPair]:
        """
        Match entries where the amount difference equals TDS% or GST% of the base amount.

        Example: Company records ₹100,000, Vendor records ₹90,000.
        If TDS = 10%, then ₹100,000 * 0.10 = ₹10,000 = difference. Match!

        This accounts for:
        - TDS deducted by company (company < vendor by TDS%)
        - GST differences (one side includes/excludes GST)
        """
        pairs: list[MatchPair] = []
        used_vendor_ids: set[UUID] = set()

        tds_fraction = tds_percentage / Decimal("100") if tds_percentage > 0 else Decimal("0")
        gst_fraction = gst_percentage / Decimal("100") if gst_percentage > 0 else Decimal("0")

        for c_entry in company:
            if abs(c_entry.amount) == 0:
                continue
            for v_entry in vendor:
                if v_entry.id in used_vendor_ids:
                    continue

                diff = abs(c_entry.amount - v_entry.amount)
                base_amount = max(abs(c_entry.amount), abs(v_entry.amount))

                matched = False

                # Check if difference = TDS% of the larger amount
                if tds_fraction > 0:
                    expected_tds = abs(base_amount * tds_fraction)
                    # Allow 1% tolerance on the TDS calculation itself
                    if abs(diff - expected_tds) <= expected_tds * Decimal("0.01"):
                        matched = True

                # Check if difference = GST% of the smaller amount
                if not matched and gst_fraction > 0:
                    smaller = min(abs(c_entry.amount), abs(v_entry.amount))
                    expected_gst = abs(smaller * gst_fraction)
                    if abs(diff - expected_gst) <= expected_gst * Decimal("0.01"):
                        matched = True

                if matched:
                    # Also verify references have some similarity (>50%)
                    ref_sim = self._reference_similarity(
                        c_entry.reference_number, v_entry.reference_number
                    )
                    if ref_sim >= 0.5 or c_entry.reference_number == v_entry.reference_number:
                        pairs.append(
                            MatchPair(
                                company_entry_id=c_entry.id,
                                vendor_entry_id=v_entry.id,
                                confidence_score=CONFIDENCE_SCORES[MatchPassType.TOLERANCE],
                                pass_number=MatchPassType.TOLERANCE,
                                matched_amount=c_entry.amount,
                                difference_amount=c_entry.amount - v_entry.amount,
                            )
                        )
                        used_vendor_ids.add(v_entry.id)
                        break

        return pairs

    # ──────────────────────────────────────────────────────────────────────
    # Pass 3: Fuzzy Reference Match
    # ──────────────────────────────────────────────────────────────────────

    def _fuzzy_reference_match(
        self,
        company: list[LedgerEntryData],
        vendor: list[LedgerEntryData],
        threshold: float = 0.8,
    ) -> list[MatchPair]:
        """
        Match entries where amounts are equal but reference numbers have
        a similarity score above the threshold (default 80%).

        Requirement 5.4: Uses difflib.SequenceMatcher for similarity.
        """
        pairs: list[MatchPair] = []
        used_vendor_ids: set[UUID] = set()

        # Build lookup for vendor entries by amount for efficient filtering
        vendor_by_amount: dict[Decimal, list[LedgerEntryData]] = {}
        for v_entry in vendor:
            vendor_by_amount.setdefault(v_entry.amount, []).append(v_entry)

        for c_entry in company:
            candidates = vendor_by_amount.get(c_entry.amount, [])
            best_match: LedgerEntryData | None = None
            best_score: float = 0.0

            for v_entry in candidates:
                if v_entry.id in used_vendor_ids:
                    continue
                similarity = self._reference_similarity(
                    c_entry.reference_number, v_entry.reference_number
                )
                if similarity > threshold and similarity > best_score:
                    best_score = similarity
                    best_match = v_entry

            if best_match is not None:
                # BRD: Pass 3 confidence = 0.70 (normalized from MatchScore 70)
                pairs.append(
                    MatchPair(
                        company_entry_id=c_entry.id,
                        vendor_entry_id=best_match.id,
                        confidence_score=CONFIDENCE_SCORES[MatchPassType.FUZZY_REFERENCE],
                        pass_number=MatchPassType.FUZZY_REFERENCE,
                        matched_amount=c_entry.amount,
                        difference_amount=Decimal("0"),
                    )
                )
                used_vendor_ids.add(best_match.id)

        return pairs

    # ──────────────────────────────────────────────────────────────────────
    # Pass 4: One-to-Many Match
    # ──────────────────────────────────────────────────────────────────────

    def _one_to_many_match(
        self,
        company: list[LedgerEntryData],
        vendor: list[LedgerEntryData],
    ) -> list[MatchGroup]:
        """
        Identify cases where one company entry matches the sum of
        multiple vendor entries.

        Requirement 5.5: One company entry = sum of multiple vendor entries.
        Uses a subset-sum approach limited to reasonable combinations.
        """
        groups: list[MatchGroup] = []
        used_vendor_ids: set[UUID] = set()

        # Sort company entries by absolute amount descending (larger amounts more
        # likely to be sums of multiple smaller vendor entries)
        sorted_company = sorted(company, key=lambda e: abs(e.amount), reverse=True)

        for c_entry in sorted_company:
            available_vendor = [
                v for v in vendor if v.id not in used_vendor_ids
            ]
            if len(available_vendor) < 2:
                continue

            # Find subset of vendor entries whose absolute amounts sum to company amount
            matching_subset = self._find_subset_sum(
                available_vendor, c_entry.amount
            )

            if matching_subset and len(matching_subset) >= 2:
                vendor_ids = [v.id for v in matching_subset]
                total_amount = sum(abs(v.amount) for v in matching_subset)
                groups.append(
                    MatchGroup(
                        company_entry_ids=[c_entry.id],
                        vendor_entry_ids=vendor_ids,
                        confidence_score=CONFIDENCE_SCORES[MatchPassType.ONE_TO_MANY],
                        pass_number=MatchPassType.ONE_TO_MANY,
                        matched_amount=abs(c_entry.amount),
                        difference_amount=abs(c_entry.amount) - total_amount,
                    )
                )
                for vid in vendor_ids:
                    used_vendor_ids.add(vid)

        return groups

    # ──────────────────────────────────────────────────────────────────────
    # Pass 5: Many-to-One Match
    # ──────────────────────────────────────────────────────────────────────

    def _many_to_one_match(
        self,
        company: list[LedgerEntryData],
        vendor: list[LedgerEntryData],
    ) -> list[MatchGroup]:
        """
        Identify cases where multiple company entries sum to one vendor entry.

        Requirement 5.6: Multiple company entries sum = one vendor entry.
        """
        groups: list[MatchGroup] = []
        used_company_ids: set[UUID] = set()

        # Sort vendor entries by absolute amount descending
        sorted_vendor = sorted(vendor, key=lambda e: abs(e.amount), reverse=True)

        for v_entry in sorted_vendor:
            available_company = [
                c for c in company if c.id not in used_company_ids
            ]
            if len(available_company) < 2:
                continue

            # Find subset of company entries whose absolute amounts sum to vendor amount
            matching_subset = self._find_subset_sum(
                available_company, v_entry.amount
            )

            if matching_subset and len(matching_subset) >= 2:
                company_ids = [c.id for c in matching_subset]
                total_amount = sum(abs(c.amount) for c in matching_subset)
                groups.append(
                    MatchGroup(
                        company_entry_ids=company_ids,
                        vendor_entry_ids=[v_entry.id],
                        confidence_score=CONFIDENCE_SCORES[MatchPassType.MANY_TO_ONE],
                        pass_number=MatchPassType.MANY_TO_ONE,
                        matched_amount=abs(v_entry.amount),
                        difference_amount=total_amount - abs(v_entry.amount),
                    )
                )
                for cid in company_ids:
                    used_company_ids.add(cid)

        return groups

    # ──────────────────────────────────────────────────────────────────────
    # Pass 6: Date-proximity Match
    # ──────────────────────────────────────────────────────────────────────

    def _date_proximity_match(
        self,
        company: list[LedgerEntryData],
        vendor: list[LedgerEntryData],
        date_tolerance_days: int = 3,
    ) -> list[MatchPair]:
        """
        Match entries where amounts are equal (by absolute value) and
        posting dates are within a configurable number of days.

        Requirement 17.1: Pass 6 matches by amount + date within N days.
        This handles cases where the amount matches exactly but the reference
        doesn't match — common when bank value dates differ from SAP posting dates.

        Default date tolerance: ±3 days (configurable).
        Confidence score: 0.70 for date-proximity matches.
        """
        if date_tolerance_days < 0:
            return []

        pairs: list[MatchPair] = []
        used_vendor_ids: set[UUID] = set()

        # Build lookup for vendor entries by absolute amount for efficient filtering
        vendor_by_abs_amount: dict[Decimal, list[LedgerEntryData]] = {}
        for v_entry in vendor:
            abs_amount = abs(v_entry.amount)
            vendor_by_abs_amount.setdefault(abs_amount, []).append(v_entry)

        for c_entry in company:
            abs_company_amount = abs(c_entry.amount)
            candidates = vendor_by_abs_amount.get(abs_company_amount, [])

            best_match: LedgerEntryData | None = None
            best_date_diff: int | None = None

            for v_entry in candidates:
                if v_entry.id in used_vendor_ids:
                    continue

                # Calculate date difference in days
                if c_entry.posting_date is None or v_entry.posting_date is None:
                    continue

                date_diff = abs(
                    (c_entry.posting_date - v_entry.posting_date).days
                )

                if date_diff <= date_tolerance_days:
                    # Pick the closest date match
                    if best_date_diff is None or date_diff < best_date_diff:
                        best_date_diff = date_diff
                        best_match = v_entry

            if best_match is not None:
                pairs.append(
                    MatchPair(
                        company_entry_id=c_entry.id,
                        vendor_entry_id=best_match.id,
                        confidence_score=0.70,
                        pass_number=MatchPassType.DATE_PROXIMITY,
                        matched_amount=c_entry.amount,
                        difference_amount=Decimal("0"),
                    )
                )
                used_vendor_ids.add(best_match.id)

        return pairs

    # ──────────────────────────────────────────────────────────────────────
    # Pass 6: Date-proximity Match
    # ──────────────────────────────────────────────────────────────────────

    def _date_proximity_match(
        self,
        company: list[LedgerEntryData],
        vendor: list[LedgerEntryData],
        date_tolerance_days: int = 3,
    ) -> list[MatchPair]:
        """
        Match entries where amounts are equal and posting dates are within
        N days of each other (configurable via date_tolerance_days).

        Requirement 17.1: Match by amount + date within configurable N days.
        BRD confidence = 0.70 (normalized from MatchScore 70).
        """
        pairs: list[MatchPair] = []
        used_vendor_ids: set[UUID] = set()

        # Build lookup for vendor entries by amount for efficient filtering
        vendor_by_amount: dict[Decimal, list[LedgerEntryData]] = {}
        for v_entry in vendor:
            vendor_by_amount.setdefault(v_entry.amount, []).append(v_entry)

        for c_entry in company:
            candidates = vendor_by_amount.get(c_entry.amount, [])
            best_match: LedgerEntryData | None = None
            best_date_diff: int | None = None

            for v_entry in candidates:
                if v_entry.id in used_vendor_ids:
                    continue
                # Calculate date difference in days
                if c_entry.posting_date is None or v_entry.posting_date is None:
                    continue
                date_diff = abs((c_entry.posting_date - v_entry.posting_date).days)
                if date_diff <= date_tolerance_days:
                    # Pick the closest date match
                    if best_date_diff is None or date_diff < best_date_diff:
                        best_date_diff = date_diff
                        best_match = v_entry

            if best_match is not None:
                pairs.append(
                    MatchPair(
                        company_entry_id=c_entry.id,
                        vendor_entry_id=best_match.id,
                        confidence_score=CONFIDENCE_SCORES[MatchPassType.DATE_PROXIMITY],
                        pass_number=MatchPassType.DATE_PROXIMITY,
                        matched_amount=c_entry.amount,
                        difference_amount=Decimal("0"),
                    )
                )
                used_vendor_ids.add(best_match.id)

        return pairs

    # ──────────────────────────────────────────────────────────────────────
    # Subset Sum Helper
    # ──────────────────────────────────────────────────────────────────────

    def _find_subset_sum(
        self,
        entries: list[LedgerEntryData],
        target: Decimal,
        max_subset_size: int = 5,
        tolerance: Decimal = Decimal("0.01"),
    ) -> list[LedgerEntryData] | None:
        """
        Find a subset of entries whose ABSOLUTE amounts sum to the absolute target.

        Sign-aware: company records payments as positive while vendor records
        receipts as negative (and vice-versa). Matching is done on absolute
        values so that e.g. company payments (+73,750 + +641,625) match a
        vendor receipt (-715,375).

        A small tolerance absorbs rounding differences.
        Limits search to combinations of up to max_subset_size entries.
        """
        from itertools import combinations

        abs_target = abs(target)
        if abs_target == 0:
            return None

        # Use absolute values; only consider entries not larger than the target
        candidates = [
            e for e in entries if Decimal("0") < abs(e.amount) <= abs_target + tolerance
        ]

        # Performance cap: keep the largest candidates
        max_candidates = min(len(candidates), 20)
        candidates = sorted(
            candidates, key=lambda e: abs(e.amount), reverse=True
        )[:max_candidates]

        for size in range(2, min(max_subset_size + 1, len(candidates) + 1)):
            for combo in combinations(candidates, size):
                total = sum(abs(e.amount) for e in combo)
                if abs(total - abs_target) <= tolerance:
                    return list(combo)

        return None

    # ──────────────────────────────────────────────────────────────────────
    # Reference Similarity
    # ──────────────────────────────────────────────────────────────────────

    @staticmethod
    def _reference_similarity(ref1: str, ref2: str) -> float:
        """
        Calculate string similarity between two reference numbers
        using difflib.SequenceMatcher.

        Returns a float between 0.0 and 1.0.
        """
        if not ref1 or not ref2:
            return 0.0
        return difflib.SequenceMatcher(None, ref1, ref2).ratio()

    # ──────────────────────────────────────────────────────────────────────
    # Statistics Calculation
    # ──────────────────────────────────────────────────────────────────────

    def _calculate_statistics(
        self,
        result: ReconciliationResult,
        company_entries: list[LedgerEntryData],
        vendor_entries: list[LedgerEntryData],
    ) -> MatchStatistics:
        """
        Calculate match statistics per pass.

        Requirement 5.12: Store match count, matched amount, and
        percentage of total entries matched per pass.
        """
        total_entries = len(company_entries) + len(vendor_entries)
        stats = MatchStatistics(
            total_company_entries=len(company_entries),
            total_vendor_entries=len(vendor_entries),
            total_matched_company=result.statistics.total_matched_company,
            total_matched_vendor=result.statistics.total_matched_vendor,
        )

        # Aggregate per pass
        pass_data: dict[int, PassStatistics] = {}
        for pass_num in range(1, 8):
            pass_data[pass_num] = PassStatistics(pass_number=pass_num)

        # Count from pairs (passes 1, 2, 3, 6; plus reversal pass 9)
        for pair in result.match_pairs:
            ps = pass_data.get(pair.pass_number)
            if ps is None:
                # Non-standard pass (e.g. reversal=9): track it dynamically.
                ps = PassStatistics(pass_number=pair.pass_number)
                pass_data[pair.pass_number] = ps
            ps.match_count += 1
            ps.matched_amount += pair.matched_amount

        # Count from groups (passes 4, 5)
        for group in result.match_groups:
            ps = pass_data[group.pass_number]
            ps.match_count += 1
            ps.matched_amount += group.matched_amount

        # Pass 7: unmatched count
        pass_data[MatchPassType.UNMATCHED].match_count = (
            len(result.unmatched_company_ids) + len(result.unmatched_vendor_ids)
        )

        # Calculate percentages
        for ps in pass_data.values():
            if total_entries > 0:
                # Entries involved: for pairs = 2 per match, for groups = n entries
                entries_involved = 0
                if ps.pass_number in (1, 2, 3, 6):
                    entries_involved = ps.match_count * 2
                elif ps.pass_number == 4:
                    for g in result.match_groups:
                        if g.pass_number == 4:
                            entries_involved += (
                                len(g.company_entry_ids) + len(g.vendor_entry_ids)
                            )
                elif ps.pass_number == 5:
                    for g in result.match_groups:
                        if g.pass_number == 5:
                            entries_involved += (
                                len(g.company_entry_ids) + len(g.vendor_entry_ids)
                            )
                elif ps.pass_number == 7:
                    entries_involved = ps.match_count

                ps.percentage = round(
                    (entries_involved / total_entries) * 100, 2
                ) if total_entries > 0 else 0.0

        stats.pass_statistics = list(pass_data.values())
        return stats

    # ──────────────────────────────────────────────────────────────────────
    # Clear Previous Results
    # ──────────────────────────────────────────────────────────────────────

    async def clear_previous_results(self, case_id: UUID) -> None:
        """
        Clear all previous match results and exceptions for a case.

        Requirement 5.13: Clear previous match results before
        re-reconciliation.
        """
        await self._match_repo.delete_by_case(case_id)
        await self._exception_repo.delete_by_case(case_id)
        await self._ledger_repo.clear_match_data_by_case(case_id)

    # ──────────────────────────────────────────────────────────────────────
    # Get Match Statistics
    # ──────────────────────────────────────────────────────────────────────

    async def get_match_statistics(self, case_id: UUID) -> dict:
        """
        Retrieve stored match statistics for a case.

        Requirement 5.12: Match statistics per pass.
        """
        return await self._match_repo.get_statistics_by_case(case_id)

    # ──────────────────────────────────────────────────────────────────────
    # Persistence
    # ──────────────────────────────────────────────────────────────────────

    async def _persist_results(
        self,
        case_id: UUID,
        result: ReconciliationResult,
        company_entries: list["LedgerEntryData"] | None = None,
        vendor_entries: list["LedgerEntryData"] | None = None,
    ) -> None:
        """Persist match results and update ledger entries with match metadata."""
        # Persist match pairs (passes 1, 2, 3, 6)
        for pair in result.match_pairs:
            match_id = uuid4()
            is_reversal = pair.pass_number == REVERSAL_PASS
            # BRD: Auto-Accept for Pass 1 (Exact) and Pass 2 (Tolerance).
            # Reversals net to zero within the company ledger, so auto-accept them.
            is_auto_accepted = is_reversal or pair.pass_number in (
                MatchPassType.EXACT, MatchPassType.TOLERANCE
            )
            # For reversal pairs BOTH entries are company-side; record them both
            # under company_entry_ids (no vendor counterpart).
            if is_reversal:
                company_ids = [str(pair.company_entry_id), str(pair.vendor_entry_id)]
                vendor_ids: list[str] = []
            else:
                company_ids = [str(pair.company_entry_id)]
                vendor_ids = [str(pair.vendor_entry_id)]
            match_data = {
                "id": match_id,
                "case_id": case_id,
                "pass_number": pair.pass_number,
                "match_type": "reversal" if is_reversal else "pair",
                "confidence_score": pair.confidence_score,
                "is_confirmed": is_auto_accepted,
                "company_entry_ids": company_ids,
                "vendor_entry_ids": vendor_ids,
                "matched_amount": float(pair.matched_amount),
                "difference_amount": float(pair.difference_amount),
            }
            await self._match_repo.create(match_data)

            # Update ledger entries with match metadata (both IDs regardless of side)
            await self._ledger_repo.bulk_update_match(
                entry_ids=[pair.company_entry_id, pair.vendor_entry_id],
                match_id=match_id,
                pass_number=pair.pass_number,
                confidence_score=pair.confidence_score,
            )

        # Persist match groups (passes 4, 5)
        for group in result.match_groups:
            match_id = uuid4()
            match_data = {
                "id": match_id,
                "case_id": case_id,
                "pass_number": group.pass_number,
                "match_type": "group",
                "confidence_score": group.confidence_score,
                "is_confirmed": False,  # Groups need confirmation (Req 5.11)
                "company_entry_ids": [str(cid) for cid in group.company_entry_ids],
                "vendor_entry_ids": [str(vid) for vid in group.vendor_entry_ids],
                "matched_amount": float(group.matched_amount),
                "difference_amount": float(group.difference_amount),
            }
            await self._match_repo.create(match_data)

            # Update all entries in the group
            all_entry_ids = group.company_entry_ids + group.vendor_entry_ids
            await self._ledger_repo.bulk_update_match(
                entry_ids=all_entry_ids,
                match_id=match_id,
                pass_number=group.pass_number,
                confidence_score=group.confidence_score,
            )

        # Persist unmatched entries as exceptions (Pass 7)
        all_unmatched = result.unmatched_company_ids + result.unmatched_vendor_ids
        if all_unmatched:
            # Build amount lookup from entries
            amount_lookup: dict[UUID, Decimal] = {}
            if company_entries:
                for e in company_entries:
                    amount_lookup[e.id] = e.amount
            if vendor_entries:
                for e in vendor_entries:
                    amount_lookup[e.id] = e.amount

            today = date.today()
            exceptions_data = []
            for entry_id in all_unmatched:
                exceptions_data.append({
                    "case_id": case_id,
                    "ledger_entry_id": entry_id,
                    "category": "unmatched",
                    "severity": "medium",  # Default; categorization happens later
                    "amount": float(amount_lookup.get(entry_id, Decimal("0"))),
                    "first_flagged_date": today,
                    "status": "open",
                })
            await self._exception_repo.bulk_create(exceptions_data)

        # Update case with match statistics
        stats_dict = {
            "total_company_entries": result.statistics.total_company_entries,
            "total_vendor_entries": result.statistics.total_vendor_entries,
            "total_matched_company": result.statistics.total_matched_company,
            "total_matched_vendor": result.statistics.total_matched_vendor,
            "pass_statistics": [
                {
                    "pass_number": ps.pass_number,
                    "match_count": ps.match_count,
                    "matched_amount": float(ps.matched_amount),
                    "percentage": ps.percentage,
                }
                for ps in result.statistics.pass_statistics
            ],
        }
        await self._case_repo.update(case_id, {"match_statistics": stats_dict})

    # ──────────────────────────────────────────────────────────────────────
    # Data Conversion Helpers
    # ──────────────────────────────────────────────────────────────────────

    @staticmethod
    def _to_entry_data_list(entries: list[object]) -> list[LedgerEntryData]:
        """Convert raw repository objects to LedgerEntryData for matching."""
        result: list[LedgerEntryData] = []
        for entry in entries:
            result.append(
                LedgerEntryData(
                    id=getattr(entry, "id"),
                    amount=Decimal(str(getattr(entry, "amount", 0))),
                    posting_date=getattr(entry, "posting_date", None),
                    reference_number=getattr(entry, "reference_number", "") or "",
                    document_number=getattr(entry, "document_number", "") or "",
                    side=getattr(entry, "side", ""),
                    document_type=(getattr(entry, "document_type", "") or ""),
                )
            )
        return result
