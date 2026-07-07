"""
Multi-Pass Reconciliation Engine Domain Service.

Implements the 6-pass matching algorithm for reconciling company and vendor
ledger entries. Enforces no-double-match invariant, calculates match statistics,
and supports re-reconciliation by clearing previous results.

Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 5.8, 5.9, 5.10, 5.11, 5.12, 5.13
"""

import difflib
from dataclasses import dataclass, field
from decimal import Decimal
from enum import IntEnum
from uuid import UUID, uuid4

from src.domain.repositories.vlr.case_repository import ICaseRepository
from src.domain.repositories.vlr.exception_repository import IExceptionRepository
from src.domain.repositories.vlr.ledger_entry_repository import ILedgerEntryRepository
from src.domain.repositories.vlr.match_result_repository import IMatchResultRepository


class MatchPassType(IntEnum):
    """Matching pass types executed in sequence."""

    EXACT = 1
    TOLERANCE = 2
    FUZZY_REFERENCE = 3
    ONE_TO_MANY = 4
    MANY_TO_ONE = 5
    UNMATCHED = 6


@dataclass
class LedgerEntryData:
    """Lightweight representation of a ledger entry for matching logic."""

    id: UUID
    amount: Decimal
    posting_date: object  # date
    reference_number: str
    document_number: str = ""
    side: str = ""


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
    Domain service implementing the 6-pass reconciliation matching algorithm.

    Pass 1: Exact Match - amount + date + reference_number identical (confidence=1.0)
    Pass 2: Tolerance Match - amount within tolerance AND reference numbers match
    Pass 3: Fuzzy Reference Match - amounts equal, reference similarity > 0.8
    Pass 4: One-to-Many - one company entry = sum of multiple vendor entries
    Pass 5: Many-to-One - multiple company entries sum to one vendor entry
    Pass 6: Unmatched - mark remaining entries as unmatched exceptions

    Invariant: No entry is matched more than once across all passes.
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
    ) -> ReconciliationResult:
        """
        Execute the full 6-pass reconciliation engine for a case.

        Requirement 5.1: Execute passes in sequence.
        Requirement 5.8: Complete within 120 seconds for 5,000 entries per side.
        Requirement 5.10: No entry matched more than once.
        Requirement 5.13: Clear previous results before re-reconciliation.
        """
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

        # ─── Pass 6: Mark Unmatched ───────────────────────────────────────
        result.unmatched_company_ids = [
            e.id for e in company_entries if e.id not in matched_company_ids
        ]
        result.unmatched_vendor_ids = [
            e.id for e in vendor_entries if e.id not in matched_vendor_ids
        ]

        # Determine if confirmation is needed (fuzzy/combination matches)
        result.needs_confirmation = len(fuzzy_pairs) > 0 or (
            len(one_to_many_groups) > 0 or len(many_to_one_groups) > 0
        )

        # Calculate statistics (Requirement 5.12)
        result.statistics.total_matched_company = len(matched_company_ids)
        result.statistics.total_matched_vendor = len(matched_vendor_ids)
        result.statistics = self._calculate_statistics(
            result, company_entries, vendor_entries
        )

        # Persist results
        await self._persist_results(case_id, result)

        return result

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

        Requirement 5.3: Amount within configured Tolerance_Amount
        and reference numbers match.
        """
        if tolerance <= 0:
            return []

        pairs: list[MatchPair] = []
        used_vendor_ids: set[UUID] = set()

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
                if diff <= tolerance:
                    confidence = float(
                        Decimal("1") - (diff / tolerance) if tolerance > 0 else Decimal("1")
                    )
                    pairs.append(
                        MatchPair(
                            company_entry_id=c_entry.id,
                            vendor_entry_id=v_entry.id,
                            confidence_score=round(confidence, 4),
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
                pairs.append(
                    MatchPair(
                        company_entry_id=c_entry.id,
                        vendor_entry_id=best_match.id,
                        confidence_score=round(best_score, 4),
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

        # Sort company entries by amount descending (larger amounts more likely
        # to be sums of multiple smaller vendor entries)
        sorted_company = sorted(company, key=lambda e: e.amount, reverse=True)

        for c_entry in sorted_company:
            available_vendor = [
                v for v in vendor if v.id not in used_vendor_ids
            ]
            if len(available_vendor) < 2:
                continue

            # Find subset of vendor entries that sum to company amount
            matching_subset = self._find_subset_sum(
                available_vendor, c_entry.amount
            )

            if matching_subset and len(matching_subset) >= 2:
                vendor_ids = [v.id for v in matching_subset]
                total_amount = sum(v.amount for v in matching_subset)
                groups.append(
                    MatchGroup(
                        company_entry_ids=[c_entry.id],
                        vendor_entry_ids=vendor_ids,
                        confidence_score=0.85,
                        pass_number=MatchPassType.ONE_TO_MANY,
                        matched_amount=c_entry.amount,
                        difference_amount=c_entry.amount - total_amount,
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

        # Sort vendor entries by amount descending
        sorted_vendor = sorted(vendor, key=lambda e: e.amount, reverse=True)

        for v_entry in sorted_vendor:
            available_company = [
                c for c in company if c.id not in used_company_ids
            ]
            if len(available_company) < 2:
                continue

            # Find subset of company entries that sum to vendor amount
            matching_subset = self._find_subset_sum(
                available_company, v_entry.amount
            )

            if matching_subset and len(matching_subset) >= 2:
                company_ids = [c.id for c in matching_subset]
                total_amount = sum(c.amount for c in matching_subset)
                groups.append(
                    MatchGroup(
                        company_entry_ids=company_ids,
                        vendor_entry_ids=[v_entry.id],
                        confidence_score=0.85,
                        pass_number=MatchPassType.MANY_TO_ONE,
                        matched_amount=v_entry.amount,
                        difference_amount=total_amount - v_entry.amount,
                    )
                )
                for cid in company_ids:
                    used_company_ids.add(cid)

        return groups

    # ──────────────────────────────────────────────────────────────────────
    # Subset Sum Helper
    # ──────────────────────────────────────────────────────────────────────

    def _find_subset_sum(
        self,
        entries: list[LedgerEntryData],
        target: Decimal,
        max_subset_size: int = 5,
    ) -> list[LedgerEntryData] | None:
        """
        Find a subset of entries whose amounts sum to the target.
        Limits search to combinations of up to max_subset_size entries
        for performance (Requirement 5.8).

        Returns the matching subset or None if not found.
        """
        from itertools import combinations

        # Limit to entries with amounts that could plausibly sum to target
        # (positive amounts less than or equal to target)
        candidates = [e for e in entries if Decimal("0") < e.amount <= target]

        # Try combinations of increasing size (2 to max_subset_size)
        max_candidates = min(len(candidates), 20)  # Performance cap
        candidates = sorted(
            candidates, key=lambda e: e.amount, reverse=True
        )[:max_candidates]

        for size in range(2, min(max_subset_size + 1, len(candidates) + 1)):
            for combo in combinations(candidates, size):
                total = sum(e.amount for e in combo)
                if total == target:
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
        for pass_num in range(1, 7):
            pass_data[pass_num] = PassStatistics(pass_number=pass_num)

        # Count from pairs (passes 1, 2, 3)
        for pair in result.match_pairs:
            ps = pass_data[pair.pass_number]
            ps.match_count += 1
            ps.matched_amount += pair.matched_amount

        # Count from groups (passes 4, 5)
        for group in result.match_groups:
            ps = pass_data[group.pass_number]
            ps.match_count += 1
            ps.matched_amount += group.matched_amount

        # Pass 6: unmatched count
        pass_data[MatchPassType.UNMATCHED].match_count = (
            len(result.unmatched_company_ids) + len(result.unmatched_vendor_ids)
        )

        # Calculate percentages
        for ps in pass_data.values():
            if total_entries > 0:
                # Entries involved: for pairs = 2 per match, for groups = n entries
                entries_involved = 0
                if ps.pass_number in (1, 2, 3):
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
                elif ps.pass_number == 6:
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
        self, case_id: UUID, result: ReconciliationResult
    ) -> None:
        """Persist match results and update ledger entries with match metadata."""
        # Persist match pairs (passes 1, 2, 3)
        for pair in result.match_pairs:
            match_id = uuid4()
            match_data = {
                "id": match_id,
                "case_id": case_id,
                "pass_number": pair.pass_number,
                "match_type": "pair",
                "confidence_score": pair.confidence_score,
                "is_confirmed": pair.pass_number == MatchPassType.EXACT,
                "company_entry_ids": [str(pair.company_entry_id)],
                "vendor_entry_ids": [str(pair.vendor_entry_id)],
                "matched_amount": float(pair.matched_amount),
                "difference_amount": float(pair.difference_amount),
            }
            await self._match_repo.create(match_data)

            # Update ledger entries with match metadata
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

        # Persist unmatched entries as exceptions (Pass 6)
        all_unmatched = result.unmatched_company_ids + result.unmatched_vendor_ids
        if all_unmatched:
            exceptions_data = []
            for entry_id in all_unmatched:
                exceptions_data.append({
                    "case_id": case_id,
                    "ledger_entry_id": entry_id,
                    "category": "unmatched",
                    "severity": "medium",  # Default; categorization happens later
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
                )
            )
        return result
