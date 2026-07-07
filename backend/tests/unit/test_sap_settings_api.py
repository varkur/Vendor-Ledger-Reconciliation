"""
Unit tests for SAP Settings API endpoints.

Tests the GET/PUT/POST endpoints for SAP connection settings and field mapping.
Verifies that credentials are never exposed in responses.

Requirements: 20.1, 20.2, 20.3, 20.5, 20.6
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.api.v1.endpoints.vlr.sap_settings_controller import (
    FIELD_MAPPING_KEY,
    GLOBAL_COMPANY_CODE,
    SAP_BASE_URL_KEY,
    SAP_CLIENT_KEY,
    SAP_HOST_KEY,
    SAP_PASSWORD_KEY,
    SAP_SYSTEM_NUMBER_KEY,
    SAP_USERNAME_KEY,
    _get_setting_repository,
    router,
)
from src.api.v1.dependencies import get_current_active_user
from src.infrastructure.database.session import get_db_session
from src.infrastructure.security.encryption import encrypt_value


def _mock_setting(key: str, value: str, value_type: str = "string") -> MagicMock:
    """Create a mock setting object."""
    setting = MagicMock()
    setting.key = key
    setting.value = value
    setting.value_type = value_type
    setting.company_code = GLOBAL_COMPANY_CODE
    return setting


def _mock_user() -> MagicMock:
    """Create a mock authenticated user."""
    user = MagicMock()
    user.id = uuid4()
    user.username = "admin"
    user.is_active = True
    user.is_blocked = False
    return user


def _create_test_app(mock_repo: AsyncMock, mock_user_obj: MagicMock | None = None) -> FastAPI:
    """Create a minimal test app with SAP settings router, bypassing auth and permissions."""
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")

    user = mock_user_obj or _mock_user()

    # Override dependencies
    app.dependency_overrides[get_current_active_user] = lambda: user
    app.dependency_overrides[_get_setting_repository] = lambda: mock_repo
    app.dependency_overrides[get_db_session] = lambda: AsyncMock()

    # Override all permission dependencies used by the router.
    # require_permission returns a new callable each time, so we override the
    # actual dependency objects that were captured during router creation.
    # The cleanest way is to override the dependencies directly on the routes.
    for route in app.routes:
        if hasattr(route, "dependencies"):
            route.dependencies = []  # type: ignore[assignment]
        if hasattr(route, "dependant"):
            route.dependant.dependencies = [
                d for d in route.dependant.dependencies
                if not _is_permission_dependency(d)
            ]

    return app


def _is_permission_dependency(dep) -> bool:
    """Check if a dependency is a require_permission dependency."""
    if hasattr(dep, "call") and dep.call is not None:
        # The permission_checker closure has the name "permission_checker"
        name = getattr(dep.call, "__name__", "")
        if name == "permission_checker":
            return True
    return False


class TestGetSAPConnection:
    """Test GET /api/v1/vlr/settings/sap-connection"""

    @pytest.mark.asyncio
    async def test_get_sap_connection_returns_masked_credentials(self):
        """Credentials should be masked in the response — never exposed as plaintext."""
        # Pre-encrypt credentials as they would be stored
        encrypted_username = encrypt_value("sap_admin_user")
        encrypted_password = encrypt_value("super_secret_pass")

        mock_repo = AsyncMock()

        async def mock_get_by_key(company_code, key):
            settings_map = {
                SAP_HOST_KEY: _mock_setting(SAP_HOST_KEY, "sap.example.com"),
                SAP_SYSTEM_NUMBER_KEY: _mock_setting(SAP_SYSTEM_NUMBER_KEY, "00"),
                SAP_CLIENT_KEY: _mock_setting(SAP_CLIENT_KEY, "100"),
                SAP_USERNAME_KEY: _mock_setting(SAP_USERNAME_KEY, encrypted_username, "encrypted"),
                SAP_PASSWORD_KEY: _mock_setting(SAP_PASSWORD_KEY, encrypted_password, "encrypted"),
                SAP_BASE_URL_KEY: _mock_setting(SAP_BASE_URL_KEY, "https://sap.example.com/api"),
            }
            return settings_map.get(key)

        mock_repo.get_by_key = mock_get_by_key

        app = _create_test_app(mock_repo)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/vlr/settings/sap-connection")

        assert response.status_code == 200
        data = response.json()

        # Credentials must be masked
        assert "sap_admin_user" not in data["username"]
        assert "super_secret_pass" not in data["password"]
        assert data["username"].startswith("*")
        assert data["password"].startswith("*")
        # Last 4 chars visible
        assert data["username"].endswith("user")
        assert data["password"].endswith("pass")

        # Non-sensitive fields should be plaintext
        assert data["host"] == "sap.example.com"
        assert data["system_number"] == "00"
        assert data["client"] == "100"
        assert data["base_url"] == "https://sap.example.com/api"
        assert data["is_configured"] is True

    @pytest.mark.asyncio
    async def test_get_sap_connection_unconfigured(self):
        """When no settings exist, should return empty/default values with is_configured=False."""
        mock_repo = AsyncMock()
        mock_repo.get_by_key = AsyncMock(return_value=None)

        app = _create_test_app(mock_repo)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/vlr/settings/sap-connection")

        assert response.status_code == 200
        data = response.json()
        assert data["is_configured"] is False
        assert data["host"] == ""
        assert data["username"] == ""
        assert data["password"] == ""


class TestUpdateSAPConnection:
    """Test PUT /api/v1/vlr/settings/sap-connection"""

    @pytest.mark.asyncio
    async def test_update_sap_connection_encrypts_credentials(self):
        """Credentials should be stored encrypted, and response should mask them."""
        stored_values: dict[str, str] = {}

        mock_repo = AsyncMock()

        async def mock_upsert(company_code, key, value, **kwargs):
            stored_values[key] = value
            setting = _mock_setting(key, value, kwargs.get("value_type", "string"))
            return setting

        async def mock_get_by_key(company_code, key):
            if key in stored_values:
                vtype = "encrypted" if "username" in key or "password" in key else "string"
                return _mock_setting(key, stored_values[key], vtype)
            return None

        mock_repo.upsert = mock_upsert
        mock_repo.get_by_key = mock_get_by_key

        app = _create_test_app(mock_repo)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.put(
                "/api/v1/vlr/settings/sap-connection",
                json={
                    "host": "new-sap.example.com",
                    "username": "new_admin",
                    "password": "new_secret_pass",
                    "base_url": "https://new-sap.example.com/api",
                },
            )

        assert response.status_code == 200
        data = response.json()

        # Response should mask credentials
        assert "new_admin" not in data["username"]
        assert "new_secret_pass" not in data["password"]
        assert data["username"].endswith("dmin")
        assert data["password"].endswith("pass")

        # Stored values should be encrypted (not plaintext)
        assert stored_values[SAP_USERNAME_KEY] != "new_admin"
        assert stored_values[SAP_PASSWORD_KEY] != "new_secret_pass"
        # Host should be stored as-is (not sensitive)
        assert stored_values[SAP_HOST_KEY] == "new-sap.example.com"

    @pytest.mark.asyncio
    async def test_update_partial_fields_only(self):
        """Updating only some fields should not affect others."""
        stored_values: dict[str, str] = {}

        mock_repo = AsyncMock()

        async def mock_upsert(company_code, key, value, **kwargs):
            stored_values[key] = value
            return _mock_setting(key, value)

        async def mock_get_by_key(company_code, key):
            if key in stored_values:
                return _mock_setting(key, stored_values[key])
            return None

        mock_repo.upsert = mock_upsert
        mock_repo.get_by_key = mock_get_by_key

        app = _create_test_app(mock_repo)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.put(
                "/api/v1/vlr/settings/sap-connection",
                json={"host": "updated-host.com"},
            )

        assert response.status_code == 200
        # Only host should be stored
        assert SAP_HOST_KEY in stored_values
        assert SAP_USERNAME_KEY not in stored_values
        assert SAP_PASSWORD_KEY not in stored_values


class TestSAPConnectionTest:
    """Test POST /api/v1/vlr/settings/sap-connection/test"""

    @pytest.mark.asyncio
    async def test_connection_test_success(self):
        """Test connection should return success when SAP is reachable."""
        mock_repo = AsyncMock()
        mock_repo.get_by_key = AsyncMock(return_value=None)

        app = _create_test_app(mock_repo)

        # Mock the SAPConnectorService.test_connection
        from src.infrastructure.external.sap_connector import ConnectionTestResult

        mock_result = ConnectionTestResult(
            success=True,
            message="SAP connection successful.",
            response_time_ms=150.5,
        )

        with patch(
            "src.api.v1.endpoints.vlr.sap_settings_controller.SAPConnectorService"
        ) as MockConnector:
            instance = MockConnector.return_value
            instance.test_connection = AsyncMock(return_value=mock_result)

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post("/api/v1/vlr/settings/sap-connection/test")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["message"] == "SAP connection successful."
        assert data["response_time_ms"] == 150.5

    @pytest.mark.asyncio
    async def test_connection_test_failure(self):
        """Test connection should return failure when SAP is unreachable."""
        mock_repo = AsyncMock()
        mock_repo.get_by_key = AsyncMock(return_value=None)

        app = _create_test_app(mock_repo)

        from src.infrastructure.external.sap_connector import ConnectionTestResult

        mock_result = ConnectionTestResult(
            success=False,
            message="SAP connection failed: ConnectTimeout",
            response_time_ms=30000.0,
        )

        with patch(
            "src.api.v1.endpoints.vlr.sap_settings_controller.SAPConnectorService"
        ) as MockConnector:
            instance = MockConnector.return_value
            instance.test_connection = AsyncMock(return_value=mock_result)

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post("/api/v1/vlr/settings/sap-connection/test")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert "failed" in data["message"]


class TestUpdateFieldMapping:
    """Test PUT /api/v1/vlr/settings/field-mapping"""

    @pytest.mark.asyncio
    async def test_update_field_mapping_valid(self):
        """Valid field mappings should be stored as JSON."""
        stored_values: dict[str, str] = {}

        mock_repo = AsyncMock()

        async def mock_upsert(company_code, key, value, **kwargs):
            stored_values[key] = value
            return _mock_setting(key, value, "json")

        mock_repo.upsert = mock_upsert

        app = _create_test_app(mock_repo)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.put(
                "/api/v1/vlr/settings/field-mapping",
                json={
                    "mappings": [
                        {"sap_field": "ZUONR", "internal_field": "assignment_number"},
                        {"sap_field": "BELNR", "internal_field": "document_number"},
                        {"sap_field": "BLART", "internal_field": "document_type"},
                        {"sap_field": "DMBTR", "internal_field": "amount"},
                        {"sap_field": "BUDAT", "internal_field": "posting_date"},
                    ]
                },
            )

        assert response.status_code == 200
        data = response.json()
        assert len(data["mappings"]) == 5
        assert data["mappings"][0]["sap_field"] == "ZUONR"
        assert data["mappings"][0]["internal_field"] == "assignment_number"
        assert data["updated_at"] is not None

        # Verify stored as JSON
        stored_json = json.loads(stored_values[FIELD_MAPPING_KEY])
        assert len(stored_json) == 5

    @pytest.mark.asyncio
    async def test_update_field_mapping_invalid_internal_field(self):
        """Invalid internal field names should be rejected with 422."""
        mock_repo = AsyncMock()

        app = _create_test_app(mock_repo)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.put(
                "/api/v1/vlr/settings/field-mapping",
                json={
                    "mappings": [
                        {"sap_field": "ZUONR", "internal_field": "nonexistent_field"},
                    ]
                },
            )

        assert response.status_code == 422
        data = response.json()
        assert "nonexistent_field" in data["detail"]

    @pytest.mark.asyncio
    async def test_update_field_mapping_empty_list_rejected(self):
        """Empty mappings list should be rejected by Pydantic validation."""
        mock_repo = AsyncMock()

        app = _create_test_app(mock_repo)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.put(
                "/api/v1/vlr/settings/field-mapping",
                json={"mappings": []},
            )

        # Pydantic min_length=1 validation on mappings list
        assert response.status_code == 422


class TestCredentialsNeverExposed:
    """Verify that credentials are NEVER present in plaintext in responses."""

    @pytest.mark.asyncio
    async def test_password_never_in_get_response_body(self):
        """The actual password should NEVER appear in any GET response."""
        real_password = "MySuper$ecret#P@ss123"
        encrypted_password = encrypt_value(real_password)

        mock_repo = AsyncMock()

        async def mock_get_by_key(company_code, key):
            if key == SAP_PASSWORD_KEY:
                return _mock_setting(key, encrypted_password, "encrypted")
            if key == SAP_USERNAME_KEY:
                return _mock_setting(key, encrypt_value("admin"), "encrypted")
            if key == SAP_HOST_KEY:
                return _mock_setting(key, "sap.example.com")
            return None

        mock_repo.get_by_key = mock_get_by_key

        app = _create_test_app(mock_repo)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/vlr/settings/sap-connection")

        # The actual password must NEVER appear in the response
        response_text = response.text
        assert real_password not in response_text
        assert encrypted_password not in response_text
