"""
Notification Pydantic schemas (request/response).

Provides validation for notification history retrieval and
manual reminder sending endpoints.

Requirements: 10.1, 10.7, 10.10, 16.6
"""

from datetime import datetime
from typing import Optional
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


class NotificationListEntry(BaseModel):
    """
    Response schema for listing notifications across all cases.
    Matches the frontend NotificationEntry interface shape.
    """

    id: str
    notification_id: str
    case_id: str
    type: str = Field(description="Notification channel: Email, SMS, In-App, WhatsApp")
    recipient: str
    subject: str
    timestamp: str
    status: str = Field(description="Sent, Delivered, Read, Failed, Pending")
    vendor_name: str
    is_read: bool = False

    model_config = {"from_attributes": True}


class PaginatedNotificationListResponse(BaseModel):
    """Paginated response for notification listing (frontend-compatible)."""

    items: list[NotificationListEntry]
    total: int
    page: int
    page_size: int
    total_pages: int = 0


class MarkReadRequest(BaseModel):
    """Request to mark notifications as read."""

    notification_ids: list[str] = Field(description="List of notification IDs to mark as read")


class MarkReadResponse(BaseModel):
    """Response from mark-as-read endpoint."""

    updated_count: int


class SendReminderBulkRequest(BaseModel):
    """Request to send reminders for multiple notification IDs."""

    notification_ids: list[str] = Field(description="List of notification IDs to re-send reminders for")


class SendReminderBulkResponse(BaseModel):
    """Response from bulk send-reminder endpoint."""

    sent_count: int
    message: str


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


class SendReminderByCasesRequest(BaseModel):
    """Request schema for sending reminders to multiple cases by case ID."""

    case_ids: list[str] = Field(
        ..., min_length=1, description="List of case IDs to send reminders for"
    )
    company_code: str = Field(..., min_length=1, description="Company code for entity scoping")


class SendReminderByCasesResultItem(BaseModel):
    """Result for a single case in a bulk send reminder action."""

    case_id: str
    success: bool
    message: str | None = None


class SendReminderByCasesResponse(BaseModel):
    """Response schema for bulk send reminder by case IDs."""

    results: list[SendReminderByCasesResultItem]
