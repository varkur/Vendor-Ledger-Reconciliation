"""
Reconciliation export service.

Builds a multi-sheet Excel workbook matching the reference Firmway export format:
  1. Summary       — header block + "Reconciliation Statement" table
  2. Reconciliation — ALL entries (matched pairs on one row, one-sided otherwise),
                      colour-coded: blue=company, yellow=party, red=difference,
                      green=metadata.
  3. Annexure sheets — one per difference category (named by annexure number),
                      referenced from the Summary "Annexure" column.
  4. Party         — all vendor/party-side entries.

The workbook is generated purely from persisted data (ledger entries + match
results) so it reflects exactly what the engine produced.
"""

from __future__ import annotations

import io
from datetime import datetime
from decimal import Decimal

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from src.domain.services.vlr.reconciliation_engine_service import (
    OTHER_ENTRY_PASS,
    MatchPassType,
    _is_tax_band_gap,
    _REVERSAL_SUFFIX_RE,
)

# Categories treated as "Invoice-like" for classification-label purposes —
# an Invoice, Debit Note, or Credit Note pair gets its own distinct label
# instead of the generic pass-based one (see _classification).
_INVOICE_LIKE_CATEGORIES = frozenset({"Invoice", "Debit Note", "Credit Note"})
_DN_CN_CATEGORIES = frozenset({"Debit Note", "Credit Note"})


# ── Colour palette (matches the reference export) ──
FILL_COMPANY = PatternFill("solid", fgColor="1E88E5")   # blue
FILL_PARTY = PatternFill("solid", fgColor="F4C20D")     # yellow
FILL_DIFF = PatternFill("solid", fgColor="E53935")      # red
FILL_META = PatternFill("solid", fgColor="7CB342")      # green
FILL_GROUP = PatternFill("solid", fgColor="F4C20D")     # yellow group header (summary)
FILL_GREEN = PatternFill("solid", fgColor="7CB342")     # green header (summary)
WHITE_BOLD = Font(bold=True, color="FFFFFF")
BOLD = Font(bold=True)


# ── Match pass → human-readable classification ──
# Taxonomy verified against a real Firmway reconciliation export (see
# docs/Reconciliation-INOX-*.xlsx). Each pass maps to a distinct Classification
# so a genuine invoice-number match is never visually indistinguishable from a
# match that only compared amount + date (the bug that caused an Emcure
# invoice to appear "matched" against the wrong invoice while showing an
# exact-match-looking label).
#
# pass numbers per MatchPassType: 1 EXACT, 2 TOLERANCE, 3 FUZZY_REFERENCE,
# 4 ONE_TO_MANY, 5 MANY_TO_ONE, 6 DATE_PROXIMITY, 7 UNMATCHED,
# 10 AMOUNT_DATE (was mislabeled as EXACT), 11 TDS_GST (was mislabeled as
# TOLERANCE), 12 TOLERANCE_DATE (was mislabeled as TOLERANCE).
PASS_CLASSIFICATION: dict[int, str] = {
    1: "Invoice Number Matched",                  # amount + date + reference(invoice no) all identical
    2: "Invoice Number Matched",                  # reference exact, amount within tolerance (small write-off)
    3: "Partial Invoice Number Matched",          # reference SIMILAR (not exact) — never claim full invoice match
    4: "Multiple Date and Amount Matched",        # one company ↔ many party (subset-sum by date)
    5: "Multiple Date and Amount Matched",        # many company ↔ one party
    6: "Date and Amount Matched - Recommended",   # date-proximity fallback, reference not checked
    MatchPassType.AMOUNT_DATE: "Date and Amount Matched",              # amount exact, reference NEVER checked
    MatchPassType.TDS_GST: "Invoice Number Matched",                   # reference similarity >= 0.5 required
    MatchPassType.TOLERANCE_DATE: "Date Range and Amount Matched",     # neither exact amount nor reference matched
    # Same invoice number AND same date on both sides, but the amount gap
    # doesn't match the configured TDS/GST rate — per explicit correction,
    # still matched (not left as two separate open items) and classified
    # as an invoice-number match with a genuine, reviewable discrepancy.
    MatchPassType.AMOUNT_MISMATCH: "Amount Mismatch",
}

# Match pass → derived rule code (our own taxonomy, prefixed VLR-)
PASS_RULE_CODE: dict[int, str] = {
    1: "VLR-EXACT-1.0",
    2: "VLR-TOLERANCE-2.0",
    3: "VLR-FUZZYREF-3.0",
    4: "VLR-ONE2MANY-4.0",
    5: "VLR-MANY2ONE-5.0",
    6: "VLR-DATEPROX-6.0",
    MatchPassType.AMOUNT_DATE: "VLR-AMTDATE-1.5",
    MatchPassType.TDS_GST: "VLR-TDSGST-2.5",
    MatchPassType.TOLERANCE_DATE: "VLR-TOLDATE-6.5",
    MatchPassType.AMOUNT_MISMATCH: "VLR-AMTMISMATCH-15.0",
    MatchPassType.REFERENCE_GROUPED: "VLR-REFGROUPED-16.0",
    MatchPassType.DATE_GROUPED: "VLR-DATEGROUPED-17.0",
}


def _classification(pass_number: int | None, c_entry=None, p_entry=None) -> str:
    """
    Map a match pass to its human-readable Classification label.

    `c_entry`/`p_entry` are optional — when supplied, a Payment-category or
    Debit Note/Credit Note-category pair gets a distinct, client-mandated
    label instead of the generic pass-based one for passes whose match
    condition is category-agnostic (blind amount+date/tolerance-date/
    subset-sum passes never inspect category on their own, so the label
    must branch here instead). Passes that are ALREADY category-specific by
    construction (invoice-number-aware passes, which per the engine's
    _requires_invoice_number_match rule never fire for Payment entries at
    all) are left exactly as before.
    """
    if pass_number is None:
        return "Unmatched"
    pn = int(pass_number)
    if pn == 8:
        return "Manually Mapped"
    if pn in (9, 13):
        # 9 = knock-off (AB) same-side netting, 13 = "Other entry" (SA)
        # same-side netting — both are entry-intrinsic reversals per the
        # mapping doc, shown identically as "Reversal Entries".
        return "Reversal Entries"
    if pn == MatchPassType.CROSS_DOCTYPE_REVERSAL:
        # Recommended candidate, not yet approved — a same-side
        # cancellation between two DIFFERENT doc types (see
        # _cross_doctype_reversal_candidates). Once a reviewer approves
        # it via /confirm, the match record is re-stamped to pass 8 and
        # this branch no longer applies (see confirm_match's ACCEPT
        # branch) — the row then reads "Manually Mapped" like any other
        # manual link, matching the client's own worked example
        # (Classification "Manually Matched").
        return "Reversal Entries (Recommended)"
    if pn == 14:
        # TDS Sequential Link: an invoice pair matched cleanly first, then a
        # separate standalone TDS ledger line linked to it as a third leg.
        return "Invoice Number Matched"

    c_cat = (getattr(c_entry, "document_category", "") or "").strip()
    p_cat = (getattr(p_entry, "document_category", "") or "").strip()
    is_dn_cn_pair = c_cat in _DN_CN_CATEGORIES or p_cat in _DN_CN_CATEGORIES
    is_payment_pair = c_cat == "Payment" or p_cat == "Payment"

    # Client mapping-doc scenario "Amount Matched - Recommended" (DN/CN):
    # a Debit Note/Credit Note pair matched via a tolerance-style pass
    # (small write-off or TDS-band gap) — distinct from the generic
    # invoice-number label these passes otherwise produce.
    if is_dn_cn_pair and pn in (2, MatchPassType.TDS_GST, MatchPassType.TOLERANCE_DATE):
        return "Amount Matched - Recommended"

    # Client mapping-doc scenario "Payment Matched - Recommended": a
    # Payment pair matched via a tolerance-style pass (small write-off/
    # rounding gap or date-range tolerance) — distinct from the generic
    # "Date and Amount Matched"/"Date Range and Amount Matched" labels
    # those passes otherwise produce for non-Payment entries.
    if is_payment_pair and pn in (2, MatchPassType.TOLERANCE_DATE):
        return "Payment Matched - Recommended"

    # New passes (see reconciliation_engine_service.py): a shared invoice/
    # assignment-number reference tying a multi-entry group together
    # ("Multiple Based on Invoice Number"), or a multi-entry date cluster
    # with no reference correlation ("Multiple Based on Date").
    if pn == MatchPassType.REFERENCE_GROUPED:
        return "Multiple Based on Invoice Number"
    if pn == MatchPassType.DATE_GROUPED:
        return "Multiple Based on Date"
    if pn == MatchPassType.INVOICE_GROUP_SUM:
        # Payment / TDS Adjusted entries grouped independently by invoice
        # number on EACH side, matched group-to-group on an exact sum —
        # see _invoice_group_sum_match. Always an exact match by
        # construction (no tolerance band), so this is never "Recommended".
        return "Multiple Based on Invoice Number"

    return PASS_CLASSIFICATION.get(pn, "Date and Amount Matched")


def _status(
    pass_number: int | None,
    c_entry,
    p_entry,
    difference: float,
    tds_percentage: float = 0.0,
    gst_percentage: float = 0.0,
    tds_percentage_min: float = 0.0,
) -> str:
    """
    Row-level Status (distinct from Classification). Reconciled unless the
    match carries a genuine residual difference, in which case Firmway
    reports the specific reason:
      - Pass 2/TOLERANCE (reference matched exactly, amount off by a small
        rounding/write-off amount, OR a gap that fits the configured
        TDS%/GST%) -> "Write off / Rounding off" or "TDS Booked by ..."
      - Pass TDS_GST (amount gap explained by a TDS/GST rate) -> "TDS Booked
        by Company" or "TDS Booked by Party", whichever side shows the
        SMALLER absolute amount (i.e. the side that had tax withheld/deducted)
      - Pass 8 (manual link) -> "Manually Mapped" (the reviewer's own
        selected reason is shown separately in the Remark column)
      - Everything else that matched -> "Reconciled"

    A gap is only ever labelled "TDS Booked by ..." if it falls within the
    case's configured TDS% RANGE [tds_percentage_min, tds_percentage] or
    matches the configured GST% almost exactly — using the exact same
    _is_tax_band_gap range check the matching engine itself used to decide
    this pair was TDS-explained in the first place (see
    reconciliation_engine_service.py).

    Client-confirmed bug (round 1): a flat "difference > Rs 5" check with
    no upper bound mislabelled gaps of tens/hundreds of thousands of
    rupees as "TDS Booked by Company" — those are a genuine amount
    mismatch, not a tax adjustment. Fixed by bounding the check to the
    configured rate.

    Client-confirmed bug (round 2): the bound-to-configured-rate fix above
    checked only the flat Max rate as a single number, e.g. a configured
    "TDS 0%-10%" range collapsed to "must be within 1% of a 10% gap" —
    so a REAL TDS deduction at any other rate within that range (a
    genuine ~0.08% deduction, well inside 0%-10%) still fell through to
    "Unexplained Amount Gap" even though the matching engine's own
    _is_tax_band_gap (a proper Min-Max range check) had already matched
    the pair correctly as TDS-explained. This function must agree with
    that same range check, not re-derive tax-matching from a different,
    narrower formula.
    """
    if pass_number is None:
        return ""
    pn = int(pass_number)
    if pn == 8:
        return "Manually Mapped"
    if pn in (9, 13, MatchPassType.CROSS_DOCTYPE_REVERSAL):
        # Matches the client's own worked example (Mapping Process.xlsx,
        # "Reversal" sheet): Status "Reversal Entries" even while the
        # Classification still reads "Manually Matched" pending review
        # (see _classification's CROSS_DOCTYPE_REVERSAL branch above).
        return "Reversal Entries"
    if pn == 14:
        # TDS Sequential Link group: exported as 2 rows — the parent
        # invoice pair row (both c_entry AND p_entry present, no residual
        # gap -> Reconciled) and the linked TDS leg's own row (only ONE
        # side present, since the TDS entry has no counterpart on the
        # other ledger -> attribute to whichever side it's actually on).
        if c_entry and p_entry:
            return "Reconciled"
        return "TDS Booked by Company" if c_entry else "TDS Booked by Party"

    c_amt = abs(_num(getattr(c_entry, "amount", 0))) if c_entry else 0.0
    p_amt = abs(_num(getattr(p_entry, "amount", 0))) if p_entry else 0.0

    # Client-confirmed rule: on an Invoice-to-Invoice pair, only "TDS
    # Booked by Company" is ever valid — a vendor doesn't withhold tax
    # from its own invoice, so "TDS Booked by Party" never makes sense
    # for a pure invoice comparison. Both directions stay valid for
    # Payment (and other non-invoice) pairs, where either side may have
    # booked a TDS deduction independently. Confirmed against the client's
    # own worked examples: the Invoice sheet's two TDS-gap rows both show
    # "TDS Booked by Company" (never "...by Party"); the standalone TDS
    # sheet's "TDS Booked by Party" example is a standalone vendor-side
    # entry with no company counterpart at all (handled separately by
    # _special_classification, untouched by this rule).
    c_cat = (getattr(c_entry, "document_category", "") or "").strip()
    p_cat = (getattr(p_entry, "document_category", "") or "").strip()
    is_invoice_pair = (
        c_cat in _INVOICE_LIKE_CATEGORIES and p_cat in _INVOICE_LIKE_CATEGORIES
    )

    def _tds_side(smaller_side_is_company: bool) -> str:
        if is_invoice_pair:
            return "TDS Booked by Company"
        return "TDS Booked by Company" if smaller_side_is_company else "TDS Booked by Party"

    def _matches_tax_amount(gap: float) -> bool:
        """Range-aware TDS/GST check — same logic (and same base-amount
        conventions: TDS off the larger amount, GST off the smaller) as
        the matching engine's own _is_tax_band_gap, so the Status label
        never disagrees with why the engine actually matched this pair."""
        if c_amt <= 0 or p_amt <= 0:
            return False
        tds_min_frac = Decimal(str(tds_percentage_min / 100.0)) if tds_percentage_min > 0 else Decimal("0")
        tds_max_frac = Decimal(str(tds_percentage / 100.0)) if tds_percentage > 0 else Decimal("0")
        gst_frac = Decimal(str(gst_percentage / 100.0)) if gst_percentage > 0 else Decimal("0")
        return _is_tax_band_gap(
            Decimal(str(gap)), Decimal(str(c_amt)), Decimal(str(p_amt)),
            tds_min_frac, tds_max_frac, gst_frac,
        )

    if pn == MatchPassType.AMOUNT_MISMATCH:
        # Same invoice number AND same date on both sides (see
        # _amount_mismatch_match in reconciliation_engine_service.py), but
        # the amount gap is NOT explained by the configured TDS/GST rate.
        #
        # Per explicit correction: do NOT report this as "Reconciled" —
        # the pair is linked/identified as the same invoice for review
        # purposes, but the money does not actually tie out, so Status
        # must say so. Status is now "Amount Mismatch" whenever the gap
        # exceeds the configured TDS tolerance band; the defensive
        # tax-band check below only fires if a gap somehow reaches this
        # pass despite genuinely matching a configured rate (shouldn't
        # normally happen — _amount_mismatch_match itself already skips
        # tax-explained gaps before creating this pass's pairs — but kept
        # here so Status/Classification never disagree if that ever
        # changes).
        if c_amt > 0 and p_amt > 0 and _matches_tax_amount(abs(difference)):
            return _tds_side(c_amt < p_amt)
        return "Amount Mismatch"
    if pn == 2 and abs(difference) > 0.005:
        # Pass 2 (_tolerance_match) now covers both small rounding
        # differences AND TDS/GST-sized gaps on an exact invoice-number
        # match (widened so those pairs don't fall through to the weaker
        # amount-only pass 12 and lose their invoice-number classification).
        # A gap in the TDS/GST range should report as TDS booked, not a
        # generic write-off — the same side-attribution logic as TDS_GST.
        # But it must actually MATCH the configured TDS%/GST% almost
        # exactly — otherwise it's a real amount mismatch.
        if abs(difference) > 5 and c_amt > 0 and p_amt > 0:
            if _matches_tax_amount(abs(difference)):
                return _tds_side(c_amt < p_amt)
            # Defensive fallback only — a same-invoice-number, same-date
            # pair with an unexplained gap should already have been
            # claimed by pass 15 (AMOUNT_MISMATCH) before reaching here;
            # this covers a pair matched on invoice number alone with a
            # DIFFERENT date, where "Amount Mismatch" would overstate how
            # confidently these are the same transaction.
            return "Unexplained Amount Gap"
        return "Write off / Rounding off"
    if pn == MatchPassType.TDS_GST:
        # The side with the SMALLER absolute amount had tax withheld/deducted
        # from it, so that side is the one that "booked" the TDS.
        if c_amt > 0 and p_amt > 0:
            if _matches_tax_amount(abs(difference)):
                return _tds_side(c_amt < p_amt)
            return "Unexplained Amount Gap"
        return "Reconciled"
    if pn == MatchPassType.TOLERANCE_DATE:
        # Client-confirmed bug (screenshot): "Date Range and Amount Matched"
        # rows with a genuine TDS-range gap (e.g. company 50780 vs vendor
        # 51656, diff 876) showed Status "Reconciled" — this pass had NO
        # tax-band check at all, unlike pass 2/TDS_GST above, so a real TDS
        # deduction went unreported. Same side-attribution rule: the side
        # with the SMALLER absolute amount had tax withheld/deducted from
        # it, so that side "booked" the TDS.
        if c_amt > 0 and p_amt > 0 and _matches_tax_amount(abs(difference)):
            return _tds_side(c_amt < p_amt)
        # Per explicit correction (same treatment as pass 15/AMOUNT_MISMATCH
        # above): this pass is the weakest matching tier — no exact amount,
        # no invoice-number correlation at all, matched purely on amount-
        # within-tolerance + date proximity. A genuine, non-negligible gap
        # that isn't explained by the configured TDS/GST rate must NOT be
        # reported as "Reconciled" — that overstates how settled the pair
        # actually is. A truly negligible/rounding-level gap (<= a paisa,
        # same 0.005 threshold used elsewhere in this module) still counts
        # as settled.
        if abs(difference) > 0.005:
            return "Amount Mismatch"
        return "Reconciled"
    return "Reconciled"


def _invoice_number(entry) -> str:
    """
    Best invoice number for an entry. Prefers the derived/document number, but
    when that's a synthetic placeholder (BAL_ROW_*) or blank, recovers the real
    value from the original uploaded row (raw_data) using common invoice-column
    header aliases.
    """
    if entry is None:
        return ""
    derived = getattr(entry, "derived_invoice_number", None)
    doc = getattr(entry, "document_number", None)
    for candidate in (derived, doc):
        if candidate and not str(candidate).startswith("BAL_ROW_"):
            return str(candidate)
    # Fall back to the original uploaded row.
    val = _raw(entry, [
        "inv no", "inv no.", "invoice no", "invoice no.", "invoice number",
        "inv number", "trx number", "transaction number", "bill no",
        "document number", "doc no", "voucher no", "vch no.", "reference",
    ], "")
    # Bug fix: for balance rows (Opening/Closing Balance) — and potentially
    # any row re-processed from a previous export/pipeline run — raw_data's
    # own "document number"/"reference" aliases can themselves already BE
    # the placeholder (e.g. raw_data={"document number": "BAL_ROW_167", ...}),
    # so this fallback needs the same BAL_ROW_* rejection as every other
    # lookup here, otherwise the placeholder round-trips right back out.
    if val and not str(val).startswith("BAL_ROW_"):
        return str(val)
    # Bug fix: this used to fall back to `derived or doc`, which returns the
    # raw synthetic BAL_ROW_* placeholder itself (e.g. "BAL_ROW_82") when no
    # real invoice number could be recovered from raw_data — client: "don't
    # need to fill the invoice number column with this BAL_ROW". Both
    # `derived` and `doc` were already excluded by the loop above whenever
    # they started with "BAL_ROW_", so if we reach here neither is usable —
    # leave the invoice number genuinely blank in the export, matching the
    # API-side equivalent (entry_columns.invoice_number) used by the
    # matched/unmatched drill-in screens.
    return ""


def _entry_signals(entry) -> str:
    """Concatenate the entry's type/category/remark/narration into one
    lowercase blob for keyword detection. Pulls from both the modelled fields
    and the original uploaded row (raw_data)."""
    if entry is None:
        return ""
    parts = [
        getattr(entry, "document_type", "") or "",
        getattr(entry, "document_category", "") or "",
        getattr(entry, "description", "") or "",
    ]
    raw = getattr(entry, "raw_data", None) or {}
    if raw:
        # Type / Remark / Narration style columns most often carry the markers.
        for k, v in raw.items():
            kl = str(k).strip().lower()
            if any(t in kl for t in ("type", "remark", "narration", "particular", "description", "text")):
                parts.append(str(v or ""))
    return " ".join(parts).lower()


def _special_classification(entry, side: str | None = None) -> str | None:
    """
    Detect entry-intrinsic classifications that don't depend on the match pass:
    Opening Balance, Closing Balance, Reversal Entries (knock-off), and
    TDS Booked by Company/Party. Returns None when no special class applies
    (so the caller falls back to the pass-based classification).

    `side` ("company" or "party"/"vendor") tells us which ledger the entry
    physically sits on, so a standalone TDS entry is attributed to the side
    that actually booked it. Client-confirmed bug: this used to hardcode
    "TDS Booked by Party" for EVERY unmatched TDS entry regardless of side
    — a genuine company-side TDS rectification entry (doc type SA,
    narration "TDS RECT.") was mislabeled "TDS Booked by Party" when it was
    actually booked by the Company. `side` is optional (defaults to the
    Party label) so existing call sites that don't have side info handy
    keep their prior behavior; every call site that DOES know the side now
    passes it through.
    """
    if entry is None:
        return None
    sig = _entry_signals(entry)
    dtype = (getattr(entry, "document_type", "") or "").strip().lower()

    # Opening / Closing balance rows (Type "op"/"CL" or "opening/closing bal").
    if "opening bal" in sig or dtype in ("op", "ob", "opbal"):
        return "Opening Balance"
    if "closing bal" in sig or dtype in ("cl", "cb", "clbal"):
        return "Closing Balance"

    # Reversal / knock-off entries. SAP doc type "AB" is the reversal doc type;
    # the category is mapped to "knocking off" in the reference.
    #
    # Client-confirmed bug (real data, AUTOPACK INDUSTRIES/EPL): a genuine,
    # correctly-matched Invoice for a physical product literally named
    # "UNIVERSAL REVERSE BENDING TOOL(ELMACH)" got silently reclassified
    # as "Reversal Entries" purely because its narration text contains the
    # substring "reverse" — nothing to do with the entry actually being a
    # reversal. Since _special_classification's callers (bucket() in
    # _compute_summary) treat "Reversal Entries" as entry-intrinsic and
    # EXCLUDE it entirely from the Summary sheet's difference accounting
    # (it's assumed to net to zero within one side, per the mapping doc),
    # this one false-positive silently dropped a real matched entry's
    # amount out of the Summary's closing-balance identity — corrupting
    # the final "Difference" row by exactly that entry's amount, with no
    # visible trace of what happened.
    #
    # "reversal"/"reverse" as bare keyword substrings are too broad for a
    # free-text narration field (any product/description containing that
    # English word false-positives). Narrowed to the same doc-number
    # reclass-suffix pattern _is_reversal() already uses in
    # reconciliation_engine_service.py ("-R"/"-RE"/"-Rev" suffix on the
    # invoice number itself) plus "knock"/explicit "reversal entr(y/ies)"
    # phrasing — not a bare "reverse" substring match on narration text.
    derived_inv = getattr(entry, "derived_invoice_number", "") or ""
    doc_no = getattr(entry, "document_number", "") or ""
    reversal_suffix_hit = (
        _REVERSAL_SUFFIX_RE.search(str(derived_inv)) or _REVERSAL_SUFFIX_RE.search(str(doc_no))
    )
    if dtype == "ab" or "knock" in sig or "reversal entr" in sig or reversal_suffix_hit:
        return "Reversal Entries"

    # "Other entry" (SA) rows — per the mapping doc these are internal to
    # each side and only net against ANOTHER SA entry on the same side
    # (_other_entry_match / OTHER_ENTRY_PASS). An UNPAIRED SA entry (no
    # same-side counterpart of equal & opposite amount — never actually
    # matched via that same-side-netting pass) is NOT an internal reversal;
    # it is a genuine open item. Client-confirmed bug: an unmatched SA entry
    # (e.g. "MSME Interest", amount -664.73, no counterpart) kept showing
    # under "Reversal Entries" purely because of its raw doc type/category,
    # even though it never netted against anything. Per the mapping doc's
    # own "Open Item Status" section ("Remaining entries open from Emcure/
    # vendor, then other entry not booked by vendor/company"), an unpaired
    # SA entry must fall through to normal open-item classification (Other
    # Differences / "Other entry not booked by Company/Party") so it shows
    # up as a genuine unmatched entry, not a hidden reversal.
    cat = (getattr(entry, "document_category", "") or "").strip()
    if (dtype == "sa" or cat == "Adjusted") and getattr(entry, "pass_number", None) == OTHER_ENTRY_PASS:
        return "Reversal Entries"

    # TDS entries (tagged by the transformation pass, or doc type/remark = TDS).
    # The side the entry actually sits on is the side that "booked" the TDS
    # — a company-ledger TDS entry is "TDS Booked by Company", a vendor-
    # ledger one is "TDS Booked by Party". Same side-attribution rule used
    # everywhere else in this module (party_missing when side=="company",
    # company_missing when side=="party").
    # Bug fix: this TDS-keyword/is_tds check used to fire unconditionally,
    # even on an entry that is PART OF a genuine cross-side match (e.g. a
    # Payment/TDS Adjusted entry whose narration happens to contain "TDS"
    # but which _invoice_group_sum_match already matched, exactly, against
    # a real vendor-side counterpart). That silently overrode a correct
    # "Reconciled, zero difference" row with a misleading "TDS Booked by
    # ..." label implying it's an unexplained one-sided TDS entry. Only
    # apply this special-case label when the entry has NO real match at
    # all (pass_number is None) — a genuinely matched entry's label comes
    # from _classification instead.
    if getattr(entry, "pass_number", None) is None and (
        getattr(entry, "is_tds", False) or "tds" in sig or dtype in ("tds", "wt")
    ):
        return "TDS Booked by Company" if side == "company" else "TDS Booked by Party"

    return None


def _has_reversal_doc_marker(c, p) -> bool:
    """
    True when either side's invoice number literally reads like a reversal
    placeholder (e.g. "Reversal Doc"), independent of the doc-type-based
    _special_classification check above (which only inspects narration/type
    fields, never the invoice number itself). This is intentionally a
    Remark-only signal — it must NEVER change Status/Classification, only
    flag the row for the reviewer.
    """
    for entry in (c, p):
        if entry is None:
            continue
        inv = _invoice_number(entry)
        if inv and "reversal" in str(inv).strip().lower():
            return True
    return False


def _auto_remark(classification: str, existing_remark: str, c, p) -> str:
    """
    Rule-driven explanatory remark for the Remark column, matching the
    client-annotated reference export (docs/Reconciliation-DYNAMIC-EVENTS---
    PRODUCTION.xlsx, "Correct Remark" column) so every row's remark is
    derived consistently from its Classification rather than left blank.

    Never overwrites an existing remark — a reviewer's manual-link reason
    (pass 8) always takes priority over any auto-generated text.

    Priority (verified against every row of the reference export):
      1. existing_remark (manual link) — always wins.
      2. Classification == "Reversal Entries" (SA/AB same-side netting) ->
         explain that this is an Emcure-internal entry showing as a reversal.
      3. Either side's invoice number literally reads like a reversal
         placeholder (e.g. "Reversal Doc") even when NOT auto-classified as
         a Reversal Entry (matched cross-side by date+amount, or genuinely
         one-sided/unmatched) -> flag it for the reviewer as "Reversal
         Entries" without changing its actual Status/Classification.
      4. Classification == "Date Range and Amount Matched" (fell back to
         amount + date-range instead of an exact invoice-number match) ->
         note that invoices should primarily be matched by invoice number.
      5. Otherwise blank.
    """
    if existing_remark:
        return existing_remark
    if classification == "Reversal Entries":
        return "Emcure internal transaction is being showing as a reversal"
    if _has_reversal_doc_marker(c, p):
        return "Reversal Entries"
    if classification == "Date Range and Amount Matched":
        return "Invoices should primarily be matched by invoice number"
    return ""


def _rule_code(pass_number: int | None) -> str:
    if pass_number is None:
        return ""
    if int(pass_number) == 8:
        return "VLR-MANUAL-8.0"
    if int(pass_number) == 9:
        return "VLR-REVERSAL-9.0"
    if int(pass_number) == 13:
        return "VLR-OTHERENTRY-13.0"
    if int(pass_number) == 14:
        return "VLR-TDSLINK-14.0"
    return PASS_RULE_CODE.get(int(pass_number), "VLR-MATCH")


def _num(value) -> float:
    if value is None:
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _fmt_date(value) -> str:
    if value is None:
        return ""
    try:
        return value.strftime("%d-%m-%Y")
    except AttributeError:
        return str(value)


def _raw(entry, header_aliases: list[str], fallback=""):
    """Look up a value from the entry's raw_data (original uploaded row) by any
    of the given header aliases (case-insensitive). Falls back to the modelled
    value when the column wasn't in the upload."""
    if entry is None:
        return ""
    raw = getattr(entry, "raw_data", None) or {}
    if raw:
        # raw_data keys are the normalized (lowercased, stripped) source headers
        norm = {str(k).strip().lower(): v for k, v in raw.items()}
        for alias in header_aliases:
            v = norm.get(alias.strip().lower())
            if v not in (None, "", "None"):
                return v
    return fallback


# ── Difference-category → Summary status labels + annexure buckets ──
# Maps a document_category to the two summary "not booked by" lines.
CATEGORY_TO_SUMMARY = {
    "Invoice": {
        "group": "Invoice Difference",
        "company_missing": "Invoice not booked by Company",
        "party_missing": "Invoice not booked by Party",
        "company_action": "Vendor to provide the invoice copies",
        "party_action": "Vendor to check the reason for invoice not appearing",
    },
    "Credit Note": {
        "group": "Debit Note / Credit Note Difference",
        "company_missing": "Credit Note not booked by Company",
        "party_missing": "Credit Note not booked by Party",
        "company_action": "Company to book the Credit Note and recover from Vendor",
        "party_action": "Vendor to book the Credit Note",
    },
    "Debit Note": {
        "group": "Debit Note / Credit Note Difference",
        "company_missing": "Debit Note not booked by Company",
        "party_missing": "Debit Note not booked by Party",
        "company_action": "Company to book the Debit Note and recover from Vendor",
        "party_action": "Vendor to book the Debit Note",
    },
    "Payment": {
        "group": "Payment / receipt Difference",
        "company_missing": "Payment not booked by Company",
        "party_missing": "Payment not booked by Party",
        "company_action": "Company to book the payment entries",
        "party_action": "Vendor to check the payment details",
    },
    "Receipt": {
        "group": "Payment / receipt Difference",
        "company_missing": "Receipt not booked by Company",
        "party_missing": "Receipt not booked by Party",
        "company_action": "Company to book the receipt entries",
        "party_action": "Vendor to check the receipt details",
    },
    # Unmatched TDS entries (see _special_classification's "TDS Booked by
    # Party"/"TDS Booked by Company") must roll up under the dedicated
    # "TDS / TCS Difference" summary group, not "Other Differences" — the
    # group already exists in group_order below but was never populated
    # because these entries fell through to DEFAULT_SUMMARY.
    "TDS Adjusted": {
        "group": "TDS / TCS Difference",
        "company_missing": "TDS not booked by Company",
        "party_missing": "TDS not booked by Party",
        "company_action": "Company to book the TDS entry",
        "party_action": "Vendor to book the TDS entry",
    },
}
DEFAULT_SUMMARY = {
    "group": "Other Differences",
    "company_missing": "Other entry not booked by Company",
    "party_missing": "Other entry not booked by Party",
    "company_action": "",
    "party_action": "",
}

# ── Status label -> Action Tracker "Action Taken Status" bucket ──
#
# Reverse-lookup built from CATEGORY_TO_SUMMARY: any status that is a
# "company_missing" label means the COMPANY needs to act (book the missing
# entry) -> bucket is "Pending with Company"; a "party_missing" label means
# the VENDOR needs to act -> "Pending with Party". TDS gaps follow the same
# convention as every other side-attribution in this module ("TDS Booked by
# Company" means the ledger that's missing the TDS entry needing action is
# the PARTY side, mirroring _unmatched_status's existing special-case
# ordering) — kept explicit here rather than derived, since TDS entries
# don't go through CATEGORY_TO_SUMMARY's normal company/party branch.
_STATUS_TO_ACTION_BUCKET: dict[str, str] = {}
for _info in CATEGORY_TO_SUMMARY.values():
    _STATUS_TO_ACTION_BUCKET[_info["company_missing"]] = "Pending with Company"
    _STATUS_TO_ACTION_BUCKET[_info["party_missing"]] = "Pending with Party"
_STATUS_TO_ACTION_BUCKET[DEFAULT_SUMMARY["company_missing"]] = "Pending with Company"
_STATUS_TO_ACTION_BUCKET[DEFAULT_SUMMARY["party_missing"]] = "Pending with Party"
_STATUS_TO_ACTION_BUCKET["TDS Booked by Company"] = "Pending with Party"
_STATUS_TO_ACTION_BUCKET["TDS Booked by Party"] = "Pending with Company"
_STATUS_TO_ACTION_BUCKET["Amount Mismatch"] = "Pending with Party"


def derive_action_taken_status(row: dict) -> str:
    """
    Map a row dict's `status` (and `difference` as a fallback signal) to the
    3-value Action Tracker bucket: "Pending with Company", "Pending with
    Party", or "No Action Required".

    Opening/Closing Balance rows and any row with no outstanding residual
    difference (fully reconciled, write-off/rounding within tolerance) need
    no action. Everything else falls back to whichever side is missing the
    entry per _STATUS_TO_ACTION_BUCKET; if the status isn't recognised at
    all, the presence of a non-zero difference still routes it to the side
    that's one-sided (`_side` == "company" -> party must act, and vice
    versa), defaulting to "No Action Required" only when there is truly
    nothing outstanding.
    """
    status = row.get("status") or ""
    if status in ("Opening Balance", "Closing Balance", "Reversal Entries"):
        return "No Action Required"
    bucket = _STATUS_TO_ACTION_BUCKET.get(status)
    if bucket is not None:
        return bucket
    try:
        diff = abs(Decimal(str(row.get("difference", 0) or 0)))
    except Exception:
        diff = Decimal("0")
    if diff < Decimal("0.005"):
        return "No Action Required"
    side = row.get("_side")
    if side == "company":
        return "Pending with Party"
    if side == "party":
        return "Pending with Company"
    return "No Action Required"


class ReconciliationExportService:
    """Builds the reconciliation export workbook from persisted case data."""

    # Class-level defaults so `_build_recon_rows`/`_row` never crash with an
    # AttributeError when called directly (e.g. from tests, or any future
    # caller) without first going through `build()`, which is the only place
    # that normally sets these to the request's actual configured values.
    _tds_percentage_value: float = 0.0
    _tds_percentage_min_value: float = 0.0
    _gst_percentage_value: float = 0.0

    # Full 46-column header for the Reconciliation sheet (matches reference).
    # Bug fix: "Remark" was a WORKING column only (used internally to carry
    # the reviewer's manual-link reason / auto-generated explanatory note
    # into the row before it's rendered) and was never meant to ship in the
    # final client-facing output file — per explicit correction, it's
    # removed from the exported headers entirely. The underlying `remark`
    # value on each row dict is still computed and still drives
    # Status/Classification (e.g. the manual-link-reason override in
    # _row()) — only the exported COLUMN is removed, not the computation.
    RECON_HEADERS = [
        "Company Id", "Party Id", "Matched Id", "Status", "Classification",
        "Company Statement Type", "Company Invoice Date", "Company Invoice Number",
        "Company DocType", "Company Original DocType", "Company Narration", "Company Amount",
        "Party Statement Type", "Party Invoice Date", "Party Invoice Number",
        "Party DocType", "Party Original DocType", "Party Narration", "Party Amount",
        "Difference", "Matched Rule", "Reco Data & Time", "Party Code",
        "Daybook Name", "Company Clearing Document Number", "Company Clearing Date",
        "Company TDS Amount", "Company Posting Date", "Company Code", "Supplier",
        "Document Number", "Business Area", "Assignment", "Document Header Text",
        "Tax Code", "Year/Month", "Reference", "Profit Center", "Posting Date",
        "Amount in Doc. Curr.", "Document Currency", "Local Currency", "Entry Date",
        "Withhldg Tax Base Amount", "Payment Date",
    ]

    # Column groups (1-indexed) for colour coding the Reconciliation header.
    COMPANY_COLS = list(range(6, 13))     # Company Statement Type .. Company Amount
    PARTY_COLS = list(range(13, 20))      # Party Statement Type .. Party Amount
    DIFF_COLS = [20]                       # Difference
    META_COLS = list(range(1, 6)) + list(range(21, 46))  # ids/status/class + tail meta

    PARTY_HEADERS = [
        "Party Id", "Matched Id", "Status", "Classification", "Party Statement Type",
        "Party Invoice Date", "Party Invoice Number", "Party DocType",
        "Party Original DocType", "Party Narration", "Party Amount", "Matched Rule",
        "Reco Data & Time", "Party Clearing Document Number", "Party Clearing Date",
        "Party TDS Amount", "Party Posting Date",
    ]

    def build(
        self,
        *,
        case,
        vendor,
        company_entries: list,
        vendor_entries: list,
        match_results: list,
        reco_datetime: datetime,
        period_start,
        period_end,
        party_code: str = "",
        tolerance_amount: str = "1.0%",
        tds_percentage: str = "0.0 - 10.0",
        date_tolerance: str = "0 - 15",
        tds_percentage_value: float = 0.0,
        tds_percentage_min_value: float = 0.0,
        gst_percentage_value: float = 0.0,
    ) -> bytes:
        wb = Workbook()
        # Index entries by id for quick lookup.
        by_id = {str(e.id): e for e in company_entries + vendor_entries}

        self._reco_dt = reco_datetime.strftime("%d-%b-%y %I:%M %p")
        self._party_code = party_code
        # Real numeric TDS%/GST% (as configured on the request) — used to
        # bound the "TDS Booked by ..." status so it's never applied to a
        # gap larger than what the actual configured rate could explain.
        # `tds_percentage`/`tolerance_amount` above are display-only strings.
        #
        # tds_percentage_min_value: bug fix — the TDS Percentage setting is
        # a MIN/MAX range (e.g. 0%–10%), not a single rate, but this
        # Min value was never threaded through to the Status calculation
        # at all. _matches_tax_amount (below, via _status) only ever
        # checked the gap against a flat Max-rate amount, so a real
        # TDS-driven gap at any rate OTHER than exactly the configured Max
        # (e.g. a genuine ~0.08% deduction, with Max=10%) always failed
        # that check and was mislabeled "Unexplained Amount Gap" — even
        # though the matching engine's own _is_tax_band_gap (a proper
        # Min–Max range check) had already matched the pair correctly as
        # TDS-explained. The Status label must agree with the same range
        # check the engine used to create the match in the first place.
        self._tds_percentage_value = float(tds_percentage_value or 0)
        self._tds_percentage_min_value = float(tds_percentage_min_value or 0)
        self._gst_percentage_value = float(gst_percentage_value or 0)

        # Build match linkage: entry_id -> match record
        entry_match: dict[str, object] = {}
        for m in match_results:
            for cid in (m.company_entry_ids or []):
                entry_match[str(cid)] = m
            for vid in (m.vendor_entry_ids or []):
                entry_match[str(vid)] = m

        rows = self._build_recon_rows(company_entries, vendor_entries, match_results, by_id)

        # ── Sheet: Summary ──
        ws_summary = wb.active
        ws_summary.title = "Summary"
        annexure_map = self._compute_summary(
            ws_summary, vendor, company_entries, vendor_entries, match_results,
            period_start, period_end, tolerance_amount, tds_percentage, date_tolerance,
            rows,
        )

        # ── Sheet: Reconciliation ──
        self._write_recon_sheet(wb, rows)

        # ── Annexure sheets (one per difference bucket) ──
        self._write_annexures(wb, rows, annexure_map)

        # ── Sheet: Party ──
        self._write_party_sheet(wb, vendor_entries, entry_match)

        buf = io.BytesIO()
        wb.save(buf)
        return buf.getvalue()

    # ------------------------------------------------------------------ rows
    def _build_recon_rows(self, company_entries, vendor_entries, match_results, by_id):
        """Return a list of row dicts covering matched pairs + one-sided entries."""
        rows = []
        used = set()

        # Matched pairs/groups first (both sides present).
        for m in match_results:
            comp_ids = [str(x) for x in (m.company_entry_ids or [])]
            party_ids = [str(x) for x in (m.vendor_entry_ids or [])]
            for cid in comp_ids:
                used.add(cid)
            for vid in party_ids:
                used.add(vid)
            # A ONE-TO-MANY/MANY-TO-ONE group has more than one entry on one
            # side (e.g. 1 company entry <-> 2 vendor entries). _row() below
            # only ever sees ONE company entry and ONE vendor entry per row
            # (aligned by index), so its own c_amt+p_amt diff calculation is
            # meaningless for a group — it's comparing a single leg's amount
            # against a single leg on the other side, not the GROUP total.
            # Client-confirmed bug: this produced a nonsense non-zero
            # "Difference" on a payment-grouped-by-clearing-document match
            # that actually reconciles to zero as a whole. The match
            # record's OWN difference_amount (computed correctly across the
            # full group by _one_to_many_match/_many_to_one_match) is the
            # true group-level answer — use it for every row of a
            # multi-entry group instead of recomputing per-row.
            is_multi_entry_group = len(comp_ids) > 1 or len(party_ids) > 1
            group_diff = _num(getattr(m, "difference_amount", 0)) if is_multi_entry_group else None
            # Pair rows: align company[i] with party[i]; extras get their own row.
            maxlen = max(len(comp_ids), len(party_ids), 1)
            for i in range(maxlen):
                c = by_id.get(comp_ids[i]) if i < len(comp_ids) else None
                p = by_id.get(party_ids[i]) if i < len(party_ids) else None
                # Status is match-pass-aware (e.g. "Write off / Rounding off"
                # for small tolerance-matched differences, "TDS Booked by ..."
                # for TDS/GST gap matches) rather than a blanket "Reconciled".
                pn = getattr(c or p, "pass_number", None)
                c_amt = _num(getattr(c, "amount", 0)) if c else 0.0
                p_amt = _num(getattr(p, "amount", 0)) if p else 0.0
                row_diff = group_diff if group_diff is not None else (
                    (c_amt + p_amt) if (c and p) else 0.0
                )
                status = _status(
                    pn, c, p, row_diff,
                    self._tds_percentage_value, self._gst_percentage_value,
                    self._tds_percentage_min_value,
                )
                rows.append(self._row(c, p, m, status=status, row_difference=group_diff))

        # One-sided (unmatched) entries.
        for e in company_entries:
            if str(e.id) not in used:
                rows.append(self._row(e, None, None, status=self._unmatched_status(e, "company")))
        for e in vendor_entries:
            if str(e.id) not in used:
                rows.append(self._row(None, e, None, status=self._unmatched_status(e, "party")))
        return rows

    @staticmethod
    def _unmatched_status(entry, side: str) -> str:
        # Opening/Closing balance, reversal (knock-off), and TDS entries are
        # not a genuine "not booked" reconciliation gap — give them their own
        # status so they aren't reported as missing on one side. Bug fix: an
        # unmatched TDS entry's Classification already said "TDS Booked by
        # Party" (via _special_classification in _row/_classification), but
        # Status fell through to the generic "Other entry not booked by..."
        # because this function didn't check for the TDS special case too.
        # `side` is passed through so a company-ledger TDS entry correctly
        # reads "TDS Booked by Company", not always "...by Party" (see
        # _special_classification's side-attribution fix).
        special = _special_classification(entry, side)
        if special in ("Opening Balance", "Closing Balance", "Reversal Entries",
                        "TDS Booked by Company", "TDS Booked by Party"):
            return special
        cat = (getattr(entry, "document_category", "") or "").strip()
        info = CATEGORY_TO_SUMMARY.get(cat, DEFAULT_SUMMARY)
        # An entry present on ONE side is missing on the OTHER side. Per the
        # Emcure mapping rules ("If Emcure invoice is open, then invoice is
        # not booked by vendor"), a company-side (Emcure) open item is
        # "not booked by Party", and a party-side (vendor) open item is
        # "not booked by Company".
        return info["party_missing"] if side == "company" else info["company_missing"]

    def _row(self, c, p, match, status: str, row_difference: float | None = None) -> dict:
        pass_number = getattr(c or p, "pass_number", None)
        c_amt = _num(getattr(c, "amount", 0)) if c else 0.0
        p_amt = _num(getattr(p, "amount", 0)) if p else 0.0
        # row_difference overrides the naive per-row (c_amt + p_amt) calc —
        # used for multi-entry ONE_TO_MANY/MANY_TO_ONE groups, where a single
        # row's two entries are not the full picture; the group's own
        # difference_amount (computed across ALL entries in the group) is
        # the correct value. See _build_recon_rows.
        diff = row_difference if row_difference is not None else (
            (c_amt + p_amt) if (c and p) else 0.0
        )
        # A row belongs to a match whenever it came from a match record — even
        # if this particular line only carries one side (the "extra" entries of
        # a one-to-many / many-to-one group). Classification and rule must key
        # off the match, not off both sides being present, otherwise the extra
        # lines of a group show "Unmatched" while status says "Reconciled".
        is_matched = match is not None
        manual_reason = (getattr(match, "status_reason", "") or "") if match else ""
        # Entry-intrinsic classification (Opening/Closing Balance, Reversal,
        # TDS) takes priority over the pass-based label, and applies whether or
        # not the row was matched. Check company side first, then party — and
        # pass the correct side through so a company-ledger TDS entry reads
        # "TDS Booked by Company", not always "...by Party" (see
        # _special_classification's side-attribution fix).
        special = _special_classification(c, "company") or _special_classification(p, "party")
        if special is not None:
            classification = special
        elif is_matched and pass_number is not None and int(pass_number) == 8 and manual_reason:
            # Manual link (pass 8): the reviewer picked a specific reason
            # from the "Reason for Linking" dropdown (e.g. "Opening Balance
            # as per Company") — that reason IS the classification for this
            # row, not the generic "Manually Mapped" placeholder. Client-
            # confirmed bug: the selected reason only ever showed up in the
            # Remark column while Classification stayed hardcoded to
            # "Manually Mapped" regardless of what was actually picked.
            classification = manual_reason
        elif is_matched:
            classification = _classification(pass_number, c, p)
        else:
            classification = "Unmatched"
        return {
            "company_id": str(c.id) if c else "",
            "party_id": str(p.id) if p else "",
            "matched_id": str(match.id) if match else "",
            "status": status,
            "classification": classification,
            # Remark: a reviewer's manually-selected reason (pass 8) always
            # wins; otherwise a rule-driven explanatory note is derived from
            # the row's Classification (see _auto_remark) so auto-matched
            # rows are no longer left blank when the client's reference
            # export expects an explanation (e.g. Reversal Entries,
            # invoice-number-matching guidance).
            "remark": _auto_remark(
                classification,
                (getattr(match, "status_reason", "") or "") if match else "",
                c, p,
            ),
            "c_stmt": "ledger" if c else "",
            "c_date": _fmt_date(getattr(c, "posting_date", None)) if c else "",
            "c_invno": _invoice_number(c) if c else "",
            "c_doctype": (getattr(c, "document_category", "") or "").lower() if c else "",
            "c_origtype": getattr(c, "document_type", "") if c else "",
            "c_narr": getattr(c, "description", "") if c else "",
            "c_amt": c_amt if c else "",
            "p_stmt": "ledger" if p else "",
            "p_date": _fmt_date(getattr(p, "posting_date", None)) if p else "",
            "p_invno": _invoice_number(p) if p else "",
            "p_doctype": (getattr(p, "document_category", "") or "").lower() if p else "",
            "p_origtype": getattr(p, "document_type", "") if p else "",
            "p_narr": getattr(p, "description", "") if p else "",
            "p_amt": p_amt if p else "",
            "difference": diff,
            "rule": _rule_code(pass_number) if is_matched else "",
            "category": (getattr(c or p, "document_category", "") or ""),
            "_side": "both" if (c and p) else ("company" if c else "party"),
            # Company-side SAP detail columns — prefer the original uploaded
            # value from raw_data, falling back to the modelled field.
            "c_clearing_doc": _raw(c, ["clearing document", "clearing document number", "clearing doc"], getattr(c, "clearing_document", "") if c else ""),
            "c_clearing_date": _raw(c, ["clearing date"], _fmt_date(getattr(c, "clearing_date", None)) if c else ""),
            "c_tds_amount": _raw(c, ["tds amount", "company tds amount", "withholding tax amount", "withhldg tax amount"], ""),
            "c_posting_date": _raw(c, ["posting date"], _fmt_date(getattr(c, "posting_date", None)) if c else ""),
            "c_company_code": _raw(c, ["company code", "company"], ""),
            "c_supplier": _raw(c, ["supplier", "vendor", "vendor name", "supplier name"], ""),
            "c_docnum": _raw(c, ["document number", "document no", "doc number", "belnr"], getattr(c, "document_number", "") if c else ""),
            "c_business_area": _raw(c, ["business area"], ""),
            "c_assignment": _raw(c, ["assignment", "assignment number", "zuonr"], getattr(c, "assignment_number", "") if c else ""),
            "c_doc_header_text": _raw(c, ["document header text", "doc header text", "header text"], ""),
            "c_tax_code": _raw(c, ["tax code"], ""),
            "c_year_month": _raw(c, ["year/month", "year month", "period", "fiscal period"], ""),
            "c_reference": _raw(c, ["reference", "reference number", "xblnr"], (getattr(c, "reference_number", None) or getattr(c, "raw_reference", "")) if c else ""),
            "c_profit_center": _raw(c, ["profit center", "profit centre"], ""),
            "c_doc_amount": _raw(c, ["amount in doc. curr.", "amount in doc curr", "amount in document currency"], _num(getattr(c, "original_amount", None) if (c and getattr(c, "original_amount", None) is not None) else getattr(c, "amount", 0)) if c else ""),
            "c_doc_currency": _raw(c, ["document currency", "doc currency", "currency"], (getattr(c, "transaction_currency", None) or getattr(c, "currency", "")) if c else ""),
            "c_local_amount": _raw(c, ["local currency", "amount in local currency", "local currency amount"], _num(getattr(c, "local_currency_amount", None)) if (c and getattr(c, "local_currency_amount", None) is not None) else ""),
            "c_entry_date": _raw(c, ["entry date"], ""),
            "c_wht_base": _raw(c, ["withhldg tax base amount", "withholding tax base amount", "w/tax base amount"], ""),
            "c_payment_date": _raw(c, ["payment date"], ""),
            "c_daybook": _raw(c, ["daybook name", "daybook"], ""),
        }

    def _recon_record(self, r: dict) -> list:
        """Map a row dict to the full 45-column Reconciliation record."""
        rec = [""] * len(self.RECON_HEADERS)
        rec[0] = r["company_id"]
        rec[1] = r["party_id"]
        rec[2] = r["matched_id"]
        rec[3] = r["status"]
        rec[4] = r["classification"]
        rec[5] = r["c_stmt"]
        rec[6] = r["c_date"]
        rec[7] = r["c_invno"]
        rec[8] = r["c_doctype"]
        rec[9] = r["c_origtype"]
        rec[10] = r["c_narr"]
        rec[11] = r["c_amt"]
        rec[12] = r["p_stmt"]
        rec[13] = r["p_date"]
        rec[14] = r["p_invno"]
        rec[15] = r["p_doctype"]
        rec[16] = r["p_origtype"]
        rec[17] = r["p_narr"]
        rec[18] = r["p_amt"]
        rec[19] = r["difference"]
        rec[20] = r["rule"]
        rec[21] = self._reco_dt
        # index 22 was "Remark" (removed from the exported output — see
        # RECON_HEADERS comment above; the underlying r["remark"] value
        # still exists on the row dict and still drives Status/
        # Classification, it's just no longer written to a column here).
        rec[22] = self._party_code
        # Company-side SAP detail columns (0-indexed against RECON_HEADERS).
        rec[23] = r["c_daybook"]           # Daybook Name
        rec[24] = r["c_clearing_doc"]      # Company Clearing Document Number
        rec[25] = r["c_clearing_date"]     # Company Clearing Date
        rec[26] = r["c_tds_amount"]        # Company TDS Amount
        rec[27] = r["c_posting_date"]      # Company Posting Date
        rec[28] = r["c_company_code"]      # Company Code
        rec[29] = r["c_supplier"]          # Supplier
        rec[30] = r["c_docnum"]            # Document Number
        rec[31] = r["c_business_area"]     # Business Area
        rec[32] = r["c_assignment"]        # Assignment
        rec[33] = r["c_doc_header_text"]   # Document Header Text
        rec[34] = r["c_tax_code"]          # Tax Code
        rec[35] = r["c_year_month"]        # Year/Month
        rec[36] = r["c_reference"]         # Reference
        rec[37] = r["c_profit_center"]     # Profit Center
        rec[38] = r["c_posting_date"]      # Posting Date
        rec[39] = r["c_doc_amount"]        # Amount in Doc. Curr.
        rec[40] = r["c_doc_currency"]      # Document Currency
        rec[41] = r["c_local_amount"]      # Local Currency
        rec[42] = r["c_entry_date"]        # Entry Date
        rec[43] = r["c_wht_base"]          # Withhldg Tax Base Amount
        rec[44] = r["c_payment_date"]      # Payment Date
        return rec

    # ------------------------------------------------------------- recon sheet
    def _write_recon_sheet(self, wb, rows):
        ws = wb.create_sheet("Reconciliation")
        ws.append(self.RECON_HEADERS)
        self._colour_recon_header(ws)
        for r in rows:
            ws.append(self._recon_record(r))
        self._autosize(ws, max_cols=25)

    def _colour_recon_header(self, ws):
        for c in range(1, len(self.RECON_HEADERS) + 1):
            cell = ws.cell(row=1, column=c)
            cell.font = WHITE_BOLD
            if c in self.COMPANY_COLS:
                cell.fill = FILL_COMPANY
            elif c in self.PARTY_COLS:
                cell.fill = FILL_PARTY
            elif c in self.DIFF_COLS:
                cell.fill = FILL_DIFF
            else:
                cell.fill = FILL_META

    # ------------------------------------------------------------- annexures
    def _write_annexures(self, wb, rows, annexure_map):
        """annexure_map: {annexure_number: (status_label, side)}."""
        for annex_no, (status_label, side) in annexure_map.items():
            matching = [r for r in rows if r["status"] == status_label]
            if not matching:
                continue
            ws = wb.create_sheet(str(annex_no))
            ws.append(self.RECON_HEADERS)
            self._colour_recon_header(ws)
            for r in matching:
                ws.append(self._recon_record(r))
            self._autosize(ws, max_cols=25)

    # ------------------------------------------------------------- party sheet
    def _write_party_sheet(self, wb, vendor_entries, entry_match):
        ws = wb.create_sheet("Party")
        ws.append(self.PARTY_HEADERS)
        for c in range(1, len(self.PARTY_HEADERS) + 1):
            cell = ws.cell(row=1, column=c)
            cell.font = WHITE_BOLD
            cell.fill = FILL_PARTY
        for e in vendor_entries:
            m = entry_match.get(str(e.id))
            pass_number = getattr(e, "pass_number", None)
            # Party sheet only has one side per row, so the TDS-side
            # comparison in _status() isn't available here; a plain
            # "Write off / Rounding off" check (via the match's persisted
            # difference_amount) is still applied for tolerance matches.
            row_diff = _num(getattr(m, "difference_amount", 0)) if m else 0.0
            ws.append([
                str(e.id),
                str(m.id) if m else "",
                _status(
                    pass_number, None, e, row_diff,
                    self._tds_percentage_value, self._gst_percentage_value,
                    self._tds_percentage_min_value,
                ) if m else self._unmatched_status(e, "party"),
                _classification(pass_number, None, e) if m else "Unmatched",
                "ledger",
                _fmt_date(getattr(e, "posting_date", None)),
                # Bug fix: this read derived_invoice_number/document_number
                # directly with no BAL_ROW_* placeholder filtering at all —
                # use the shared _invoice_number() helper so the "Party"
                # sheet's invoice number column matches the same
                # blank-when-unidentifiable behavior as every other sheet.
                _invoice_number(e),
                (getattr(e, "document_category", "") or "").lower(),
                getattr(e, "document_type", ""),
                getattr(e, "description", ""),
                _num(getattr(e, "amount", 0)),
                _rule_code(pass_number) if m else "",
                self._reco_dt,
                getattr(e, "clearing_document", "") or "",
                _fmt_date(getattr(e, "clearing_date", None)),
                "",
                _fmt_date(getattr(e, "posting_date", None)),
            ])
        self._autosize(ws, max_cols=17)

    # ------------------------------------------------------------- summary
    def _compute_summary(
        self, ws, vendor, company_entries, vendor_entries, match_results,
        period_start, period_end, tolerance_amount, tds_percentage, date_tolerance,
        rows: list[dict] | None = None,
    ) -> dict:
        """Write the Summary sheet; return {annexure_no: (status_label, side)}."""
        vname = getattr(vendor, "name", "") or ""
        # ── Header block ──
        header_rows = [
            ("Party Name", vname, "Date Tolerance", date_tolerance),
            ("Reconciliation Period",
             f"{_fmt_date(period_start)} to {_fmt_date(period_end)}",
             "TDS Percentage", tds_percentage),
            ("Statement Type", "Ledger", "Amount Tolerance", tolerance_amount),
            ("Party Type", "Vendor", "", ""),
            ("Reconciliation Date", self._reco_dt, "", ""),
        ]
        for a, b, c, d in header_rows:
            ws.append([a, b, c, d])
        for r in range(1, 6):
            ws.cell(row=r, column=1).font = BOLD
            ws.cell(row=r, column=3).font = BOLD
            ws.cell(row=r, column=1).alignment = Alignment(horizontal="right")
            ws.cell(row=r, column=3).alignment = Alignment(horizontal="right")

        ws.append([])  # row 6 blank

        # ── "Reconciliation Statement" banner (row 7) ──
        ws.append(["Reconciliation Statement"])
        banner = ws.cell(row=7, column=1)
        banner.fill = FILL_GREEN
        banner.font = WHITE_BOLD
        ws.merge_cells(start_row=7, start_column=1, end_row=7, end_column=5)

        # ── Table header (row 8) ──
        ws.append(["Particulars", "Annexure", "Amount", "No. of Entries", "Action Required"])
        for c in range(1, 6):
            cell = ws.cell(row=8, column=c)
            cell.fill = FILL_GREEN
            cell.font = WHITE_BOLD

        # Build unmatched buckets by category/side, assigning annexure numbers.
        annexure_map: dict[int, tuple] = {}
        annex_counter = {"n": 0}

        def next_annex():
            annex_counter["n"] += 1
            return annex_counter["n"]

        def bucket(entries, side):
            """Aggregate UNMATCHED entries per (group, label, action).

            An entry is "unmatched" when it has no match_id. Opening/Closing
            balance rows are excluded (shown in their own section).
            Returns {(grp, label, action): [amount_sum, count]}.
            """
            out: dict = {}
            for e in entries:
                if getattr(e, "match_id", None):
                    continue
                cat = (getattr(e, "document_category", "") or "").strip()
                if cat in ("Opening Balance", "Closing Balance"):
                    continue
                # Balance and reversal (knock-off) entries are entry-intrinsic
                # classifications, not a cross-ledger "not booked" gap. A
                # knock-off nets within one side, so it must not surface as a
                # difference "not booked by" the other side.
                special = _special_classification(e, side)
                if special in ("Opening Balance", "Closing Balance", "Reversal Entries"):
                    continue
                # An unmatched TDS entry must roll up under "TDS / TCS
                # Difference" regardless of its raw document_category (TDS
                # detection in _special_classification checks is_tds/doc
                # type/narration, not document_category) — otherwise it fell
                # through to DEFAULT_SUMMARY ("Other Differences"). Checks
                # both possible TDS labels since `special` is now side-aware
                # (see _special_classification's side-attribution fix).
                if special in ("TDS Booked by Party", "TDS Booked by Company"):
                    info = CATEGORY_TO_SUMMARY["TDS Adjusted"]
                else:
                    info = CATEGORY_TO_SUMMARY.get(cat, DEFAULT_SUMMARY)
                # Same side-attribution rule as _unmatched_status: an entry
                # open on the company side is missing on the party side, and
                # vice versa (see Emcure mapping rules doc).
                label = info["party_missing"] if side == "company" else info["company_missing"]
                action = info["party_action"] if side == "company" else info["company_action"]
                grp = info["group"]
                key = (grp, label, action)
                agg = out.setdefault(key, [Decimal("0"), 0])
                agg[0] += Decimal(str(_num(getattr(e, "amount", 0))))
                agg[1] += 1
            return out

        comp_buckets = bucket(company_entries, "company")
        party_buckets = bucket(vendor_entries, "party")

        # Group the buckets under their difference group, in reference order.
        group_order = [
            "Invoice Difference",
            "Debit Note / Credit Note Difference",
            "Payment / receipt Difference",
            "Other Differences",
            "TDS / TCS Difference",
            "Amount Mismatch Difference",
            "Write Off / Rounding Off Difference",
            "Unexplained Amount Gap Difference",
        ]
        # Collect detail lines per group. Company side is shown as a positive
        # "owed" amount and party side as negative so the section total reflects
        # the net difference for that category.
        lines_by_group: dict[str, list] = {g: [] for g in group_order}
        for (grp, label, action), (amt, cnt) in {**comp_buckets, **party_buckets}.items():
            lines_by_group.setdefault(grp, [])
            annex_no = next_annex()
            side = "company" if "Company" in label else "party"
            annexure_map[annex_no] = (label, side)
            lines_by_group[grp].append((label, annex_no, amt, cnt, action, side))

        # Matched pairs that still carry a genuine residual (TDS deducted,
        # rounding write-off, or an unexplained gap) were previously invisible
        # here — only one-sided (unmatched) entries were itemised above. Fold
        # them into the same groups so they get their own linked annexure and
        # entry count instead of vanishing into the "Amount Unsettled" plug.
        for (grp, label, action), (amt, cnt) in matched_residual_bucket(rows).items():
            lines_by_group.setdefault(grp, [])
            annex_no = next_annex()
            annexure_map[annex_no] = (label, "both")
            lines_by_group[grp].append((label, annex_no, amt, cnt, action, "both"))

        # ── Opening balance (computed FIRST — closing's fallback below
        # needs it). Client-confirmed rule: opening balance is 0 ONLY when
        # there's genuinely no Opening Balance row on that side at all; if
        # one or more rows exist (even multiple, even sharing a date — see
        # _balance_sum), they are summed as the real opening figure. ──
        company_opening = _balance_sum(company_entries, "opening")
        party_opening = _balance_sum(vendor_entries, "opening")
        n_company_opening = _balance_count(company_entries, "opening")
        n_party_opening = _balance_count(vendor_entries, "opening")

        # ── Closing balance section. Client-confirmed rule: closing
        # balance is NEVER assumed to be 0 — when no literal Closing
        # Balance row exists, it's derived as opening + sum(everything
        # else) instead (see _closing/_effective_closing). ──
        company_closing = _company_closing(company_entries, company_opening)
        party_closing = _closing(vendor_entries, party_opening)
        n_company_closing = _closing_count(company_entries)
        n_party_closing = _closing_count(vendor_entries)
        closing_diff = company_closing + party_closing

        row = 9
        row = self._summary_group(
            ws, row, "Closing Balance Difference",
            total_amount=closing_diff,
            total_count=n_company_closing + n_party_closing,
            detail_lines=[
                ("Closing Balance as per Company", None, company_closing, n_company_closing, "", "company"),
                ("Closing Balance as per Party", None, party_closing, n_party_closing, "", "party"),
            ],
        )

        # ── Opening balance section (counted so all balance rows appear) ──
        if n_company_opening or n_party_opening:
            row = self._summary_group(
                ws, row, "Opening Balance Difference",
                total_amount=company_opening + party_opening,
                total_count=n_company_opening + n_party_opening,
                detail_lines=[
                    ("Opening Balance as per Company", None, company_opening, n_company_opening, "", "company"),
                    ("Opening Balance as per Party", None, party_opening, n_party_opening,
                     "Vendor to provide the breakup of Opening Balance", "party"),
                ],
            )

        # ── Difference groups ──
        # Track the running sum of all difference sections for the final check.
        #
        # Client-confirmed rule: the Opening Balance gap must be folded
        # into this running total too, not just displayed informationally.
        # Proof this is the correct (and ONLY correct) treatment: for each
        # side individually, opening + sum(all non-balance entries) =
        # -closing (pure bookkeeping identity, confirmed exact on real
        # AUTOPACK INDUSTRIES/EPL data down to the rupee). Summed across
        # both sides: opening_diff + total_diff_amount_itemised =
        # -closing_diff, which rearranges to
        # closing_diff + opening_diff + total_diff_amount_itemised = 0.
        # Without opening_diff in this sum, "Difference" collapses to
        # exactly `-opening_diff` whenever every OTHER entry is correctly
        # itemised — i.e. a real, non-zero opening-balance mismatch was
        # silently passed through to "Difference" unexplained, even though
        # the actual itemised categories fully reconciled. Folding it in
        # here means "Difference" is zero exactly when the itemised
        # categories fully explain BOTH the opening AND closing gaps —
        # the genuine, complete monetary difference.
        total_diff_amount = company_opening + party_opening
        for grp in group_order:
            lines = lines_by_group.get(grp, [])
            if not lines:
                continue
            grp_amount = sum((amt for (_l, _a, amt, _c, _act, _s) in lines), Decimal("0"))
            grp_count = sum((cnt for (_l, _a, _amt, cnt, _act, _s) in lines), 0)
            total_diff_amount += grp_amount
            row = self._summary_group(
                ws, row, grp, total_amount=grp_amount, total_count=grp_count,
                detail_lines=lines,
            )

        # ── Reconciled (matched) section ──
        # Client-reported bug: this section re-summed the SAME matched-pair
        # amounts that a residual (TDS deducted / rounding write-off /
        # Amount Mismatch) is already itemised under via
        # matched_residual_bucket above — a fully-cancelling pair nets to
        # 0 and contributes nothing, but a pair WITH a residual shows that
        # exact residual amount a second time under "Reconciled - Company/
        # Party", creating a double effect on the Summary sheet. Removed
        # per explicit correction: matched entries with a residual are
        # already covered by their own difference group; matched entries
        # with NO residual net to zero and add no information here.

        # ── Amount Unsettled section removed ──
        # This was a forced balancing plug (`closing_diff - total_diff_amount`)
        # with no linked annexure and no real entry count, inserted purely to
        # make the final "Difference" row show zero. Per explicit correction,
        # the Summary sheet must only reflect genuine open items/differences
        # that were actually classified — not a fabricated residual used to
        # force a balance. The "Difference" row below can now be non-zero
        # when the itemised differences don't fully explain the closing-
        # balance gap (e.g. data not yet mapped/classified); that gap is
        # exactly what should be surfaced, not hidden by a plug line.

        # ── Total Entries check row ──
        total_all_entries = len(company_entries) + len(vendor_entries)
        ws.append([])
        row += 1
        ws.cell(row=row, column=1, value="Total Entries (Company + Party)")
        ws.cell(row=row, column=1).font = BOLD
        ws.cell(row=row, column=4, value=total_all_entries)
        ws.cell(row=row, column=4).font = BOLD
        row += 1

        # ── Calculated Balance + final Difference (green) ──
        ws.append([])
        row += 1
        ws.cell(row=row, column=1, value="Calculated Balance")
        ws.cell(row=row, column=1).font = BOLD
        ws.cell(row=row, column=3, value=float(total_diff_amount))
        ws.cell(row=row, column=3).font = BOLD
        row += 1

        # No forced balancing plug — "Difference" is the HONEST gap between
        # the closing-balance difference and what the itemised categories
        # actually explain. A non-zero value here is a real signal (data not
        # yet classified/mapped) that should be visible, not hidden by
        # inserting a fabricated "Amount Unsettled" line to zero it out.
        #
        # Client-confirmed bug (real data, EMCURE/ZUVENTUS ledgers): this was
        # `closing_diff - total_diff_amount`, which ALWAYS doubles the real
        # gap instead of explaining it — verified against the real matching
        # engine output, not just a hand-picked example. Proof: a closing
        # balance is by definition the running total of every OTHER entry on
        # that same side, so for each side individually:
        #   opening + sum(that side's non-balance entries) = -that side's closing
        #   => sum(that side's non-balance entries) = -that side's closing - opening
        # `total_diff_amount` now includes BOTH the opening-balance gap AND
        # the sum of both sides' non-balance (unmatched + matched-residual)
        # entries (client-confirmed correction — the opening gap must be
        # folded in to get the true monetary difference, not just shown
        # informationally), so:
        #   total_diff_amount = (company_opening + party_opening)
        #                       + [-(company_closing) - company_opening]
        #                       + [-(party_closing) - party_opening]
        #                     = -(company_closing + party_closing)
        #                     = -closing_diff
        # This identity holds for ANY ledger pair regardless of match
        # quality, classification, or opening-balance shape (single row,
        # multiple rows on the same date, or none at all — see
        # _balance_sum/_effective_closing) — it's pure bookkeeping, not
        # data-dependent. So `closing_diff - total_diff_amount` always
        # equals `closing_diff - (-closing_diff) = 2 * closing_diff` —
        # exactly the doubling seen in production (closing_diff=-41424
        # produced Difference=-82848). The itemised categories (now
        # including the opening-balance gap) DO fully explain the closing-
        # balance gap when `total_diff_amount == -closing_diff`; adding
        # them (which correctly nets to zero) is what actually reflects
        # that, not subtracting.
        final_difference = closing_diff + total_diff_amount
        ws.cell(row=row, column=1, value="Difference")
        for c in range(1, 6):
            ws.cell(row=row, column=c).fill = FILL_GREEN
            ws.cell(row=row, column=c).font = WHITE_BOLD
        ws.cell(row=row, column=3, value=float(final_difference))

        self._autosize(ws, max_cols=5)
        return annexure_map

    def _summary_group(self, ws, row, group_title, *, total_amount=None, total_count=None, detail_lines=None):
        """Write a yellow group header row (with section totals) + white detail
        rows. Returns the next free row."""
        # Group header (yellow) — carries the section total amount + entry count.
        ws.cell(row=row, column=1, value=group_title)
        if total_amount is not None:
            ws.cell(row=row, column=3, value=float(total_amount))
        if total_count is not None:
            ws.cell(row=row, column=4, value=int(total_count))
        for c in range(1, 6):
            ws.cell(row=row, column=c).fill = FILL_GROUP
            ws.cell(row=row, column=c).font = BOLD
        row += 1

        for (label, annex_no, amt, cnt, act, _side) in (detail_lines or []):
            ws.cell(row=row, column=1, value=label)
            if annex_no is not None:
                ws.cell(row=row, column=2, value=annex_no)
            ws.cell(row=row, column=3, value=float(amt))
            if cnt:
                ws.cell(row=row, column=4, value=int(cnt))
            if act:
                ws.cell(row=row, column=5, value=act)
            row += 1
        return row

    # ------------------------------------------------------------- utilities
    @staticmethod
    def _autosize(ws, max_cols: int = 20):
        for c in range(1, min(ws.max_column, max_cols) + 1):
            letter = get_column_letter(c)
            width = 12
            for row in range(1, min(ws.max_row, 200) + 1):
                v = ws.cell(row=row, column=c).value
                if v is not None:
                    width = max(width, min(len(str(v)) + 2, 40))
            ws.column_dimensions[letter].width = width


def _balance_sum(entries, keyword: str) -> Decimal:
    """Sum every entry whose category contains `keyword` ("opening"/
    "closing"). When multiple rows share that category (e.g. two literal
    "Opening Balance" rows on the same date — confirmed on real client
    data, AUTOPACK INDUSTRIES vendor ledger), they are ALL summed together
    rather than only the first one being used — a real ledger's opening
    position can legitimately be recorded as more than one line."""
    total = Decimal("0")
    for e in entries:
        cat = (getattr(e, "document_category", "") or "").lower()
        if keyword in cat:
            total += Decimal(str(_num(getattr(e, "amount", 0))))
    return total


def _balance_count(entries, keyword: str) -> int:
    return sum(
        1 for e in entries
        if keyword in (getattr(e, "document_category", "") or "").lower()
    )


def _sum_non_balance(entries) -> Decimal:
    """Total of a side's transactional entries, excluding Opening/Closing
    Balance rows — used as the closing-balance fallback below. Mirrors
    reconciliation_engine_service.py's _compute_summary_fields helper of
    the same name/purpose, kept as a separate local copy here since the
    export service doesn't share that module's private scope."""
    total = Decimal("0")
    for e in entries:
        cat = (getattr(e, "document_category", "") or "").lower()
        if "opening" in cat or "closing" in cat:
            continue
        total += Decimal(str(_num(getattr(e, "amount", 0))))
    return total


def _effective_closing(entries, opening: Decimal) -> Decimal:
    """
    Closing balance for one side, with a fallback when there's no literal
    Closing Balance row on that side.

    Client-confirmed rule: a ledger's closing balance is NEVER genuinely
    zero just because the file didn't carry an explicit "Closing Balance"
    row — every ledger with any activity has a real ending position. When
    no Closing Balance row exists, derive it the same way
    reconciliation_engine_service.py's _compute_summary_fields already
    does: opening + sum(every other entry on that side). This is exact
    bookkeeping, not an approximation — a closing balance is BY DEFINITION
    the running total of everything that came before it.

    Confirmed real-data bug fix: a vendor file with zero Opening/Closing
    rows at all (Prince Graphics) was previously read as
    party_closing=0/party_opening=0, breaking the Summary sheet's core
    identity (`Difference` should be 0 when every entry is itemised) and
    producing a genuinely wrong non-zero Difference (144,450.17 on real
    data) that had nothing to do with any actual reconciliation gap.

    Only used as a FALLBACK — when a real Closing Balance row exists, it
    always wins (see caller).
    """
    return opening + _sum_non_balance(entries)


def _closing(entries, opening: Decimal | None = None) -> Decimal:
    """
    Closing balance for one side. Prefers a literal Closing Balance row
    (summed, same multi-row handling as _balance_sum); falls back to
    `_effective_closing` (opening + sum of everything else) ONLY when no
    such row exists at all. `opening` must be pre-computed by the caller
    (via _balance_sum(entries, "opening"), defaulting to 0 when absent —
    see the Opening Balance rule below) and passed in for the fallback.
    """
    stated = _balance_sum(entries, "closing")
    if _balance_count(entries, "closing") > 0:
        return stated
    return _effective_closing(entries, opening if opening is not None else Decimal("0"))


def _closing_count(entries) -> int:
    """Entry count for the Closing Balance row(s). When falling back to
    the derived closing balance (no literal row present), there is no
    real "closing balance entry" to count — 0, consistent with the
    Opening Balance section's own "count 0 when absent" convention."""
    return _balance_count(entries, "closing")


def _company_closing(entries, opening: Decimal | None = None) -> Decimal:
    return _closing(entries, opening)


# Row Status -> (Summary group, Action Required text) for MATCHED pairs that
# still carry a genuine residual difference. Previously these were invisible
# on the Summary sheet: only UNMATCHED (one-sided) entries were itemised by
# `bucket()` above, so a matched pair's own leftover gap (TDS withheld,
# rounding write-off, or an unexplained amount gap) never appeared anywhere
# — it just inflated the generic "Amount Unsettled by Company/Vendor" plug
# at the bottom with no annexure and no entry count.
_MATCHED_RESIDUAL_INFO: dict[str, tuple[str, str]] = {
    "TDS Booked by Company": (
        "TDS / TCS Difference",
        "Company to confirm TDS deducted and share the TDS certificate",
    ),
    "TDS Booked by Party": (
        "TDS / TCS Difference",
        "Vendor to confirm TDS deducted and share the TDS certificate",
    ),
    "Write off / Rounding off": (
        "Write Off / Rounding Off Difference",
        "No action required - within configured tolerance",
    ),
    "Unexplained Amount Gap": (
        "Unexplained Amount Gap Difference",
        "Finance to review - matched pair's gap does not match the configured TDS/GST rate",
    ),
    # Status "Amount Mismatch" is now reported by TWO passes, per explicit
    # correction that a genuine unexplained gap must never be reported as
    # "Reconciled" (settled):
    #   - Pass 15 (AMOUNT_MISMATCH): same invoice number + same document
    #     date on both sides, gap NOT explained by TDS/GST.
    #   - Pass 12 (TOLERANCE_DATE, "Date Range and Amount Matched"): the
    #     weakest matching tier — no exact amount, no invoice-number
    #     correlation at all — previously always reported "Reconciled"
    #     even for a large, unexplained gap.
    "Amount Mismatch": (
        "Amount Mismatch Difference",
        "Finance to review - invoice number and date match but amount differs",
    ),
}

# Classification -> (Summary group, Action Required text) fallback for
# matched pairs whose Status doesn't already have an entry in
# _MATCHED_RESIDUAL_INFO above. Per explicit correction, pass 15
# (AMOUNT_MISMATCH) now reports Status = "Amount Mismatch" directly (it used
# to always report "Reconciled" with the caveat living only in
# Classification) — so it's found via the primary Status-keyed lookup above
# in the normal case. This dict is kept as a defensive fallback only.
_MATCHED_RESIDUAL_INFO_BY_CLASSIFICATION: dict[str, tuple[str, str]] = {
    "Amount Mismatch": (
        "Amount Mismatch Difference",
        "Finance to review - invoice number and date match but amount differs",
    ),
}


def matched_residual_bucket(rows: list[dict] | None) -> dict:
    """
    Aggregate MATCHED rows that still carry a genuine residual difference
    into the same (group, label, action) -> [amount, count] shape the
    unmatched `bucket()` helper produces, so they can be merged into the
    same Summary sections and get their own linked annexure sheet + entry
    count instead of silently inflating the generic "Amount Unsettled" plug.

    Client-reported bug: "the values appearing under 'To Be Settled' and
    'Adjust Between Our Side and Vendor Side' show a large difference...
    however, the differential amount is not getting linked/mapped in the
    output file." Root cause: matched-pair residuals (TDS deducted,
    rounding write-offs, unexplained gaps) were never itemised on the
    Summary sheet at all — only one-sided (unmatched) entries were. The
    gap between the itemised total and the closing-balance difference was
    dumped wholesale into the unlinked "Amount Unsettled" line.

    Count bug fix: the entry count was incremented by 1 PER ROW, but each
    row here is a matched PAIR — it carries a company-side ledger entry AND
    a vendor-side ledger entry (2 actual ledger lines), or just one side for
    an unpaired leg of a one-to-many/many-to-one group. Every OTHER count in
    this module (`bucket()` for unmatched entries, `matched_bucket()` for
    "Reconciled Entries") counts actual ledger entries, not rows/pairs — so
    this one silently under-counted by roughly half versus every other
    figure on the same statement (client: "why is the count of no. of
    entries so less?"). Now counts len(entries actually present on the row)
    instead of a flat +1.
    """
    out: dict = {}
    if not rows:
        return out
    for r in rows:
        status = r.get("status")
        info = _MATCHED_RESIDUAL_INFO.get(status)
        label = status
        if info is None:
            info = _MATCHED_RESIDUAL_INFO_BY_CLASSIFICATION.get(r.get("classification"))
            label = r.get("classification")
        if info is None:
            continue
        diff = Decimal(str(_num(r.get("difference", 0))))
        if abs(diff) < Decimal("0.005"):
            continue
        grp, action = info
        key = (grp, label, action)
        agg = out.setdefault(key, [Decimal("0"), 0])
        agg[0] += diff
        # Count the actual ledger entries this row represents (1 or 2), not
        # the row itself.
        entry_count = sum(1 for side_id in (r.get("company_id"), r.get("party_id")) if side_id)
        agg[1] += entry_count or 1
    return out
