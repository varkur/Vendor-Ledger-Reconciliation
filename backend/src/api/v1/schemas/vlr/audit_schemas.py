"""
Request/Response schemas for the Audit Trail API endpoints.

Requirements: 38.1, 39.1, 39.2, 39.3
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


# ──────────────────────────────────────────────────────────────────────
# Response Schemas
# ──────────────────────────────────────────────────────────────────────


class AuditEventResponse(BaseModel):
    """Response model for a single audit event."""

    id: UUID = Field(..., description="Audit event ID")
    actor_id: UUID | None = Field(None, description="User ID of the actor")
    actor_username: str = Field(..., description="Username of the actor")
    event_type: str = Field(..., description="Type of audit event")
    case_id: UUID | None = Field(None, description="Associated case ID")
    event_details: dict = Field(default_factory=dict, description="Event details (JSON)")
    timestamp: datetime = Field(..., description="When the event occurred")
    ip_address: str | None = Field(None, description="IP address of the actor")
    created_date: datetime | None = Field(None, description="Record creation timestamp")

    model_config = {"from_attributes": True}


class AuditEventListResponse(BaseModel):
    """Paginated response for audit event listing."""

    items: list[AuditEventResponse] = Field(
        default_factory=list, description="Audit events"
    )
    total: int = Field(..., description="Total number of matching events")
    page: int = Field(..., description="Current page number")
    page_size: int = Field(..., description="Items per page")
    total_pages: int = Field(..., description="Total number of pages")
