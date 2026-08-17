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
        c_entry = FakeEntry()
        c_entry.amount = -29729.22  # type: ignore[attr-defined]
        p_entry = FakeEntry()
        p_entry.amount = 31524.0  # type: ignore[attr-defined]
        result = _status(2, c_entry, p_entry, difference=1794.78)
        # Company has the SMALLER absolute amount -> company booked the TDS.
        assert result == "TDS Booked by Company"


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
