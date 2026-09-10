"""
Unit tests for reconciliation export summary labelling.

Covers the "not booked by" side attribution (bug: company/party sides were
swapped). Emcure is the company side, the vendor is the party side, so:
  - a company-side (Emcure) open item is missing on the PARTY side
    → "Invoice not booked by Party"
  - a party-side (vendor) open item is missing on the COMPANY side
    → "Invoice not booked by Company"
"""

from dataclasses import dataclass, field
from uuid import UUID, uuid4

from src.domain.services.vlr.reconciliation_export_service import (
    ReconciliationExportService,
    _invoice_number,
    _status,
)


@dataclass
class FakeEntry:
    id: UUID = field(default_factory=uuid4)
    document_category: str = "Invoice"
    document_type: str = "KR"
    description: str = ""
    raw_data: dict = field(default_factory=dict)
    is_tds: bool = False
    amount: float = 0.0
    posting_date: object = None
    pass_number: int | None = None
    document_number: str = ""
    derived_invoice_number: str | None = None
    clearing_document: str = ""
    clearing_date: object = None


@dataclass
class FakeMatch:
    """Fake persisted MatchResultModel for testing row/group rendering."""

    id: UUID = field(default_factory=uuid4)
    company_entry_ids: list = field(default_factory=list)
    vendor_entry_ids: list = field(default_factory=list)
    difference_amount: float = 0.0
    status_reason: str | None = None


class TestUnmatchedStatusSide:
    def test_company_invoice_missing_on_party_side(self):
        entry = FakeEntry(document_category="Invoice")
        status = ReconciliationExportService._unmatched_status(entry, "company")
        assert status == "Invoice not booked by Party"

    def test_party_invoice_missing_on_company_side(self):
        entry = FakeEntry(document_category="Invoice")
        status = ReconciliationExportService._unmatched_status(entry, "party")
        assert status == "Invoice not booked by Company"

    def test_company_payment_missing_on_party_side(self):
        entry = FakeEntry(document_category="Payment", document_type="KZ")
        status = ReconciliationExportService._unmatched_status(entry, "company")
        assert status == "Payment not booked by Party"

    def test_party_payment_missing_on_company_side(self):
        entry = FakeEntry(document_category="Payment", document_type="KZ")
        status = ReconciliationExportService._unmatched_status(entry, "party")
        assert status == "Payment not booked by Company"

    def test_balance_entry_keeps_own_status(self):
        entry = FakeEntry(document_category="Opening Balance", document_type="OP")
        status = ReconciliationExportService._unmatched_status(entry, "company")
        assert status == "Opening Balance"

    def test_unmatched_tds_entry_status_matches_classification(self):
        """
        Bug fix: an unmatched TDS entry's Classification already showed "TDS
        Booked by Party" (client-confirmed), but Status showed the generic
        "Other entry not booked by Company" instead of following suit.
        """
        entry = FakeEntry(document_category="Journal", document_type="Journal", is_tds=True)
        status = ReconciliationExportService._unmatched_status(entry, "party")
        assert status == "TDS Booked by Party"


class TestPassTwoStatusTdsVsWriteOff:
    """
    Bug fix: client reported that for an invoice-number match with a real
    (non-rounding) amount difference, the difference should be classified
    under TDS, not shown as a generic write-off. Pass 2 (_tolerance_match)
    was widened to also match TDS/GST-sized gaps, so its Status must
    distinguish a genuine TDS-sized gap from a small rounding write-off.
    """

    def test_small_rounding_gap_is_write_off(self):
        c_entry = FakeEntry()
        p_entry = FakeEntry()
        # A tiny gap (<= 5) stays a rounding write-off, not TDS.
        result = _status(2, c_entry, p_entry, difference=2.5)
        assert result == "Write off / Rounding off"

    def test_large_tds_sized_gap_is_tds_booked_by_party(self):
        """The gap must actually match the configured TDS/GST% (within a
        tight +/-1% band) to be labelled TDS — passing the case's real
        6% TDS rate here (1794.78 / 29729.22 ~= 6.0%)."""
        c_entry = FakeEntry()
        c_entry.amount = -29729.22  # type: ignore[attr-defined]
        p_entry = FakeEntry()
        p_entry.amount = 31524.0  # type: ignore[attr-defined]
        result = _status(2, c_entry, p_entry, difference=1794.78, tds_percentage=5.69)
        # Company has the SMALLER absolute amount -> company booked the TDS.
        assert result == "TDS Booked by Company"

    def test_gap_not_matching_any_configured_rate_is_unexplained(self):
        """Without a configured TDS/GST rate that actually explains the gap,
        a real (non-rounding) amount difference must NOT be silently
        labelled as TDS — this is the fix for the flat 'difference > Rs 5'
        bug that mislabelled arbitrary mismatches as TDS."""
        c_entry = FakeEntry()
        c_entry.amount = -29729.22  # type: ignore[attr-defined]
        p_entry = FakeEntry()
        p_entry.amount = 31524.0  # type: ignore[attr-defined]
        result = _status(2, c_entry, p_entry, difference=1794.78)
        assert result == "Unexplained Amount Gap"

    def test_low_rate_gap_within_configured_min_max_range_is_tds_booked(self):
        """
        Client-confirmed bug (round 2): TDS Percentage on the Reconciliation
        Settings screen is a MIN-MAX range (e.g. 0%-10%), but the Status
        check only ever compared the gap against a flat Max-rate amount —
        so a genuine TDS deduction at any OTHER rate within that range
        (here, ~0.085%, well inside 0%-10%) fell through to "Unexplained
        Amount Gap" even though the matching engine's own range-aware
        _is_tax_band_gap had already matched the pair correctly as TDS.
        Real numbers from the client's export: company -238290.75,
        party 238492.75, diff 202 (202/238492.75 ~= 0.0847%).
        """
        c_entry = FakeEntry()
        c_entry.amount = -238290.75  # type: ignore[attr-defined]
        p_entry = FakeEntry()
        p_entry.amount = 238492.75  # type: ignore[attr-defined]
        result = _status(
            2, c_entry, p_entry, difference=202.0,
            tds_percentage=10.0, gst_percentage=0.0, tds_percentage_min=0.0,
        )
        # Company has the SMALLER absolute amount -> company booked the TDS.
        assert result == "TDS Booked by Company"

    def test_multiple_real_client_rows_within_tds_range_all_booked(self):
        """A second and third row from the same client export, all with
        implied rates in the ~0.08%-0.09% band, well within a configured
        0%-10% TDS range."""
        cases = [
            (-346189.0, 346483.57, 294.57),
            (-207695.46, 207871.46, 176.0),
        ]
        for c_amt, p_amt, diff in cases:
            c_entry = FakeEntry()
            c_entry.amount = c_amt  # type: ignore[attr-defined]
            p_entry = FakeEntry()
            p_entry.amount = p_amt  # type: ignore[attr-defined]
            result = _status(
                2, c_entry, p_entry, difference=diff,
                tds_percentage=10.0, gst_percentage=0.0, tds_percentage_min=0.0,
            )
            assert result == "TDS Booked by Company", f"failed for c={c_amt}, p={p_amt}, diff={diff}"

    def test_tds_gst_pass_also_respects_min_max_range(self):
        """Pass TDS_GST (11) must use the same range-aware check as pass 2,
        not the old flat-rate comparison."""
        c_entry = FakeEntry()
        c_entry.amount = -238290.75  # type: ignore[attr-defined]
        p_entry = FakeEntry()
        p_entry.amount = 238492.75  # type: ignore[attr-defined]
        from src.domain.services.vlr.reconciliation_engine_service import MatchPassType
        result = _status(
            MatchPassType.TDS_GST, c_entry, p_entry, difference=202.0,
            tds_percentage=10.0, gst_percentage=0.0, tds_percentage_min=0.0,
        )
        assert result == "TDS Booked by Company"

    def test_gap_below_configured_min_is_still_unexplained(self):
        """A gap whose implied rate is genuinely below the configured Min
        (with margin) — not just any small gap — must still be
        Unexplained, proving this isn't a blanket loosening."""
        c_entry = FakeEntry()
        c_entry.amount = -1000000.0  # type: ignore[attr-defined]
        p_entry = FakeEntry()
        p_entry.amount = 1000010.0  # type: ignore[attr-defined]
        # implied rate ~= 0.001% -- below a configured Min of 2%
        result = _status(
            2, c_entry, p_entry, difference=10.0,
            tds_percentage=10.0, gst_percentage=0.0, tds_percentage_min=2.0,
        )
        assert result == "Unexplained Amount Gap"


class TestToleranceDatePassTdsStatus:
    """
    Client-confirmed bug (screenshot): "Date Range and Amount Matched"
    (pass TOLERANCE_DATE / 12 — neither exact amount nor invoice-number
    matched, fell back to amount+date-range) rows with a genuine TDS-range
    gap (e.g. company 50780 vs party 51656, diff 876) showed Status
    "Reconciled" instead of "TDS Booked by ...". Unlike pass 2/TDS_GST,
    this pass had NO tax-band check in _status at all — it fell straight
    through to the generic "Reconciled" regardless of whether the gap was
    tax-explained.
    """

    def test_tds_range_gap_on_tolerance_date_pass_is_tds_booked_by_party(self):
        """Real numbers from the screenshot: company -50780, party 51656,
        diff 876 (~1.7% of 51656) — within a configured 0%-2% TDS range."""
        from src.domain.services.vlr.reconciliation_engine_service import MatchPassType

        c_entry = FakeEntry()
        c_entry.amount = -50780.0  # type: ignore[attr-defined]
        p_entry = FakeEntry()
        p_entry.amount = 51656.0  # type: ignore[attr-defined]
        result = _status(
            MatchPassType.TOLERANCE_DATE, c_entry, p_entry, difference=876.0,
            tds_percentage=2.0, gst_percentage=0.0, tds_percentage_min=0.0,
        )
        # Company has the SMALLER absolute amount -> company booked the TDS
        # (same side-attribution rule as pass 2/TDS_GST above).
        assert result == "TDS Booked by Company"

    def test_tolerance_date_gap_not_matching_configured_rate_is_amount_mismatch(self):
        """
        Per explicit correction (same treatment as pass 15): without a
        configured rate that explains the gap, this weakest matching tier
        (no exact amount, no invoice-number correlation) must NOT report
        a genuine, non-negligible gap as "Reconciled" — that overstates
        how settled the pair is. Status is now "Amount Mismatch".
        """
        from src.domain.services.vlr.reconciliation_engine_service import MatchPassType

        c_entry = FakeEntry()
        c_entry.amount = -50780.0  # type: ignore[attr-defined]
        p_entry = FakeEntry()
        p_entry.amount = 51656.0  # type: ignore[attr-defined]
        result = _status(
            MatchPassType.TOLERANCE_DATE, c_entry, p_entry, difference=876.0,
        )
        assert result == "Amount Mismatch"

    def test_tolerance_date_negligible_gap_still_reconciled(self):
        """A truly negligible/rounding-level gap (<= 0.005, same threshold
        used elsewhere in this module) must still count as settled, not
        be reclassified as Amount Mismatch — this isn't a blanket
        downgrade of every pass-12 match."""
        from src.domain.services.vlr.reconciliation_engine_service import MatchPassType

        c_entry = FakeEntry()
        c_entry.amount = -50780.0  # type: ignore[attr-defined]
        p_entry = FakeEntry()
        p_entry.amount = 50780.0  # type: ignore[attr-defined]
        result = _status(
            MatchPassType.TOLERANCE_DATE, c_entry, p_entry, difference=0.0,
        )
        assert result == "Reconciled"


class TestManualLinkStatusAndRemark:
    """
    Manual-link feature: a reviewer manually pairing two unmatched entries
    must select a mandatory reason (from docs/Update Status.xlsx). The row's
    Status should show "Manually Mapped" (not the old "Reconciled" fallback),
    and the reviewer's selected reason surfaces in the Remark column.
    """

    def test_pass_8_status_is_manually_mapped(self):
        c_entry = FakeEntry()
        p_entry = FakeEntry()
        result = _status(8, c_entry, p_entry, difference=0.0)
        assert result == "Manually Mapped"

    def test_pass_8_classification_is_manually_mapped(self):
        from src.domain.services.vlr.reconciliation_export_service import _classification
        assert _classification(8) == "Manually Mapped"

    def test_remark_shows_reviewer_reason_for_manual_link(self):
        c1 = FakeEntry(pass_number=8)
        p1 = FakeEntry(pass_number=8)
        match = FakeMatch(
            company_entry_ids=[c1.id], vendor_entry_ids=[p1.id],
            difference_amount=0.0, status_reason="Invoice Booked And Adjusted",
        )
        by_id = {str(c1.id): c1, str(p1.id): p1}

        rows = ReconciliationExportService()._build_recon_rows([c1], [p1], [match], by_id)

        assert len(rows) == 1
        assert rows[0]["remark"] == "Invoice Booked And Adjusted"
        assert rows[0]["status"] == "Manually Mapped"

    def test_classification_shows_reviewer_selected_reason_not_generic_label(self):
        """
        Client-confirmed bug: after manually linking two entries and
        selecting a reason (e.g. "Opening Balance as per Company") in the
        "Reason for Linking" dialog, the exported Classification column
        always showed the generic "Manually Mapped" placeholder instead of
        the actual reason the reviewer picked — losing that specific
        selection entirely from the Classification column (it only ever
        appeared in Remark).
        """
        c1 = FakeEntry(pass_number=8)
        p1 = FakeEntry(pass_number=8)
        match = FakeMatch(
            company_entry_ids=[c1.id], vendor_entry_ids=[p1.id],
            difference_amount=15110.0, status_reason="Opening Balance as per Company",
        )
        by_id = {str(c1.id): c1, str(p1.id): p1}

        rows = ReconciliationExportService()._build_recon_rows([c1], [p1], [match], by_id)

        assert len(rows) == 1
        assert rows[0]["status"] == "Manually Mapped"
        assert rows[0]["classification"] == "Opening Balance as per Company"

    def test_classification_falls_back_to_manually_mapped_when_no_reason_stored(self):
        """A pass-8 match with no status_reason persisted (legacy data,
        or a reason that failed to save) must still fall back to the
        generic "Manually Mapped" label rather than showing blank."""
        c1 = FakeEntry(pass_number=8)
        p1 = FakeEntry(pass_number=8)
        match = FakeMatch(company_entry_ids=[c1.id], vendor_entry_ids=[p1.id], status_reason=None)
        by_id = {str(c1.id): c1, str(p1.id): p1}

        rows = ReconciliationExportService()._build_recon_rows([c1], [p1], [match], by_id)

        assert rows[0]["classification"] == "Manually Mapped"

    def test_remark_blank_for_auto_matched_rows(self):
        """A plain exact invoice-number match (pass 1) carries no auto-remark
        — only rows falling back to weaker classifications or flagged by the
        reversal-doc marker get an explanatory remark (see
        TestAutoGeneratedRemark below)."""
        c1 = FakeEntry(pass_number=1, amount=1000.0)
        p1 = FakeEntry(pass_number=1, amount=-1000.0)
        match = FakeMatch(company_entry_ids=[c1.id], vendor_entry_ids=[p1.id])
        by_id = {str(c1.id): c1, str(p1.id): p1}

        rows = ReconciliationExportService()._build_recon_rows([c1], [p1], [match], by_id)

        assert rows[0]["remark"] == ""


class TestAutoGeneratedRemark:
    """
    Client-provided reference export (docs/Reconciliation-DYNAMIC-EVENTS---
    PRODUCTION.xlsx) annotates a "Correct Remark" for every row that isn't a
    clean exact match, opening/closing balance, or plain one-sided TDS/invoice
    difference. _auto_remark derives that same remark automatically from the
    row's Classification and invoice-number "reversal" marker, so exports no
    longer leave those rows blank.
    """

    def test_reversal_entries_classification_gets_internal_transaction_remark(self):
        """SA/AB same-side netting (Classification == 'Reversal Entries')
        always gets the Emcure-internal-transaction explanation."""
        c1 = FakeEntry(document_type="SA", pass_number=13)
        c2 = FakeEntry(document_type="SA", pass_number=13)
        match = FakeMatch(company_entry_ids=[c1.id, c2.id], vendor_entry_ids=[])
        by_id = {str(c1.id): c1, str(c2.id): c2}

        rows = ReconciliationExportService()._build_recon_rows([c1, c2], [], [match], by_id)

        assert all(r["classification"] == "Reversal Entries" for r in rows)
        assert all(
            r["remark"] == "Emcure internal transaction is being showing as a reversal"
            for r in rows
        )

    def test_unpaired_sa_entry_is_not_classified_as_reversal_entries(self):
        """
        Client-confirmed bug (screenshot): an UNPAIRED SA entry ("MSME
        Interest", amount -664.73, no same-side netting counterpart) still
        showed up under "Reversal Entries" purely because of its raw doc
        type/category — even though it never actually netted against
        another SA entry via _other_entry_match (pass 13). Only an SA entry
        that DID pair off (pass_number == OTHER_ENTRY_PASS) is a genuine
        same-side reversal; an unpaired one is a real open item and must
        fall through to normal unmatched classification.
        """
        c1 = FakeEntry(document_type="SA", document_category="Adjusted", pass_number=None)
        rows = ReconciliationExportService()._build_recon_rows([c1], [], [], {str(c1.id): c1})

        assert rows[0]["classification"] != "Reversal Entries"
        assert rows[0]["classification"] == "Unmatched"

    def test_date_range_and_amount_matched_gets_invoice_number_guidance(self):
        """Pass TOLERANCE_DATE (fell back to amount + date range instead of
        an exact invoice-number match) gets the invoice-number-matching
        guidance remark."""
        from src.domain.services.vlr.reconciliation_engine_service import MatchPassType

        c1 = FakeEntry(
            pass_number=MatchPassType.TOLERANCE_DATE, amount=-251546.0,
            derived_invoice_number="DEP/25-26/0234",
        )
        p1 = FakeEntry(
            pass_number=MatchPassType.TOLERANCE_DATE, amount=255883.0,
            derived_invoice_number="DEP/25-26/0234",
        )
        match = FakeMatch(company_entry_ids=[c1.id], vendor_entry_ids=[p1.id])
        by_id = {str(c1.id): c1, str(p1.id): p1}

        rows = ReconciliationExportService()._build_recon_rows([c1], [p1], [match], by_id)

        assert rows[0]["classification"] == "Date Range and Amount Matched"
        assert rows[0]["remark"] == "Invoices should primarily be matched by invoice number"

    def test_reversal_doc_placeholder_invoice_number_flags_remark_without_reclassifying(self):
        """An entry whose invoice number literally reads like a reversal
        placeholder (e.g. "Reversal Doc") gets the Reversal Entries remark
        as a reviewer hint, even when it matched (or stayed unmatched) under
        a different Classification entirely — the marker never changes
        Status/Classification, only the Remark."""
        c1 = FakeEntry(
            document_category="Invoice", derived_invoice_number="Reversal Doc",
        )
        rows = ReconciliationExportService()._build_recon_rows([c1], [], [], {str(c1.id): c1})

        assert rows[0]["classification"] == "Unmatched"
        assert rows[0]["remark"] == "Reversal Entries"

    def test_manual_link_reason_always_overrides_auto_remark(self):
        """A reviewer's manual-link reason takes priority over any
        auto-generated remark, even if the row would otherwise qualify for
        one (e.g. classification == 'Reversal Entries')."""
        c1 = FakeEntry(document_type="SA", pass_number=8)
        p1 = FakeEntry(document_type="SA", pass_number=8)
        match = FakeMatch(
            company_entry_ids=[c1.id], vendor_entry_ids=[p1.id],
            status_reason="Company Internal Entries",
        )
        by_id = {str(c1.id): c1, str(p1.id): p1}

        rows = ReconciliationExportService()._build_recon_rows([c1], [p1], [match], by_id)

        assert rows[0]["remark"] == "Company Internal Entries"

    def test_plain_unmatched_invoice_with_no_marker_stays_blank(self):
        """A genuinely one-sided invoice difference with no reversal marker
        and no fallback classification gets no auto-remark."""
        p1 = FakeEntry(document_category="Invoice", derived_invoice_number="DEP/25-26/0993")
        rows = ReconciliationExportService()._build_recon_rows([], [p1], [], {str(p1.id): p1})

        assert rows[0]["remark"] == ""


class TestMultiEntryGroupDifference:
    """
    Client-reported bug: while matching payments, entries are grouped
    together based on the clearing document (a MANY_TO_ONE / ONE_TO_MANY
    match). During the difference calculation, only ONE column's amount was
    considered per row instead of the total grouped amount, producing a
    non-zero "Difference" on a match that actually reconciles to zero as a
    whole group.

    Reproduces the exact scenario: 1 party payment (-41088) matched against
    2 company entries (17143 + 23945 = 41088) grouped by clearing document
    "7053009376". The group's own difference_amount is correctly 0, but
    each row previously recomputed its own (c_amt + p_amt), giving -23945
    on the row with only one company leg and no party leg.
    """

    def test_group_rows_show_group_total_difference_not_per_row(self):
        c1 = FakeEntry(
            document_category="Payment", document_type="KZ", amount=17143.0,
            document_number="0177", pass_number=5,
        )
        c2 = FakeEntry(
            document_category="Payment", document_type="KZ", amount=23945.0,
            document_number="0177", pass_number=5,
        )
        p1 = FakeEntry(
            document_category="Receipt", document_type="RO", amount=-41088.0,
            document_number="7053009376", pass_number=5,
        )
        match = FakeMatch(
            company_entry_ids=[c1.id, c2.id],
            vendor_entry_ids=[p1.id],
            difference_amount=0.0,
        )
        by_id = {str(c1.id): c1, str(c2.id): c2, str(p1.id): p1}

        rows = ReconciliationExportService()._build_recon_rows(
            [c1, c2], [p1], [match], by_id
        )

        assert len(rows) == 2
        for r in rows:
            assert r["difference"] == 0.0

    def test_single_pair_match_unaffected_by_group_fix(self):
        """A plain 1:1 match (not a group) must still use its own per-row
        (c_amt + p_amt) diff, unchanged by the group-difference fix."""
        c1 = FakeEntry(document_category="Invoice", amount=-1000.0, pass_number=1)
        p1 = FakeEntry(document_category="Invoice", amount=995.0, pass_number=1)
        match = FakeMatch(
            company_entry_ids=[c1.id], vendor_entry_ids=[p1.id], difference_amount=-5.0,
        )
        by_id = {str(c1.id): c1, str(p1.id): p1}

        rows = ReconciliationExportService()._build_recon_rows(
            [c1], [p1], [match], by_id
        )

        assert len(rows) == 1
        assert rows[0]["difference"] == -5.0


class TestInvoiceNumberNeverExportsPlaceholder:
    """
    Client-reported bug: the exported workbook's Invoice Number columns
    (Party/Company Invoice Number, and the standalone "Party" sheet) were
    getting filled with the internal synthetic placeholder "BAL_ROW_<n>"
    (inserted by file_parser_service for rows with no recognizable invoice
    column) instead of being left blank. "Don't need to fill the invoice
    number column with this BAL_ROW."

    _invoice_number()'s main lookup loop already skipped BAL_ROW_* values,
    but its final fallback line returned `derived or doc` unconditionally —
    exactly the values the loop had just rejected — so a genuinely
    unidentifiable invoice number resurfaced as the raw placeholder anyway.
    """

    def test_bal_row_placeholder_in_document_number_is_left_blank(self):
        entry = FakeEntry(document_number="BAL_ROW_82", derived_invoice_number=None)
        assert _invoice_number(entry) == ""

    def test_bal_row_placeholder_in_derived_invoice_number_is_left_blank(self):
        entry = FakeEntry(document_number="", derived_invoice_number="BAL_ROW_15")
        assert _invoice_number(entry) == ""

    def test_bal_row_in_both_fields_is_left_blank(self):
        entry = FakeEntry(document_number="BAL_ROW_9", derived_invoice_number="BAL_ROW_9")
        assert _invoice_number(entry) == ""

    def test_real_document_number_is_still_returned(self):
        entry = FakeEntry(document_number="INV-1001", derived_invoice_number=None)
        assert _invoice_number(entry) == "INV-1001"

    def test_real_derived_invoice_number_takes_priority(self):
        entry = FakeEntry(document_number="DOC-1", derived_invoice_number="XBLNR-500")
        assert _invoice_number(entry) == "XBLNR-500"

    def test_falls_back_to_raw_data_alias_when_placeholder(self):
        entry = FakeEntry(
            document_number="BAL_ROW_3",
            derived_invoice_number=None,
            raw_data={"Invoice No": "REAL-789"},
        )
        assert _invoice_number(entry) == "REAL-789"

    def test_none_entry_returns_blank(self):
        assert _invoice_number(None) == ""

    def test_raw_data_containing_placeholder_itself_is_rejected(self):
        """
        Real-data bug: for balance rows (Opening/Closing Balance), raw_data's
        own "document number"/"reference" aliases can already BE the
        BAL_ROW_* placeholder (carried over from an earlier pipeline pass),
        e.g. raw_data={"document number": "BAL_ROW_167"}. The raw_data
        fallback must reject that too, not just the modelled
        document_number/derived_invoice_number fields — otherwise the
        placeholder round-trips straight back out through the "reference"
        alias.
        """
        entry = FakeEntry(
            document_number="BAL_ROW_167",
            derived_invoice_number=None,
            raw_data={"document number": "BAL_ROW_167", "reference": "BAL_ROW_167"},
        )
        assert _invoice_number(entry) == ""


class TestMatchedResidualBucket:
    """
    Client-reported bug: the Summary sheet's "Amount Unsettled by
    Company/Vendor" line showed a large plug value with no linked annexure
    and no entry count ("the differential amount is not getting
    linked/mapped in the output file"). Root cause: matched-pair residuals
    (TDS deducted, rounding write-offs, unexplained gaps) were never
    itemised on the Summary sheet — only one-sided (unmatched) entries were
    — so their combined difference silently fell into the generic residual
    plug at the bottom instead of a real, traceable summary line.
    """

    def test_summary_sheet_has_no_reconciled_entries_or_amount_unsettled_sections(self):
        """
        Client-reported bug (screenshot): matched entries with a genuine
        residual (e.g. a journal-entry-vs-payment pair booked as
        "Reconciled") appeared BOTH as their own itemised difference-group
        line (via matched_residual_bucket) AND a second time under a
        "Reconciled Entries" section ("Reconciled - Company" /
        "Reconciled - Party") — the same rupee amount counted twice on
        the same sheet, described as "it creates a double effect in the
        reconciliation, and the same double impact is getting reflected".
        Per explicit correction, both the "Reconciled Entries" section AND
        the "Amount Unsettled by Company/Vendor" balancing-plug section
        (which is not a real classification — it should only reflect
        open items/not-reconciled points) must not appear on the Summary
        sheet at all.
        """
        c1 = FakeEntry(document_category="Invoice", amount=-100000.0, pass_number=2)
        p1 = FakeEntry(document_category="Journal", amount=100000.0, pass_number=2)
        match = FakeMatch(
            company_entry_ids=[c1.id], vendor_entry_ids=[p1.id],
            difference_amount=0.0,
        )
        by_id = {str(c1.id): c1, str(p1.id): p1}

        service = ReconciliationExportService()
        service._tds_percentage_value = 0.0
        service._gst_percentage_value = 0.0
        service._reco_dt = "07-Sep-26 12:00 PM"
        service._party_code = ""

        rows = service._build_recon_rows([c1], [p1], [match], by_id)

        from openpyxl import Workbook
        wb = Workbook()
        ws = wb.active

        class FakeVendor:
            name = "Newtroninc"

        service._compute_summary(
            ws, FakeVendor(), [c1], [p1], [match],
            None, None, "1.0 Rs", "0.0 - 10.0", "0 - 15",
            rows,
        )

        all_labels = {
            cell.value for row in ws.iter_rows() for cell in row if cell.value is not None
        }
        assert "Reconciled Entries" not in all_labels
        assert "Reconciled - Company" not in all_labels
        assert "Reconciled - Party" not in all_labels
        assert "Amount Unsettled by Company" not in all_labels
        assert "Amount Unsettled by Vendor" not in all_labels

    def test_tds_booked_row_is_bucketed_under_tds_group(self):
        from src.domain.services.vlr.reconciliation_export_service import (
            matched_residual_bucket,
        )

        rows = [
            {"status": "TDS Booked by Company", "difference": 1794.78},
        ]
        out = matched_residual_bucket(rows)
        key = ("TDS / TCS Difference", "TDS Booked by Company",
               "Company to confirm TDS deducted and share the TDS certificate")
        assert key in out
        assert float(out[key][0]) == 1794.78
        assert out[key][1] == 1

    def test_write_off_row_is_bucketed_separately_from_tds(self):
        from src.domain.services.vlr.reconciliation_export_service import (
            matched_residual_bucket,
        )

        rows = [
            {"status": "Write off / Rounding off", "difference": 2.5},
            {"status": "TDS Booked by Party", "difference": 500.0},
        ]
        out = matched_residual_bucket(rows)
        assert len(out) == 2

    def test_reconciled_rows_are_excluded(self):
        from src.domain.services.vlr.reconciliation_export_service import (
            matched_residual_bucket,
        )

        rows = [
            {"status": "Reconciled", "difference": 0.0},
            {"status": "Manually Mapped", "difference": 0.0},
        ]
        assert matched_residual_bucket(rows) == {}

    def test_zero_difference_rows_are_excluded(self):
        from src.domain.services.vlr.reconciliation_export_service import (
            matched_residual_bucket,
        )

        rows = [{"status": "TDS Booked by Company", "difference": 0.0}]
        assert matched_residual_bucket(rows) == {}

    def test_multiple_rows_same_status_aggregate_amount_and_count(self):
        from src.domain.services.vlr.reconciliation_export_service import (
            matched_residual_bucket,
        )

        rows = [
            {"status": "TDS Booked by Company", "difference": 1000.0},
            {"status": "TDS Booked by Company", "difference": 500.0},
        ]
        out = matched_residual_bucket(rows)
        assert len(out) == 1
        amt, cnt = next(iter(out.values()))
        assert amt == 1500.0
        assert cnt == 2

    def test_summary_sheet_links_matched_residuals_to_annexure_no_plug(self):
        """
        End-to-end: a matched pair with a genuine TDS-sized residual must
        show up as its own linked, counted Summary line, and must NOT be
        hidden behind a fabricated "Amount Unsettled" balancing plug (that
        plug section was removed entirely per explicit correction — the
        Summary sheet must only show genuine classified differences, and
        "Difference" should show the honest unexplained gap rather than
        being forced to zero).
        """
        c1 = FakeEntry(document_category="Invoice", amount=-90000.0, pass_number=2)
        p1 = FakeEntry(document_category="Invoice", amount=100000.0, pass_number=2)
        match = FakeMatch(
            company_entry_ids=[c1.id], vendor_entry_ids=[p1.id],
            difference_amount=10000.0,
        )
        by_id = {str(c1.id): c1, str(p1.id): p1}

        service = ReconciliationExportService()
        service._tds_percentage_value = 10.0
        service._gst_percentage_value = 0.0
        service._reco_dt = "24-Aug-26 12:00 PM"
        service._party_code = ""

        rows = service._build_recon_rows([c1], [p1], [match], by_id)
        assert rows[0]["status"] == "TDS Booked by Company"

        from openpyxl import Workbook
        wb = Workbook()
        ws = wb.active

        class FakeVendor:
            name = "Test Vendor"

        annexure_map = service._compute_summary(
            ws, FakeVendor(), [c1], [p1], [match],
            None, None, "1.0 Rs", "0.0 - 10.0", "0 - 15",
            rows,
        )

        # The TDS residual must appear as its own linked annexure line, not
        # folded silently into an unlinked "Amount Unsettled" plug.
        labels = {v[0] for v in annexure_map.values()}
        assert "TDS Booked by Company" in labels

        # No "Amount Unsettled" plug line must appear anywhere on the sheet.
        assert "Amount Unsettled by Company" not in labels
        assert "Amount Unsettled by Vendor" not in labels
        for row in ws.iter_rows():
            for cell in row:
                if cell.value is not None:
                    assert "Amount Unsettled" not in str(cell.value)
                    assert "Reconciled - Company" != cell.value
                    assert "Reconciled - Party" != cell.value

    def test_count_reflects_actual_ledger_entries_not_row_count(self):
        """
        Client-confirmed bug: "why is the count of no. of entries so less?"
        A matched-pair row represents TWO actual ledger lines (one company,
        one vendor) — the entry count must reflect that, matching every
        other count on the same statement (unmatched entries, Reconciled
        Entries), not just count "1 per row" the way this function
        previously did. A real case with 16 TDS-matched PAIRS showed "16"
        on the Particulars statement instead of the true 32 ledger entries.
        """
        from src.domain.services.vlr.reconciliation_export_service import (
            matched_residual_bucket,
        )

        # Realistic row dicts as produced by _build_recon_rows: both sides
        # present (a real matched pair) -> counts as 2 entries.
        rows = [
            {"status": "TDS Booked by Company", "difference": 100.0,
             "company_id": "c1", "party_id": "p1"},
            {"status": "TDS Booked by Company", "difference": 200.0,
             "company_id": "c2", "party_id": "p2"},
        ]
        out = matched_residual_bucket(rows)
        key = ("TDS / TCS Difference", "TDS Booked by Company",
               "Company to confirm TDS deducted and share the TDS certificate")
        assert key in out
        amt, cnt = out[key]
        assert float(amt) == 300.0
        assert cnt == 4, "2 matched pairs = 4 actual ledger entries, not 2 rows"

    def test_count_for_one_sided_leg_of_group_is_one_entry(self):
        """A one-to-many/many-to-one group's 'extra' leg row carries only
        ONE side (see _build_recon_rows) — that's genuinely 1 ledger entry,
        not 2."""
        from src.domain.services.vlr.reconciliation_export_service import (
            matched_residual_bucket,
        )

        rows = [
            {"status": "TDS Booked by Company", "difference": 50.0,
             "company_id": "", "party_id": "p1"},
        ]
        out = matched_residual_bucket(rows)
        key = ("TDS / TCS Difference", "TDS Booked by Company",
               "Company to confirm TDS deducted and share the TDS certificate")
        amt, cnt = out[key]
        assert cnt == 1

    def test_amount_mismatch_row_is_bucketed_by_classification_not_dropped(self):
        """
        Client-confirmed bug (Prince Graphics case): after the Amount
        Mismatch pass (15) was added, its residual was never registered
        for Summary-sheet bucketing, so every one of these matched-but-
        discrepant pairs fell through to the unlinked "Amount Unsettled"
        plug instead of getting its own itemised Summary line — inflating
        "Amount Unsettled by Company" with money that actually belonged to
        a real, already-matched category.

        Status for this pass is "Reconciled" (the pair IS matched) per
        explicit correction — the caveat lives in Classification =
        "Amount Mismatch", so bucketing must key off Classification here,
        not Status.
        """
        from src.domain.services.vlr.reconciliation_export_service import (
            matched_residual_bucket,
        )

        rows = [
            {"status": "Reconciled", "classification": "Amount Mismatch", "difference": 5000.0},
            {"status": "Reconciled", "classification": "Amount Mismatch", "difference": -1200.0},
        ]
        out = matched_residual_bucket(rows)
        key = ("Amount Mismatch Difference", "Amount Mismatch",
               "Finance to review - invoice number and date match but amount differs")
        assert key in out
        assert float(out[key][0]) == 3800.0
        assert out[key][1] == 2

    def test_summary_amount_mismatch_gets_own_linked_line_not_amount_unsettled(self):
        """
        End-to-end reproduction of the Prince Graphics bug: a same-invoice-
        number, same-date pair with an unexplained gap (pass 15) must
        appear as its own "Amount Mismatch Difference" Summary line with a
        real annexure and entry count — not be absorbed into the unlinked
        "Amount Unsettled" plug (that plug section was removed entirely per
        explicit correction).
        """
        from src.domain.services.vlr.reconciliation_engine_service import MatchPassType

        c1 = FakeEntry(
            document_category="Invoice", amount=-90000.0,
            pass_number=MatchPassType.AMOUNT_MISMATCH,
        )
        p1 = FakeEntry(
            document_category="Invoice", amount=95000.0,
            pass_number=MatchPassType.AMOUNT_MISMATCH,
        )
        match = FakeMatch(
            company_entry_ids=[c1.id], vendor_entry_ids=[p1.id],
            difference_amount=5000.0,
        )
        by_id = {str(c1.id): c1, str(p1.id): p1}

        service = ReconciliationExportService()
        service._tds_percentage_value = 0.0
        service._gst_percentage_value = 0.0
        service._reco_dt = "31-Aug-26 12:00 PM"
        service._party_code = ""

        rows = service._build_recon_rows([c1], [p1], [match], by_id)
        # Per explicit correction: an unexplained gap must never report as
        # "Reconciled" — Status is now "Amount Mismatch" directly.
        assert rows[0]["status"] == "Amount Mismatch"
        assert rows[0]["classification"] == "Amount Mismatch"

        from openpyxl import Workbook
        wb = Workbook()
        ws = wb.active

        class FakeVendor:
            name = "Prince Graphics Pvt Ltd"

        annexure_map = service._compute_summary(
            ws, FakeVendor(), [c1], [p1], [match],
            None, None, "1.0 Rs", "0.0 - 10.0", "0 - 15",
            rows,
        )

        labels = {v[0] for v in annexure_map.values()}
        assert "Amount Mismatch" in labels
        assert "Amount Unsettled by Company" not in labels
        assert "Amount Unsettled by Vendor" not in labels

        group_row = None
        for row in ws.iter_rows():
            if row[0].value == "Amount Mismatch Difference":
                group_row = row
        assert group_row is not None, "Amount Mismatch Difference group must render on the Summary sheet"

    def test_tolerance_date_amount_mismatch_gets_own_linked_line_too(self):
        """
        Same end-to-end check, but for pass 12 (TOLERANCE_DATE, "Date Range
        and Amount Matched") — the weakest matching tier. A large,
        unexplained gap on this pass must ALSO get its own linked
        "Amount Mismatch Difference" Summary line, not silently sit as
        "Reconciled" — per explicit correction, both passes 12 and 15 now
        share the same "Amount Mismatch" Status treatment.
        """
        from src.domain.services.vlr.reconciliation_engine_service import MatchPassType

        c1 = FakeEntry(
            document_category="Invoice", amount=-50000.0,
            pass_number=MatchPassType.TOLERANCE_DATE,
        )
        p1 = FakeEntry(
            document_category="Invoice", amount=75000.0,
            pass_number=MatchPassType.TOLERANCE_DATE,
        )
        match = FakeMatch(
            company_entry_ids=[c1.id], vendor_entry_ids=[p1.id],
            difference_amount=25000.0,
        )
        by_id = {str(c1.id): c1, str(p1.id): p1}

        service = ReconciliationExportService()
        service._tds_percentage_value = 0.0
        service._gst_percentage_value = 0.0
        service._reco_dt = "07-Sep-26 12:00 PM"
        service._party_code = ""

        rows = service._build_recon_rows([c1], [p1], [match], by_id)
        assert rows[0]["status"] == "Amount Mismatch"

        from openpyxl import Workbook
        wb = Workbook()
        ws = wb.active

        class FakeVendor:
            name = "Test Vendor"

        annexure_map = service._compute_summary(
            ws, FakeVendor(), [c1], [p1], [match],
            None, None, "1.0 Rs", "0.0 - 10.0", "0 - 15",
            rows,
        )

        labels = {v[0] for v in annexure_map.values()}
        assert "Amount Mismatch" in labels

        group_row = None
        for row in ws.iter_rows():
            if row[0].value == "Amount Mismatch Difference":
                group_row = row
        assert group_row is not None, "Amount Mismatch Difference group must render for a pass-12 row too"


class TestAmountMismatchPassClassification:
    """
    Pass 15 (AMOUNT_MISMATCH) — same invoice number + same date, gap not
    explained by TDS/GST. Per explicit correction: this must NOT be
    reported as "Reconciled" — a genuinely unexplained amount gap is not
    settled, so Status is now "Amount Mismatch" directly (same as
    Classification for this pass), UNLESS the gap turns out to actually
    match the configured TDS tolerance band, in which case it is reported
    as a TDS booking instead (defensive — _amount_mismatch_match itself
    already excludes tax-explained gaps before creating these pairs).
    """

    def test_status_is_amount_mismatch_when_gap_exceeds_tds_tolerance(self):
        from src.domain.services.vlr.reconciliation_engine_service import MatchPassType
        c_entry = FakeEntry(amount=-100000.0)
        p_entry = FakeEntry(amount=95000.0)
        result = _status(MatchPassType.AMOUNT_MISMATCH, c_entry, p_entry, difference=-5000.0)
        assert result == "Amount Mismatch"

    def test_status_is_tds_booked_when_gap_is_within_configured_tds_range(self):
        """Defensive branch: if a gap reaching this pass actually DOES fall
        within the configured TDS range, Status must report the TDS
        booking, not "Amount Mismatch" — Status/Classification must never
        contradict why a gap was or wasn't explained."""
        from src.domain.services.vlr.reconciliation_engine_service import MatchPassType
        c_entry = FakeEntry(amount=-95000.0)
        p_entry = FakeEntry(amount=100000.0)
        result = _status(
            MatchPassType.AMOUNT_MISMATCH, c_entry, p_entry, difference=5000.0,
            tds_percentage=10.0, gst_percentage=0.0, tds_percentage_min=0.0,
        )
        assert result == "TDS Booked by Company"

    def test_classification_is_amount_mismatch(self):
        from src.domain.services.vlr.reconciliation_export_service import _classification
        from src.domain.services.vlr.reconciliation_engine_service import MatchPassType
        assert _classification(MatchPassType.AMOUNT_MISMATCH) == "Amount Mismatch"

    def test_row_status_via_build_recon_rows(self):
        from src.domain.services.vlr.reconciliation_engine_service import MatchPassType
        c1 = FakeEntry(
            document_category="Invoice", amount=-100000.0,
            pass_number=MatchPassType.AMOUNT_MISMATCH,
        )
        p1 = FakeEntry(
            document_category="Invoice", amount=95000.0,
            pass_number=MatchPassType.AMOUNT_MISMATCH,
        )
        match = FakeMatch(
            company_entry_ids=[c1.id], vendor_entry_ids=[p1.id],
            difference_amount=-5000.0,
        )
        by_id = {str(c1.id): c1, str(p1.id): p1}

        rows = ReconciliationExportService()._build_recon_rows([c1], [p1], [match], by_id)

        assert len(rows) == 1
        assert rows[0]["status"] == "Amount Mismatch"
        assert rows[0]["classification"] == "Amount Mismatch"
