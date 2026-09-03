"""
Unit tests for surfacing MATCHED-pair residual differences on the
Particulars/Differences statement.

Root cause: the Particulars endpoint (`/reconciliation/{case_id}/particulars`)
only ever aggregated UNMATCHED (one-sided) entries into its difference
groups. A matched PAIR that still carries a genuine residual — TDS deducted
from one side, a small rounding write-off, an unexplained amount gap, or a
same-invoice amount mismatch — never appeared in the statement at all, even
though the downloaded Excel export already surfaces these via
`matched_residual_bucket`. Client: "are the matched columns not a part of
these particulars and differences? we also need those."

Covers:
- `_filter_matches_by_computed_status` correctly identifies matches by their
  computed Status ("TDS Booked by Company") or Classification
  ("Amount Mismatch").
- `computed_status_filter` query param is declared on both matched and
  confirmation endpoints, so the new drill-in actually works end to end.
- `ParticularsChild`/`ParticularsGroup` schemas carry the new
  is_matched_residual/matched_status fields needed for the frontend to
  route "View" to the Matched/Recommended tab instead of unmatched.
"""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.api.v1.endpoints.vlr.reconciliation_output_controller import (
    _filter_matches_by_computed_status,
    get_confirmation_items,
    get_matched_items,
)
from src.api.v1.schemas.vlr.reconciliation_output_schemas import (
    ParticularsChild,
    ParticularsGroup,
)
from src.domain.services.vlr.reconciliation_engine_service import MatchPassType


def _mock_entry(amount=0):
    entry = MagicMock()
    entry.amount = Decimal(str(amount))
    entry.raw_data = None
    return entry


def _mock_match(match_id, pass_number, difference_amount=None):
    match = MagicMock()
    match.id = match_id
    match.pass_number = pass_number
    match.difference_amount = difference_amount
    match.company_entry_ids = ["c-" + match_id]
    match.vendor_entry_ids = ["v-" + match_id]
    return match


class TestFilterMatchesByComputedStatus:
    async def _run(self, matches, entries_by_match, filter_value, tds_max=10.0, tds_min=0.0, gst=0.0):
        async def fake_get_first_entry(entry_ids, session):
            if not entry_ids:
                return None
            entry_id = entry_ids[0]
            for mid, (ce, ve) in entries_by_match.items():
                if entry_id == "c-" + mid:
                    return ce
                if entry_id == "v-" + mid:
                    return ve
            return None

        with patch(
            "src.api.v1.endpoints.vlr.reconciliation_output_controller._get_first_entry",
            side_effect=fake_get_first_entry,
        ):
            return await _filter_matches_by_computed_status(
                matches, filter_value, tds_max, tds_min, gst, session=AsyncMock()
            )

    @pytest.mark.asyncio
    async def test_finds_tds_gst_pass_matching_configured_rate(self):
        # TDS_GST pass, company amount smaller -> "TDS Booked by Company",
        # gap of exactly 10% of the vendor amount (within configured 0-10%).
        ce = _mock_entry(900)
        ve = _mock_entry(1000)
        m = _mock_match("m1", MatchPassType.TDS_GST, difference_amount=-100)
        result = await self._run([m], {"m1": (ce, ve)}, "TDS Booked by Company")
        assert result == [m]

    @pytest.mark.asyncio
    async def test_amount_mismatch_pass_filtered_by_classification(self):
        # AMOUNT_MISMATCH pass -> Status "Reconciled", Classification
        # "Amount Mismatch" — filter must match on Classification here,
        # not Status (they deliberately differ for this one pass).
        ce = _mock_entry(1000)
        ve = _mock_entry(1200)
        m = _mock_match("m1", MatchPassType.AMOUNT_MISMATCH, difference_amount=-200)
        result = await self._run([m], {"m1": (ce, ve)}, "Amount Mismatch")
        assert result == [m]

    @pytest.mark.asyncio
    async def test_no_match_for_unrelated_filter_value(self):
        ce = _mock_entry(900)
        ve = _mock_entry(1000)
        m = _mock_match("m1", MatchPassType.TDS_GST, difference_amount=-100)
        result = await self._run([m], {"m1": (ce, ve)}, "Write off / Rounding off")
        assert result == []

    @pytest.mark.asyncio
    async def test_exact_pass_matches_reconciled_only_when_asked(self):
        ce = _mock_entry(1000)
        ve = _mock_entry(1000)
        m = _mock_match("m1", MatchPassType.EXACT, difference_amount=0)
        result = await self._run([m], {"m1": (ce, ve)}, "Reconciled")
        assert result == [m]


class TestComputedStatusFilterParamDeclared:
    """Guard against the exact regression: matched-pair residuals were
    completely invisible on the Particulars statement because there was no
    way to filter the Matched/Confirmation endpoints by computed Status at
    all. Assert the param now exists."""

    @pytest.mark.parametrize("endpoint", [get_matched_items, get_confirmation_items])
    def test_computed_status_filter_param_declared(self, endpoint):
        import inspect

        params = inspect.signature(endpoint).parameters
        assert "computed_status_filter" in params, (
            f"{endpoint.__name__} does not declare a `computed_status_filter` "
            "query param — the Particulars statement's matched-residual "
            "drill-in would have no way to scope results."
        )


class TestParticularsSchemaCarriesMatchedResidualFields:
    def test_child_defaults_to_not_matched_residual(self):
        child = ParticularsChild(label="x", amount=Decimal("0"), no_of_entries=0)
        assert child.is_matched_residual is False
        assert child.matched_status == ""

    def test_child_can_be_marked_as_matched_residual(self):
        child = ParticularsChild(
            label="TDS Booked by Company",
            amount=Decimal("1794.78"),
            no_of_entries=3,
            is_matched_residual=True,
            matched_status="TDS Booked by Company",
        )
        assert child.is_matched_residual is True
        assert child.matched_status == "TDS Booked by Company"

    def test_group_defaults_to_not_matched_residual(self):
        group = ParticularsGroup(label="Invoice Difference", amount=Decimal("0"), no_of_entries=0)
        assert group.is_matched_residual is False

    def test_group_can_be_marked_as_matched_residual(self):
        group = ParticularsGroup(
            label="TDS / TCS Difference", amount=Decimal("1794.78"), no_of_entries=3,
            is_matched_residual=True,
        )
        assert group.is_matched_residual is True
