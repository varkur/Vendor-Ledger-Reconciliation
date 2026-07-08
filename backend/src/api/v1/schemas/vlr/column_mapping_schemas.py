"""
Request/response schemas for the Column Mapping API endpoints.

Requirements: 9.1, 10.1, 10.2, 11.1
"""

from uuid import UUID

from pydantic import BaseModel, Field


# ──────────────────────────────────────────────────────────────────────────────
# Response Models
# ──────────────────────────────────────────────────────────────────────────────


class FilePreviewResponse(BaseModel):
    """Response for file upload preview (first 10 rows)."""

    headers: list[str] = Field(..., description="Column headers from the file")
    rows: list[list[str]] = Field(
        ..., description="First 10 data rows from the file"
    )
    total_row_count: int = Field(
        ..., description="Total number of data rows in the file"
    )
    filename: str = Field(..., description="Original filename")

    model_config = {"from_attributes": True}


class ColumnSuggestionResponse(BaseModel):
    """A single auto-mapping suggestion for a column."""

    column_index: int = Field(..., description="0-based column index")
    header: str = Field(..., description="Column header text")
    suggested_tag: str | None = Field(
        None, description="Suggested transaction type tag"
    )
    confidence: str | None = Field(
        None, description="Confidence level: High, Medium, or Low"
    )
    should_preselect: bool = Field(
        False, description="Whether the suggestion should be pre-selected"
    )

    model_config = {"from_attributes": True}


class AutoMapResponse(BaseModel):
    """Response for auto-mapping suggestions."""

    suggestions: list[ColumnSuggestionResponse] = Field(
        ..., description="Auto-mapping suggestions for each column"
    )

    model_config = {"from_attributes": True}


class ColumnMappingEntrySchema(BaseModel):
    """A single column-to-tag mapping entry."""

    column_index: int = Field(..., description="0-based column index")
    header: str = Field(..., description="Column header text")
    tag: str = Field(..., description="Transaction type tag assigned to this column")


class SaveTemplateRequest(BaseModel):
    """Request to save a column mapping template for a vendor."""

    vendor_id: UUID = Field(..., description="Vendor UUID to associate the template with")
    mappings: list[ColumnMappingEntrySchema] = Field(
        ..., description="List of column-to-tag mapping entries"
    )


class SaveTemplateResponse(BaseModel):
    """Response after saving a column mapping template."""

    vendor_id: UUID = Field(..., description="Vendor UUID the template is saved for")
    message: str = Field(..., description="Confirmation message")

    model_config = {"from_attributes": True}


class TemplateResponse(BaseModel):
    """Response for retrieving a saved column mapping template."""

    vendor_id: UUID = Field(..., description="Vendor UUID")
    mappings: list[ColumnMappingEntrySchema] = Field(
        ..., description="Saved column-to-tag mapping entries"
    )

    model_config = {"from_attributes": True}


# ──────────────────────────────────────────────────────────────────────────────
# Request Models
# ──────────────────────────────────────────────────────────────────────────────


class AutoMapRequest(BaseModel):
    """Request for auto-mapping column headers."""

    headers: list[str] = Field(
        ..., description="List of column headers to auto-map"
    )
