"""
Unit tests for the manual-link status reason feature.

Covers:
- The fixed reason list (docs/Update Status.xlsx) is loaded correctly.
- ManualLinkRequest requires status_reason (Pydantic validation).
"""

import pytest
from pydantic import ValidationError

from src.domain.services.vlr.status_reasons import STATUS_REASONS, VALID_STATUS_REASONS
from src.api.v1.endpoints.vlr.reconciliation_output_controller import ManualLinkRequest


class TestStatusReasonsList:
    def test_reasons_list_matches_source_count(self):
        # docs/Update Status.xlsx has 92 reason rows (excluding the header).
        assert len(STATUS_REASONS) == 92

    def test_valid_status_reasons_is_a_set_of_the_same_values(self):
        assert VALID_STATUS_REASONS == frozenset(STATUS_REASONS)

    def test_known_reasons_present(self):
        for expected in (
            "Reconciled",
            "TDS Booked by Company",
            "Write off / Rounding off",
            "Invoice Booked And Adjusted",
        ):
            assert expected in VALID_STATUS_REASONS

    def test_no_duplicate_reasons(self):
        assert len(STATUS_REASONS) == len(set(STATUS_REASONS))


class TestManualLinkRequestSchema:
    """status_reason must be mandatory on the manual-link request payload —
    a reviewer cannot link two entries without selecting why."""

    def test_status_reason_is_required(self):
        with pytest.raises(ValidationError):
            ManualLinkRequest(
                company_entry_ids=["c1"],
                vendor_entry_ids=["v1"],
            )

    def test_status_reason_accepted_when_provided(self):
        req = ManualLinkRequest(
            company_entry_ids=["c1"],
            vendor_entry_ids=["v1"],
            status_reason="Reconciled",
        )
        assert req.status_reason == "Reconciled"

    def test_notes_remains_optional(self):
        req = ManualLinkRequest(
            company_entry_ids=["c1"],
            vendor_entry_ids=["v1"],
            status_reason="Reconciled",
        )
        assert req.notes is None
