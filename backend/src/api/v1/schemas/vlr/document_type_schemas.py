"""
Pydantic schemas for Document Type Mapping CRUD endpoints.

Requirements: 19
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator


# ──────────────────────────────────────────────────────────────────────
# Request schemas
# ──────────────────────────────────────────────────────────────────────


VALID_CATEGORIES = [
    "Invoice",
    "Payment",
    "Credit Note",
    "Debit Note",
    "TDS",
    "Other",
]


class CreateDocumentTypeRequest(BaseModel):
    """Request to create a new document type mapping."""

    document_type_code: str = Field(
        ..., min_length=1, max_length=10,
        description="SAP document type code (e.g., RE, KR, DR, ZP)",
    )
    category: str = Field(
        ..., min_length=1, max_length=30,
        description="Classification category",
    )
    is_tds: bool = Field(
        default=False,
        description="Whether this document type is a TDS entry",
    )
    is_active: bool = Field(
        default=True,
        description="Whether this mapping is active",
    )

    @field_validator("document_type_code")
    @classmethod
    def validate_code(cls, v: str) -> str:
        return v.strip().upper()

    @field_validator("category")
    @classmethod
    def validate_category(cls, v: str) -> str:
        if v not in VALID_CATEGORIES:
            raise ValueError(
                f"Invalid category '{v}'. Must be one of: {VALID_CATEGORIES}"
            )
        return v


class UpdateDocumentTypeRequest(BaseModel):
    """Request to update an existing document type mapping."""

    document_type_code: Optional[str] = Field(
        None, min_length=1, max_length=10,
        description="SAP document type code",
    )
    category: Optional[str] = Field(
        None, min_length=1, max_length=30,
        description="Classification category",
    )
    is_tds: Optional[bool] = Field(
        None,
        description="Whether this document type is a TDS entry",
    )
    is_active: Optional[bool] = Field(
        None,
        description="Whether this mapping is active",
    )

    @field_validator("document_type_code")
    @classmethod
    def validate_code(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            return v.strip().upper()
        return v

    @field_validator("category")
    @classmethod
    def validate_category(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in VALID_CATEGORIES:
            raise ValueError(
                f"Invalid category '{v}'. Must be one of: {VALID_CATEGORIES}"
            )
        return v


# ──────────────────────────────────────────────────────────────────────
# Response schemas
# ──────────────────────────────────────────────────────────────────────


class DocumentTypeResponse(BaseModel):
    """Response for a single document type mapping."""

    id: str
    document_type_code: str
    category: str
    is_tds: bool
    is_active: bool
    created_date: Optional[datetime] = None
    modified_date: Optional[datetime] = None

    model_config = {"from_attributes": True}


class DocumentTypeListResponse(BaseModel):
    """Paginated response for document type mappings."""

    items: list[DocumentTypeResponse]
    total: int
    page: int
    page_size: int
