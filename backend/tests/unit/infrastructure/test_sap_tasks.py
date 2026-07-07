"""
Unit tests for SAP pull Celery task and API endpoint.

Tests the task dispatch, progress tracking, audit logging, and
error handling for the SAP data extraction workflow.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient

from src.api.v1.endpoints.vlr.sap_pull_controller import (
    SAPPullRequest,
    SAPPullResponse,
    SAPPullStatusResponse,
    router,
)
from src.infrastructure.tasks.vlr.sap_tasks import sap_pull_task, _execute_sap_pull


# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def app():
    """Create a test FastAPI app with the SAP pull router."""
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    return app


@pytest.fixture
def mock_current_user():
    """Mock an authenticated user."""
    user = MagicMock()
    user.username = "testuser"
    user.id = uuid4()
    user.is_active = True
    user.is_blocked = False
    return user


@pytest.fixture
def mock_request_model():
    """Create a mock reconciliation request model."""
    model = MagicMock()
    model.id = str(uuid4())
    model.company_code = "1000"
    model.status = "active"
    model.period_start = date(2024, 1, 1)
    model.period_end = date(2024, 12, 31)
    model.fiscal_year = "2024"
    return model


# ---------------------------------------------------------------------------
# Schema Tests
# ---------------------------------------------------------------------------


class TestSAPPullRequestSchema:
    """Test the SAPPullRequest Pydantic schema."""

    def test_empty_body_allows_none_vendor_codes(self):
        """An empty body defaults vendor_codes to None (pull all)."""
        req = SAPPullRequest()
        assert req.vendor_codes is None

    def test_explicit_vendor_codes(self):
        """Vendor codes can be explicitly specified."""
        req = SAPPullRequest(vendor_codes=["V001", "V002"])
        assert req.vendor_codes == ["V001", "V002"]

    def test_empty_list_is_valid(self):
        """An empty list is a valid value for vendor_codes."""
        req = SAPPullRequest(vendor_codes=[])
        assert req.vendor_codes == []


class TestSAPPullResponseSchema:
    """Test the SAPPullResponse Pydantic schema."""

    def test_response_serialization(self):
        """Response schema serializes correctly."""
        resp = SAPPullResponse(
            task_id="abc-123",
            request_id="req-456",
            status="accepted",
            message="Queued for 3 vendors.",
            vendor_count=3,
        )
        data = resp.model_dump()
        assert data["task_id"] == "abc-123"
        assert data["vendor_count"] == 3
        assert data["status"] == "accepted"


class TestSAPPullStatusResponseSchema:
    """Test the SAPPullStatusResponse Pydantic schema."""

    def test_pending_status(self):
        """Pending task has no progress or result."""
        resp = SAPPullStatusResponse(task_id="t1", status="PENDING")
        assert resp.progress is None
        assert resp.result is None

    def test_progress_status(self):
        """In-progress task includes progress metadata."""
        resp = SAPPullStatusResponse(
            task_id="t1",
            status="PROGRESS",
            progress={"current": 2, "total": 5, "status": "Processing..."},
        )
        assert resp.progress["current"] == 2

    def test_success_status(self):
        """Completed task includes result."""
        resp = SAPPullStatusResponse(
            task_id="t1",
            status="SUCCESS",
            result={"total_rows": 500, "status": "completed"},
        )
        assert resp.result["total_rows"] == 500


# ---------------------------------------------------------------------------
# Endpoint Tests
# ---------------------------------------------------------------------------


class TestSAPPullEndpoint:
    """Test the POST /api/v1/vlr/requests/{id}/sap-pull endpoint."""

    @pytest.mark.asyncio
    async def test_trigger_sap_pull_returns_202(self, app, mock_current_user, mock_request_model):
        """Successful trigger returns 202 with task info."""
        from src.api.v1.dependencies import get_current_active_user
        from src.infrastructure.database.session import get_db_session

        # Mock dependencies
        app.dependency_overrides[get_current_active_user] = lambda: mock_current_user

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_request_model
        mock_session.execute = AsyncMock(return_value=mock_result)

        # Mock the vendor query for getting vendor codes
        mock_vendor_result = MagicMock()
        mock_vendor_result.all.return_value = [("V001",), ("V002",)]

        # First call returns the request, second call returns vendor codes
        mock_session.execute = AsyncMock(
            side_effect=[mock_result, mock_vendor_result]
        )

        app.dependency_overrides[get_db_session] = lambda: mock_session

        # Mock Celery task dispatch
        mock_task_result = MagicMock()
        mock_task_result.id = "celery-task-id-123"

        with patch(
            "src.api.v1.endpoints.vlr.sap_pull_controller.sap_pull_task"
        ) as mock_task:
            mock_task.delay.return_value = mock_task_result

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post(
                    f"/api/v1/vlr/requests/{mock_request_model.id}/sap-pull",
                    json={"vendor_codes": ["V001", "V002"]},
                )

            assert response.status_code == 202
            data = response.json()
            assert data["task_id"] == "celery-task-id-123"
            assert data["status"] == "accepted"
            assert data["vendor_count"] == 2

        # Clean up overrides
        app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_trigger_sap_pull_request_not_found(self, app, mock_current_user):
        """Returns 404 when request doesn't exist."""
        from src.api.v1.dependencies import get_current_active_user
        from src.infrastructure.database.session import get_db_session

        app.dependency_overrides[get_current_active_user] = lambda: mock_current_user

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)
        app.dependency_overrides[get_db_session] = lambda: mock_session

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                f"/api/v1/vlr/requests/{uuid4()}/sap-pull",
            )

        assert response.status_code == 404
        app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_trigger_sap_pull_invalid_status(self, app, mock_current_user, mock_request_model):
        """Returns 409 when request is in closed status."""
        from src.api.v1.dependencies import get_current_active_user
        from src.infrastructure.database.session import get_db_session

        mock_request_model.status = "closed"
        app.dependency_overrides[get_current_active_user] = lambda: mock_current_user

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_request_model
        mock_session.execute = AsyncMock(return_value=mock_result)
        app.dependency_overrides[get_db_session] = lambda: mock_session

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                f"/api/v1/vlr/requests/{mock_request_model.id}/sap-pull",
            )

        assert response.status_code == 409
        assert "closed" in response.json()["detail"]
        app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_trigger_sap_pull_no_vendors(self, app, mock_current_user, mock_request_model):
        """Returns 400 when no vendors found for the request."""
        from src.api.v1.dependencies import get_current_active_user
        from src.infrastructure.database.session import get_db_session

        app.dependency_overrides[get_current_active_user] = lambda: mock_current_user

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_request_model

        # Second call for vendors returns empty
        mock_vendor_result = MagicMock()
        mock_vendor_result.all.return_value = []

        mock_session.execute = AsyncMock(
            side_effect=[mock_result, mock_vendor_result]
        )
        app.dependency_overrides[get_db_session] = lambda: mock_session

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                f"/api/v1/vlr/requests/{mock_request_model.id}/sap-pull",
            )

        assert response.status_code == 400
        assert "No vendors" in response.json()["detail"]
        app.dependency_overrides.clear()


class TestSAPPullStatusEndpoint:
    """Test the GET /api/v1/vlr/requests/{id}/sap-pull/{task_id} endpoint."""

    @pytest.mark.asyncio
    async def test_get_pending_status(self, app, mock_current_user):
        """Returns PENDING status for queued tasks."""
        from src.api.v1.dependencies import get_current_active_user

        app.dependency_overrides[get_current_active_user] = lambda: mock_current_user

        mock_async_result = MagicMock()
        mock_async_result.status = "PENDING"
        mock_async_result.info = None
        mock_async_result.result = None

        with patch(
            "src.api.v1.endpoints.vlr.sap_pull_controller.celery_app"
        ) as mock_celery:
            mock_celery.AsyncResult.return_value = mock_async_result

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get(
                    f"/api/v1/vlr/requests/{uuid4()}/sap-pull/task-id-123",
                )

            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "PENDING"
            assert data["progress"] is None

        app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_get_progress_status(self, app, mock_current_user):
        """Returns progress info for in-progress tasks."""
        from src.api.v1.dependencies import get_current_active_user

        app.dependency_overrides[get_current_active_user] = lambda: mock_current_user

        mock_async_result = MagicMock()
        mock_async_result.status = "PROGRESS"
        mock_async_result.info = {"current": 3, "total": 5, "status": "Processing..."}
        mock_async_result.result = None

        with patch(
            "src.api.v1.endpoints.vlr.sap_pull_controller.celery_app"
        ) as mock_celery:
            mock_celery.AsyncResult.return_value = mock_async_result

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get(
                    f"/api/v1/vlr/requests/{uuid4()}/sap-pull/task-id-456",
                )

            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "PROGRESS"
            assert data["progress"]["current"] == 3
            assert data["progress"]["total"] == 5

        app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_get_success_status(self, app, mock_current_user):
        """Returns result data for completed tasks."""
        from src.api.v1.dependencies import get_current_active_user

        app.dependency_overrides[get_current_active_user] = lambda: mock_current_user

        mock_async_result = MagicMock()
        mock_async_result.status = "SUCCESS"
        mock_async_result.info = None
        mock_async_result.result = {
            "total_rows": 500,
            "status": "completed",
            "vendor_count": 3,
        }

        with patch(
            "src.api.v1.endpoints.vlr.sap_pull_controller.celery_app"
        ) as mock_celery:
            mock_celery.AsyncResult.return_value = mock_async_result

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get(
                    f"/api/v1/vlr/requests/{uuid4()}/sap-pull/task-id-789",
                )

            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "SUCCESS"
            assert data["result"]["total_rows"] == 500

        app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Celery Task Unit Tests
# ---------------------------------------------------------------------------


class TestSAPPullTask:
    """Test the Celery task configuration and behavior."""

    def test_task_is_registered(self):
        """The SAP pull task is properly registered with Celery."""
        assert sap_pull_task.name == "vlr.sap_pull"

    def test_task_has_correct_time_limits(self):
        """Task has appropriate time limits for SAP extraction."""
        assert sap_pull_task.time_limit == 120
        assert sap_pull_task.soft_time_limit == 90

    def test_task_has_retry_configuration(self):
        """Task has retry configuration."""
        assert sap_pull_task.max_retries == 3

    def test_sap_pull_request_schema_validation(self):
        """SAPPullRequest validates vendor_codes as optional list of strings."""
        # Valid with vendor codes
        req = SAPPullRequest(vendor_codes=["V001", "V002", "V003"])
        assert len(req.vendor_codes) == 3

        # Valid without vendor codes (pulls all)
        req = SAPPullRequest()
        assert req.vendor_codes is None
