"""
Reminder Configuration API endpoints.
Manages reminder groups and templates per company entity.

Routes:
- GET   /api/v1/vlr/settings/reminders                              — List reminder groups (paginated, searchable)
- POST  /api/v1/vlr/settings/reminders                              — Create a reminder group
- GET   /api/v1/vlr/settings/reminders/{group_id}                   — Get group detail with reminders
- GET   /api/v1/vlr/settings/reminders/{group_id}/reminders/{reminder_id} — Get single reminder (for preview)

Requirements: Reminder management for VLR confirmation workflows.
"""

from __future__ import annotations

import json
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
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

router = APIRouter(prefix="/vlr/settings", tags=["VLR - Reminders"])

GLOBAL_COMPANY_CODE = "__global__"


# ──────────────────────────────────────────────────────────────────────
# Schemas
# ──────────────────────────────────────────────────────────────────────


class ReminderTemplate(BaseModel):
    id: str
    name: str
    email_subject: str
    email_content: str


class ReminderGroupResponse(BaseModel):
    id: str
    name: str
    interval_days: int
    total_reminders: int
    creator: str = "Admin"
    reminders: list[ReminderTemplate] = []


class ReminderGroupListResponse(BaseModel):
    items: list[ReminderGroupResponse]
    total: int
    page: int
    page_size: int


class CreateReminderGroupRequest(BaseModel):
    name: str
    interval_days: int
    total_reminders: int
    reminders: list[ReminderTemplate] = []


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


def _storage_key(company_code: str) -> str:
    """Build storage key scoped to an entity."""
    code = company_code if company_code else GLOBAL_COMPANY_CODE
    return f"reminders.{code}.groups"


# Default seed data matching Firmway screenshots
DEFAULT_GROUPS: list[dict] = [
    {
        "id": "1",
        "name": "Audit - 3 Reminders (Interval 3 days)",
        "interval_days": 3,
        "total_reminders": 1,
        "creator": "Admin",
        "reminders": [
            {
                "id": "121",
                "name": "3 Reminders (Interval 3 days)",
                "email_subject": "Reminder __reminder_count__ - Balances confirmations of Organization.",
                "email_content": (
                    "Dear Contact person,\n"
                    "Organization\n"
                    "Branch Name\n\n"
                    "It has come to our attention that you have missed to respond to the previous email.\n\n"
                    "This is a Balances Confirmation request from the auditors, Chartered Accountants.\n"
                    "Click to Respond to Balances confirmation request of Organization for Sender Branch Name branch as on 31/03/2018.\n\n"
                    "Note:\n"
                    "1. The above link is encrypted and secured with HTTPS. Kindly respond by clicking on the link. Do not respond to this email.\n"
                    "2. In case of mismatch in amount kindly attach the ledger / outstanding statements in excel format through the link only.\n"
                    "3. If you are not the right recipient, forward this email to the authorised person.\n"
                    "4. To know how to respond to this confirmation, Watch a video Read User Guide."
                ),
            }
        ],
    },
    {"id": "2", "name": "Audit - 5 Reminders (Interval 3 days)", "interval_days": 3, "total_reminders": 1, "creator": "Admin", "reminders": []},
    {"id": "3", "name": "Audit - 5 Reminders (Interval 7 days)", "interval_days": 7, "total_reminders": 1, "creator": "Admin", "reminders": []},
    {"id": "4", "name": "Bank - 5 Reminders (Interval 3 days)", "interval_days": 3, "total_reminders": 1, "creator": "Admin", "reminders": []},
    {"id": "5", "name": "Bank - 5 Reminders (Interval 7 days)", "interval_days": 7, "total_reminders": 1, "creator": "Admin", "reminders": []},
    {"id": "6", "name": "Data Management 5 Reminders (Interval 3 days)", "interval_days": 3, "total_reminders": 1, "creator": "Admin", "reminders": []},
    {"id": "7", "name": "Ledger Request Reminder", "interval_days": 3, "total_reminders": 1, "creator": "Admin", "reminders": []},
    {"id": "8", "name": "Management - 5 Reminders (Interval 3 days)", "interval_days": 3, "total_reminders": 1, "creator": "Admin", "reminders": []},
    {"id": "9", "name": "Management - 5 Reminders (Interval 7 days)", "interval_days": 7, "total_reminders": 1, "creator": "Admin", "reminders": []},
]


async def _load_groups(repo: SettingRepositoryImpl, company_code: str) -> list[dict]:
    """Load reminder groups from storage; return defaults if not stored."""
    key = _storage_key(company_code)
    setting = await repo.get_by_key(GLOBAL_COMPANY_CODE, key)
    if setting and setting.value:
        try:
            return json.loads(setting.value)
        except (json.JSONDecodeError, TypeError):
            pass
    return DEFAULT_GROUPS


async def _save_groups(
    repo: SettingRepositoryImpl,
    company_code: str,
    groups: list[dict],
    user: str = "system",
) -> None:
    """Persist reminder groups to storage."""
    key = _storage_key(company_code)
    await repo.upsert(
        GLOBAL_COMPANY_CODE,
        key,
        json.dumps(groups),
        value_type="json",
        description="Reminder groups configuration",
        modified_by=user,
    )


# ──────────────────────────────────────────────────────────────────────
# Endpoints
# ──────────────────────────────────────────────────────────────────────


@router.get(
    "/reminders",
    response_model=ReminderGroupListResponse,
    summary="List reminder groups",
    dependencies=[Depends(require_permission("vlr.settings.read"))],
)
async def list_reminder_groups(
    company_code: str = Query(default="", description="Company code"),
    page: int = Query(default=1, ge=1, description="Page number"),
    page_size: int = Query(default=10, ge=1, le=100, description="Items per page"),
    search: Optional[str] = Query(default=None, description="Search filter on group name"),
    current_user: User = Depends(get_current_active_user),
    repo: SettingRepositoryImpl = Depends(_get_setting_repository),
) -> ReminderGroupListResponse:
    """
    GET /api/v1/vlr/settings/reminders?company_code=1000&page=1&page_size=10&search=audit
    """
    groups = await _load_groups(repo, company_code)

    # Apply search filter
    if search:
        search_lower = search.lower()
        groups = [g for g in groups if search_lower in g.get("name", "").lower()]

    total = len(groups)

    # Paginate
    start = (page - 1) * page_size
    end = start + page_size
    page_items = groups[start:end]

    return ReminderGroupListResponse(
        items=[ReminderGroupResponse(**g) for g in page_items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post(
    "/reminders",
    response_model=ReminderGroupResponse,
    summary="Create a reminder group",
    dependencies=[Depends(require_permission("vlr.settings.write"))],
)
async def create_reminder_group(
    request: CreateReminderGroupRequest,
    company_code: str = Query(default="", description="Company code"),
    current_user: User = Depends(get_current_active_user),
    repo: SettingRepositoryImpl = Depends(_get_setting_repository),
) -> ReminderGroupResponse:
    """
    POST /api/v1/vlr/settings/reminders?company_code=1000
    """
    groups = await _load_groups(repo, company_code)

    new_group = {
        "id": str(uuid.uuid4())[:8],
        "name": request.name,
        "interval_days": request.interval_days,
        "total_reminders": request.total_reminders,
        "creator": current_user.username or "Admin",
        "reminders": [r.model_dump() for r in request.reminders],
    }

    groups.append(new_group)
    await _save_groups(repo, company_code, groups, user=current_user.username)

    logger.info(
        "Reminder group created: name=%s by user=%s for company=%s",
        request.name,
        current_user.username,
        company_code,
    )

    return ReminderGroupResponse(**new_group)


@router.get(
    "/reminders/{group_id}",
    response_model=ReminderGroupResponse,
    summary="Get reminder group detail",
    dependencies=[Depends(require_permission("vlr.settings.read"))],
)
async def get_reminder_group(
    group_id: str,
    company_code: str = Query(default="", description="Company code"),
    current_user: User = Depends(get_current_active_user),
    repo: SettingRepositoryImpl = Depends(_get_setting_repository),
) -> ReminderGroupResponse:
    """
    GET /api/v1/vlr/settings/reminders/{group_id}?company_code=1000
    """
    groups = await _load_groups(repo, company_code)

    for g in groups:
        if g["id"] == group_id:
            return ReminderGroupResponse(**g)

    raise HTTPException(status_code=404, detail=f"Reminder group '{group_id}' not found.")


@router.get(
    "/reminders/{group_id}/reminders/{reminder_id}",
    response_model=ReminderTemplate,
    summary="Get single reminder template (preview)",
    dependencies=[Depends(require_permission("vlr.settings.read"))],
)
async def get_reminder_template(
    group_id: str,
    reminder_id: str,
    company_code: str = Query(default="", description="Company code"),
    current_user: User = Depends(get_current_active_user),
    repo: SettingRepositoryImpl = Depends(_get_setting_repository),
) -> ReminderTemplate:
    """
    GET /api/v1/vlr/settings/reminders/{group_id}/reminders/{reminder_id}?company_code=1000
    """
    groups = await _load_groups(repo, company_code)

    for g in groups:
        if g["id"] == group_id:
            for r in g.get("reminders", []):
                if r["id"] == reminder_id:
                    return ReminderTemplate(**r)
            raise HTTPException(
                status_code=404,
                detail=f"Reminder '{reminder_id}' not found in group '{group_id}'.",
            )

    raise HTTPException(status_code=404, detail=f"Reminder group '{group_id}' not found.")


class UpdateReminderTemplateRequest(BaseModel):
    """Request to update a reminder template's email subject/content."""

    name: Optional[str] = None
    email_subject: Optional[str] = None
    email_content: Optional[str] = None


class EmailTemplateOption(BaseModel):
    """Flattened template option for dropdowns (e.g. in Request Statement page)."""

    id: str
    group_id: str
    group_name: str
    name: str
    email_subject: str


@router.put(
    "/reminders/{group_id}/reminders/{reminder_id}",
    response_model=ReminderTemplate,
    summary="Update a reminder template",
    dependencies=[Depends(require_permission("vlr.settings.write"))],
)
async def update_reminder_template(
    group_id: str,
    reminder_id: str,
    request: UpdateReminderTemplateRequest,
    company_code: str = Query(default="", description="Company code"),
    current_user: User = Depends(get_current_active_user),
    repo: SettingRepositoryImpl = Depends(_get_setting_repository),
) -> ReminderTemplate:
    """
    PUT /api/v1/vlr/settings/reminders/{group_id}/reminders/{reminder_id}?company_code=1000

    Updates the email subject and/or content of a reminder template.
    """
    groups = await _load_groups(repo, company_code)

    for g in groups:
        if g["id"] == group_id:
            for r in g.get("reminders", []):
                if r["id"] == reminder_id:
                    if request.name is not None:
                        r["name"] = request.name
                    if request.email_subject is not None:
                        r["email_subject"] = request.email_subject
                    if request.email_content is not None:
                        r["email_content"] = request.email_content

                    await _save_groups(repo, company_code, groups, user=current_user.username)
                    logger.info(
                        "Reminder template updated: group=%s reminder=%s by user=%s",
                        group_id, reminder_id, current_user.username,
                    )
                    return ReminderTemplate(**r)

            raise HTTPException(
                status_code=404,
                detail=f"Reminder '{reminder_id}' not found in group '{group_id}'.",
            )

    raise HTTPException(status_code=404, detail=f"Reminder group '{group_id}' not found.")


@router.get(
    "/email-templates",
    response_model=list[EmailTemplateOption],
    summary="List all email templates (for dropdowns)",
    dependencies=[Depends(require_permission("vlr.settings.read"))],
)
async def list_email_templates(
    company_code: str = Query(default="", description="Company code"),
    current_user: User = Depends(get_current_active_user),
    repo: SettingRepositoryImpl = Depends(_get_setting_repository),
) -> list[EmailTemplateOption]:
    """
    GET /api/v1/vlr/settings/email-templates?company_code=1000

    Returns a flattened list of all email templates from all reminder groups.
    Used by the Request Statement page to populate email/reminder template dropdowns.
    """
    groups = await _load_groups(repo, company_code)

    templates: list[EmailTemplateOption] = []
    for g in groups:
        for r in g.get("reminders", []):
            templates.append(
                EmailTemplateOption(
                    id=r["id"],
                    group_id=g["id"],
                    group_name=g["name"],
                    name=r.get("name", ""),
                    email_subject=r.get("email_subject", ""),
                )
            )

    return templates
