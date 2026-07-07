"""
Pydantic schemas for VLR Settings API endpoints.
Covers tolerance, matching rules, notification, and approval threshold settings.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Optional

from pydantic import BaseModel, Field, field_validator


# ──────────────────────────────────────────────────────────────────────
# Tolerance Settings
# ──────────────────────────────────────────────────────────────────────


class ToleranceUpdateRequest(BaseModel):
    """Request to update tolerance settings."""

    amount_tolerance_percentage: Optional[float] = Field(
        None,
        ge=0.0,
        le=10.0,
        description="Percentage tolerance for amount matching (0.0 - 10.0%)",
    )
    amount_tolerance_absolute: Optional[float] = Field(
        None,
        ge=0.0,
        le=10000.0,
        description="Absolute tolerance for amount matching (0.0 - 10000.0 in base currency)",
    )
    date_tolerance_days: Optional[int] = Field(
        None,
        ge=0,
        le=90,
        description="Number of days tolerance for date matching (0 - 90)",
    )
    currency_tolerance_percentage: Optional[float] = Field(
        None,
        ge=0.0,
        le=5.0,
        description="Percentage tolerance for currency conversion differences (0.0 - 5.0%)",
    )


class ToleranceResponse(BaseModel):
    """Current tolerance settings."""

    amount_tolerance_percentage: float = 0.0
    amount_tolerance_absolute: float = 0.0
    date_tolerance_days: int = 0
    currency_tolerance_percentage: float = 0.0
    updated_at: Optional[datetime] = None


# ──────────────────────────────────────────────────────────────────────
# Matching Rule Settings
# ──────────────────────────────────────────────────────────────────────


class MatchingStrategy(StrEnum):
    """Available matching strategies."""

    EXACT = "exact"
    FUZZY = "fuzzy"
    RULE_BASED = "rule_based"


class MatchingUpdateRequest(BaseModel):
    """Request to update matching configuration."""

    strategy: Optional[MatchingStrategy] = Field(
        None,
        description="Matching strategy: exact, fuzzy, or rule_based",
    )
    auto_match_threshold: Optional[float] = Field(
        None,
        ge=0.0,
        le=1.0,
        description="Confidence threshold for automatic matching (0.0 - 1.0)",
    )
    require_document_number_match: Optional[bool] = Field(
        None,
        description="Whether document number must match exactly",
    )
    require_amount_match: Optional[bool] = Field(
        None,
        description="Whether amount must match within tolerance",
    )
    require_date_match: Optional[bool] = Field(
        None,
        description="Whether posting date must match within tolerance",
    )
    max_suggestions: Optional[int] = Field(
        None,
        ge=1,
        le=20,
        description="Maximum number of match suggestions to return (1 - 20)",
    )


class MatchingResponse(BaseModel):
    """Current matching configuration."""

    strategy: str = "exact"
    auto_match_threshold: float = 0.8
    require_document_number_match: bool = True
    require_amount_match: bool = True
    require_date_match: bool = False
    max_suggestions: int = 5
    updated_at: Optional[datetime] = None


# ──────────────────────────────────────────────────────────────────────
# Notification Settings
# ──────────────────────────────────────────────────────────────────────


class NotificationChannel(StrEnum):
    """Notification delivery channels."""

    EMAIL = "email"
    IN_APP = "in_app"
    BOTH = "both"


class NotificationUpdateRequest(BaseModel):
    """Request to update notification settings."""

    channel: Optional[NotificationChannel] = Field(
        None,
        description="Notification delivery channel",
    )
    notify_on_exception: Optional[bool] = Field(
        None,
        description="Send notification when exception is raised",
    )
    notify_on_approval_required: Optional[bool] = Field(
        None,
        description="Send notification when approval is required",
    )
    notify_on_reconciliation_complete: Optional[bool] = Field(
        None,
        description="Send notification when reconciliation completes",
    )
    notify_on_case_status_change: Optional[bool] = Field(
        None,
        description="Send notification on case status changes",
    )
    reminder_interval_hours: Optional[int] = Field(
        None,
        ge=1,
        le=168,
        description="Hours between reminder notifications (1 - 168)",
    )
    digest_enabled: Optional[bool] = Field(
        None,
        description="Enable daily digest notifications",
    )
    digest_time_utc: Optional[str] = Field(
        None,
        pattern=r"^([01]\d|2[0-3]):([0-5]\d)$",
        description="Time for daily digest in HH:MM UTC format",
    )


class NotificationResponse(BaseModel):
    """Current notification settings."""

    channel: str = "both"
    notify_on_exception: bool = True
    notify_on_approval_required: bool = True
    notify_on_reconciliation_complete: bool = True
    notify_on_case_status_change: bool = False
    reminder_interval_hours: int = 24
    digest_enabled: bool = False
    digest_time_utc: str = "08:00"
    updated_at: Optional[datetime] = None


# ──────────────────────────────────────────────────────────────────────
# Approval Threshold Settings
# ──────────────────────────────────────────────────────────────────────


class ApprovalThresholdUpdateRequest(BaseModel):
    """Request to update approval threshold settings."""

    auto_approve_below: Optional[float] = Field(
        None,
        ge=0.0,
        le=1000000.0,
        description="Auto-approve exceptions below this amount (0 - 1,000,000)",
    )
    manager_approval_below: Optional[float] = Field(
        None,
        ge=0.0,
        le=10000000.0,
        description="Manager can approve below this amount (0 - 10,000,000)",
    )
    director_approval_required_above: Optional[float] = Field(
        None,
        ge=0.0,
        le=100000000.0,
        description="Director approval required above this amount",
    )
    require_dual_approval_above: Optional[float] = Field(
        None,
        ge=0.0,
        le=100000000.0,
        description="Dual approval required above this amount",
    )
    escalation_timeout_hours: Optional[int] = Field(
        None,
        ge=1,
        le=720,
        description="Hours before escalating pending approvals (1 - 720)",
    )

    @field_validator("manager_approval_below")
    @classmethod
    def manager_must_be_gte_auto(cls, v, info):
        """Manager threshold should be validated against auto-approve at the API level."""
        return v

    @field_validator("director_approval_required_above")
    @classmethod
    def director_must_be_gte_manager(cls, v, info):
        """Director threshold should be validated against manager at the API level."""
        return v


class ApprovalThresholdResponse(BaseModel):
    """Current approval threshold settings."""

    auto_approve_below: float = 100.0
    manager_approval_below: float = 10000.0
    director_approval_required_above: float = 50000.0
    require_dual_approval_above: float = 100000.0
    escalation_timeout_hours: int = 48
    updated_at: Optional[datetime] = None


# ──────────────────────────────────────────────────────────────────────
# Aggregate Settings Response
# ──────────────────────────────────────────────────────────────────────


class AllSettingsResponse(BaseModel):
    """Complete settings overview."""

    tolerance: ToleranceResponse
    matching: MatchingResponse
    notifications: NotificationResponse
    approval_thresholds: ApprovalThresholdResponse
