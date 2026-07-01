"""
Integration tests for authentication API endpoints.
Tests the full request/response cycle through FastAPI test client.
"""

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from src.domain.entities.user import User
from src.infrastructure.security.password_encoder import hash_password
from src.main import app


@pytest.fixture
def active_user():
    return User(
        id=uuid4(),
        username="integrationuser",
        password_hash=hash_password("TestPass123!"),
        is_active=True,
        is_blocked=False,
        role="USER",
    )


@pytest.fixture
def mock_user_repo(active_user):
    repo = AsyncMock()
    repo.get_by_username.return_value = active_user
    return repo


@pytest.mark.asyncio
class TestLoginAPI:
    """Integration tests for POST /api/v1/auth/login."""

    async def test_login_success(self, mock_user_repo, active_user):
        """Valid login should return 200 with token pair."""
        with patch(
            "src.api.v1.dependencies.get_user_repository",
            return_value=mock_user_repo,
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post(
                    "/api/v1/auth/login",
                    json={"username": "integrationuser", "password": "TestPass123!"},
                )

            assert response.status_code == 200
            data = response.json()
            assert "access_token" in data
            assert "refresh_token" in data
            assert data["token_type"] == "Bearer"

    async def test_login_invalid_password(self, mock_user_repo):
        """Wrong password should return 401."""
        with patch(
            "src.api.v1.dependencies.get_user_repository",
            return_value=mock_user_repo,
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post(
                    "/api/v1/auth/login",
                    json={"username": "integrationuser", "password": "WrongPass!"},
                )

            assert response.status_code == 401

    async def test_login_missing_fields(self):
        """Missing fields should return 422."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/auth/login",
                json={},
            )

        assert response.status_code == 422


@pytest.mark.asyncio
class TestCorrelationIdHeader:
    """Integration tests verifying correlation ID is returned in responses."""

    async def test_response_has_correlation_id(self):
        """Every response should include X-Correlation-ID header."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/")

        assert "x-correlation-id" in response.headers

    async def test_provided_correlation_id_is_echoed(self):
        """If client sends X-Correlation-ID, it should be echoed back."""
        custom_id = "my-custom-correlation-id"
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                "/", headers={"X-Correlation-ID": custom_id}
            )

        assert response.headers.get("x-correlation-id") == custom_id
