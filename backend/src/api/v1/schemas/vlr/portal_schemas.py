"""
Vendor Portal Pydantic schemas (request/response).

Provides validation for portal authentication, file upload, statement retrieval,
and digital sign-off endpoints.

Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8, 4.9, 4.10, 4.11
"""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field


# ──────────────────────────────────────────────────────────────────────
# Response Schemas
# ──────────────────────────────────────────────────────────────────────


class PortalAuthResponse(BaseModel):
    """Response for portal token authentication (GET /auth/{token})."""

    case_id: UUID
    vendor_id: UUID
    status: str = Field(description="Current case status")
    upload_count: int = Field(description="Number of uploads used")
    max_uploads: int = Field(default=5, description="Maximum uploads allowed")
    token_valid_until: datetime | None = Field(
        default=None, description="Token expiry timestamp (UTC)"
    )


class PortalUploadResponse(BaseModel):
    """Response for file upload (POST /upload)."""

    case_id: UUID
    status: str = Field(description="Case status after upload")
    upload_count: int = Field(description="New upload count after this upload")
    entries_parsed: int = Field(description="Number of entries parsed from file")
    message: str = Field(description="Human-readable upload result")
    task_id: str | None = Field(
        default=None, description="Celery task ID if re-reconciliation triggered"
    )


class PortalStatementResponse(BaseModel):
    """Response for statement retrieval (GET /statement)."""

    case_id: UUID
    status: str
    company_entries: list[dict] = Field(default_factory=list)
    vendor_entries: list[dict] = Field(default_factory=list)
    match_results: list[dict] = Field(default_factory=list)
    exceptions: list[dict] = Field(default_factory=list)
    row_10_balance: Decimal | None = None
    statement_version: str = Field(description="Statement version identifier")


class PortalSignOffRequest(BaseModel):
    """Request body for digital sign-off (POST /sign-off)."""

    statement_version: str = Field(
        ...,
        min_length=1,
        max_length=50,
        description="Version of the statement being signed off",
    )


class PortalSignOffResponse(BaseModel):
    """Response for digital sign-off (POST /sign-off)."""

    case_id: UUID
    signed_at: datetime
    ip_address: str
    statement_version: str
    status: str = Field(description="Case status after sign-off")
    message: str = Field(description="Human-readable sign-off result")
