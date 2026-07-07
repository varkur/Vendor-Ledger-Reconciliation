"""
VLR Settings API endpoints.
Manages reconciliation operational settings: tolerance, matching rules,
notifications, and approval thresholds.

Routes:
- GET    /api/v1/vlr/settings/                    — Get all settings
- PUT    /api/v1/vlr/settings/tolerance           — Update tolerance settings
- PUT    /api/v1/vlr/settings/matching            — Update matching rule settings
- PUT    /api/v1/vlr/settings/notifications       — Update notification settings
- PUT    /api/v1/vlr/settings/approval-thresholds — Update approval threshold settings

Design:
- New settings apply to future operations only; in-progress cases are unaffected.
- All changes are recorded in the audit log via the automatic audit listener
  AND explicit audit entries for traceability.
- Setting values are validated against defined ranges (enforced by Pydantic schemas
  and cross-field validation in the controller).

Requirements: 13.1-13.10
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.v1.dependencies import get_current_active_user
from src.api.v1.schemas.vlr.settings_schemas import (
    AllSettingsResponse,
    ApprovalThresholdResponse,
    ApprovalThresholdUpdateRequest,
    MatchingResponse,
    MatchingUpdateRequest,
    NotificationResponse,
    NotificationUpdateRequest,
    ToleranceResponse,
    ToleranceUpdateRequest,
)
from src.domain.entities.user import User
from src.infrastructure.database.repositories.vlr.setting_repository_impl import (
    SettingRepositoryImpl,
)
from src.infrastructure.database.session import get_db_session
from src.infrastructure.security.audit_service import AuditService
from src.infrastructure.security.permission_manager import require_permission

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/vlr/settings", tags=["VLR - Settings"])

# ──────────────────────────────────────────────────────────────────────
# Setting key constants
# ──────────────────────────────────────────────────────────────────────

GLOBAL_COMPANY_CODE = "__global__"

# Tolerance keys
TOLERANCE_PREFIX = "tolerance"
TOLERANCE_AMOUNT_PCT_KEY = f"{TOLERANCE_PREFIX}.amount_tolerance_percentage"
TOLERANCE_AMOUNT_ABS_KEY = f"{TOLERANCE_PREFIX}.amount_tolerance_absolute"
TOLERANCE_DATE_DAYS_KEY = f"{TOLERANCE_PREFIX}.date_tolerance_days"
TOLERANCE_CURRENCY_PCT_KEY = f"{TOLERANCE_PREFIX}.currency_tolerance_percentage"

# Matching keys
MATCHING_PREFIX = "matching"
MATCHING_STRATEGY_KEY = f"{MATCHING_PREFIX}.strategy"
MATCHING_AUTO_THRESHOLD_KEY = f"{MATCHING_PREFIX}.auto_match_threshold"
MATCHING_REQUIRE_DOC_KEY = f"{MATCHING_PREFIX}.require_document_number_match"
MATCHING_REQUIRE_AMOUNT_KEY = f"{MATCHING_PREFIX}.require_amount_match"
MATCHING_REQUIRE_DATE_KEY = f"{MATCHING_PREFIX}.require_date_match"
MATCHING_MAX_SUGGESTIONS_KEY = f"{MATCHING_PREFIX}.max_suggestions"

# Notification keys
NOTIFICATION_PREFIX = "notification"
NOTIFICATION_CHANNEL_KEY = f"{NOTIFICATION_PREFIX}.channel"
NOTIFICATION_ON_EXCEPTION_KEY = f"{NOTIFICATION_PREFIX}.notify_on_exception"
NOTIFICATION_ON_APPROVAL_KEY = f"{NOTIFICATION_PREFIX}.notify_on_approval_required"
NOTIFICATION_ON_COMPLETE_KEY = f"{NOTIFICATION_PREFIX}.notify_on_reconciliation_complete"
NOTIFICATION_ON_STATUS_KEY = f"{NOTIFICATION_PREFIX}.notify_on_case_status_change"
NOTIFICATION_REMINDER_KEY = f"{NOTIFICATION_PREFIX}.reminder_interval_hours"
NOTIFICATION_DIGEST_ENABLED_KEY = f"{NOTIFICATION_PREFIX}.digest_enabled"
NOTIFICATION_DIGEST_TIME_KEY = f"{NOTIFICATION_PREFIX}.digest_time_utc"

# Approval threshold keys
APPROVAL_PREFIX = "approval_threshold"
APPROVAL_AUTO_BELOW_KEY = f"{APPROVAL_PREFIX}.auto_approve_below"
APPROVAL_MANAGER_BELOW_KEY = f"{APPROVAL_PREFIX}.manager_approval_below"
APPROVAL_DIRECTOR_ABOVE_KEY = f"{APPROVAL_PREFIX}.director_approval_required_above"
APPROVAL_DUAL_ABOVE_KEY = f"{APPROVAL_PREFIX}.require_dual_approval_above"
APPROVAL_ESCALATION_KEY = f"{APPROVAL_PREFIX}.escalation_timeout_hours"


# ──────────────────────────────────────────────────────────────────────
# Dependencies
# ──────────────────────────────────────────────────────────────────────


def _get_setting_repository(
    session: AsyncSession = Depends(get_db_session),
) -> SettingRepositoryImpl:
    return SettingRepositoryImpl(session)


def _get_audit_service(
    session: AsyncSession = Depends(get_db_session),
) -> AuditService:
    return AuditService(session)


# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────


async def _get_setting_value(
    repo: SettingRepositoryImpl,
    key: str,
    default: str = "",
) -> str:
    """Load a single setting value from DB, returning default if not found."""
    setting = await repo.get_by_key(GLOBAL_COMPANY_CODE, key)
    return setting.value if setting else default


async def _upsert_setting(
    repo: SettingRepositoryImpl,
    key: str,
    value: str,
    *,
    value_type: str = "string",
    description: str = "",
    modified_by: str = "system",
) -> None:
    """Create or update a setting."""
    await repo.upsert(
        GLOBAL_COMPANY_CODE,
        key,
        value,
        value_type=value_type,
        description=description,
        modified_by=modified_by,
    )


async def _record_settings_audit(
    audit: AuditService,
    user: User,
    settings_group: str,
    old_values: dict,
    new_values: dict,
) -> None:
    """Record a settings change in the audit log."""
    await audit.log(
        actor_id=user.id,
        actor_username=user.username,
        action="SETTINGS_UPDATED",
        resource_type="VLRSettings",
        resource_id=settings_group,
        old_value=old_values,
        new_value=new_values,
        metadata={"settings_group": settings_group, "note": "Applied to future operations only"},
    )


# ──────────────────────────────────────────────────────────────────────
# Load helpers (build response models from stored settings)
# ──────────────────────────────────────────────────────────────────────


async def _load_tolerance(repo: SettingRepositoryImpl) -> ToleranceResponse:
    return ToleranceResponse(
        amount_tolerance_percentage=float(
            await _get_setting_value(repo, TOLERANCE_AMOUNT_PCT_KEY, "0.0")
        ),
        amount_tolerance_absolute=float(
            await _get_setting_value(repo, TOLERANCE_AMOUNT_ABS_KEY, "0.0")
        ),
        date_tolerance_days=int(
            await _get_setting_value(repo, TOLERANCE_DATE_DAYS_KEY, "0")
        ),
        currency_tolerance_percentage=float(
            await _get_setting_value(repo, TOLERANCE_CURRENCY_PCT_KEY, "0.0")
        ),
    )


async def _load_matching(repo: SettingRepositoryImpl) -> MatchingResponse:
    return MatchingResponse(
        strategy=await _get_setting_value(repo, MATCHING_STRATEGY_KEY, "exact"),
        auto_match_threshold=float(
            await _get_setting_value(repo, MATCHING_AUTO_THRESHOLD_KEY, "0.8")
        ),
        require_document_number_match=(
            await _get_setting_value(repo, MATCHING_REQUIRE_DOC_KEY, "true")
        ).lower() == "true",
        require_amount_match=(
            await _get_setting_value(repo, MATCHING_REQUIRE_AMOUNT_KEY, "true")
        ).lower() == "true",
        require_date_match=(
            await _get_setting_value(repo, MATCHING_REQUIRE_DATE_KEY, "false")
        ).lower() == "true",
        max_suggestions=int(
            await _get_setting_value(repo, MATCHING_MAX_SUGGESTIONS_KEY, "5")
        ),
    )


async def _load_notifications(repo: SettingRepositoryImpl) -> NotificationResponse:
    return NotificationResponse(
        channel=await _get_setting_value(repo, NOTIFICATION_CHANNEL_KEY, "both"),
        notify_on_exception=(
            await _get_setting_value(repo, NOTIFICATION_ON_EXCEPTION_KEY, "true")
        ).lower() == "true",
        notify_on_approval_required=(
            await _get_setting_value(repo, NOTIFICATION_ON_APPROVAL_KEY, "true")
        ).lower() == "true",
        notify_on_reconciliation_complete=(
            await _get_setting_value(repo, NOTIFICATION_ON_COMPLETE_KEY, "true")
        ).lower() == "true",
        notify_on_case_status_change=(
            await _get_setting_value(repo, NOTIFICATION_ON_STATUS_KEY, "false")
        ).lower() == "true",
        reminder_interval_hours=int(
            await _get_setting_value(repo, NOTIFICATION_REMINDER_KEY, "24")
        ),
        digest_enabled=(
            await _get_setting_value(repo, NOTIFICATION_DIGEST_ENABLED_KEY, "false")
        ).lower() == "true",
        digest_time_utc=await _get_setting_value(
            repo, NOTIFICATION_DIGEST_TIME_KEY, "08:00"
        ),
    )


async def _load_approval_thresholds(repo: SettingRepositoryImpl) -> ApprovalThresholdResponse:
    return ApprovalThresholdResponse(
        auto_approve_below=float(
            await _get_setting_value(repo, APPROVAL_AUTO_BELOW_KEY, "100.0")
        ),
        manager_approval_below=float(
            await _get_setting_value(repo, APPROVAL_MANAGER_BELOW_KEY, "10000.0")
        ),
        director_approval_required_above=float(
            await _get_setting_value(repo, APPROVAL_DIRECTOR_ABOVE_KEY, "50000.0")
        ),
        require_dual_approval_above=float(
            await _get_setting_value(repo, APPROVAL_DUAL_ABOVE_KEY, "100000.0")
        ),
        escalation_timeout_hours=int(
            await _get_setting_value(repo, APPROVAL_ESCALATION_KEY, "48")
        ),
    )


# ──────────────────────────────────────────────────────────────────────
# Endpoints
# ──────────────────────────────────────────────────────────────────────


@router.get(
    "/",
    response_model=AllSettingsResponse,
    summary="Get all VLR settings",
    dependencies=[Depends(require_permission("vlr.settings.read"))],
)
async def get_all_settings(
    current_user: User = Depends(get_current_active_user),
    repo: SettingRepositoryImpl = Depends(_get_setting_repository),
) -> AllSettingsResponse:
    """
    GET /api/v1/vlr/settings/

    Returns all VLR operational settings grouped by category.
    """
    return AllSettingsResponse(
        tolerance=await _load_tolerance(repo),
        matching=await _load_matching(repo),
        notifications=await _load_notifications(repo),
        approval_thresholds=await _load_approval_thresholds(repo),
    )


@router.put(
    "/tolerance",
    response_model=ToleranceResponse,
    summary="Update tolerance settings",
    dependencies=[Depends(require_permission("vlr.settings.write"))],
)
async def update_tolerance(
    request: ToleranceUpdateRequest,
    current_user: User = Depends(get_current_active_user),
    repo: SettingRepositoryImpl = Depends(_get_setting_repository),
    audit: AuditService = Depends(_get_audit_service),
) -> ToleranceResponse:
    """
    PUT /api/v1/vlr/settings/tolerance

    Updates tolerance settings. Only provided fields are changed.
    New values apply to future reconciliation operations only.
    """
    # Capture old state for audit
    old_state = (await _load_tolerance(repo)).model_dump()
    modifier = current_user.username

    if request.amount_tolerance_percentage is not None:
        await _upsert_setting(
            repo, TOLERANCE_AMOUNT_PCT_KEY,
            str(request.amount_tolerance_percentage),
            value_type="float",
            description="Amount tolerance percentage (0-10%)",
            modified_by=modifier,
        )

    if request.amount_tolerance_absolute is not None:
        await _upsert_setting(
            repo, TOLERANCE_AMOUNT_ABS_KEY,
            str(request.amount_tolerance_absolute),
            value_type="float",
            description="Absolute amount tolerance",
            modified_by=modifier,
        )

    if request.date_tolerance_days is not None:
        await _upsert_setting(
            repo, TOLERANCE_DATE_DAYS_KEY,
            str(request.date_tolerance_days),
            value_type="integer",
            description="Date tolerance in days (0-90)",
            modified_by=modifier,
        )

    if request.currency_tolerance_percentage is not None:
        await _upsert_setting(
            repo, TOLERANCE_CURRENCY_PCT_KEY,
            str(request.currency_tolerance_percentage),
            value_type="float",
            description="Currency conversion tolerance percentage (0-5%)",
            modified_by=modifier,
        )

    # Load new state and record audit
    new_response = await _load_tolerance(repo)
    new_state = new_response.model_dump()

    await _record_settings_audit(audit, current_user, "tolerance", old_state, new_state)

    logger.info("Tolerance settings updated by user=%s", current_user.username)
    return new_response


@router.put(
    "/matching",
    response_model=MatchingResponse,
    summary="Update matching rule settings",
    dependencies=[Depends(require_permission("vlr.settings.write"))],
)
async def update_matching(
    request: MatchingUpdateRequest,
    current_user: User = Depends(get_current_active_user),
    repo: SettingRepositoryImpl = Depends(_get_setting_repository),
    audit: AuditService = Depends(_get_audit_service),
) -> MatchingResponse:
    """
    PUT /api/v1/vlr/settings/matching

    Updates matching rule configuration. Only provided fields are changed.
    New values apply to future reconciliation operations only.
    """
    old_state = (await _load_matching(repo)).model_dump()
    modifier = current_user.username

    if request.strategy is not None:
        await _upsert_setting(
            repo, MATCHING_STRATEGY_KEY,
            request.strategy.value,
            value_type="string",
            description="Matching strategy",
            modified_by=modifier,
        )

    if request.auto_match_threshold is not None:
        await _upsert_setting(
            repo, MATCHING_AUTO_THRESHOLD_KEY,
            str(request.auto_match_threshold),
            value_type="float",
            description="Auto-match confidence threshold (0.0-1.0)",
            modified_by=modifier,
        )

    if request.require_document_number_match is not None:
        await _upsert_setting(
            repo, MATCHING_REQUIRE_DOC_KEY,
            str(request.require_document_number_match).lower(),
            value_type="boolean",
            description="Require exact document number match",
            modified_by=modifier,
        )

    if request.require_amount_match is not None:
        await _upsert_setting(
            repo, MATCHING_REQUIRE_AMOUNT_KEY,
            str(request.require_amount_match).lower(),
            value_type="boolean",
            description="Require amount match within tolerance",
            modified_by=modifier,
        )

    if request.require_date_match is not None:
        await _upsert_setting(
            repo, MATCHING_REQUIRE_DATE_KEY,
            str(request.require_date_match).lower(),
            value_type="boolean",
            description="Require posting date match within tolerance",
            modified_by=modifier,
        )

    if request.max_suggestions is not None:
        await _upsert_setting(
            repo, MATCHING_MAX_SUGGESTIONS_KEY,
            str(request.max_suggestions),
            value_type="integer",
            description="Maximum match suggestions (1-20)",
            modified_by=modifier,
        )

    new_response = await _load_matching(repo)
    new_state = new_response.model_dump()

    await _record_settings_audit(audit, current_user, "matching", old_state, new_state)

    logger.info("Matching settings updated by user=%s", current_user.username)
    return new_response


@router.put(
    "/notifications",
    response_model=NotificationResponse,
    summary="Update notification settings",
    dependencies=[Depends(require_permission("vlr.settings.write"))],
)
async def update_notifications(
    request: NotificationUpdateRequest,
    current_user: User = Depends(get_current_active_user),
    repo: SettingRepositoryImpl = Depends(_get_setting_repository),
    audit: AuditService = Depends(_get_audit_service),
) -> NotificationResponse:
    """
    PUT /api/v1/vlr/settings/notifications

    Updates notification settings. Only provided fields are changed.
    """
    old_state = (await _load_notifications(repo)).model_dump()
    modifier = current_user.username

    if request.channel is not None:
        await _upsert_setting(
            repo, NOTIFICATION_CHANNEL_KEY,
            request.channel.value,
            value_type="string",
            description="Notification delivery channel",
            modified_by=modifier,
        )

    if request.notify_on_exception is not None:
        await _upsert_setting(
            repo, NOTIFICATION_ON_EXCEPTION_KEY,
            str(request.notify_on_exception).lower(),
            value_type="boolean",
            description="Notify on exception raised",
            modified_by=modifier,
        )

    if request.notify_on_approval_required is not None:
        await _upsert_setting(
            repo, NOTIFICATION_ON_APPROVAL_KEY,
            str(request.notify_on_approval_required).lower(),
            value_type="boolean",
            description="Notify when approval is required",
            modified_by=modifier,
        )

    if request.notify_on_reconciliation_complete is not None:
        await _upsert_setting(
            repo, NOTIFICATION_ON_COMPLETE_KEY,
            str(request.notify_on_reconciliation_complete).lower(),
            value_type="boolean",
            description="Notify on reconciliation complete",
            modified_by=modifier,
        )

    if request.notify_on_case_status_change is not None:
        await _upsert_setting(
            repo, NOTIFICATION_ON_STATUS_KEY,
            str(request.notify_on_case_status_change).lower(),
            value_type="boolean",
            description="Notify on case status change",
            modified_by=modifier,
        )

    if request.reminder_interval_hours is not None:
        await _upsert_setting(
            repo, NOTIFICATION_REMINDER_KEY,
            str(request.reminder_interval_hours),
            value_type="integer",
            description="Reminder interval in hours (1-168)",
            modified_by=modifier,
        )

    if request.digest_enabled is not None:
        await _upsert_setting(
            repo, NOTIFICATION_DIGEST_ENABLED_KEY,
            str(request.digest_enabled).lower(),
            value_type="boolean",
            description="Enable daily digest notifications",
            modified_by=modifier,
        )

    if request.digest_time_utc is not None:
        await _upsert_setting(
            repo, NOTIFICATION_DIGEST_TIME_KEY,
            request.digest_time_utc,
            value_type="string",
            description="Daily digest time (HH:MM UTC)",
            modified_by=modifier,
        )

    new_response = await _load_notifications(repo)
    new_state = new_response.model_dump()

    await _record_settings_audit(audit, current_user, "notifications", old_state, new_state)

    logger.info("Notification settings updated by user=%s", current_user.username)
    return new_response


@router.put(
    "/approval-thresholds",
    response_model=ApprovalThresholdResponse,
    summary="Update approval threshold settings",
    dependencies=[Depends(require_permission("vlr.settings.write"))],
)
async def update_approval_thresholds(
    request: ApprovalThresholdUpdateRequest,
    current_user: User = Depends(get_current_active_user),
    repo: SettingRepositoryImpl = Depends(_get_setting_repository),
    audit: AuditService = Depends(_get_audit_service),
) -> ApprovalThresholdResponse:
    """
    PUT /api/v1/vlr/settings/approval-thresholds

    Updates approval threshold settings. Only provided fields are changed.
    Cross-field validation ensures thresholds maintain logical ordering:
    auto_approve < manager_approval < director_approval.
    """
    old_state = (await _load_approval_thresholds(repo)).model_dump()
    modifier = current_user.username

    # Resolve effective values for cross-field validation
    effective_auto = (
        request.auto_approve_below
        if request.auto_approve_below is not None
        else old_state["auto_approve_below"]
    )
    effective_manager = (
        request.manager_approval_below
        if request.manager_approval_below is not None
        else old_state["manager_approval_below"]
    )
    effective_director = (
        request.director_approval_required_above
        if request.director_approval_required_above is not None
        else old_state["director_approval_required_above"]
    )
    effective_dual = (
        request.require_dual_approval_above
        if request.require_dual_approval_above is not None
        else old_state["require_dual_approval_above"]
    )

    # Cross-field validation: auto < manager < director <= dual
    if effective_auto > effective_manager:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"auto_approve_below ({effective_auto}) must not exceed "
                f"manager_approval_below ({effective_manager})"
            ),
        )
    if effective_manager > effective_director:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"manager_approval_below ({effective_manager}) must not exceed "
                f"director_approval_required_above ({effective_director})"
            ),
        )
    if effective_director > effective_dual:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"director_approval_required_above ({effective_director}) must not exceed "
                f"require_dual_approval_above ({effective_dual})"
            ),
        )

    # Persist changes
    if request.auto_approve_below is not None:
        await _upsert_setting(
            repo, APPROVAL_AUTO_BELOW_KEY,
            str(request.auto_approve_below),
            value_type="float",
            description="Auto-approve threshold",
            modified_by=modifier,
        )

    if request.manager_approval_below is not None:
        await _upsert_setting(
            repo, APPROVAL_MANAGER_BELOW_KEY,
            str(request.manager_approval_below),
            value_type="float",
            description="Manager approval threshold",
            modified_by=modifier,
        )

    if request.director_approval_required_above is not None:
        await _upsert_setting(
            repo, APPROVAL_DIRECTOR_ABOVE_KEY,
            str(request.director_approval_required_above),
            value_type="float",
            description="Director approval threshold",
            modified_by=modifier,
        )

    if request.require_dual_approval_above is not None:
        await _upsert_setting(
            repo, APPROVAL_DUAL_ABOVE_KEY,
            str(request.require_dual_approval_above),
            value_type="float",
            description="Dual approval threshold",
            modified_by=modifier,
        )

    if request.escalation_timeout_hours is not None:
        await _upsert_setting(
            repo, APPROVAL_ESCALATION_KEY,
            str(request.escalation_timeout_hours),
            value_type="integer",
            description="Escalation timeout in hours (1-720)",
            modified_by=modifier,
        )

    new_response = await _load_approval_thresholds(repo)
    new_state = new_response.model_dump()

    await _record_settings_audit(
        audit, current_user, "approval_thresholds", old_state, new_state
    )

    logger.info("Approval threshold settings updated by user=%s", current_user.username)
    return new_response
