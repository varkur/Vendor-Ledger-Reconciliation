"""
Exception Management Pydantic schemas (request/response).

Provides validation for exception listing, resolution, and bulk operations.
Requirements: 6.2, 6.3, 6.9, 11.2
"""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field


# ──────────────────────────────────────────────────────────────────────
# Request Schemas
# ──────────────────────────────────────────────────────────────────────


class ResolveExceptionRequest(BaseModel):
    """Request body for resolving a single exception."""

    action: str = Field(
        ...,
        pattern=r"^(accept_company_match|request_document_vendor|mark_tds_difference|mark_agreed_adjustment|write_off|escalate)$",
        description="Resolution action to apply",
    )
    comment: str | None = Field(
        default=None,
        max_length=1000,
        description="Optional comment for the resolution",
    )


class BulkResolveRequest(BaseModel):
    """Request body for bulk resolving exceptions."""

    exception_ids: list[UUID] = Field(
        ...,
        min_length=1,
        max_length=100,
        description="List of exception IDs to resolve",
    )
    action: str = Field(
        ...,
        pattern=r"^(accept_company_match|request_document_vendor|mark_tds_difference|mark_agreed_adjustment|write_off|escalate)$",
        description="Resolution action to apply to all exceptions",
    )
    comment: str | None = Field(
        default=None,
        max_length=1000,
        description="Optional comment for the bulk resolution",
    )


# ──────────────────────────────────────────────────────────────────────
# Response Schemas
# ──────────────────────────────────────────────────────────────────────


class ExceptionResponse(BaseModel):
    """Response schema for a single reconciliation exception."""

    id: UUID
    case_id: UUID
    ledger_entry_id: UUID | None = None
    category: str
    severity: str
    amount: Decimal | None = None
    first_flagged_date: date | None = None
    status: str
    created_date: datetime | None = None

    model_config = {"from_attributes": True}


class ExceptionListResponse(BaseModel):
    """Paginated exception list response."""

    items: list[ExceptionResponse]
    total: int = Field(default=0, description="Total matching records")
    page: int = Field(default=1, description="Current page number")
    page_size: int = Field(default=50, description="Items per page")
    total_pages: int = Field(default=0, description="Total pages available")


class ResolutionResponse(BaseModel):
    """Response schema for a resolution action result."""

    exception_id: UUID
    action: str
    status: str
    resolved_by: UUID
    resolved_date: datetime
    comments: str | None = None


class BulkResolveResponse(BaseModel):
    """Response schema for a bulk resolution operation."""

    total: int = Field(description="Total exceptions in the request")
    resolved: int = Field(description="Number successfully resolved")
    failed: int = Field(description="Number that failed to resolve")
    results: list[ResolutionResponse] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class ExceptionCategoryResponse(BaseModel):
    """Response schema for exception categories with counts."""

    severity: str
    count: int


class ExceptionCategoriesResponse(BaseModel):
    """Response schema for all exception category counts for a case."""

    case_id: UUID
    categories: list[ExceptionCategoryResponse] = Field(default_factory=list)
    total: int = Field(default=0, description="Total exception count")
