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
