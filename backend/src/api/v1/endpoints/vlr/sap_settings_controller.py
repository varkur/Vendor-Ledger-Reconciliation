"""
SAP Settings API endpoints.
Thin controller — manages SAP connection configuration, connection testing,
and field mapping for the VLR module.

Routes:
- GET    /api/v1/vlr/settings/sap-connection       — Get SAP connection settings (masked)
- PUT    /api/v1/vlr/settings/sap-connection       — Update SAP connection settings
- POST   /api/v1/vlr/settings/sap-connection/test  — Test SAP connection
- PUT    /api/v1/vlr/settings/field-mapping        — Update SAP field mapping

Security:
- SAP credentials are stored encrypted via Fernet symmetric encryption.
- Credentials are NEVER exposed in API responses — only masked values are returned.
- Credentials are NEVER logged.

Requirements: 20.1, 20.2, 20.3, 20.5, 20.6
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.v1.dependencies import get_current_active_user
from src.api.v1.schemas.vlr.sap_settings_schemas import (
    FieldMappingEntry,
    FieldMappingResponse,
    FieldMappingUpdateRequest,
    SAPConnectionResponse,
    SAPConnectionTestResponse,
    SAPConnectionUpdateRequest,
)
from src.domain.entities.user import User
from src.infrastructure.database.repositories.vlr.setting_repository_impl import (
    SettingRepositoryImpl,
)
from src.infrastructure.database.session import get_db_session
from src.infrastructure.external.sap_connector import SAPConfig, SAPConnectorService
from src.infrastructure.security.encryption import decrypt_value, encrypt_value, mask_credential
from src.infrastructure.security.permission_manager import require_permission

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/vlr/settings", tags=["VLR - SAP Settings"])

# ──────────────────────────────────────────────────────────────────────
# Constants for setting keys
# ──────────────────────────────────────────────────────────────────────

SAP_SETTING_PREFIX = "sap_connection"
SAP_HOST_KEY = f"{SAP_SETTING_PREFIX}.host"
SAP_SYSTEM_NUMBER_KEY = f"{SAP_SETTING_PREFIX}.system_number"
SAP_CLIENT_KEY = f"{SAP_SETTING_PREFIX}.client"
SAP_USERNAME_KEY = f"{SAP_SETTING_PREFIX}.username"
SAP_PASSWORD_KEY = f"{SAP_SETTING_PREFIX}.password"
SAP_BASE_URL_KEY = f"{SAP_SETTING_PREFIX}.base_url"

FIELD_MAPPING_KEY = "sap_field_mapping"

# Default company code for global SAP settings (not tenant-specific)
GLOBAL_COMPANY_CODE = "__global__"


# ──────────────────────────────────────────────────────────────────────
# Dependencies
# ──────────────────────────────────────────────────────────────────────


def _get_setting_repository(
    session: AsyncSession = Depends(get_db_session),
) -> SettingRepositoryImpl:
    """FastAPI dependency — creates SettingRepository."""
    return SettingRepositoryImpl(session)


# ──────────────────────────────────────────────────────────────────────
# Helper functions
# ──────────────────────────────────────────────────────────────────────


async def _load_sap_config(repo: SettingRepositoryImpl) -> dict[str, str]:
    """Load all SAP connection settings from the database."""
    config: dict[str, str] = {}
    keys = [
        SAP_HOST_KEY,
        SAP_SYSTEM_NUMBER_KEY,
        SAP_CLIENT_KEY,
        SAP_USERNAME_KEY,
        SAP_PASSWORD_KEY,
        SAP_BASE_URL_KEY,
    ]
    for key in keys:
        setting = await repo.get_by_key(GLOBAL_COMPANY_CODE, key)
        if setting:
            config[key] = setting.value
    return config


def _build_sap_config_from_settings(raw_config: dict[str, str]) -> SAPConfig:
    """Build a SAPConfig object from raw setting values (decrypting credentials)."""
    username_encrypted = raw_config.get(SAP_USERNAME_KEY, "")
    password_encrypted = raw_config.get(SAP_PASSWORD_KEY, "")

    username = decrypt_value(username_encrypted) if username_encrypted else ""
    password = decrypt_value(password_encrypted) if password_encrypted else ""

    return SAPConfig(
        host=raw_config.get(SAP_HOST_KEY, ""),
        system_number=raw_config.get(SAP_SYSTEM_NUMBER_KEY, "00"),
        client=raw_config.get(SAP_CLIENT_KEY, "100"),
        username=username,
        password=password,
        base_url=raw_config.get(SAP_BASE_URL_KEY, ""),
    )


# ──────────────────────────────────────────────────────────────────────
# Endpoints
# ──────────────────────────────────────────────────────────────────────


@router.get(
    "/sap-connection",
    response_model=SAPConnectionResponse,
    summary="Get SAP connection settings (credentials masked)",
    dependencies=[Depends(require_permission("vlr.settings.read"))],
)
async def get_sap_connection(
    current_user: User = Depends(get_current_active_user),
    repo: SettingRepositoryImpl = Depends(_get_setting_repository),
) -> SAPConnectionResponse:
    """
    GET /api/v1/vlr/settings/sap-connection

    Returns SAP connection settings with credentials masked.
    Username and password are never returned in plaintext.
    """
    raw_config = await _load_sap_config(repo)
    sap_config = _build_sap_config_from_settings(raw_config)

    return SAPConnectionResponse(
        host=sap_config.host,
        system_number=sap_config.system_number,
        client=sap_config.client,
        username=mask_credential(sap_config.username),
        password=mask_credential(sap_config.password),
        base_url=sap_config.base_url,
        is_configured=sap_config.is_configured,
    )


@router.put(
    "/sap-connection",
    response_model=SAPConnectionResponse,
    summary="Update SAP connection settings",
    dependencies=[Depends(require_permission("vlr.settings.write"))],
)
async def update_sap_connection(
    request: SAPConnectionUpdateRequest,
    current_user: User = Depends(get_current_active_user),
    repo: SettingRepositoryImpl = Depends(_get_setting_repository),
) -> SAPConnectionResponse:
    """
    PUT /api/v1/vlr/settings/sap-connection

    Updates SAP connection settings. Credentials are encrypted before storage.
    Only provided fields are updated; omitted fields remain unchanged.
    """
    now = datetime.now(timezone.utc)
    modifier = current_user.username

    # Update each provided field
    if request.host is not None:
        await repo.upsert(
            GLOBAL_COMPANY_CODE, SAP_HOST_KEY, request.host,
            value_type="string", description="SAP host address",
            modified_by=modifier,
        )

    if request.system_number is not None:
        await repo.upsert(
            GLOBAL_COMPANY_CODE, SAP_SYSTEM_NUMBER_KEY, request.system_number,
            value_type="string", description="SAP system number",
            modified_by=modifier,
        )

    if request.client is not None:
        await repo.upsert(
            GLOBAL_COMPANY_CODE, SAP_CLIENT_KEY, request.client,
            value_type="string", description="SAP client number",
            modified_by=modifier,
        )

    if request.username is not None:
        # Encrypt username before storage
        encrypted_username = encrypt_value(request.username)
        await repo.upsert(
            GLOBAL_COMPANY_CODE, SAP_USERNAME_KEY, encrypted_username,
            value_type="encrypted", description="SAP username (encrypted)",
            modified_by=modifier,
        )

    if request.password is not None:
        # Encrypt password before storage
        encrypted_password = encrypt_value(request.password)
        await repo.upsert(
            GLOBAL_COMPANY_CODE, SAP_PASSWORD_KEY, encrypted_password,
            value_type="encrypted", description="SAP password (encrypted)",
            modified_by=modifier,
        )

    if request.base_url is not None:
        await repo.upsert(
            GLOBAL_COMPANY_CODE, SAP_BASE_URL_KEY, request.base_url,
            value_type="string", description="SAP API base URL",
            modified_by=modifier,
        )

    logger.info(
        "SAP connection settings updated by user=%s",
        current_user.username,
    )

    # Return current state (masked)
    raw_config = await _load_sap_config(repo)
    sap_config = _build_sap_config_from_settings(raw_config)

    return SAPConnectionResponse(
        host=sap_config.host,
        system_number=sap_config.system_number,
        client=sap_config.client,
        username=mask_credential(sap_config.username),
        password=mask_credential(sap_config.password),
        base_url=sap_config.base_url,
        is_configured=sap_config.is_configured,
    )


@router.post(
    "/sap-connection/test",
    response_model=SAPConnectionTestResponse,
    summary="Test SAP connection",
    dependencies=[Depends(require_permission("vlr.settings.write"))],
)
async def test_sap_connection(
    current_user: User = Depends(get_current_active_user),
    repo: SettingRepositoryImpl = Depends(_get_setting_repository),
) -> SAPConnectionTestResponse:
    """
    POST /api/v1/vlr/settings/sap-connection/test

    Attempts a connection to the configured SAP system and reports
    success or failure within 30 seconds.
    """
    raw_config = await _load_sap_config(repo)
    sap_config = _build_sap_config_from_settings(raw_config)

    connector = SAPConnectorService(config=sap_config)
    result = await connector.test_connection()

    logger.info(
        "SAP connection test by user=%s: success=%s, response_time_ms=%.1f",
        current_user.username,
        result.success,
        result.response_time_ms,
    )

    return SAPConnectionTestResponse(
        success=result.success,
        message=result.message,
        response_time_ms=result.response_time_ms,
    )


@router.put(
    "/field-mapping",
    response_model=FieldMappingResponse,
    summary="Update SAP-to-VLR field mapping",
    dependencies=[Depends(require_permission("vlr.settings.write"))],
)
async def update_field_mapping(
    request: FieldMappingUpdateRequest,
    current_user: User = Depends(get_current_active_user),
    repo: SettingRepositoryImpl = Depends(_get_setting_repository),
) -> FieldMappingResponse:
    """
    PUT /api/v1/vlr/settings/field-mapping

    Updates the SAP-to-VLR column field mapping configuration.
    Validates that all mappings have non-empty field names.
    The mapping is stored as a JSON value in the settings table.
    """
    # Validate mapping entries (additional semantic validation)
    valid_internal_fields = {
        "assignment_number", "document_number", "document_type",
        "amount", "posting_date", "clearing_date", "clearing_document",
        "vendor_code", "company_code", "currency", "description",
        "reference_number",
    }

    for entry in request.mappings:
        if entry.internal_field not in valid_internal_fields:
            from fastapi import HTTPException, status
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    f"Invalid internal field '{entry.internal_field}'. "
                    f"Valid fields: {', '.join(sorted(valid_internal_fields))}"
                ),
            )

    # Store as JSON
    mapping_data = [
        {"sap_field": m.sap_field, "internal_field": m.internal_field}
        for m in request.mappings
    ]
    mapping_json = json.dumps(mapping_data)

    now = datetime.now(timezone.utc)
    await repo.upsert(
        GLOBAL_COMPANY_CODE,
        FIELD_MAPPING_KEY,
        mapping_json,
        value_type="json",
        description="SAP-to-VLR field mapping configuration",
        modified_by=current_user.username,
    )

    logger.info(
        "SAP field mapping updated by user=%s, mapping_count=%d",
        current_user.username,
        len(request.mappings),
    )

    return FieldMappingResponse(
        mappings=[
            FieldMappingEntry(sap_field=m.sap_field, internal_field=m.internal_field)
            for m in request.mappings
        ],
        updated_at=now,
    )
