"""
Unit tests for VLR bulk action API endpoints.

Tests the POST endpoints for bulk case actions:
- POST /api/v1/vlr/reminders/send — Send reminders for specified case IDs
- POST /api/v1/vlr/cases/bulk-review — Bulk advance cases to review stage
- POST /api/v1/vlr/cases/bulk-review-done — Bulk mark review as complete
- POST /api/v1/vlr/cases/bulk-signoff-request — Bulk trigger sign-off invite

Requirements: 4
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.api.v1.endpoints.vlr.case_controller import router as case_router
from src.api.v1.endpoints.vlr.notification_controller import reminders_router
from src.api.v1.dependencies import get_current_active_user
from src.infrastructure.database.session import get_db_session


def _mock_user() -> MagicMock:
    """Create a mock authenticated user."""
    user = MagicMock()
    user.id = uuid4()
    user.username = "test_analyst"
    user.is_active = True
    user.is_blocked = False
    return user


def _mock_case(case_id=None, status="matched", workflow_step="auto_reconciliation"):
    """Create a mock case object."""
    case = MagicMock()
    case.id = case_id or uuid4()
    case.status = status
    case.current_workflow_step = workflow_step
    case.is_deleted = False
    return case


def _create_test_app_cases(mock_session: AsyncMock) -> FastAPI:
    """Create a test app with case router, bypassing auth and permissions."""
    app = FastAPI()
    app.include_router(case_router, prefix="/api/v1")

    user = _mock_user()
    app.dependency_overrides[get_current_active_user] = lambda: user

    async def _mock_get_db_session():
        yield mock_session

    app.dependency_overrides[get_db_session] = _mock_get_db_session

    # Remove permission dependencies from routes
    for route in app.routes:
        if hasattr(route, "dependencies"):
            route.dependencies = []
        if hasattr(route, "dependant"):
            route.dependant.dependencies = [
                d for d in route.dependant.dependencies
                if not _is_permission_dependency(d)
            ]

    return app


def _create_test_app_reminders(mock_session: AsyncMock) -> FastAPI:
    """Create a test app with reminders router, bypassing auth and permissions."""
    app = FastAPI()
    app.include_router(reminders_router, prefix="/api/v1")

    user = _mock_user()
    app.dependency_overrides[get_current_active_user] = lambda: user

    async def _mock_get_db_session():
        yield mock_session

    app.dependency_overrides[get_db_session] = _mock_get_db_session

    # Remove permission dependencies from routes
    for route in app.routes:
        if hasattr(route, "dependencies"):
            route.dependencies = []
        if hasattr(route, "dependant"):
            route.dependant.dependencies = [
                d for d in route.dependant.dependencies
                if not _is_permission_dependency(d)
            ]

    return app


def _is_permission_dependency(dep) -> bool:
    """Check if a dependency is a require_permission dependency."""
    if hasattr(dep, "call") and dep.call is not None:
        name = getattr(dep.call, "__name__", "")
        if name == "permission_checker":
            return True
    return False


# ──────────────────────────────────────────────────────────────────────
# Tests: POST /api/v1/vlr/reminders/send
# ──────────────────────────────────────────────────────────────────────


class TestSendRemindersByCases:
    """Test POST /api/v1/vlr/reminders/send"""

    @pytest.mark.asyncio
    async def test_send_reminders_success(self):
        """Valid case IDs should return success results."""
        case_id = str(uuid4())
        mock_session = MagicMock()

        # Mock the async execute call - session.execute is awaited
        mock_case = _mock_case(case_id=case_id)
        mock_exec_result = MagicMock()
        mock_exec_result.scalar_one_or_none.return_value = mock_case

        async def mock_execute(*args, **kwargs):
            return mock_exec_result

        mock_session.execute = mock_execute

        app = _create_test_app_reminders(mock_session)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/vlr/reminders/send",
                json={"case_ids": [case_id], "company_code": "1000"},
            )

        assert response.status_code == 200
        data = response.json()
        assert len(data["results"]) == 1
        assert data["results"][0]["case_id"] == case_id
        assert data["results"][0]["success"] is True

    @pytest.mark.asyncio
    async def test_send_reminders_case_not_found(self):
        """Non-existent case IDs should return failure results."""
        case_id = str(uuid4())
        mock_session = MagicMock()

        # Mock no case found
        mock_exec_result = MagicMock()
        mock_exec_result.scalar_one_or_none.return_value = None

        async def mock_execute(*args, **kwargs):
            return mock_exec_result

        mock_session.execute = mock_execute

        app = _create_test_app_reminders(mock_session)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/vlr/reminders/send",
                json={"case_ids": [case_id], "company_code": "1000"},
            )

        assert response.status_code == 200
        data = response.json()
        assert len(data["results"]) == 1
        assert data["results"][0]["case_id"] == case_id
        assert data["results"][0]["success"] is False
        assert "not found" in data["results"][0]["message"]

    @pytest.mark.asyncio
    async def test_send_reminders_invalid_case_id_format(self):
        """Invalid UUID format should return failure."""
        mock_session = MagicMock()

        app = _create_test_app_reminders(mock_session)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/vlr/reminders/send",
                json={"case_ids": ["not-a-uuid"], "company_code": "1000"},
            )

        assert response.status_code == 200
        data = response.json()
        assert len(data["results"]) == 1
        assert data["results"][0]["success"] is False
        assert "Invalid case ID format" in data["results"][0]["message"]

    @pytest.mark.asyncio
    async def test_send_reminders_empty_case_ids_rejected(self):
        """Empty case_ids list should be rejected by validation."""
        mock_session = MagicMock()

        app = _create_test_app_reminders(mock_session)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/vlr/reminders/send",
                json={"case_ids": [], "company_code": "1000"},
            )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_send_reminders_multiple_cases_mixed_results(self):
        """Multiple case IDs should return independent results."""
        valid_case_id = str(uuid4())
        invalid_case_id = "not-a-uuid"
        mock_session = MagicMock()

        # Mock: valid case found
        mock_case = _mock_case(case_id=valid_case_id)
        mock_exec_result = MagicMock()
        mock_exec_result.scalar_one_or_none.return_value = mock_case

        async def mock_execute(*args, **kwargs):
            return mock_exec_result

        mock_session.execute = mock_execute

        app = _create_test_app_reminders(mock_session)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/vlr/reminders/send",
                json={"case_ids": [valid_case_id, invalid_case_id], "company_code": "1000"},
            )

        assert response.status_code == 200
        data = response.json()
        assert len(data["results"]) == 2
        # First result should succeed
        assert data["results"][0]["case_id"] == valid_case_id
        assert data["results"][0]["success"] is True
        # Second result should fail
        assert data["results"][1]["case_id"] == invalid_case_id
        assert data["results"][1]["success"] is False


# ──────────────────────────────────────────────────────────────────────
# Tests: POST /api/v1/vlr/cases/bulk-review
# ──────────────────────────────────────────────────────────────────────


class TestBulkReview:
    """Test POST /api/v1/vlr/cases/bulk-review"""

    @pytest.mark.asyncio
    async def test_bulk_review_success(self):
        """Valid cases should be advanced to review stage."""
        case_id = str(uuid4())
        mock_session = AsyncMock()

        app = _create_test_app_cases(mock_session)

        with patch(
            "src.api.v1.endpoints.vlr.case_controller.CaseRepositoryImpl"
        ) as MockRepo, patch(
            "src.domain.services.vlr.workflow_orchestrator_service.WorkflowOrchestratorService.advance",
            new_callable=AsyncMock,
        ) as mock_advance, patch(
            "src.api.v1.endpoints.vlr.case_controller.RequestManagerService"
        ) as MockService:
            # Setup mock repo
            mock_repo_instance = AsyncMock()
            mock_case = _mock_case(case_id=case_id)
            mock_repo_instance.get_by_id = AsyncMock(return_value=mock_case)
            MockRepo.return_value = mock_repo_instance

            # Setup mock service
            mock_service_instance = AsyncMock()
            mock_service_instance.transition_case_status = AsyncMock(return_value=mock_case)
            MockService.return_value = mock_service_instance

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post(
                    "/api/v1/vlr/cases/bulk-review",
                    json={"case_ids": [case_id], "company_code": "1000"},
                )

        assert response.status_code == 200
        data = response.json()
        assert len(data["results"]) == 1
        assert data["results"][0]["case_id"] == case_id
        assert data["results"][0]["success"] is True
        assert "review" in data["results"][0]["message"].lower()

    @pytest.mark.asyncio
    async def test_bulk_review_case_not_found(self):
        """Non-existent cases should return failure results."""
        case_id = str(uuid4())
        mock_session = AsyncMock()

        app = _create_test_app_cases(mock_session)

        with patch(
            "src.api.v1.endpoints.vlr.case_controller.CaseRepositoryImpl"
        ) as MockRepo:
            mock_repo_instance = AsyncMock()
            mock_repo_instance.get_by_id = AsyncMock(return_value=None)
            MockRepo.return_value = mock_repo_instance

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post(
                    "/api/v1/vlr/cases/bulk-review",
                    json={"case_ids": [case_id], "company_code": "1000"},
                )

        assert response.status_code == 200
        data = response.json()
        assert data["results"][0]["success"] is False
        assert "not found" in data["results"][0]["message"]

    @pytest.mark.asyncio
    async def test_bulk_review_empty_case_ids_rejected(self):
        """Empty case_ids list should be rejected by validation."""
        mock_session = AsyncMock()
        app = _create_test_app_cases(mock_session)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/vlr/cases/bulk-review",
                json={"case_ids": [], "company_code": "1000"},
            )

        assert response.status_code == 422


# ──────────────────────────────────────────────────────────────────────
# Tests: POST /api/v1/vlr/cases/bulk-review-done
# ──────────────────────────────────────────────────────────────────────


class TestBulkReviewDone:
    """Test POST /api/v1/vlr/cases/bulk-review-done"""

    @pytest.mark.asyncio
    async def test_bulk_review_done_success(self):
        """Valid cases should be marked as review done."""
        case_id = str(uuid4())
        mock_session = AsyncMock()

        app = _create_test_app_cases(mock_session)

        with patch(
            "src.api.v1.endpoints.vlr.case_controller.CaseRepositoryImpl"
        ) as MockRepo, patch(
            "src.domain.services.vlr.workflow_orchestrator_service.WorkflowOrchestratorService.advance",
            new_callable=AsyncMock,
        ) as mock_advance, patch(
            "src.api.v1.endpoints.vlr.case_controller.RequestManagerService"
        ) as MockService:
            mock_repo_instance = AsyncMock()
            mock_case = _mock_case(case_id=case_id, status="review", workflow_step="finance_review")
            mock_repo_instance.get_by_id = AsyncMock(return_value=mock_case)
            MockRepo.return_value = mock_repo_instance

            mock_service_instance = AsyncMock()
            mock_service_instance.transition_case_status = AsyncMock(return_value=mock_case)
            MockService.return_value = mock_service_instance

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post(
                    "/api/v1/vlr/cases/bulk-review-done",
                    json={"case_ids": [case_id], "company_code": "1000"},
                )

        assert response.status_code == 200
        data = response.json()
        assert len(data["results"]) == 1
        assert data["results"][0]["case_id"] == case_id
        assert data["results"][0]["success"] is True
        assert "complete" in data["results"][0]["message"].lower()

    @pytest.mark.asyncio
    async def test_bulk_review_done_invalid_id(self):
        """Invalid case ID format should return failure."""
        mock_session = AsyncMock()
        app = _create_test_app_cases(mock_session)

        with patch(
            "src.api.v1.endpoints.vlr.case_controller.CaseRepositoryImpl"
        ) as MockRepo:
            MockRepo.return_value = AsyncMock()

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post(
                    "/api/v1/vlr/cases/bulk-review-done",
                    json={"case_ids": ["invalid-id"], "company_code": "1000"},
                )

        assert response.status_code == 200
        data = response.json()
        assert data["results"][0]["success"] is False
        assert "Invalid case ID format" in data["results"][0]["message"]


# ──────────────────────────────────────────────────────────────────────
# Tests: POST /api/v1/vlr/cases/bulk-signoff-request
# ──────────────────────────────────────────────────────────────────────


class TestBulkSignoffRequest:
    """Test POST /api/v1/vlr/cases/bulk-signoff-request"""

    @pytest.mark.asyncio
    async def test_bulk_signoff_request_success(self):
        """Valid cases should be advanced to sign-off and invite sent."""
        case_id = str(uuid4())
        mock_session = AsyncMock()

        app = _create_test_app_cases(mock_session)

        with patch(
            "src.api.v1.endpoints.vlr.case_controller.CaseRepositoryImpl"
        ) as MockRepo, patch(
            "src.domain.services.vlr.workflow_orchestrator_service.WorkflowOrchestratorService.advance",
            new_callable=AsyncMock,
        ) as mock_advance:
            mock_repo_instance = AsyncMock()
            mock_case = _mock_case(case_id=case_id, status="pending_approval", workflow_step="finance_approval")
            mock_repo_instance.get_by_id = AsyncMock(return_value=mock_case)
            MockRepo.return_value = mock_repo_instance

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post(
                    "/api/v1/vlr/cases/bulk-signoff-request",
                    json={"case_ids": [case_id], "company_code": "1000"},
                )

        assert response.status_code == 200
        data = response.json()
        assert len(data["results"]) == 1
        assert data["results"][0]["case_id"] == case_id
        assert data["results"][0]["success"] is True
        assert "sign-off" in data["results"][0]["message"].lower()

    @pytest.mark.asyncio
    async def test_bulk_signoff_request_case_not_found(self):
        """Non-existent cases should return failure."""
        case_id = str(uuid4())
        mock_session = AsyncMock()

        app = _create_test_app_cases(mock_session)

        with patch(
            "src.api.v1.endpoints.vlr.case_controller.CaseRepositoryImpl"
        ) as MockRepo:
            mock_repo_instance = AsyncMock()
            mock_repo_instance.get_by_id = AsyncMock(return_value=None)
            MockRepo.return_value = mock_repo_instance

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post(
                    "/api/v1/vlr/cases/bulk-signoff-request",
                    json={"case_ids": [case_id], "company_code": "1000"},
                )

        assert response.status_code == 200
        data = response.json()
        assert data["results"][0]["success"] is False
        assert "not found" in data["results"][0]["message"]

    @pytest.mark.asyncio
    async def test_bulk_signoff_missing_company_code_rejected(self):
        """Missing company_code should be rejected by validation."""
        mock_session = AsyncMock()
        app = _create_test_app_cases(mock_session)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/vlr/cases/bulk-signoff-request",
                json={"case_ids": [str(uuid4())]},
            )

        assert response.status_code == 422
