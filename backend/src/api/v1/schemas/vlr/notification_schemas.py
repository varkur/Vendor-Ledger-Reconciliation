"""
Notification Pydantic schemas (request/response).

Provides validation for notification history retrieval and
manual reminder sending endpoints.

Requirements: 10.1, 10.7, 10.10, 16.6
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


# ──────────────────────────────────────────────────────────────────────
# Response Schemas
# ──────────────────────────────────────────────────────────────────────


class NotificationResponse(BaseModel):
    """Response schema for a single notification record."""

    id: UUID
    case_id: UUID
    type: str = Field(description="Notification type (invitation, reminder, escalation, etc.)")
    recipient_email: str
    status: str = Field(description="Delivery status (pending, sent, failed, retrying)")
    retry_count: int = 0
    template_code: str | None = None
    context_data: dict | None = None
    sent_date: datetime | None = None
    next_retry_date: datetime | None = None
    created_date: datetime | None = None

    model_config = {"from_attributes": True}


class NotificationHistoryResponse(BaseModel):
    """Paginated response for notification history."""

    items: list[NotificationResponse]
    total: int
    page: int
    page_size: int
    total_pages: int = 0

    model_config = {"from_attributes": True}


class SendReminderResponse(BaseModel):
    """Response for sending a reminder notification."""

    case_id: UUID
    notification_id: UUID | None = None
    task_id: str | None = Field(default=None, description="Celery task ID for async delivery")
    notification_type: str
    recipient_email: str
    status: str
    message: str = Field(description="Human-readable result message")


# ──────────────────────────────────────────────────────────────────────
# Request Schemas
# ──────────────────────────────────────────────────────────────────────


class SendReminderRequest(BaseModel):
    """Request schema for manually sending a reminder."""

    case_id: UUID = Field(description="Reconciliation case ID to send reminder for")
    recipient_email: EmailStr | None = Field(
        default=None,
        description="Override recipient email (optional, uses primary contact if not provided)",
    )
    company_code: str | None = Field(
        default=None,
        description="Company code for settings lookup (optional)",
    )
