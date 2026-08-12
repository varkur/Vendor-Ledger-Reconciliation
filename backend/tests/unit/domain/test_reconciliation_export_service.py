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
