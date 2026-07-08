"""
Vendor Portal Pydantic schemas (request/response).

Provides validation for portal authentication, file upload, statement retrieval,
and digital sign-off endpoints.

Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8, 4.9, 4.10, 4.11, 24.1, 24.2, 24.3, 24.4, 33.1, 33.2
"""

from datetime import date, datetime
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


# ──────────────────────────────────────────────────────────────────────
# New Endpoints - Requirements 24.1, 24.2, 24.3, 24.4, 33.1, 33.2
# ──────────────────────────────────────────────────────────────────────


class PortalValidateTokenRequest(BaseModel):
    """Request body for POST /validate-token."""

    token: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Portal access token to validate",
    )


class PortalValidateTokenResponse(BaseModel):
    """Response for POST /validate-token — returns case summary if token is valid."""

    case_id: UUID
    vendor_name: str = Field(description="Vendor name associated with the case")
    period_start: date | None = Field(default=None, description="Reconciliation period start")
    period_end: date | None = Field(default=None, description="Reconciliation period end")
    status: str = Field(description="Current case status")
    upload_count: int = Field(description="Number of uploads used")
    max_uploads: int = Field(default=5, description="Maximum uploads allowed")
    token_valid_until: datetime | None = Field(
        default=None, description="Token expiry timestamp (UTC)"
    )


class PortalCaseSignOffRequest(BaseModel):
    """Request body for POST /sign-off/{case_id} — vendor approval with confirmation text."""

    confirmation_text: str = Field(
        ...,
        min_length=1,
        max_length=1000,
        description="Vendor confirmation/approval text",
    )
    statement_version: str = Field(
        ...,
        min_length=1,
        max_length=50,
        description="Version of the statement being signed off",
    )


class PortalCaseSignOffResponse(BaseModel):
    """Response for POST /sign-off/{case_id}."""

    case_id: UUID
    signed_at: datetime
    ip_address: str
    confirmation_text: str
    statement_version: str
    status: str = Field(description="Case status after sign-off")
    message: str = Field(description="Human-readable sign-off result")


class PortalStatementResultResponse(BaseModel):
    """
    Response for GET /statement/{case_id} — vendor-facing reconciliation results.

    Displays matched items summary, status, and balances.
    Does NOT include internal SAP data per BRD Section 7.1.
    """

    case_id: UUID
    status: str = Field(description="Current reconciliation case status")
    vendor_name: str = Field(description="Vendor name")
    period_start: date | None = Field(default=None, description="Reconciliation period start")
    period_end: date | None = Field(default=None, description="Reconciliation period end")
    total_matched_entries: int = Field(default=0, description="Count of matched entry pairs")
    total_unmatched_vendor: int = Field(default=0, description="Count of unmatched vendor entries")
    vendor_opening_balance: Decimal | None = Field(
        default=None, description="Vendor opening balance"
    )
    vendor_closing_balance: Decimal | None = Field(
        default=None, description="Vendor closing balance"
    )
    net_difference: Decimal | None = Field(
        default=None, description="Net difference between company and vendor"
    )
    match_summary: list[dict] = Field(
        default_factory=list,
        description="Summary of match results (match type, count, total amount)",
    )
    statement_version: str = Field(description="Statement version identifier for sign-off")
