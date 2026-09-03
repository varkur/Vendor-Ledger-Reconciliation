"""
Unit tests for the "search" query param bug fix on the Reconciliation Output
tabs.

Root cause: the "Search by reference..." box on all 4 tab endpoints
(matched, confirmation, unmatched-company, unmatched-vendor) sent a
`search=...` query param on every keystroke, but none of the endpoints
declared or read it — FastAPI silently drops unrecognized query params, so
the box never actually filtered anything.

Covers:
- `_filter_matches_by_search` (used by the matched/confirmation tabs, where
  the reference number lives on the LINKED ledger entry, not on
  MatchResultModel itself).
- The `search` query param is now declared and wired on all 4 GET endpoints.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.api.v1.endpoints.vlr.reconciliation_output_controller import (
    _filter_matches_by_search,
    get_confirmation_items,
    get_matched_items,
    get_unmatched_company,
    get_unmatched_vendor,
)


def _mock_entry(reference_number=None, document_number=None, derived_invoice_number=None):
    entry = MagicMock()
    entry.reference_number = reference_number
    entry.document_number = document_number
    entry.derived_invoice_number = derived_invoice_number
    entry.raw_data = None
    return entry


def _mock_match(match_id, company_entry=None, vendor_entry=None):
    match = MagicMock()
    match.id = match_id
    match.company_entry_ids = ["c-" + match_id] if company_entry else []
    match.vendor_entry_ids = ["v-" + match_id] if vendor_entry else []
    match._company_entry = company_entry
    match._vendor_entry = vendor_entry
    return match


class TestFilterMatchesBySearch:
    """`_filter_matches_by_search` — matched/confirmation tabs."""

    async def _run(self, matches, term):
        async def fake_get_first_entry(entry_ids, session):
            if not entry_ids:
                return None
            entry_id = entry_ids[0]
            for m in matches:
                if entry_id == ("c-" + m.id) and m._company_entry is not None:
                    return m._company_entry
                if entry_id == ("v-" + m.id) and m._vendor_entry is not None:
                    return m._vendor_entry
            return None

        with patch(
            "src.api.v1.endpoints.vlr.reconciliation_output_controller._get_first_entry",
            side_effect=fake_get_first_entry,
        ):
            return await _filter_matches_by_search(matches, term, session=AsyncMock())

    @pytest.mark.asyncio
    async def test_matches_by_company_reference_number(self):
        m1 = _mock_match("m1", company_entry=_mock_entry(reference_number="INV-1001"))
        m2 = _mock_match("m2", company_entry=_mock_entry(reference_number="INV-2002"))
        result = await self._run([m1, m2], "1001")
        assert result == [m1]

    @pytest.mark.asyncio
    async def test_matches_by_vendor_document_number(self):
        m1 = _mock_match("m1", vendor_entry=_mock_entry(document_number="DOC-9"))
        m2 = _mock_match("m2", vendor_entry=_mock_entry(document_number="DOC-8"))
        result = await self._run([m1, m2], "doc-9")
        assert result == [m1]

    @pytest.mark.asyncio
    async def test_search_is_case_insensitive(self):
        m1 = _mock_match("m1", company_entry=_mock_entry(reference_number="ABC-XYZ"))
        result = await self._run([m1], "abc-xyz")
        assert result == [m1]

    @pytest.mark.asyncio
    async def test_empty_search_returns_all_matches_unfiltered(self):
        m1 = _mock_match("m1", company_entry=_mock_entry(reference_number="INV-1"))
        m2 = _mock_match("m2", vendor_entry=_mock_entry(reference_number="INV-2"))
        result = await self._run([m1, m2], "")
        assert result == [m1, m2]

    @pytest.mark.asyncio
    async def test_no_match_when_term_not_found_in_either_side(self):
        m1 = _mock_match(
            "m1",
            company_entry=_mock_entry(reference_number="INV-1"),
            vendor_entry=_mock_entry(reference_number="INV-1"),
        )
        result = await self._run([m1], "does-not-exist")
        assert result == []


class TestSearchParamDeclaredOnAllFourEndpoints:
    """Guard against the exact regression: FastAPI silently drops undeclared
    query params, so this asserts `search` is a real parameter on every
    tab's list endpoint (not just present in the request from the frontend)."""

    @pytest.mark.parametrize(
        "endpoint",
        [get_matched_items, get_confirmation_items, get_unmatched_company, get_unmatched_vendor],
    )
    def test_search_param_declared(self, endpoint):
        import inspect

        params = inspect.signature(endpoint).parameters
        assert "search" in params, (
            f"{endpoint.__name__} does not declare a `search` query param — "
            "the frontend search box would silently be ignored."
        )
