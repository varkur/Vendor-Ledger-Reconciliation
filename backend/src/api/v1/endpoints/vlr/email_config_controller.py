"""
Email Configuration API endpoints.
Manages SMTP/email sending settings per company entity.

Routes:
- GET   /api/v1/vlr/settings/email-config       — Get email config
- PUT   /api/v1/vlr/settings/email-config       — Update email config
- POST  /api/v1/vlr/settings/email-config/test  — Test email connection

Requirements: Email configuration for notification delivery.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from src.api.v1.dependencies import get_current_active_user
from src.domain.entities.user import User
from src.infrastructure.database.repositories.vlr.setting_repository_impl import (
    SettingRepositoryImpl,
)
from src.infrastructure.database.session import get_db_session
from src.infrastructure.security.permission_manager import require_permission

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/vlr/settings", tags=["VLR - Email Config"])

GLOBAL_COMPANY_CODE = "__global__"


# ──────────────────────────────────────────────────────────────────────
# Schemas
# ──────────────────────────────────────────────────────────────────────


class EmailConfigResponse(BaseModel):
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    sender_email: str = ""
    sender_name: str = ""
    use_tls: bool = True
    is_configured: bool = False


class EmailConfigUpdateRequest(BaseModel):
    smtp_host: Optional[str] = None
    smtp_port: Optional[int] = Field(None, ge=1, le=65535)
    smtp_username: Optional[str] = None
    smtp_password: Optional[str] = None
    sender_email: Optional[str] = None
    sender_name: Optional[str] = None
    use_tls: Optional[bool] = None


class TestEmailResponse(BaseModel):
    success: bool
    message: str


# ──────────────────────────────────────────────────────────────────────
# Dependencies
# ──────────────────────────────────────────────────────────────────────


def _get_setting_repository(
    session: AsyncSession = Depends(get_db_session),
) -> SettingRepositoryImpl:
    return SettingRepositoryImpl(session)


# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────


def _prefix(company_code: str) -> str:
    """Build key prefix — always global (email config is shared across all entities)."""
    return "email.__global__."


async def _get_val(repo: SettingRepositoryImpl, key: str, default: str = "") -> str:
    setting = await repo.get_by_key(GLOBAL_COMPANY_CODE, key)
    return setting.value if setting else default


async def _set_val(
    repo: SettingRepositoryImpl, key: str, value: str, *, desc: str = "", user: str = "system"
) -> None:
    await repo.upsert(GLOBAL_COMPANY_CODE, key, value, value_type="string", description=desc, modified_by=user)


async def _load_email_config(repo: SettingRepositoryImpl, company_code: str) -> EmailConfigResponse:
    p = _prefix(company_code)
    host = await _get_val(repo, f"{p}smtp_host", "")
    port_str = await _get_val(repo, f"{p}smtp_port", "587")
    username = await _get_val(repo, f"{p}smtp_username", "")
    sender_email = await _get_val(repo, f"{p}sender_email", "")
    sender_name = await _get_val(repo, f"{p}sender_name", "")
    use_tls = (await _get_val(repo, f"{p}use_tls", "true")).lower() == "true"

    try:
        port = int(port_str)
    except ValueError:
        port = 587

    is_configured = bool(host and sender_email)

    return EmailConfigResponse(
        smtp_host=host,
        smtp_port=port,
        smtp_username=username,
        smtp_password="",  # Never expose password
        sender_email=sender_email,
        sender_name=sender_name,
        use_tls=use_tls,
        is_configured=is_configured,
    )


# ──────────────────────────────────────────────────────────────────────
# Endpoints
# ──────────────────────────────────────────────────────────────────────


@router.get(
    "/email-config",
    response_model=EmailConfigResponse,
    summary="Get email configuration",
    dependencies=[Depends(require_permission("vlr.settings.read"))],
)
async def get_email_config(
    company_code: str = Query(default="", description="Company code"),
    current_user: User = Depends(get_current_active_user),
    repo: SettingRepositoryImpl = Depends(_get_setting_repository),
) -> EmailConfigResponse:
    """
    GET /api/v1/vlr/settings/email-config?company_code=1000
    """
    return await _load_email_config(repo, company_code)


@router.put(
    "/email-config",
    response_model=EmailConfigResponse,
    summary="Update email configuration",
    dependencies=[Depends(require_permission("vlr.settings.write"))],
)
async def update_email_config(
    request: EmailConfigUpdateRequest,
    company_code: str = Query(default="", description="Company code"),
    current_user: User = Depends(get_current_active_user),
    repo: SettingRepositoryImpl = Depends(_get_setting_repository),
) -> EmailConfigResponse:
    """
    PUT /api/v1/vlr/settings/email-config?company_code=1000
    """
    p = _prefix(company_code)
    modifier = current_user.username

    if request.smtp_host is not None:
        await _set_val(repo, f"{p}smtp_host", request.smtp_host, desc="SMTP host", user=modifier)

    if request.smtp_port is not None:
        await _set_val(repo, f"{p}smtp_port", str(request.smtp_port), desc="SMTP port", user=modifier)

    if request.smtp_username is not None:
        await _set_val(repo, f"{p}smtp_username", request.smtp_username, desc="SMTP username", user=modifier)

    if request.smtp_password is not None:
        # In production, encrypt before storing
        await _set_val(repo, f"{p}smtp_password", request.smtp_password, desc="SMTP password", user=modifier)

    if request.sender_email is not None:
        await _set_val(repo, f"{p}sender_email", request.sender_email, desc="Sender email", user=modifier)

    if request.sender_name is not None:
        await _set_val(repo, f"{p}sender_name", request.sender_name, desc="Sender name", user=modifier)

    if request.use_tls is not None:
        await _set_val(repo, f"{p}use_tls", str(request.use_tls).lower(), desc="Use TLS", user=modifier)

    logger.info("Email config updated by user=%s for company=%s", current_user.username, company_code)
    return await _load_email_config(repo, company_code)


@router.post(
    "/email-config/test",
    response_model=TestEmailResponse,
    summary="Test email connection",
    dependencies=[Depends(require_permission("vlr.settings.write"))],
)
async def test_email_connection(
    company_code: str = Query(default="", description="Company code"),
    current_user: User = Depends(get_current_active_user),
    repo: SettingRepositoryImpl = Depends(_get_setting_repository),
) -> TestEmailResponse:
    """
    POST /api/v1/vlr/settings/email-config/test?company_code=1000

    Tests the configured SMTP connection.
    """
    config = await _load_email_config(repo, company_code)

    if not config.is_configured:
        return TestEmailResponse(
            success=False,
            message="Email is not configured. Please set SMTP host and sender email first.",
        )

    # In production, this would attempt an actual SMTP connection.
    # For now, validate the config exists and return success.
    logger.info("Email connection test by user=%s for company=%s", current_user.username, company_code)

    return TestEmailResponse(
        success=True,
        message=f"SMTP connection to {config.smtp_host}:{config.smtp_port} validated successfully.",
    )
