"""
Vendor Management Pydantic schemas (request/response).

Provides validation for vendor CRUD, bulk import, and export operations.
Requirements: 2.1, 2.2, 2.4, 2.5, 2.7, 2.9
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


# ──────────────────────────────────────────────────────────────────────
# Request Schemas
# ──────────────────────────────────────────────────────────────────────


class VendorContactRequest(BaseModel):
    """Schema for creating/updating a vendor contact."""

    name: str = Field(..., min_length=1, max_length=255)
    email: str = Field(..., min_length=3, max_length=255)
    phone: str | None = Field(default=None, max_length=50)
    designation: str | None = Field(default=None, max_length=255)
    is_primary: bool = Field(default=False)


class CreateVendorRequest(BaseModel):
    """Request body for creating a new vendor."""

    vendor_code: str = Field(..., min_length=1, max_length=50, description="Unique vendor code within company")
    company_code: str = Field(..., min_length=1, max_length=20, description="Company code for multi-tenant scoping")
    name: str = Field(..., min_length=1, max_length=255, description="Vendor name")
    pan: str | None = Field(default=None, max_length=20, description="PAN number")
    gstin: str | None = Field(default=None, max_length=20, description="GSTIN number")
    city: str | None = Field(default=None, max_length=100, description="City")
    status: str = Field(default="active", pattern=r"^(active|inactive)$", description="Vendor status")
    contacts: list[VendorContactRequest] = Field(default_factory=list, description="Vendor contacts")


class UpdateVendorRequest(BaseModel):
    """Request body for updating an existing vendor."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    pan: str | None = Field(default=None, max_length=20)
    gstin: str | None = Field(default=None, max_length=20)
    city: str | None = Field(default=None, max_length=100)
    status: str | None = Field(default=None, pattern=r"^(active|inactive)$")
    contacts: list[VendorContactRequest] | None = Field(default=None, description="Replace manual contacts")


# ──────────────────────────────────────────────────────────────────────
# Response Schemas
# ──────────────────────────────────────────────────────────────────────


class VendorContactResponse(BaseModel):
    """Response schema for a vendor contact."""

    id: UUID
    vendor_id: UUID
    name: str
    email: str
    phone: str | None = None
    designation: str | None = None
    is_primary: bool = False
    source: str = "manual"

    model_config = {"from_attributes": True}


class VendorResponse(BaseModel):
    """Response schema for a single vendor record."""

    id: UUID
    vendor_code: str
    company_code: str
    name: str
    pan: str | None = None
    gstin: str | None = None
    city: str | None = None
    status: str
    is_deleted: bool = False
    created_date: datetime | None = None
    modified_date: datetime | None = None
    contacts: list[VendorContactResponse] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class VendorListResponse(BaseModel):
    """Paginated vendor list response."""

    items: list[VendorResponse]
    total: int = Field(default=0, description="Total matching records")
    page: int = Field(default=1, description="Current page number")
    page_size: int = Field(default=50, description="Items per page")
    total_pages: int = Field(default=0, description="Total pages available")


# ──────────────────────────────────────────────────────────────────────
# Bulk Import Schemas
# ──────────────────────────────────────────────────────────────────────


class BulkImportRowErrorResponse(BaseModel):
    """Error detail for a single row in bulk import."""

    row_number: int
    vendor_code: str | None = None
    errors: list[str]


class BulkImportResultResponse(BaseModel):
    """Response for bulk vendor import operation."""

    total_rows: int
    successful: int
    failed: int
    errors: list[BulkImportRowErrorResponse] = Field(default_factory=list)
