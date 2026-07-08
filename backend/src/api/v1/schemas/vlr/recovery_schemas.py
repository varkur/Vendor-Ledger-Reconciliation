"""
Request/Response schemas for the Recovery API endpoints.

Requirements: 30.1, 31.1, 31.3
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field


# ──────────────────────────────────────────────────────────────────────
# Request Schemas
# ──────────────────────────────────────────────────────────────────────


class CreateRecoveryItemRequest(BaseModel):
    """Request body for creating a new recovery item."""

    case_id: UUID = Field(..., description="Associated reconciliation case ID")
    vendor_id: UUID = Field(..., description="Vendor ID for this recovery item")
    amount: Decimal = Field(..., gt=0, description="Recoverable amount")
    currency: str = Field(
        default="INR", min_length=3, max_length=3, description="Currency code (ISO 4217)"
    )
    identified_date: date | None = Field(
        None, description="Date recovery was identified (defaults to today)"
    )
    follow_up_interval_days: int = Field(
        default=7, ge=1, le=365, description="Days between follow-up reminders"
    )
    notes: str | None = Field(None, max_length=2000, description="Additional notes")


class UpdateRecoveryItemRequest(BaseModel):
    """Request body for updating a recovery item's status and/or notes."""

    status: str | None = Field(
        None,
        description="New status: open, in_progress, recovered, written_off",
    )
    notes: str | None = Field(None, max_length=2000, description="Updated notes")


# ──────────────────────────────────────────────────────────────────────
# Response Schemas
# ──────────────────────────────────────────────────────────────────────


class RecoveryItemResponse(BaseModel):
    """Response model for a single recovery item."""

    id: UUID = Field(..., description="Recovery item ID")
    case_id: UUID = Field(..., description="Associated reconciliation case ID")
    vendor_id: UUID = Field(..., description="Vendor ID")
    amount: Decimal = Field(..., description="Recoverable amount")
    currency: str = Field(..., description="Currency code")
    status: str = Field(..., description="Current status")
    identified_date: date = Field(..., description="Date recovery was identified")
    next_follow_up_date: date | None = Field(
        None, description="Next scheduled follow-up date"
    )
    follow_up_interval_days: int = Field(
        ..., description="Days between follow-up reminders"
    )
    notes: str | None = Field(None, description="Additional notes")
    created_date: datetime | None = Field(None, description="Record creation timestamp")
    modified_date: datetime | None = Field(None, description="Last modification timestamp")

    model_config = {"from_attributes": True}


class RecoveryItemListResponse(BaseModel):
    """Paginated response for recovery item listing."""

    items: list[RecoveryItemResponse] = Field(
        default_factory=list, description="Recovery items"
    )
    total: int = Field(..., description="Total number of matching items")
    page: int = Field(..., description="Current page number")
    page_size: int = Field(..., description="Items per page")
    total_pages: int = Field(..., description="Total number of pages")


class FollowUpEntryResponse(BaseModel):
    """Response model for a single follow-up log entry."""

    id: UUID = Field(..., description="Follow-up entry ID")
    recovery_item_id: UUID = Field(..., description="Parent recovery item ID")
    action_taken: str = Field(..., description="Description of the action taken")
    action_by: str = Field(..., description="User who performed the action")
    action_date: datetime = Field(..., description="Timestamp of the action")
    next_follow_up_date: date | None = Field(
        None, description="Next follow-up date set by this action"
    )

    model_config = {"from_attributes": True}


class FollowUpListResponse(BaseModel):
    """Response model for follow-up log listing."""

    items: list[FollowUpEntryResponse] = Field(
        default_factory=list, description="Follow-up log entries"
    )
    total: int = Field(..., description="Total number of follow-up entries")
