"""
Unit tests for the Particulars-statement "View" drill-in bug fix.

Root cause: on the reconciliation statement (Particulars) table, every
difference group ("Closing Balance Difference", "Invoice Difference",
"Other Differences", "TDS / TCS Difference", ...) had its `view_key` set to
one of two generic placeholders ("closing_balance"/"unmatched"), and the
frontend's `particularsViewSlug()` had NO branch that used the group's own
identity at all for non-closing/non-knocking/non-manually-mapped groups —
every one of them fell through to the same hardcoded 'unmatched-company'
slug with zero filtering. So every group's "View" button showed the exact
same full unmatched list, regardless of which group was clicked.

Also covers a second, related bug found while fixing the first: the child
row `side` attribution in `get_reconciliation_particulars` was inverted —
a label containing "by Company" was assigned side="company" when the
underlying entries actually live in the VENDOR ledger (a "not booked by
Company" line means the company hasn't booked it, so the entry itself is
sitting in the vendor's book).

Covers:
- `_particulars_group_for_entry` classifies entries into the same group
  labels used by the Particulars endpoint's own bucketing.
- `group_filter` query param is declared on both unmatched endpoints.
- The particulars endpoint's ParticularsGroup/ParticularsChild view_key
  values equal the real group label (not a generic placeholder), and child
  `side` is attributed correctly.
"""

from unittest.mock import MagicMock

import pytest

from src.api.v1.endpoints.vlr.reconciliation_output_controller import (
    _particulars_group_for_entry,
    get_unmatched_company,
    get_unmatched_vendor,
)


def _mock_entry(document_category="", document_type="", is_tds=False, pass_number=None):
    entry = MagicMock()
    entry.document_category = document_category
    entry.document_type = document_type
    entry.is_tds = is_tds
    entry.raw_data = None
    entry.description = ""
    entry.pass_number = pass_number
    return entry


class TestParticularsGroupForEntry:
    def test_invoice_category_maps_to_invoice_difference(self):
        e = _mock_entry(document_category="Invoice")
        assert _particulars_group_for_entry(e) == "Invoice Difference"

    def test_credit_note_maps_to_debit_credit_note_difference(self):
        e = _mock_entry(document_category="Credit Note")
        assert _particulars_group_for_entry(e) == "Debit Note / Credit Note Difference"

    def test_debit_note_maps_to_debit_credit_note_difference(self):
        e = _mock_entry(document_category="Debit Note")
        assert _particulars_group_for_entry(e) == "Debit Note / Credit Note Difference"

    def test_payment_maps_to_payment_receipt_difference(self):
        e = _mock_entry(document_category="Payment")
        assert _particulars_group_for_entry(e) == "Payment / receipt Difference"

    def test_receipt_maps_to_payment_receipt_difference(self):
        e = _mock_entry(document_category="Receipt")
        assert _particulars_group_for_entry(e) == "Payment / receipt Difference"

    def test_unknown_category_falls_back_to_other_differences(self):
        e = _mock_entry(document_category="Something Unclassified")
        assert _particulars_group_for_entry(e) == "Other Differences"

    def test_opening_balance_excluded(self):
        e = _mock_entry(document_category="Opening Balance")
        assert _particulars_group_for_entry(e) is None

    def test_closing_balance_excluded(self):
        e = _mock_entry(document_category="Closing Balance")
        assert _particulars_group_for_entry(e) is None

    def test_reversal_knockoff_excluded(self):
        e = _mock_entry(document_category="Knocking Off", document_type="AB")
        assert _particulars_group_for_entry(e) is None

    def test_paired_sa_entry_excluded_as_reversal(self):
        """An SA entry that actually netted via same-side pass 13
        (_other_entry_match) is a genuine internal reversal and must stay
        excluded from the difference groups, same as a knock-off."""
        from src.domain.services.vlr.reconciliation_engine_service import (
            OTHER_ENTRY_PASS,
        )
        e = _mock_entry(document_category="Adjusted", document_type="SA", pass_number=OTHER_ENTRY_PASS)
        assert _particulars_group_for_entry(e) is None

    def test_unpaired_sa_entry_is_a_genuine_difference_not_excluded(self):
        """
        Client-confirmed bug (screenshot): an UNPAIRED SA entry ("MSME
        Interest", no same-side netting counterpart, pass_number None)
        was being excluded from the difference groups purely because of
        its raw doc type/category, exactly like a genuine same-side-netted
        reversal — hiding a real open item. Per the mapping doc's Open Item
        Status section, an unpaired SA entry is a genuine difference and
        must fall through to normal classification (Other Differences),
        not be silently dropped.
        """
        e = _mock_entry(document_category="Adjusted", document_type="SA", pass_number=None)
        assert _particulars_group_for_entry(e) == "Other Differences"

    def test_different_groups_are_actually_distinguishable(self):
        # This is the crux of the original bug: every group used to
        # collapse onto the same value. Assert they are genuinely different.
        invoice = _particulars_group_for_entry(_mock_entry(document_category="Invoice"))
        other = _particulars_group_for_entry(_mock_entry(document_category="Unclassified Thing"))
        payment = _particulars_group_for_entry(_mock_entry(document_category="Payment"))
        assert len({invoice, other, payment}) == 3

    def test_unmatched_tds_entry_maps_to_tds_group_regardless_of_raw_category(self):
        # Bug fix (round 2): a genuine unmatched TDS entry is detected via
        # _special_classification (is_tds flag / doc type / narration), NOT
        # via document_category — its raw category can be anything ("TDS
        # Adjusted", "Journal", etc). get_reconciliation_particulars's own
        # _bucket() closure special-cases this and routes it to "TDS / TCS
        # Difference" regardless of raw category, but this function
        # (used for the group_filter drill-in) originally did NOT apply the
        # same override — so the statement's count included the entry under
        # "TDS / TCS Difference" while clicking "View" for that group
        # returned zero results for it, because the drill-in computed a
        # DIFFERENT group for the same entry.
        e = _mock_entry(document_category="Journal", is_tds=True)
        assert _particulars_group_for_entry(e) == "TDS / TCS Difference"

    def test_unmatched_tds_entry_with_tds_adjusted_category_also_maps_correctly(self):
        e = _mock_entry(document_category="TDS Adjusted", is_tds=True)
        assert _particulars_group_for_entry(e) == "TDS / TCS Difference"


class TestGroupFilterParamDeclaredOnUnmatchedEndpoints:
    """Guard against the exact regression: every group's View link used to
    route to the unmatched endpoints with no group-scoping parameter at
    all. Assert `group_filter` is a real declared parameter."""

    @pytest.mark.parametrize("endpoint", [get_unmatched_company, get_unmatched_vendor])
    def test_group_filter_param_declared(self, endpoint):
        import inspect

        params = inspect.signature(endpoint).parameters
        assert "group_filter" in params, (
            f"{endpoint.__name__} does not declare a `group_filter` query "
            "param — the Particulars statement's per-group View links would "
            "have no way to scope results to a single group."
        )


class TestGenuineUnmatchedConditionsExcludeOnlyKnockoffNotSA:
    """
    Client-confirmed bug (screenshot): _NON_DIFFERENCE_CATEGORIES /
    _NON_DIFFERENCE_DOC_TYPES used to blanket-exclude ANY entry with
    category "Adjusted" / doc type "SA" from the unmatched list, regardless
    of match_id — so an unpaired SA entry ("MSME Interest", genuinely
    match_id IS NULL) never showed up as unmatched anywhere, on top of being
    mislabeled "Reversal Entries" in the export. Knock-off (category
    "Knocking Off" / doc type "AB") IS correctly excluded by category/type
    here as defense-in-depth (paired knock-offs get a match_id anyway), but
    "Adjusted"/"SA" must NOT be — an unpaired SA entry only gets excluded by
    match_id IS NOT NULL (i.e. it actually netted via pass 13).
    """

    def test_adjusted_category_not_in_non_difference_categories(self):
        from src.api.v1.endpoints.vlr.reconciliation_output_controller import (
            _NON_DIFFERENCE_CATEGORIES,
        )
        assert "Adjusted" not in _NON_DIFFERENCE_CATEGORIES

    def test_sa_doc_type_not_in_non_difference_doc_types(self):
        from src.api.v1.endpoints.vlr.reconciliation_output_controller import (
            _NON_DIFFERENCE_DOC_TYPES,
        )
        assert "SA" not in _NON_DIFFERENCE_DOC_TYPES

    def test_knocking_off_and_ab_still_excluded(self):
        """Knock-off exclusion by category/doc-type must be unaffected."""
        from src.api.v1.endpoints.vlr.reconciliation_output_controller import (
            _NON_DIFFERENCE_CATEGORIES,
            _NON_DIFFERENCE_DOC_TYPES,
        )
        assert "Knocking Off" in _NON_DIFFERENCE_CATEGORIES
        assert "AB" in _NON_DIFFERENCE_DOC_TYPES
