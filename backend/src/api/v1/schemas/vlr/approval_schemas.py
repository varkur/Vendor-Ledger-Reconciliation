"""
Approval Workflow Pydantic schemas (request/response).

Provides validation for approval decisions, delegation, and pending approvals.
Requirements: 7.3, 7.4, 7.9, 11.3
"""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field


# ──────────────────────────────────────────────────────────────────────
# Request Schemas
# ──────────────────────────────────────────────────────────────────────


class SubmitForApprovalRequest(BaseModel):
    """Request body for submitting a reconciliation case for approval."""

    case_id: UUID = Field(
        ...,
        description="The reconciliation case ID to submit for approval",
    )
    comments: str | None = Field(
        default=None,
        max_length=2000,
        description="Optional comments for the submission",
    )


class SubmitForApprovalResponse(BaseModel):
    """Response schema for a successful approval submission."""

    approval_id: UUID
    case_id: UUID
    status: str = Field(description="New case status after submission")
    message: str = Field(description="Human-readable success message")


class ApproveRequest(BaseModel):
    """Request body for approving a reconciliation case."""

    comments: str | None = Field(
        default=None,
        max_length=2000,
        description="Optional comments for the approval",
    )


class RejectRequest(BaseModel):
    """Request body for rejecting a reconciliation case."""

    comments: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="Rejection reason (required)",
    )


class DelegateRequest(BaseModel):
    """Request body for delegating approval authority."""

    to_user_id: UUID = Field(
        ...,
        description="The user ID to delegate approval authority to",
    )
    duration_days: int = Field(
        default=30,
        ge=1,
        le=30,
        description="Duration of delegation in days (max 30)",
    )


# ──────────────────────────────────────────────────────────────────────
# Response Schemas
# ──────────────────────────────────────────────────────────────────────


class ApprovalResponse(BaseModel):
    """Response schema for an approval action result."""

    approval_id: UUID
    case_id: UUID
    decision: str
    comments: str | None = None
    approver_id: UUID
    approval_level: str
    decision_date: datetime


class DelegationResponse(BaseModel):
    """Response schema for a delegation record."""

    id: UUID
    from_user_id: UUID
    to_user_id: UUID
    start_date: datetime
    end_date: datetime
    is_active: bool


class PendingApprovalCaseResponse(BaseModel):
    """Response schema for a case pending approval."""

    id: UUID
    request_id: UUID | None = None
    vendor_id: UUID | None = None
    case_type: str | None = None
    status: str
    row_10_balance: Decimal | None = None
    created_date: datetime | None = None

    model_config = {"from_attributes": True}


class PendingApprovalsListResponse(BaseModel):
    """Response schema for list of pending approval cases."""

    items: list[PendingApprovalCaseResponse]
    total: int = Field(default=0, description="Total pending approvals")
