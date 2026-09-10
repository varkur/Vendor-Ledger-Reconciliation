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
import re
import time
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from enum import IntEnum
from uuid import UUID, uuid4


def _is_tax_band_gap(
    diff: Decimal,
    c_amt: Decimal,
    v_amt: Decimal,
    tds_min_frac: Decimal,
    tds_max_frac: Decimal,
    gst_frac: Decimal,
    band_pct: Decimal = Decimal("0.01"),
) -> bool:
    """
    True if `diff` corresponds to a tax rate that falls within the
    configured TDS range [tds_min_frac, tds_max_frac] (inclusive, with a
    tiny +/-1% margin on the boundary to absorb paise-level rounding), OR
    matches the single configured GST rate (also within a tight +/-1%
    band). This is a RANGE check for TDS, not "does it match one exact
    number" — the mapping doc calls out multiple real-world TDS tiers
    (e.g. 0.1%, 2%, 10%), and the Reconciliation Settings screen has
    always presented TDS as a Min/Max range for exactly this reason. A
    flat single-rate check meant a real TDS-driven gap at any tier other
    than whichever one number the user happened to type into "Max" could
    never be recognized as tax and would fall through to an unexplained
    gap.

    Still NOT "any gap smaller than the largest possible tax amount" —
    the older ceiling-based bug this replaced would auto-match arbitrary
    unrelated amount mismatches as long as they happened to be under the
    ceiling. Every candidate rate in the range must actually explain the
    observed gap within a tight band, not merely be larger than it.

    TDS and GST are computed off DIFFERENT base amounts, mirroring
    `_tds_gst_match`'s own logic: TDS is withheld FROM the larger
    (pre-deduction) amount, so its base is max(c_amt, v_amt); GST is
    added ON TOP OF the smaller (pre-tax) amount, so its base is
    min(c_amt, v_amt). Using a single shared `base_amount` (as an
    earlier version of this function did) silently broke every
    configured-GST gap check, since `base_amount * gst_frac` computed
    off the LARGER amount never matches the actual GST added to the
    smaller one.
    """
    if diff <= 0 or c_amt <= 0 or v_amt <= 0:
        return False

    tds_base = max(c_amt, v_amt)
    implied_rate = diff / tds_base  # e.g. 0.02 for a 2% gap

    # TDS range check: does the gap's implied rate fall within
    # [tds_min_frac, tds_max_frac] (with rounding margin on each edge)?
    if tds_max_frac > 0:
        lo = min(tds_min_frac, tds_max_frac)
        hi = max(tds_min_frac, tds_max_frac)
        margin = max(hi * band_pct, Decimal("0.0001"))
        if (lo - margin) <= implied_rate <= (hi + margin):
            return True

    # GST is still a single configured rate, not a range — tight +/-1% band
    # around the exact computed amount (base = the SMALLER/pre-tax amount).
    if gst_frac > 0:
        gst_base = min(c_amt, v_amt)
        expected_gst = gst_base * gst_frac
        if expected_gst > 0 and abs(diff - expected_gst) <= expected_gst * band_pct:
            return True

    return False

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
    # Sub-passes kept outside the 1-7 BRD numbering but given their own
    # identity (previously these mis-reported themselves as EXACT/TOLERANCE,
    # which hid from users that the invoice/reference number was never
    # compared — see AMOUNT_DATE below).
    AMOUNT_DATE = 10
    TDS_GST = 11
    TOLERANCE_DATE = 12
    # Same invoice number AND same date on both sides, but the amount gap
    # is NOT explained by the configured TDS/GST rate (see
    # _amount_mismatch_match). Per explicit correction: these must still be
    # matched (not left as two separate open items) so the reviewer sees
    # them as one linked pair with a genuine, reviewable discrepancy —
    # labelled "Amount Mismatch", the one case where the engine itself
    # emits that classification (see reconciliation_export_service.py).
    AMOUNT_MISMATCH = 15


# BRD Section 5.6.10 - Matching Priority Rules confidence scores (normalized to 0.0-1.0)
# Pass 1 (Exact): 100 → 1.0, Auto-Accept = Yes
# Pass 2 (Tolerance): 85 → 0.85, Auto-Accept = Yes
# Pass 3 (Fuzzy Reference): 70 → 0.70, Auto-Accept = No
# Pass 4 (One-to-Many): 80 → 0.80, Auto-Accept = No
# Pass 5 (Many-to-One): 75 → 0.75, Auto-Accept = No
# Pass 6 (Date-proximity): 70 → 0.70, Auto-Accept = No
# Pass 7 (Unmatched): 0 → 0.0
# AMOUNT_DATE (1.5): 90 → 0.90, Auto-Accept = Yes (amount exact, no ref check)
# TDS_GST (2.5): 85 → 0.85, Auto-Accept = Yes (ref similarity gate applied)
# TOLERANCE_DATE (6.5): 70 → 0.70, Auto-Accept = No (neither ref nor exact
#                        amount matched — weakest tier, always needs review)
CONFIDENCE_SCORES: dict[int, float] = {
    MatchPassType.EXACT: 1.0,
    MatchPassType.TOLERANCE: 0.85,
    MatchPassType.FUZZY_REFERENCE: 0.70,
    MatchPassType.ONE_TO_MANY: 0.80,
    MatchPassType.MANY_TO_ONE: 0.75,
    MatchPassType.DATE_PROXIMITY: 0.70,
    MatchPassType.UNMATCHED: 0.0,
    MatchPassType.AMOUNT_DATE: 0.90,
    MatchPassType.TDS_GST: 0.85,
    MatchPassType.TOLERANCE_DATE: 0.70,
    14: 0.90,  # TDS_LINK_PASS (constant defined further below in this module)
    # Same invoice number + same date is strong identification evidence,
    # but the gap is unexplained — always needs Finance review, never
    # auto-accepted (see _persist_results).
    MatchPassType.AMOUNT_MISMATCH: 0.60,
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
    assignment_number: str = ""
    category: str = ""
    # The CLEAN-derived invoice number (ZUONR > XBLNR > BELNR fallback, see
    # DataTransformationService). This is where the "-R"/"-RE"/"-Rev"
    # reclass/reversal suffix actually lives on real data — NOT on
    # document_number, which is a plain SAP document number (e.g.
    # "6000009613") with no suffix at all.
    derived_invoice_number: str = ""
    # Best available invoice number for MATCHING purposes: derived_invoice_number
    # when present and not a synthetic "BAL_ROW_*" placeholder, else
    # document_number. Confirmed against real data that `reference_number`
    # on the company (SAP) side is NOT an invoice number at all — it's a
    # generic cost-center/reference code (e.g. "EP22", "EMHC") shared by
    # hundreds of unrelated entries. The invoice-number-aware passes
    # (_exact_match, _tolerance_match, _fuzzy_reference_match) must key off
    # THIS field, not reference_number, or genuine invoice-number matches
    # never fire and everything falls through to weaker amount/date passes.
    invoice_number: str = ""
    # TDS linking (populated by DataTransformationService.tag_tds_entries,
    # persisted on LedgerEntryModel). is_tds marks a standalone TDS ledger
    # line; tds_parent_entry_id points at the (same-side) invoice/reference
    # entry it was derived from, already computed during transformation —
    # the reconciliation engine's _tds_link_match pass below just needs to
    # follow this pointer once the parent has been cross-side matched.
    is_tds: bool = False
    tds_parent_entry_id: UUID | None = None

    def __post_init__(self) -> None:
        # Callers that construct LedgerEntryData directly without knowledge
        # of the derived-invoice-number pipeline (tests, ad-hoc scripts)
        # historically used reference_number as the matchable identifier.
        # Default invoice_number to reference_number in that case so those
        # call sites keep working unchanged. Production code always passes
        # invoice_number explicitly (see _to_entry_data_list), so this
        # default never fires there.
        if not self.invoice_number:
            self.invoice_number = self.reference_number


# ── Document-category matching rules (Vendor Ledger Mapping Rules doc) ────
# Cross-side matching must respect the economic nature of each entry: an
# invoice may only reconcile against an invoice, a payment only against a
# payment, etc. Matching purely on amount/date produced false matches such
# as an invoice knocking off against a vendor payment, or a debit note
# against an unrelated knock-off entry. The ONE explicit cross-category
# exception is Debit Note <-> Credit Note, called out directly in the
# mapping doc — every other category matches only itself.

# Categories that are entry-intrinsic and must NEVER cross-match with the
# other side. Opening/closing balances are summary rows; knock-off (AB) and
# "Other entry" (SA/Adjusted) rows are each side's own internal entries and,
# per the mapping doc, only net against entries of the SAME category on the
# SAME side ("Knocking entries... should be only map with their internal
# entries"; "Other entry... therefore that only map with each other in both
# side").
NON_MATCHABLE_CATEGORIES: frozenset[str] = frozenset(
    {"Opening Balance", "Closing Balance", "Knocking Off"}
)

# Explicit compatibility groups per the mapping doc:
#   Invoice -> Invoice only
#   Debit Note -> Credit Note only (and vice versa) — this is the ONE
#     deliberate cross-category exception, because the mapping doc is
#     explicit and unambiguous: "Emcure debit note (KG) map with the
#     vendor credit note on the basis of Invoice no, date, amount." A
#     debit note and credit note are the SAME adjustment recorded from
#     each side's own perspective (Emcure debits the vendor, the vendor
#     simultaneously credits Emcure for the identical amount) — there is
#     no such thing as a debit note ever appearing on both sides for the
#     same transaction, so same-category matching would never find a
#     pair here at all.
#   Payment -> Payment only, Receipt -> Receipt only — previously this
#     also cross-matched Payment<->Receipt as an assumption (the mapping
#     doc never actually says this; it only describes Emcure's KZ
#     payment matching by date+amount and doesn't name a vendor-side
#     "Receipt" counterpart type at all). Removed per explicit
#     correction: cross-category matching should not occur except where
#     the doc explicitly requires it (Debit Note/Credit Note above).
#   TDS Adjusted -> TDS Adjusted only
#   Journal -> Journal only — "Journal" is a real, user-selected category
#     (assigned via the Map Document Type / Document Types admin screen),
#     NOT a placeholder for un-mapped data. It has no documented
#     cross-category behavior in the mapping doc at all, so treating it as
#     a wildcard let a company Payment (KZ) entry match a vendor Journal
#     (JE) entry purely on date+amount — a real cross-doctype match the
#     business explicitly said should never happen. Confirmed same-side
#     self-only per the "no cross-doctype matching" rule.
# A category not listed here is a wildcard (matches anything) so we never
# block a match we're unsure about — we only block pairings we KNOW are
# economically incompatible.
CATEGORY_COMPATIBILITY: dict[str, frozenset[str]] = {
    "Invoice": frozenset({"Invoice"}),
    "Debit Note": frozenset({"Debit Note", "Credit Note"}),
    "Credit Note": frozenset({"Credit Note", "Debit Note"}),
    "Payment": frozenset({"Payment"}),
    "Receipt": frozenset({"Receipt"}),
    "TDS Adjusted": frozenset({"TDS Adjusted"}),
    "Journal": frozenset({"Journal"}),
}

# "Adjusted" (SA / Other entry) is explicitly excluded from the wildcard set:
# the mapping doc says SA entries only net with each other, never with real
# invoices/payments. Unknown/uncategorized entries stay wildcard until the
# user maps them via the Map Document Type screen.
#
# "Other" is included here because the data-transformation pipeline
# (DataTransformationService.classify_document_type) runs BEFORE
# reconciliation and writes a much narrower hardcoded category set
# (RE/KR/DR->Invoice, ZP/KZ/ZV->Payment, KG->Credit Note, RV->Debit Note) —
# any doc type outside that small set (e.g. MA, MI, most vendor Tally codes)
# gets persisted as document_category="Other" on the entry BEFORE this
# engine ever runs its own _derive_category fallback (_to_entry_data_list
# always prefers a category already saved on the entry). Treating "Other" as
# a real, mutually-exclusive category here caused a severe false-negative
# regression: an Invoice-categorized entry could never match an
# "Other"-categorized entry even though they were the same real invoice,
# collapsing match counts from ~340 to ~18 on a real case. "Other" must be
# wildcard, not a known category, until the user explicitly maps it via the
# Map Document Type screen.
#
# "Journal" is deliberately NOT in this wildcard set (see
# CATEGORY_COMPATIBILITY above) — unlike "Other", it is never auto-assigned
# as a fallback bucket; it only appears when a user explicitly maps a doc
# type to "Journal" via the Document Types screen, or when the raw doc-type
# text itself contains the word "journal" (_derive_category heuristic).
# Either way it is a real, known category and must self-match only.
WILDCARD_CATEGORIES: frozenset[str] = frozenset({"Unknown", "Other", ""})


def _derive_category(document_type: str) -> str:
    """
    Derive a standard document category from a raw document type code.

    Tries the configurable SAP doc-type map first, then falls back to
    keyword heuristics on the raw text (handles Tally-style / descriptive
    doc types that aren't literal SAP codes).
    """
    from src.domain.services.vlr.doc_type_mapping import classify_document_type

    dt = (document_type or "").strip()
    if not dt:
        return ""
    category = classify_document_type(dt)
    if category != "Unknown":
        return category
    lowered = dt.lower()
    if "open" in lowered:
        return "Opening Balance"
    if "clos" in lowered:
        return "Closing Balance"
    if "debit" in lowered:
        return "Debit Note"
    if "credit" in lowered:
        return "Credit Note"
    if "sale" in lowered or "invoice" in lowered:
        return "Invoice"
    if "receipt" in lowered:
        return "Receipt"
    if "payment" in lowered:
        return "Payment"
    if "journal" in lowered:
        return "Journal"
    if "knock" in lowered or "revers" in lowered:
        return "Knocking Off"
    if "tds" in lowered:
        return "TDS Adjusted"
    # Unrecognized raw codes (e.g. Tally-style "RV"/"DZ" on the vendor side
    # that have no SAP-doc-type equivalent) must be treated as a wildcard, NOT
    # as a literal category. Returning the raw code here would make it a
    # "known" category that fails compatibility checks against every side,
    # blocking ALL matches until the user maps it via the Map Document Type
    # screen.
    return "Unknown"


def _best_invoice_number(derived_invoice_number: str, document_number: str) -> str:
    """
    Best invoice number for MATCHING: prefer derived_invoice_number (the
    CLEAN-derived ZUONR/XBLNR/BELNR value), falling back to document_number,
    skipping synthetic "BAL_ROW_*" placeholders inserted by the file parser
    for rows with no recognizable invoice column. Mirrors
    entry_columns.invoice_number()'s fallback so matching and the
    export/UI agree on what "the invoice number" is for a given entry.

    Deliberately does NOT consider reference_number: on real company (SAP)
    data, reference_number is a generic cost-center/reference code (e.g.
    "EP22") shared by hundreds of unrelated entries, never an invoice number.
    """
    for candidate in (derived_invoice_number, document_number):
        candidate = (candidate or "").strip()
        if candidate and not candidate.startswith("BAL_ROW_"):
            return candidate
    return ""


def _is_matchable(entry: "LedgerEntryData") -> bool:
    """True when an entry may participate in cross-side matching."""
    return entry.category not in NON_MATCHABLE_CATEGORIES and entry.category != "Adjusted"


def _categories_compatible(cat_a: str, cat_b: str) -> bool:
    """
    True when two document categories may reconcile against each other.

    - Non-matchable / self-only categories (balances, knock-offs, "Adjusted"
      other-entries) never cross-match.
    - Wildcard categories (unknown/other/blank — un-mapped data only) match
      anything else. "Journal" is a known category, not a wildcard, and
      self-matches only.
    - Otherwise both sides must appear in each other's compatibility set.
    """
    if cat_a in NON_MATCHABLE_CATEGORIES or cat_b in NON_MATCHABLE_CATEGORIES:
        return False
    if cat_a == "Adjusted" or cat_b == "Adjusted":
        return False
    if cat_a in WILDCARD_CATEGORIES or cat_b in WILDCARD_CATEGORIES:
        return True
    allowed_a = CATEGORY_COMPATIBILITY.get(cat_a)
    allowed_b = CATEGORY_COMPATIBILITY.get(cat_b)
    if allowed_a is None and allowed_b is None:
        return True
    if allowed_a is not None and cat_b not in allowed_a:
        return False
    if allowed_b is not None and cat_a not in allowed_b:
        return False
    return True


_REVERSAL_SUFFIX_RE = re.compile(r"-(RE|REV|R)$", re.IGNORECASE)


def _reversal_base_invoice(entry: "LedgerEntryData") -> str:
    """
    Base invoice number with the reclass/reversal suffix stripped, e.g.
    "GJ2501027881-RE" -> "GJ2501027881". Used to require that suffix-based
    reversal pairs share the SAME base invoice before netting them — pairing
    purely on "amount happens to cancel" would risk netting two entries that
    are unrelated other than a coincidental equal-and-opposite amount (e.g.
    a Debit Note and a TDS Adjusted entry that both happen to be 17174.51).
    Returns "" when the entry has no suffixed invoice number at all (e.g.
    AB/Knocking Off entries, which are paired on amount alone per the
    mapping doc — they don't carry an invoice number concept).
    """
    derived = (entry.derived_invoice_number or "").strip()
    doc_no = (entry.document_number or "").strip()
    ref_no = (entry.reference_number or "").strip()
    for candidate in (derived, doc_no, ref_no):
        if candidate and _REVERSAL_SUFFIX_RE.search(candidate):
            return _REVERSAL_SUFFIX_RE.sub("", candidate).strip().upper()
    return ""


def _is_reversal(entry: "LedgerEntryData") -> bool:
    """True when an entry is a knock-off / reversal entry (nets within a side)."""
    if entry.category == "Knocking Off":
        return True
    if (entry.document_type or "").strip().upper() == "AB":
        return True
    # Company-side reclass/reversal convention confirmed against real DB
    # data: Emcure reposts an invoice under the SAME base invoice number with
    # a "-R", "-RE", or "-Rev" suffix and the opposite sign (e.g.
    # "GJ2501027881-R" = -16755.62 paired with "GJ2501027881-RE" = +16755.62).
    # Critically, this suffix lives on `derived_invoice_number` (the
    # CLEAN-derived value from ZUONR/XBLNR/BELNR fallback) — NOT on
    # `document_number`, which is a plain SAP document number with no
    # suffix (e.g. "6000009613"). Checking document_number/reference_number
    # here never matches real data; it only ever matched hand-built test
    # fixtures. The original, un-suffixed invoice keeps its normal Invoice
    # category and still matches cross-side as usual. An unpaired suffixed
    # entry (no opposite-sign counterpart at the same amount) simply falls
    # through to normal matching, same as any other unmatched reversal
    # candidate.
    derived = (entry.derived_invoice_number or "").strip()
    doc_no = (entry.document_number or "").strip()
    ref_no = (entry.reference_number or "").strip()
    if (
        _REVERSAL_SUFFIX_RE.search(derived)
        or _REVERSAL_SUFFIX_RE.search(doc_no)
        or _REVERSAL_SUFFIX_RE.search(ref_no)
    ):
        return True
    return False


def _is_other_entry(entry: "LedgerEntryData") -> bool:
    """True when an entry is an "Other entry" (SA) that only nets within its own side."""
    if entry.category == "Adjusted":
        return True
    return (entry.document_type or "").strip().upper() == "SA"


def _date_diff_within_window(
    c_category: str, c_date: object, v_date: object, window_days: int
) -> int | None:
    """
    Compute the date gap between a company and vendor entry, respecting the
    directional window the mapping doc specifies for Payments.

    Per doc: "map with date range mapping, from the date of payment made
    from Emcure to after 15 days of receipt amount of vendor" — i.e. for
    Payment entries, the vendor's receipt date must fall ON OR AFTER the
    company's payment date, within ``window_days`` days FORWARD only (not a
    symmetric ± window). All other categories keep the previous symmetric
    ±window_days behaviour since the doc doesn't specify directionality for
    them.

    Returns the (non-negative) day gap if within the allowed window, else
    None.
    """
    if c_date is None or v_date is None:
        return 0
    try:
        if c_category == "Payment":
            delta = (v_date - c_date).days
            if 0 <= delta <= window_days:
                return delta
            return None
        date_diff = abs((c_date - v_date).days)
        return date_diff if date_diff <= window_days else None
    except (TypeError, AttributeError):
        return 0


# Pass number for the company-side reversal (knock-off) pass. Kept outside the
# 1–7 MatchPassType range so it doesn't disturb the standard pass statistics.
REVERSAL_PASS = 9
# Pass number for "Other entry" (SA) same-side netting.
OTHER_ENTRY_PASS = 13
# Pass number for the TDS sequential-link pass: an invoice pair is matched
# cleanly first (full amount, no gap), THEN a separate, standalone TDS
# ledger line on one side is linked to that already-matched pair as a third
# leg. Per the mapping doc: "if vendor has separate tds entry then it get
# match with in sequence like after Emcure invoice match with vendor
# invoice then their difference value map with the remaining tds entry of
# vendor ledger." Distinct from TDS_GST (11), which only catches TDS when it
# shows up as a single amount gap between two entries, not as a separate
# third TDS line item.
TDS_LINK_PASS = 14


@dataclass
class MatchPair:
    """A matched pair of entries (1:1 match).

    For same-side netting pairs (reversal/knock-off, "Other entry" SA) both
    entries live on the same ledger side; ``reversal_side`` records which
    side ("company" or "vendor") so persistence can attribute both IDs to
    the correct side.
    """

    company_entry_id: UUID
    vendor_entry_id: UUID
    confidence_score: float
    pass_number: int
    matched_amount: Decimal
    difference_amount: Decimal = Decimal("0")
    reversal_side: str = "company"


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
        tds_percentage_min: Decimal = Decimal("0"),
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

        # ─── Pass 0: Reversal (knock-off) knock-out on BOTH sides ────────
        # Net offsetting reversal/knock-off entries within EACH ledger before
        # any cross-side matching, so they don't surface as differences or
        # get falsely matched against real invoices on the opposite side.
        # (Previously this only ran on the company side — vendor-side AB
        # entries fell straight into the general matching pool.)
        company_reversal_pairs = self._reversal_match(company_entries, side="company")
        for pair in company_reversal_pairs:
            matched_company_ids.add(pair.company_entry_id)
            matched_company_ids.add(pair.vendor_entry_id)
            result.match_pairs.append(pair)

        vendor_reversal_pairs = self._reversal_match(vendor_entries, side="vendor")
        for pair in vendor_reversal_pairs:
            matched_vendor_ids.add(pair.company_entry_id)
            matched_vendor_ids.add(pair.vendor_entry_id)
            result.match_pairs.append(pair)

        # ─── Pass 0.5: "Other entry" (SA) knock-out on BOTH sides ────────
        # Per mapping doc: SA entries are internal to each side and only net
        # against other SA entries on the SAME side, never against real
        # invoices/payments on the other side.
        company_other_pairs = self._other_entry_match(company_entries, side="company")
        for pair in company_other_pairs:
            matched_company_ids.add(pair.company_entry_id)
            matched_company_ids.add(pair.vendor_entry_id)
            result.match_pairs.append(pair)

        vendor_other_pairs = self._other_entry_match(vendor_entries, side="vendor")
        for pair in vendor_other_pairs:
            matched_vendor_ids.add(pair.company_entry_id)
            matched_vendor_ids.add(pair.vendor_entry_id)
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

        # ─── Pass 2: Tolerance Match (reference exact, amount within %) ───
        # Reference/invoice-number-aware passes (2, 3, 2.5) run BEFORE the
        # blind Amount+Date pass (1.5). Amount+Date never inspects the
        # invoice number, so if it ran first it could pair two DIFFERENT
        # invoices that merely share an amount and a nearby date (e.g. two
        # recurring monthly charges of the same value), stealing an entry
        # that a reference-aware pass would have paired correctly. Running
        # the reference-aware passes first ensures a genuine invoice-number
        # match always wins over a coincidental amount/date match.
        available_company = [
            e for e in company_entries if e.id not in matched_company_ids
        ]
        available_vendor = [
            e for e in vendor_entries if e.id not in matched_vendor_ids
        ]
        tolerance_pairs = self._tolerance_match(
            available_company, available_vendor, tolerance,
            tds_percentage, gst_percentage, tds_percentage_min,
        )
        for pair in tolerance_pairs:
            matched_company_ids.add(pair.company_entry_id)
            matched_vendor_ids.add(pair.vendor_entry_id)
            result.match_pairs.append(pair)

        # ─── Pass 3: Fuzzy Reference Match (reference similar > threshold) ─
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

        # ─── Pass 2.5: TDS/GST Tolerance Match ─────────────────────────────
        # Match entries where the difference equals TDS% or GST% of the amount
        # (e.g., company booked ₹100 but vendor shows ₹90 because 10% TDS was deducted)
        # Still reference-aware (requires similarity >= 0.5), so it belongs
        # ahead of the blind Amount+Date pass too.
        tds_gst_pairs: list[MatchPair] = []
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

        # ─── Pass 15: Amount Mismatch (same invoice number + same date,
        # gap NOT explained by TDS/GST) ─────────────────────────────────
        # Runs AFTER Tolerance (2) and TDS/GST (2.5) so a gap that DOES fit
        # the configured tax rate is captured by those passes first as a
        # "real" match; only a genuinely unexplained gap on an otherwise
        # identical (invoice number + date) pair reaches this pass. Runs
        # BEFORE the blind Amount+Date pass so a same-invoice-number pair
        # is never mistaken for two unrelated entries that merely share an
        # amount/date coincidence.
        available_company = [
            e for e in company_entries if e.id not in matched_company_ids
        ]
        available_vendor = [
            e for e in vendor_entries if e.id not in matched_vendor_ids
        ]
        amount_mismatch_pairs = self._amount_mismatch_match(
            available_company, available_vendor,
            tds_percentage, gst_percentage, tds_percentage_min,
        )
        for pair in amount_mismatch_pairs:
            matched_company_ids.add(pair.company_entry_id)
            matched_vendor_ids.add(pair.vendor_entry_id)
            result.match_pairs.append(pair)

        # ─── Pass 1.5: Amount + Date Match (ignoring doc number) ──────────
        # Most common scenario: company SAP doc numbers don't match vendor invoice numbers
        # but amounts are exactly equal and dates are close. Runs LAST among the
        # 1:1 passes (after every reference-aware pass) so it only claims entries
        # that truly have no traceable invoice-number correspondence left.
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

        # ─── Pass 0.75 (applied here): TDS Sequential Link ────────────────
        # Now that invoice pairs are matched (EXACT/TOLERANCE/AMOUNT_DATE),
        # link any still-unmatched standalone TDS ledger line to its parent
        # pair (via tds_parent_entry_id, computed during transformation).
        # A linked pair is promoted from a 2-entry MatchPair into a 3-entry
        # MatchGroup, so the original pair is removed from match_pairs to
        # avoid double-counting it once as a pair and again as a group.
        available_company = [
            e for e in company_entries if e.id not in matched_company_ids
        ]
        available_vendor = [
            e for e in vendor_entries if e.id not in matched_vendor_ids
        ]
        tds_link_groups = self._tds_link_match(
            result.match_pairs, available_company, available_vendor
        )
        if tds_link_groups:
            absorbed_pair_ids: set[tuple] = set()
            for group in tds_link_groups:
                # The parent pair's ids are the group's ids MINUS the newly
                # linked TDS entry — reconstruct which original pair this
                # group absorbed so it can be removed from match_pairs.
                for cid in group.company_entry_ids:
                    for vid in group.vendor_entry_ids:
                        absorbed_pair_ids.add((cid, vid))
                for cid in group.company_entry_ids:
                    matched_company_ids.add(cid)
                for vid in group.vendor_entry_ids:
                    matched_vendor_ids.add(vid)
            result.match_pairs = [
                p for p in result.match_pairs
                if (p.company_entry_id, p.vendor_entry_id) not in absorbed_pair_ids
            ]
            result.match_groups.extend(tds_link_groups)

        # ─── Pass 3.5: UTR-based Payment Grouping ─────────────────────────
        # Per mapping doc: combine Emcure's split payment entries sharing the
        # same UTR before matching against a single vendor entry. Runs before
        # the generic one-to-many/many-to-one subset-sum so a genuine UTR
        # grouping always wins over an incidental amount coincidence.
        available_company = [
            e for e in company_entries if e.id not in matched_company_ids
        ]
        available_vendor = [
            e for e in vendor_entries if e.id not in matched_vendor_ids
        ]
        utr_groups = self._utr_payment_match(
            available_company, available_vendor, date_tolerance_days=15
        )
        for group in utr_groups:
            for cid in group.company_entry_ids:
                matched_company_ids.add(cid)
            for vid in group.vendor_entry_ids:
                matched_vendor_ids.add(vid)
            result.match_groups.append(group)

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
        tol_date_pairs: list[MatchPair] = []
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
                tds_percentage_min,
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

        # Determine if confirmation is needed (fuzzy/combination/date-proximity/
        # tolerance-date matches — anything not auto-accepted above).
        result.needs_confirmation = len(fuzzy_pairs) > 0 or (
            len(utr_groups) > 0
            or len(one_to_many_groups) > 0 or len(many_to_one_groups) > 0
            or len(date_proximity_pairs) > 0 or len(tol_date_pairs) > 0
            or len(amount_mismatch_pairs) > 0
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

        def _classify_entries(entries: list) -> None:
            """
            Set document_category on each entry based on its doc type —
            but ONLY when no category has been set yet.

            The Map Document Type screen writes the user's authoritative
            category choice directly onto entry.document_category. That must
            win over this fallback guesser on every subsequent reconciliation
            re-run; otherwise a saved mapping (e.g. vendor "RV" -> Invoice)
            gets silently reverted to "Unknown" the moment reconciliation
            executes, re-poisoning the category gate used by the matching
            passes. Uses the same derivation logic as the matching engine
            (_derive_category) so the category shown in the export always
            matches the category the passes actually gated on.
            """
            for e in entries:
                existing = (getattr(e, "document_category", "") or "").strip()
                if existing:
                    continue
                dt = getattr(e, "document_type", None)
                if dt:
                    category = _derive_category(dt)
                    # _derive_category returns "Unknown" for unrecognized raw
                    # codes (e.g. Tally-style "RV"/"DZ") rather than falling
                    # back to the literal code — never poison document_category
                    # with a raw code that would then fail every category
                    # compatibility check on future re-runs.
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

        # Net difference = company closing + vendor closing (NOT a subtraction).
        # Bug fix: vendor-side amounts are stored with the OPPOSITE sign
        # convention from the company side for the same underlying balance
        # (confirmed by the Particulars statement / Excel export, which
        # already computes this correctly as `company_closing + party_closing`
        # with the comment "Party amounts are stored with the opposite sign,
        # so the difference is the SUM of the two sides"). A genuinely
        # reconciled pair of ledgers has company_closing ~= -vendor_closing,
        # so ADDING them cancels out to the true residual gap. Subtracting
        # them instead (the previous behaviour here) doubled the reported
        # gap for any case where the two sides were actually close to
        # agreeing — client-reported: "Difference Amount" showing almost
        # exactly 2x the Company Amount on a case that otherwise looked
        # correctly matched (confirmed: company_closing=3,156,328,
        # vendor_closing=-3,160,129.12, so the true gap is ~3,801 but the
        # old subtraction reported 6,316,457.12 — roughly double the
        # company amount).
        net_difference = None
        if effective_company_closing is not None and effective_vendor_closing is not None:
            net_difference = effective_company_closing + effective_vendor_closing

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
        self, entries: list[LedgerEntryData], side: str = "company"
    ) -> list[MatchPair]:
        """
        Knock off reversal (knock-off / AB) entries against each other within
        a SINGLE ledger side.

        Per the mapping doc: "Knocking entries are internal entries for both
        Emcure and vendor — it should be only map with their internal
        entries." A reversal pair is two entries on the SAME side with:
          - a reversal/knock-off marker (SAP doc type "AB" or category
            "Knocking Off"), and
          - equal magnitude, opposite sign (they net to zero).

        These offset within one ledger (e.g. an entry posted and later
        reversed), so they should be removed from the reconciliation
        difference rather than reported as unmatched or — worse — matched
        against a real invoice on the other side. Each pair is returned as a
        MatchPair whose two entries are both on the same side; the caller
        marks both as used on that side only.
        """
        pairs: list[MatchPair] = []
        used: set[UUID] = set()

        ab_entries = [e for e in entries if _is_reversal(e)]

        # Bucket by (base invoice number, absolute amount) so we can find
        # opposite-sign counterparts. AB/Knocking-Off entries have no
        # invoice-number concept (base == ""), so they're bucketed by
        # amount alone, same as before. Suffix-triggered candidates (e.g.
        # "GJ2501027881-R" / "-RE") additionally require the SAME base
        # invoice number, so a Debit Note and an unrelated TDS entry that
        # merely happen to cancel out in amount are never netted together.
        by_key: dict[tuple[str, Decimal], list[LedgerEntryData]] = {}
        for e in ab_entries:
            base = _reversal_base_invoice(e)
            by_key.setdefault((base, abs(e.amount)), []).append(e)

        for (_base, abs_amt), group in by_key.items():
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
                            vendor_entry_id=cr.id,  # both on the same side here
                            confidence_score=1.0,
                            pass_number=REVERSAL_PASS,
                            matched_amount=abs_amt,
                            difference_amount=Decimal("0"),
                            reversal_side=side,
                        )
                    )
                    break

        return pairs

    def _other_entry_match(
        self, entries: list[LedgerEntryData], side: str = "company"
    ) -> list[MatchPair]:
        """
        Net "Other entry" (SA) rows against each other within a SINGLE side.

        Per the mapping doc: "Other entry like SA from both side, its
        internal entries of Emcure and vendor therefore that only map with
        each other in both side." Same netting logic as reversal_match but
        for category "Adjusted" / doc-type "SA" instead of "AB".
        """
        pairs: list[MatchPair] = []
        used: set[UUID] = set()

        sa_entries = [e for e in entries if _is_other_entry(e)]

        by_abs: dict[Decimal, list[LedgerEntryData]] = {}
        for e in sa_entries:
            by_abs.setdefault(abs(e.amount), []).append(e)

        for abs_amt, group in by_abs.items():
            if abs_amt == 0:
                continue
            debits = [e for e in group if e.amount > 0]
            credits = [e for e in group if e.amount < 0]
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
                            vendor_entry_id=cr.id,  # both on the same side here
                            confidence_score=1.0,
                            pass_number=OTHER_ENTRY_PASS,
                            matched_amount=abs_amt,
                            difference_amount=Decimal("0"),
                            reversal_side=side,
                        )
                    )
                    break

        return pairs

    # ──────────────────────────────────────────────────────────────────────
    # Pass 0.75: TDS Sequential Link (invoice pair matched first, then a
    # separate standalone TDS ledger line is linked to it as a third leg)
    # ──────────────────────────────────────────────────────────────────────

    def _tds_link_match(
        self,
        already_matched_pairs: list[MatchPair],
        company: list[LedgerEntryData],
        vendor: list[LedgerEntryData],
    ) -> list[MatchGroup]:
        """
        Link a standalone TDS ledger line to an ALREADY cross-side-matched
        invoice pair, per the mapping doc's sequential TDS rule: "if vendor
        has separate tds entry then it get match with in sequence like
        after Emcure invoice match with vendor invoice then their
        difference value map with the remaining tds entry of vendor
        ledger."

        This is distinct from _tds_gst_match (pass 11), which only catches
        TDS when it shows up as a single amount GAP between two entries —
        it never handles a TDS amount that exists as its OWN separate line
        item on one ledger side (a third entry, not baked into either the
        company or vendor invoice amount).

        DataTransformationService.tag_tds_entries already computes exactly
        this linkage during transformation (same-side, by reference/document
        number) and persists it as tds_parent_entry_id — this pass only
        needs to follow that existing pointer once its parent has been
        cross-side matched, and turn the pair into a 3-entry group.

        Only considers pairs from passes that leave no unexplained residual
        amount gap (EXACT/TOLERANCE/AMOUNT_DATE) — TDS_GST/TOLERANCE_DATE
        pairs already used up their gap explaining a DIFFERENT (single
        amount-gap) TDS/GST scenario, so re-linking a third TDS line to
        those would double-count the same tax adjustment.
        """
        eligible_passes = {
            MatchPassType.EXACT, MatchPassType.TOLERANCE, MatchPassType.AMOUNT_DATE,
        }
        pair_by_parent_id: dict[UUID, MatchPair] = {}
        for pair in already_matched_pairs:
            if pair.pass_number not in eligible_passes:
                continue
            pair_by_parent_id[pair.company_entry_id] = pair
            pair_by_parent_id[pair.vendor_entry_id] = pair

        groups: list[MatchGroup] = []
        for tds_entry in company + vendor:
            if not tds_entry.is_tds or tds_entry.tds_parent_entry_id is None:
                continue
            parent_pair = pair_by_parent_id.get(tds_entry.tds_parent_entry_id)
            if parent_pair is None:
                continue
            # tds_entry's own side determines which id-list it's appended to;
            # the parent pair already has one id on each side.
            is_company_side = any(
                tds_entry.id == e.id for e in company
            )
            company_ids = [parent_pair.company_entry_id] + (
                [tds_entry.id] if is_company_side else []
            )
            vendor_ids = [parent_pair.vendor_entry_id] + (
                [] if is_company_side else [tds_entry.id]
            )
            groups.append(
                MatchGroup(
                    company_entry_ids=company_ids,
                    vendor_entry_ids=vendor_ids,
                    confidence_score=CONFIDENCE_SCORES[TDS_LINK_PASS],
                    pass_number=TDS_LINK_PASS,
                    matched_amount=parent_pair.matched_amount,
                    difference_amount=tds_entry.amount,
                )
            )

        return groups

    # ──────────────────────────────────────────────────────────────────────
    # Pass 1: Exact Match
    # ──────────────────────────────────────────────────────────────────────

    def _exact_match(
        self,
        company: list[LedgerEntryData],
        vendor: list[LedgerEntryData],
    ) -> list[MatchPair]:
        """
        Match entries where amount, date, and invoice number are identical.

        Requirement 5.2: confidence_score = 1.0 for exact matches.

        Uses `invoice_number` (derived_invoice_number, falling back to
        document_number), NOT `reference_number` — on real company (SAP)
        data, reference_number is a generic cost-center/reference code
        (e.g. "EP22") shared across hundreds of unrelated entries, never an
        invoice number. Keying off it here meant a genuine invoice-number
        match could never be recognized as such.
        """
        pairs: list[MatchPair] = []
        used_vendor_ids: set[UUID] = set()

        # Build a lookup for vendor entries by (amount, date, invoice number)
        # — the raw string, for a true byte-for-byte exact match — AND a
        # second lookup keyed on the NORMALIZED invoice number (fiscal-year
        # token + separators stripped, case-folded), so two invoice numbers
        # that are the same invoice written in a different component order
        # or separator style ("114/25-26" vs "25-26 114") still clear this
        # pass instead of being demoted to the weaker Fuzzy Reference pass
        # (confidence capped at 70%, always needs manual confirmation).
        # Only matchable entries participate (excludes balances/knock-offs/SA).
        vendor_lookup: dict[tuple, list[LedgerEntryData]] = {}
        vendor_lookup_normalized: dict[tuple, list[LedgerEntryData]] = {}
        for v_entry in vendor:
            if not _is_matchable(v_entry):
                continue
            if not v_entry.invoice_number:
                continue
            # abs(amount): company records payables as negative, vendor
            # records sales as positive for the SAME invoice (confirmed on
            # real data). Without abs() here, no company/vendor pair for the
            # same invoice could ever match in this pass — they'd always
            # fall through to the weaker _amount_date_match pass instead.
            key = (abs(v_entry.amount), v_entry.posting_date, v_entry.invoice_number)
            vendor_lookup.setdefault(key, []).append(v_entry)
            norm = self._normalized_invoice_key(v_entry.invoice_number)
            if norm:
                norm_key = (abs(v_entry.amount), v_entry.posting_date, norm)
                vendor_lookup_normalized.setdefault(norm_key, []).append(v_entry)

        for c_entry in company:
            if not _is_matchable(c_entry):
                continue
            if not c_entry.invoice_number:
                continue
            key = (abs(c_entry.amount), c_entry.posting_date, c_entry.invoice_number)
            candidates = vendor_lookup.get(key, [])
            if not candidates:
                # Fall back to the normalized key only when the raw string
                # didn't already match — the raw exact-string check always
                # takes priority so this normalization is purely additive.
                norm = self._normalized_invoice_key(c_entry.invoice_number)
                if norm:
                    norm_key = (abs(c_entry.amount), c_entry.posting_date, norm)
                    candidates = vendor_lookup_normalized.get(norm_key, [])
            for v_entry in candidates:
                if v_entry.id in used_vendor_ids:
                    continue
                if not _categories_compatible(c_entry.category, v_entry.category):
                    continue
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
    # Pass 15: Amount Mismatch (same invoice number + same date, gap NOT
    # explained by TDS/GST)
    # ──────────────────────────────────────────────────────────────────────

    def _amount_mismatch_match(
        self,
        company: list[LedgerEntryData],
        vendor: list[LedgerEntryData],
        tds_percentage: Decimal = Decimal("0"),
        gst_percentage: Decimal = Decimal("0"),
        tds_percentage_min: Decimal = Decimal("0"),
    ) -> list[MatchPair]:
        """
        Pair entries that share the SAME invoice number AND the SAME
        DOCUMENT DATE (Invoice Date) on both sides, when the amount gap is
        real (not a rounding difference) and NOT explained by the
        configured TDS/GST rate.

        Uses `LedgerEntryData.posting_date`, which — despite the field's
        legacy name — holds the DOCUMENT DATE (Invoice Date / SAP BLDAT),
        not the SAP posting date (BUDAT), for any entry where the user has
        mapped a Document/Invoice Date column on the Map Columns screen.
        See column_mapping_controller.py's date-derivation logic: Invoice
        Date is deliberately given priority over Posting Date there
        specifically because SAP's posting date can lag the document date
        by many days on real data (confirmed gap: 19-Apr document date vs
        02-May posting date for the SAME invoice), which would otherwise
        push a genuine same-invoice pair out of this pass entirely. This
        field only falls back to the raw SAP posting date if no
        Document/Invoice Date column was ever mapped for that case.

        Per explicit correction: an identical invoice number and document
        date is strong-enough identification that these two entries ARE the
        same transaction — they must be matched and surfaced to the
        reviewer as one linked pair with a genuine discrepancy, rather than
        left as two separate "not booked by X" open items (which hides
        that they're actually the same invoice with a real, reviewable
        value mismatch). This is the one case where the engine itself
        emits the "Amount Mismatch" classification/status (see
        reconciliation_export_service.py) — every other pass either
        explains the gap (TDS/GST/rounding) or leaves the entries
        unmatched.

        Runs AFTER _tolerance_match / _tds_gst_match in the pass order so a
        gap that DOES fit the configured TDS/GST band is still captured by
        those passes first (as "Invoice Number Matched" / "TDS Booked by
        ..."), and only a genuinely unexplained gap on a same-invoice
        same-document-date pair reaches this pass.
        """
        pairs: list[MatchPair] = []
        used_vendor_ids: set[UUID] = set()

        tds_min_frac = tds_percentage_min / Decimal("100") if tds_percentage_min > 0 else Decimal("0")
        tds_max_frac = tds_percentage / Decimal("100") if tds_percentage > 0 else Decimal("0")
        gst_frac = gst_percentage / Decimal("100") if gst_percentage > 0 else Decimal("0")

        # Build a lookup for vendor entries by (document date, invoice
        # number) — NOT amount, since the whole point of this pass is that
        # the amounts differ. `posting_date` here holds the DOCUMENT DATE
        # (see docstring above), not the raw SAP posting date. Also builds
        # a normalized-key lookup (see _normalized_invoice_key) so a same
        # invoice number written in a different component order/separator
        # is still recognized as the same invoice for this pass, same
        # rationale as _exact_match/_tolerance_match.
        vendor_lookup: dict[tuple, list[LedgerEntryData]] = {}
        vendor_lookup_normalized: dict[tuple, list[LedgerEntryData]] = {}
        for v_entry in vendor:
            if not _is_matchable(v_entry):
                continue
            if not v_entry.invoice_number:
                continue
            key = (v_entry.posting_date, v_entry.invoice_number)
            vendor_lookup.setdefault(key, []).append(v_entry)
            norm = self._normalized_invoice_key(v_entry.invoice_number)
            if norm:
                vendor_lookup_normalized.setdefault((v_entry.posting_date, norm), []).append(v_entry)

        for c_entry in company:
            if not _is_matchable(c_entry):
                continue
            if not c_entry.invoice_number:
                continue
            key = (c_entry.posting_date, c_entry.invoice_number)
            candidates = vendor_lookup.get(key, [])
            if not candidates:
                norm = self._normalized_invoice_key(c_entry.invoice_number)
                if norm:
                    candidates = vendor_lookup_normalized.get((c_entry.posting_date, norm), [])
            for v_entry in candidates:
                if v_entry.id in used_vendor_ids:
                    continue
                if not _categories_compatible(c_entry.category, v_entry.category):
                    continue

                diff = abs(abs(c_entry.amount) - abs(v_entry.amount))
                if diff <= Decimal("0.005"):
                    # No real gap at all — belongs to _exact_match, not here
                    # (shouldn't normally reach this pass since exact_match
                    # runs first and would have already claimed it).
                    continue

                is_tax_match = _is_tax_band_gap(
                    diff, abs(c_entry.amount), abs(v_entry.amount),
                    tds_min_frac, tds_max_frac, gst_frac,
                )
                if is_tax_match:
                    # A real TDS/GST-driven gap — not an amount mismatch.
                    # Should already have been claimed by an earlier pass,
                    # but skip defensively rather than mislabel it here.
                    continue

                pairs.append(
                    MatchPair(
                        company_entry_id=c_entry.id,
                        vendor_entry_id=v_entry.id,
                        confidence_score=CONFIDENCE_SCORES[MatchPassType.AMOUNT_MISMATCH],
                        pass_number=MatchPassType.AMOUNT_MISMATCH,
                        matched_amount=c_entry.amount,
                        difference_amount=c_entry.amount + v_entry.amount,
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

        # Build vendor lookup by absolute amount for fast matching.
        # Only matchable entries participate (excludes balances/knock-offs/SA).
        vendor_by_abs_amount: dict[Decimal, list[LedgerEntryData]] = {}
        for v_entry in vendor:
            if not _is_matchable(v_entry):
                continue
            abs_amt = abs(v_entry.amount)
            vendor_by_abs_amount.setdefault(abs_amt, []).append(v_entry)

        for c_entry in company:
            if not _is_matchable(c_entry):
                continue
            abs_c_amount = abs(c_entry.amount)
            candidates = vendor_by_abs_amount.get(abs_c_amount, [])

            best_match: LedgerEntryData | None = None
            best_date_diff: int = date_tolerance_days + 1

            for v_entry in candidates:
                if v_entry.id in used_vendor_ids:
                    continue
                # Gate on document-category compatibility so an invoice never
                # matches a payment/receipt of the same magnitude.
                if not _categories_compatible(c_entry.category, v_entry.category):
                    continue

                # Check date proximity (directional forward-only window for
                # Payment entries per the mapping doc; symmetric otherwise).
                date_diff = _date_diff_within_window(
                    c_entry.category, c_entry.posting_date, v_entry.posting_date,
                    date_tolerance_days,
                )
                if date_diff is None:
                    continue

                if date_diff < best_date_diff:
                    best_date_diff = date_diff
                    best_match = v_entry

            if best_match is not None:
                pairs.append(
                    MatchPair(
                        company_entry_id=c_entry.id,
                        vendor_entry_id=best_match.id,
                        confidence_score=CONFIDENCE_SCORES[MatchPassType.AMOUNT_DATE],
                        pass_number=MatchPassType.AMOUNT_DATE,
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
        tds_percentage_min: Decimal = Decimal("0"),
    ) -> list[MatchPair]:
        """
        Match entries whose ABSOLUTE amounts are within an allowed difference
        (tolerance %, TDS % range, or GST %) and whose dates are within
        tolerance days, WITHOUT requiring reference numbers to match.

        Catches invoices that differ by GST rounding or small journal adjustments
        (e.g. company 208,683 vs vendor 208,860 → diff 177 within tolerance).
        These are flagged as needing confirmation (Pass 6 confidence).
        """
        pairs: list[MatchPair] = []
        used_vendor_ids: set[UUID] = set()

        # Determine tolerance fraction (tolerance may be percentage < 1 or absolute)
        is_pct = tolerance < Decimal("1")
        tds_min_frac = tds_percentage_min / Decimal("100") if tds_percentage_min > 0 else Decimal("0")
        tds_max_frac = tds_percentage / Decimal("100") if tds_percentage > 0 else Decimal("0")
        gst_frac = gst_percentage / Decimal("100") if gst_percentage > 0 else Decimal("0")

        for c_entry in company:
            if not _is_matchable(c_entry):
                continue
            abs_c = abs(c_entry.amount)
            if abs_c == 0:
                continue

            # Plain rounding tolerance ceiling, with a small ₹5 floor to
            # absorb rounding. The TDS/GST-sized portion is checked
            # separately via _is_tax_band_gap (range-aware band around the
            # actual computed tax amount, not a blanket ceiling) — same
            # false-match issue _tolerance_match had.
            allowed = Decimal("0")
            if tolerance > 0:
                allowed = abs_c * tolerance if is_pct else tolerance
            allowed = max(allowed, Decimal("5"))

            best_match: LedgerEntryData | None = None
            best_diff: Decimal | None = None

            for v_entry in vendor:
                if v_entry.id in used_vendor_ids:
                    continue
                if not _is_matchable(v_entry):
                    continue
                if not _categories_compatible(c_entry.category, v_entry.category):
                    continue

                diff = abs(abs_c - abs(v_entry.amount))
                is_tax_match = _is_tax_band_gap(
                    diff, abs_c, abs(v_entry.amount), tds_min_frac, tds_max_frac, gst_frac,
                )
                if diff > allowed and not is_tax_match:
                    continue

                # Date proximity check (directional forward-only window for
                # Payment entries per the mapping doc; symmetric otherwise).
                date_diff = _date_diff_within_window(
                    c_entry.category, c_entry.posting_date, v_entry.posting_date,
                    date_tolerance_days,
                )
                if date_diff is None:
                    continue

                if best_diff is None or diff < best_diff:
                    best_diff = diff
                    best_match = v_entry

            if best_match is not None:
                pairs.append(
                    MatchPair(
                        company_entry_id=c_entry.id,
                        vendor_entry_id=best_match.id,
                        confidence_score=CONFIDENCE_SCORES[MatchPassType.TOLERANCE_DATE],
                        pass_number=MatchPassType.TOLERANCE_DATE,
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
        tds_percentage: Decimal = Decimal("0"),
        gst_percentage: Decimal = Decimal("0"),
        tds_percentage_min: Decimal = Decimal("0"),
    ) -> list[MatchPair]:
        """
        Match entries where amount difference is within tolerance
        AND invoice numbers match exactly.

        Tolerance can be a percentage (fraction like 0.01 for 1%) applied to
        the company entry amount, or an absolute value if > 1. The allowed
        gap is ALSO widened to cover a TDS/GST-sized difference (same
        calculation as _tolerance_date_match) — otherwise a pair with an
        exact invoice-number AND date match, but a real tax-driven amount
        gap, fails this pass on amount alone and falls through to the
        weaker _tolerance_date_match (which doesn't check invoice number at
        all), reporting a real invoice-number match as the much weaker
        "Date Range and Amount Matched" classification and losing the TDS
        signal on the difference entirely.

        TDS is a RANGE [tds_percentage_min, tds_percentage] (the
        Reconciliation Settings screen's Min/Max), not a single rate — the
        mapping doc calls out multiple real tiers (0.1%/2%/10%).

        Requirement 5.3: Amount within configured Tolerance_Amount
        and invoice numbers match.

        Uses `invoice_number`, NOT `reference_number` — see _exact_match.
        """
        if tolerance <= 0 and tds_percentage <= 0 and gst_percentage <= 0:
            return []

        pairs: list[MatchPair] = []
        used_vendor_ids: set[UUID] = set()

        # Determine if tolerance is percentage-based (< 1) or absolute (>= 1)
        is_percentage = tolerance < Decimal("1")
        tds_min_frac = tds_percentage_min / Decimal("100") if tds_percentage_min > 0 else Decimal("0")
        tds_max_frac = tds_percentage / Decimal("100") if tds_percentage > 0 else Decimal("0")
        gst_frac = gst_percentage / Decimal("100") if gst_percentage > 0 else Decimal("0")

        # Build invoice-number lookup for vendor entries (matchable only) —
        # by raw string AND by normalized key (see _normalized_invoice_key),
        # same rationale as _exact_match: a same invoice number written in
        # a different component order/separator ("114/25-26" vs "25-26
        # 114") must still clear this pass rather than being demoted to
        # the weaker Fuzzy Reference pass.
        vendor_by_ref: dict[str, list[LedgerEntryData]] = {}
        vendor_by_ref_normalized: dict[str, list[LedgerEntryData]] = {}
        for v_entry in vendor:
            if not _is_matchable(v_entry):
                continue
            if not v_entry.invoice_number:
                continue
            vendor_by_ref.setdefault(v_entry.invoice_number, []).append(v_entry)
            norm = self._normalized_invoice_key(v_entry.invoice_number)
            if norm:
                vendor_by_ref_normalized.setdefault(norm, []).append(v_entry)

        for c_entry in company:
            if not _is_matchable(c_entry):
                continue
            if not c_entry.invoice_number:
                continue
            candidates = vendor_by_ref.get(c_entry.invoice_number, [])
            if not candidates:
                # Raw string didn't match — fall back to the normalized
                # key. The raw exact-string check always takes priority so
                # this normalization is purely additive.
                norm = self._normalized_invoice_key(c_entry.invoice_number)
                if norm:
                    candidates = vendor_by_ref_normalized.get(norm, [])
            for v_entry in candidates:
                if v_entry.id in used_vendor_ids:
                    continue
                if not _categories_compatible(c_entry.category, v_entry.category):
                    continue
                # abs(amount) on both sides: company records payables as
                # negative, vendor records sales as positive for the SAME
                # invoice. Without abs() here, diff = |c - v| would compute
                # the SUM's magnitude instead of the actual amount gap
                # (e.g. -15498.94 vs 15498.94 -> diff of ~31000, not 0),
                # so no genuine invoice-number+tolerance match could ever
                # pass the tolerance check.
                diff = abs(abs(c_entry.amount) - abs(v_entry.amount))

                # Plain rounding tolerance (small write-offs) — unrelated to
                # tax, so this stays a simple ceiling check.
                if is_percentage:
                    allowed = abs(c_entry.amount) * tolerance
                else:
                    allowed = tolerance

                # TDS/GST-sized gap: only accepted if it actually resembles
                # the configured rate applied to the base amount (within a
                # tight band), not merely "smaller than the largest possible
                # tax amount" — see _is_tax_band_gap for why the ceiling
                # check let real amount mismatches through as false matches.
                is_tax_match = _is_tax_band_gap(
                    diff, abs(c_entry.amount), abs(v_entry.amount),
                    tds_min_frac, tds_max_frac, gst_frac,
                )

                if diff <= allowed or is_tax_match:
                    pairs.append(
                        MatchPair(
                            company_entry_id=c_entry.id,
                            vendor_entry_id=v_entry.id,
                            confidence_score=CONFIDENCE_SCORES[MatchPassType.TOLERANCE],
                            pass_number=MatchPassType.TOLERANCE,
                            matched_amount=c_entry.amount,
                            difference_amount=c_entry.amount + v_entry.amount,
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
            if not _is_matchable(c_entry):
                continue
            for v_entry in vendor:
                if v_entry.id in used_vendor_ids:
                    continue
                if not _is_matchable(v_entry):
                    continue
                # TDS/GST gap only applies between economically compatible
                # entries (invoice<->invoice). Never let a TDS gap knock a
                # real invoice off against a reversal, receipt, or SA entry.
                if not _categories_compatible(c_entry.category, v_entry.category):
                    continue

                # abs() on both sides: company records payables as negative,
                # vendor records sales as positive for the SAME invoice.
                # Without abs() here, diff would compute the SUM's magnitude
                # (e.g. -100000 vs 90000 -> ~190000) instead of the actual
                # TDS/GST gap (~10000), so this pass could never fire on
                # real opposite-signed data.
                diff = abs(abs(c_entry.amount) - abs(v_entry.amount))
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
                    # Also verify invoice numbers have some similarity (>50%).
                    # Uses invoice_number, NOT reference_number — see _exact_match.
                    ref_sim = self._reference_similarity(
                        c_entry.invoice_number, v_entry.invoice_number
                    )
                    if ref_sim >= 0.5 or (
                        c_entry.invoice_number
                        and c_entry.invoice_number == v_entry.invoice_number
                    ):
                        pairs.append(
                            MatchPair(
                                company_entry_id=c_entry.id,
                                vendor_entry_id=v_entry.id,
                                confidence_score=CONFIDENCE_SCORES[MatchPassType.TDS_GST],
                                pass_number=MatchPassType.TDS_GST,
                                matched_amount=c_entry.amount,
                                difference_amount=c_entry.amount + v_entry.amount,
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
        Match entries where amounts are equal but invoice numbers have
        a similarity score above the threshold (default 80%).

        Requirement 5.4: Uses difflib.SequenceMatcher for similarity.

        Uses `invoice_number`, NOT `reference_number` — see _exact_match.
        Buckets by abs(amount): company records payables as negative,
        vendor records sales as positive for the same invoice.
        """
        pairs: list[MatchPair] = []
        used_vendor_ids: set[UUID] = set()

        # Build lookup for vendor entries by amount for efficient filtering
        # (matchable only).
        vendor_by_amount: dict[Decimal, list[LedgerEntryData]] = {}
        for v_entry in vendor:
            if not _is_matchable(v_entry):
                continue
            vendor_by_amount.setdefault(abs(v_entry.amount), []).append(v_entry)

        for c_entry in company:
            if not _is_matchable(c_entry):
                continue
            candidates = vendor_by_amount.get(abs(c_entry.amount), [])
            best_match: LedgerEntryData | None = None
            best_score: float = 0.0

            for v_entry in candidates:
                if v_entry.id in used_vendor_ids:
                    continue
                if not _categories_compatible(c_entry.category, v_entry.category):
                    continue
                similarity = self._reference_similarity(
                    c_entry.invoice_number, v_entry.invoice_number
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

    def _utr_payment_match(
        self,
        company: list[LedgerEntryData],
        vendor: list[LedgerEntryData],
        date_tolerance_days: int = 15,
    ) -> list[MatchGroup]:
        """
        Combine company-side Payment entries that share the same UTR
        (assignment_number) into a single total, and match that total
        against a single vendor entry by amount + date.

        Per the mapping doc: "If Emcure has made the payment in multiple
        split entries under the same UTR, then combine all those entries and
        match them with the vendor's entry based on the payment date and
        total amount." Runs BEFORE the generic one-to-many/many-to-one
        subset-sum passes so a genuine UTR grouping always wins over an
        incidental amount coincidence.
        """
        groups: list[MatchGroup] = []
        used_company_ids: set[UUID] = set()
        used_vendor_ids: set[UUID] = set()

        payment_entries = [
            e for e in company
            if e.category == "Payment" and (e.assignment_number or "").strip()
        ]
        by_utr: dict[str, list[LedgerEntryData]] = {}
        for e in payment_entries:
            by_utr.setdefault(e.assignment_number.strip(), []).append(e)

        available_vendor = [v for v in vendor if _is_matchable(v)]

        for utr, group_entries in by_utr.items():
            if len(group_entries) < 2:
                continue  # Only split entries need combining; single entries go through normal passes.
            total = sum(e.amount for e in group_entries)
            anchor_date = max(
                (e.posting_date for e in group_entries if e.posting_date is not None),
                default=None,
            )

            best_match: LedgerEntryData | None = None
            best_date_diff: int | None = None
            for v_entry in available_vendor:
                if v_entry.id in used_vendor_ids:
                    continue
                if not _categories_compatible("Payment", v_entry.category):
                    continue
                if abs(abs(total) - abs(v_entry.amount)) > Decimal("0.01"):
                    continue
                # Directional forward-only window: vendor receipt date must
                # be on/after the (last) company payment date, within
                # date_tolerance_days days — per the mapping doc.
                date_diff = _date_diff_within_window(
                    "Payment", anchor_date, v_entry.posting_date, date_tolerance_days
                )
                if date_diff is None:
                    continue
                if best_date_diff is None or date_diff < best_date_diff:
                    best_date_diff = date_diff
                    best_match = v_entry

            if best_match is not None:
                company_ids = [e.id for e in group_entries]
                groups.append(
                    MatchGroup(
                        company_entry_ids=company_ids,
                        vendor_entry_ids=[best_match.id],
                        confidence_score=CONFIDENCE_SCORES[MatchPassType.MANY_TO_ONE],
                        pass_number=MatchPassType.MANY_TO_ONE,
                        matched_amount=abs(total),
                        difference_amount=abs(total) - abs(best_match.amount),
                    )
                )
                used_company_ids.update(company_ids)
                used_vendor_ids.add(best_match.id)

        return groups

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
        # likely to be sums of multiple smaller vendor entries). Only matchable
        # company entries with a KNOWN category drive one-to-many grouping —
        # a wildcard-category (Journal/Unknown/Other) anchor entry has no
        # reliable economic identity of its own to group multiple vendor
        # entries against.
        sorted_company = sorted(
            (e for e in company if _is_matchable(e) and e.category not in WILDCARD_CATEGORIES),
            key=lambda e: abs(e.amount),
            reverse=True,
        )

        for c_entry in sorted_company:
            # Candidate vendor entries must be unused, matchable, of a
            # category compatible with the company entry (no invoice<->receipt,
            # no matching against knock-offs/SA entries), AND have a KNOWN
            # economic category (not Journal/Unknown/Other/blank).
            #
            # Client-confirmed bug: a subset-sum group pulled in an unrelated
            # vendor "Journal" entry that merely happened to make the total
            # add up, and the row was reported "Reconciled" alongside the
            # real invoices in the group. Unlike Exact/Tolerance matching
            # (which is keyed on invoice NUMBER identity — a strong signal
            # that tolerates a wildcard category), subset-sum grouping has
            # NO invoice-number correlation at all; it is pure amount
            # coincidence within a date window. Wildcard categories must
            # never participate in that weaker signal, or any journal/
            # unclassified entry that happens to fit the sum gets silently
            # absorbed into a real invoice group.
            available_vendor = [
                v for v in vendor
                if v.id not in used_vendor_ids
                and _is_matchable(v)
                and v.category not in WILDCARD_CATEGORIES
                and _categories_compatible(c_entry.category, v.category)
            ]
            if len(available_vendor) < 2:
                continue

            # Find subset of vendor entries whose absolute amounts sum to
            # company amount, constrained to entries near the company entry's date.
            matching_subset = self._find_subset_sum(
                available_vendor, c_entry.amount, anchor_date=c_entry.posting_date
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

        # Sort vendor entries by absolute amount descending (matchable only,
        # KNOWN category — see _one_to_many_match for why wildcard-category
        # entries can't anchor a subset-sum group).
        sorted_vendor = sorted(
            (e for e in vendor if _is_matchable(e) and e.category not in WILDCARD_CATEGORIES),
            key=lambda e: abs(e.amount),
            reverse=True,
        )

        for v_entry in sorted_vendor:
            # Candidate company entries must ALSO have a known category —
            # same rationale as _one_to_many_match: subset-sum grouping is
            # pure amount coincidence with no invoice-number correlation, so
            # a wildcard-category (e.g. Journal) entry that merely happens
            # to fit the sum must never be silently absorbed into a real
            # invoice/payment group.
            available_company = [
                c for c in company
                if c.id not in used_company_ids
                and _is_matchable(c)
                and c.category not in WILDCARD_CATEGORIES
                and _categories_compatible(v_entry.category, c.category)
            ]
            if len(available_company) < 2:
                continue

            # Find subset of company entries whose absolute amounts sum to
            # vendor amount, constrained to entries near the vendor entry's date.
            matching_subset = self._find_subset_sum(
                available_company, v_entry.amount, anchor_date=v_entry.posting_date
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
        Match entries where amounts are equal and posting dates are within
        N days of each other (configurable via date_tolerance_days).

        Requirement 17.1: Match by amount + date within configurable N days.
        BRD confidence = 0.70 (normalized from MatchScore 70).
        """
        if date_tolerance_days < 0:
            return []

        pairs: list[MatchPair] = []
        used_vendor_ids: set[UUID] = set()

        # Build lookup for vendor entries by amount for efficient filtering
        # (matchable only).
        vendor_by_amount: dict[Decimal, list[LedgerEntryData]] = {}
        for v_entry in vendor:
            if not _is_matchable(v_entry):
                continue
            vendor_by_amount.setdefault(v_entry.amount, []).append(v_entry)

        for c_entry in company:
            if not _is_matchable(c_entry):
                continue
            candidates = vendor_by_amount.get(c_entry.amount, [])
            best_match: LedgerEntryData | None = None
            best_date_diff: int | None = None

            for v_entry in candidates:
                if v_entry.id in used_vendor_ids:
                    continue
                # Gate on category so an invoice can't match a receipt/payment
                # merely because the amount and date align.
                if not _categories_compatible(c_entry.category, v_entry.category):
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
        anchor_date: object | None = None,
        date_window_days: int = 45,
    ) -> list[LedgerEntryData] | None:
        """
        Find a subset of entries whose ABSOLUTE amounts sum to the absolute target.

        Sign-aware: company records payments as positive while vendor records
        receipts as negative (and vice-versa). Matching is done on absolute
        values so that e.g. company payments (+73,750 + +641,625) match a
        vendor receipt (-715,375).

        A small tolerance absorbs rounding differences.
        Limits search to combinations of up to max_subset_size entries.

        When ``anchor_date`` is supplied, only entries whose posting date
        falls within ``date_window_days`` of the anchor are considered. This
        stops the subset-sum from fabricating a group out of unrelated
        entries that merely happen to add up to the target amount.
        """
        from itertools import combinations

        abs_target = abs(target)
        if abs_target == 0:
            return None

        def _within_window(entry: LedgerEntryData) -> bool:
            if anchor_date is None or entry.posting_date is None:
                return True
            try:
                return abs((entry.posting_date - anchor_date).days) <= date_window_days
            except (TypeError, AttributeError):
                return True

        # Use absolute values; only consider entries not larger than the
        # target and within the date window of the anchor entry.
        candidates = [
            e for e in entries
            if Decimal("0") < abs(e.amount) <= abs_target + tolerance
            and _within_window(e)
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

    # Matches a 2-digit year, with an OPTIONAL 2-digit century prefix,
    # followed by an optional single separator (hyphen, slash, or space),
    # followed by the next 2-digit year (also with an optional century
    # prefix), e.g. "25-26", "25/26", "25 26", "2025-26", "2025/26",
    # "2025-2026", or the CLEAN-derived digit-only "2526". Built with a
    # lookahead so overlapping candidate positions are all considered
    # (finditer alone would skip past a match and miss a fiscal-year token
    # that starts partway through another digit run, e.g. the "2526"
    # inside "1142526").
    #
    # Bug fix: the previous pattern only ever captured the TRAILING 2
    # digits of each year, so a 4-digit-year value like "2025-26" matched
    # via the overlapping-lookahead scan starting at the "25" (not the
    # "20"), stripping only "25-26" and leaving the leading "20" behind.
    # Two DIFFERENT invoice numbers that both happen to use this 4-digit-
    # year format then kept an identical leftover "20" fragment after
    # stripping, artificially inflating their SequenceMatcher similarity
    # (client-confirmed real case: "47/HOC/2025-26" vs "36/HOC/2025/26"
    # scored 0.78 similarity — above several matching thresholds — purely
    # from the shared, incompletely-stripped "20" prefix, not genuine
    # invoice similarity). The optional century-prefix groups now let the
    # WHOLE 4-digit year get captured and stripped, not just its tail.
    # The optional century prefix is restricted to the LITERAL "19" or
    # "20" (not an arbitrary \d{2}) — real invoice dates in this business
    # domain are all 1900s/2000s, and restricting to a literal century
    # value (rather than "any 2 digits") prevents unrelated invoice digits
    # that merely happen to precede a valid 2-digit year pair from being
    # misread as a century prefix (e.g. invoice "114" followed by year
    # "25" must NOT have its "14" swallowed as a fake century of "25").
    _FISCAL_YEAR_PATTERN = re.compile(
        r"(?=(19|20)?(\d{2})([-/\s]?)(19|20)?(\d{2}))"
    )

    # Separators commonly used to punctuate an invoice number (hyphen,
    # slash, underscore, dot, whitespace) — stripped during normalization
    # so purely-cosmetic formatting differences (e.g. component order,
    # separator choice) don't block an exact-match lookup. Deliberately
    # does NOT strip alphanumeric characters — only separator punctuation.
    _INVOICE_SEPARATOR_PATTERN = re.compile(r"[\s\-/_.]+")

    @classmethod
    def _normalized_invoice_key(cls, value: str) -> str:
        """
        Canonical invoice-number key for EXACT-equality lookups (Pass 1
        _exact_match, Pass 2 _tolerance_match), tolerant of purely cosmetic
        formatting differences between company and vendor systems.

        Client-confirmed bug: company Assignment "114/25-26" and vendor Vch
        No. "25-26 114" are the SAME invoice (114, fiscal year 25-26) with
        the components in a different order and a different separator —
        but the exact-match/tolerance passes key on the raw string, so this
        pair could never clear those passes and was demoted all the way to
        the weaker Fuzzy Reference pass (confidence capped at 70%, always
        needs manual confirmation) despite being an unambiguous, zero-
        difference match.

        Normalization applied, in order:
          1. Strip the fiscal-year token (e.g. "25-26"/"2526") using the
             SAME `_find_fiscal_year_spans` detector _strip_shared_fiscal_year
             uses — a real fiscal-year token is recognized structurally
             (two consecutive 2-digit years, second = first+1), not by
             guessing at position, so this doesn't accidentally eat real
             invoice digits that happen to look year-like only when they
             ALSO appear elsewhere in the string coincidentally more than
             once (see safety note below).
          2. Strip separator punctuation (space, hyphen, slash, underscore,
             dot) so "-", "/", " " differences collapse.
          3. Uppercase, so case differences ("inv" vs "INV") don't matter.

        SAFETY — why this does not increase false-positive risk:
          - This is intentionally NARROWER than the fuzzy-similarity check
            used by Pass 3 (which accepts a >0.8 SequenceMatcher ratio —
            an approximate, position-independent score). This function
            instead produces a single canonical string; two invoice
            numbers must become EXACTLY equal after normalization to be
            treated as the same invoice by Pass 1/2 — no partial-credit
            fuzziness is introduced into the exact-match tier.
          - The fiscal-year stripping only removes a token that
            STRUCTURALLY looks like a fiscal year (consecutive N, N+1 two-
            digit years) — it does not remove arbitrary digit runs, so two
            DIFFERENT invoice numbers that don't share that exact
            structural pattern are never coincidentally collapsed together
            (e.g. "114" vs "447" stay "114" vs "447" — confirmed via the
            existing regression test that these must NOT fuzzy-match; this
            normalization doesn't touch that outcome since neither string
            contains a fiscal-year token to strip once isolated from a
            shared prefix — see _strip_shared_fiscal_year's own "only when
            BOTH sides share the token" gate, mirrored here since this
            function only strips a token that independently matches the
            fiscal-year structural pattern on its OWN string, never one
            borrowed from the other side).
          - A value that normalizes to an EMPTY string (e.g. the raw value
            was purely a fiscal-year token like "25-26" with nothing else)
            is never used as a match key — callers must still gate on the
            normalized key being non-empty, exactly like the existing
            `if not entry.invoice_number: continue` guards, so two
            genuinely different blank/placeholder invoice numbers can never
            collide on an empty string.
        """
        if not value:
            return ""
        spans = cls._find_fiscal_year_spans(value)
        s = value
        for token, start, end in sorted(spans, key=lambda sp: sp[1], reverse=True):
            s = s[:start] + s[end:]
        s = cls._INVOICE_SEPARATOR_PATTERN.sub("", s)
        return s.strip().upper()

    @classmethod
    def _find_fiscal_year_spans(cls, value: str) -> list[tuple[str, int, int]]:
        """
        Find substrings that look like a fiscal-year token (two consecutive
        2-digit years, the second being the first + 1, wrapping at year
        100 — e.g. "25-26", "2526", "99-00"), across the raw
        Assignment-style 2-digit-year format ("114/25-26"), a 4-digit-year
        variant ("114/2025-26", "114/2025/2026"), and the CLEAN-derived
        digit-only format ("1142526"). Returns (normalized_token, start,
        end) tuples so the exact matched span — including any separator
        AND any century-prefix digits actually present — can be fully
        stripped from the original string.

        The lookahead pattern generates an overlapping candidate at EVERY
        position a valid token could start, so a 4-digit-year value like
        "2025-26" produces TWO valid candidates: the full "2025-26" (start
        0) and the nested "25-26" (start 2, both years read as their
        trailing 2 digits). Only the LONGER (century-inclusive) span is
        kept when candidates overlap — this is what fixed the real bug:
        previously (before century-prefix support existed) only the
        shorter nested match was found at all, so a leading century
        fragment ("20") was left un-stripped, artificially inflating
        SequenceMatcher similarity between two otherwise-different invoice
        numbers that happened to share that leftover fragment.
        """
        candidates: list[tuple[str, int, int, int]] = []
        for m in cls._FISCAL_YEAR_PATTERN.finditer(value):
            century1, y1, sep, century2, y2 = m.groups()
            a, b = int(y1), int(y2)
            if b != (a + 1) % 100:
                continue
            start = m.start()
            length = (
                (len(century1) if century1 else 0)
                + 2
                + len(sep)
                + (len(century2) if century2 else 0)
                + 2
            )
            end = start + length
            token = (century1 or "") + y1 + (century2 or "") + y2
            candidates.append((token, start, end, length))

        # Prefer longer (more specific, century-inclusive) spans; discard
        # any candidate that overlaps an already-selected longer span.
        candidates.sort(key=lambda c: (-c[3], c[1]))
        selected: list[tuple[str, int, int]] = []
        for token, start, end, _length in candidates:
            if any(start < s_end and s_start < end for (_t, s_start, s_end) in selected):
                continue
            selected.append((token, start, end))

        selected.sort(key=lambda sp: sp[1])
        return selected

    @classmethod
    def _strip_shared_fiscal_year(cls, ref1: str, ref2: str) -> tuple[str, str]:
        """
        Remove a fiscal-year token (e.g. "25-26" / "2526") from BOTH
        references when the SAME year token appears in both — but only
        then, so genuinely different fiscal years are never altered. This
        isolates the actual distinguishing invoice digits before
        similarity scoring.

        Bug fix (client-reported, real data confirmed — vendor AUTOPACK
        INDUSTRIES): invoice numbers routinely embed the fiscal year
        alongside the real invoice digits, and NOT always in the fully
        CLEAN-derived digit-only form — real data showed company
        Assignment "114/25-26" (slash + hyphen still present) paired
        against vendor Vch No. "25-26 447" (space-separated). Because the
        shared "25-26"/"2526" token dominates difflib.SequenceMatcher's
        ratio on these short strings, TWO COMPLETELY DIFFERENT invoices
        (114 vs 447) scored ~0.56 — the SAME ballpark as the correct pair
        (114 vs 114) — clearing the 0.5 threshold in `_tds_gst_match`
        regardless of which invoice number was actually attached.
        Stripping the shared token first (independent of which separator,
        if any, surrounds it) makes the comparison key off the real
        invoice digits instead of the noise.

        An earlier version of this fix only matched the fully-cleaned
        4-consecutive-digit form ("2526") and silently no-opped on the raw
        separator-containing form ("25-26") actually present in production
        data — this version matches both.
        """
        spans1 = cls._find_fiscal_year_spans(ref1)
        spans2 = cls._find_fiscal_year_spans(ref2)
        if not spans1 or not spans2:
            return ref1, ref2
        tokens1 = {t for t, _, _ in spans1}
        tokens2 = {t for t, _, _ in spans2}
        shared = tokens1 & tokens2
        if not shared:
            return ref1, ref2

        def _remove_first_shared(value: str, spans: list[tuple[str, int, int]]) -> str:
            for token, start, end in spans:
                if token in shared:
                    return value[:start] + value[end:]
            return value

        r1 = _remove_first_shared(ref1, spans1)
        r2 = _remove_first_shared(ref2, spans2)
        return r1.strip(), r2.strip()

    @classmethod
    def _reference_similarity(cls, ref1: str, ref2: str) -> float:
        """
        Calculate string similarity between two reference numbers using
        difflib.SequenceMatcher, after stripping a shared fiscal-year token
        (see _strip_shared_fiscal_year) so a common "25-26"-style suffix
        can't inflate the score for two otherwise-unrelated invoice numbers.

        Returns a float between 0.0 and 1.0.
        """
        if not ref1 or not ref2:
            return 0.0
        r1, r2 = cls._strip_shared_fiscal_year(ref1, ref2)
        if not r1 or not r2:
            # Stripping the fiscal year left one side empty (it was PURELY
            # the fiscal-year token, e.g. two "2526"-only references) —
            # fall back to the un-stripped comparison rather than treating
            # this as a hard 0.0.
            return difflib.SequenceMatcher(None, ref1, ref2).ratio()
        return difflib.SequenceMatcher(None, r1, r2).ratio()

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

        # Count from groups (passes 4, 5, plus non-standard passes like
        # TDS_LINK_PASS=14 that aren't pre-seeded in pass_data above).
        for group in result.match_groups:
            ps = pass_data.get(group.pass_number)
            if ps is None:
                ps = PassStatistics(pass_number=group.pass_number)
                pass_data[group.pass_number] = ps
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
                if ps.pass_number in (
                    1, 2, 3, 6,
                    MatchPassType.AMOUNT_DATE,
                    MatchPassType.TDS_GST,
                    MatchPassType.TOLERANCE_DATE,
                    MatchPassType.AMOUNT_MISMATCH,
                ):
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
        # Persist match pairs (passes 1, 2, 3, 6, plus same-side netting 9/13)
        for pair in result.match_pairs:
            match_id = uuid4()
            is_same_side_netting = pair.pass_number in (REVERSAL_PASS, OTHER_ENTRY_PASS)
            # BRD: Auto-Accept for Pass 1 (Exact) and Pass 2 (Tolerance).
            # AMOUNT_DATE (1.5) and TDS_GST (2.5) are also high-confidence
            # (0.90/0.85) so they auto-accept too; TOLERANCE_DATE (6.5) is the
            # weakest tier (neither exact amount nor reference matched) and
            # always needs Finance review, same as Pass 6 Date-proximity.
            # Reversal/"Other entry" netting nets to zero within a single
            # ledger, so auto-accept it.
            is_auto_accepted = is_same_side_netting or pair.pass_number in (
                MatchPassType.EXACT, MatchPassType.TOLERANCE,
                MatchPassType.AMOUNT_DATE, MatchPassType.TDS_GST,
            )
            # For same-side netting pairs BOTH entries live on the SAME side
            # (company or vendor, per reversal_side) — record them both under
            # that side's id list (no cross-side counterpart).
            if is_same_side_netting:
                if pair.reversal_side == "vendor":
                    company_ids: list[str] = []
                    vendor_ids = [str(pair.company_entry_id), str(pair.vendor_entry_id)]
                else:
                    company_ids = [str(pair.company_entry_id), str(pair.vendor_entry_id)]
                    vendor_ids = []
            else:
                company_ids = [str(pair.company_entry_id)]
                vendor_ids = [str(pair.vendor_entry_id)]
            match_data = {
                "id": match_id,
                "case_id": case_id,
                "pass_number": pair.pass_number,
                "match_type": "reversal" if is_same_side_netting else "pair",
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
                # Groups generally need confirmation (Req 5.11), EXCEPT
                # TDS_LINK groups: the underlying pair was already an
                # auto-accepted EXACT/TOLERANCE/AMOUNT_DATE match, and the
                # TDS leg is a deterministic, already-computed linkage
                # (tds_parent_entry_id from transformation), not a
                # probabilistic combination like one-to-many/many-to-one.
                "is_confirmed": group.pass_number == TDS_LINK_PASS,
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
            document_type = getattr(entry, "document_type", "") or ""
            # Prefer a category already computed/saved on the entry
            # (e.g. via the Map Document Type screen); otherwise derive it
            # from the document type so matching can gate on it.
            category = (getattr(entry, "document_category", "") or "").strip()
            if not category:
                category = _derive_category(document_type)
            derived_invoice_number = getattr(entry, "derived_invoice_number", "") or ""
            result.append(
                LedgerEntryData(
                    id=getattr(entry, "id"),
                    amount=Decimal(str(getattr(entry, "amount", 0))),
                    posting_date=getattr(entry, "posting_date", None),
                    reference_number=getattr(entry, "reference_number", "") or "",
                    document_number=getattr(entry, "document_number", "") or "",
                    side=getattr(entry, "side", ""),
                    document_type=document_type,
                    assignment_number=getattr(entry, "assignment_number", "") or "",
                    category=category,
                    derived_invoice_number=derived_invoice_number,
                    invoice_number=_best_invoice_number(
                        derived_invoice_number, getattr(entry, "document_number", "") or ""
                    ),
                    is_tds=bool(getattr(entry, "is_tds", False)),
                    tds_parent_entry_id=getattr(entry, "tds_parent_entry_id", None),
                )
            )
        return result
