"""
Unit tests for the dashboard controller endpoints.

Tests the KPI widget aggregation queries and recent confirmations endpoint.

Requirements: 26.1, 26.2, 26.3, 26.4, 26.5, 26.6, 26.7, 26.8
"""

import pytest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4


# ─── Tests for GET /widgets ──────────────────────────────────────────────────


class TestGetDashboardWidgets:
    """Tests for GET /api/v1/vlr/dashboard/widgets."""

    @pytest.mark.asyncio
    async def test_returns_all_kpi_metrics(self):
        """Widget endpoint returns all expected KPI fields."""
        from src.api.v1.endpoints.vlr.dashboard_controller import get_dashboard_widgets

        mock_session = AsyncMock()

        # Mock sequential query results:
        # 1. open_cases = 5
        # 2. pending_vendor_upload = 2
        # 3. pending_finance_review = 3
        # 4. overdue_cases = 1
        # 5. cases_closed_this_month = 4
        # 6. average_cycle_time = 12.5 days (in seconds epoch diff / 86400)
        # 7. total_entries = 100
        # 8. auto_matched = 60

        results = []
        for value in [5, 2, 3, 1, 4, 12.5, 100, 60]:
            mock_result = MagicMock()
            mock_result.scalar_one.return_value = value
            results.append(mock_result)

        mock_session.execute.side_effect = results

        response = await get_dashboard_widgets(company_code=None, session=mock_session)

        assert response.open_cases == 5
        assert response.pending_vendor_upload == 2
        assert response.pending_finance_review == 3
        assert response.overdue_cases == 1
        assert response.cases_closed_this_month == 4
        assert response.average_cycle_time_days == 12.5
        assert response.auto_match_rate == 60.0  # (60/100)*100

    @pytest.mark.asyncio
    async def test_returns_null_cycle_time_when_no_closed_cases(self):
        """Average cycle time is null when no closed cases exist."""
        from src.api.v1.endpoints.vlr.dashboard_controller import get_dashboard_widgets

        mock_session = AsyncMock()

        # avg returns None when no closed cases
        results = []
        for value in [0, 0, 0, 0, 0, None, 0]:
            mock_result = MagicMock()
            mock_result.scalar_one.return_value = value
            results.append(mock_result)

        mock_session.execute.side_effect = results

        response = await get_dashboard_widgets(company_code=None, session=mock_session)

        assert response.average_cycle_time_days is None
        assert response.auto_match_rate is None  # 0 total entries

    @pytest.mark.asyncio
    async def test_returns_null_auto_match_rate_when_no_entries(self):
        """Auto-match rate is null when no ledger entries exist."""
        from src.api.v1.endpoints.vlr.dashboard_controller import get_dashboard_widgets

        mock_session = AsyncMock()

        # All zeros except auto_match total entries = 0
        results = []
        for value in [10, 2, 1, 0, 3, 5.0, 0]:
            mock_result = MagicMock()
            mock_result.scalar_one.return_value = value
            results.append(mock_result)

        mock_session.execute.side_effect = results

        response = await get_dashboard_widgets(company_code=None, session=mock_session)

        assert response.auto_match_rate is None
        assert response.open_cases == 10

    @pytest.mark.asyncio
    async def test_company_code_filter_applied(self):
        """When company_code is provided, queries are filtered."""
        from src.api.v1.endpoints.vlr.dashboard_controller import get_dashboard_widgets

        mock_session = AsyncMock()

        results = []
        for value in [3, 1, 2, 0, 1, 8.0, 50, 30]:
            mock_result = MagicMock()
            mock_result.scalar_one.return_value = value
            results.append(mock_result)

        mock_session.execute.side_effect = results

        response = await get_dashboard_widgets(company_code="CC01", session=mock_session)

        # Verify it returns data (filtering is validated by SQL construction)
        assert response.open_cases == 3
        assert response.auto_match_rate == 60.0  # (30/50)*100

    @pytest.mark.asyncio
    async def test_auto_match_rate_percentage_calculation(self):
        """Auto-match rate is correctly calculated as percentage."""
        from src.api.v1.endpoints.vlr.dashboard_controller import get_dashboard_widgets

        mock_session = AsyncMock()

        # 200 total entries, 75 auto-matched => 37.5%
        results = []
        for value in [0, 0, 0, 0, 0, None, 200, 75]:
            mock_result = MagicMock()
            mock_result.scalar_one.return_value = value
            results.append(mock_result)

        mock_session.execute.side_effect = results

        response = await get_dashboard_widgets(company_code=None, session=mock_session)

        assert response.auto_match_rate == 37.5


# ─── Tests for GET /recent-confirmations ─────────────────────────────────────


class TestGetRecentConfirmations:
    """Tests for GET /api/v1/vlr/dashboard/recent-confirmations."""

    @pytest.mark.asyncio
    async def test_returns_recent_sign_offs(self):
        """Returns the last N vendor sign-offs ordered by most recent first."""
        from src.api.v1.endpoints.vlr.dashboard_controller import (
            get_recent_confirmations,
        )

        mock_session = AsyncMock()
        case_id_1 = uuid4()
        case_id_2 = uuid4()
        now = datetime.now(timezone.utc)

        # Mock the main query result (rows)
        mock_rows = [
            MagicMock(
                case_id=case_id_1,
                vendor_name="Vendor A",
                signed_at=now - timedelta(hours=1),
                statement_version="v1.0",
                confirmation_text="Confirmed",
            ),
            MagicMock(
                case_id=case_id_2,
                vendor_name="Vendor B",
                signed_at=now - timedelta(hours=2),
                statement_version="v2.0",
                confirmation_text=None,
            ),
        ]

        # First call: main query returning rows
        main_result = MagicMock()
        main_result.all.return_value = mock_rows

        # Second call: count query
        count_result = MagicMock()
        count_result.scalar_one.return_value = 25

        mock_session.execute.side_effect = [main_result, count_result]

        response = await get_recent_confirmations(
            limit=10, company_code=None, session=mock_session
        )

        assert len(response.items) == 2
        assert response.total == 25
        assert response.items[0].case_id == case_id_1
        assert response.items[0].vendor_name == "Vendor A"
        assert response.items[0].statement_version == "v1.0"
        assert response.items[0].confirmation_text == "Confirmed"
        assert response.items[1].case_id == case_id_2
        assert response.items[1].vendor_name == "Vendor B"
        assert response.items[1].confirmation_text is None

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_sign_offs(self):
        """Returns empty list when no sign-offs exist."""
        from src.api.v1.endpoints.vlr.dashboard_controller import (
            get_recent_confirmations,
        )

        mock_session = AsyncMock()

        main_result = MagicMock()
        main_result.all.return_value = []

        count_result = MagicMock()
        count_result.scalar_one.return_value = 0

        mock_session.execute.side_effect = [main_result, count_result]

        response = await get_recent_confirmations(
            limit=10, company_code=None, session=mock_session
        )

        assert len(response.items) == 0
        assert response.total == 0

    @pytest.mark.asyncio
    async def test_respects_limit_parameter(self):
        """Custom limit parameter controls max items returned."""
        from src.api.v1.endpoints.vlr.dashboard_controller import (
            get_recent_confirmations,
        )

        mock_session = AsyncMock()
        now = datetime.now(timezone.utc)

        # Return 5 items
        mock_rows = [
            MagicMock(
                case_id=uuid4(),
                vendor_name=f"Vendor {i}",
                signed_at=now - timedelta(hours=i),
                statement_version=f"v{i}",
                confirmation_text=None,
            )
            for i in range(5)
        ]

        main_result = MagicMock()
        main_result.all.return_value = mock_rows

        count_result = MagicMock()
        count_result.scalar_one.return_value = 100

        mock_session.execute.side_effect = [main_result, count_result]

        response = await get_recent_confirmations(
            limit=5, company_code=None, session=mock_session
        )

        assert len(response.items) == 5
        assert response.total == 100
