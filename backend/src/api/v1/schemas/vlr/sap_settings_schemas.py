"""
SAP Settings Pydantic schemas (request/response).

Provides validation for SAP connection configuration, connection testing,
and field mapping endpoints.

Security: Credentials are never exposed in response schemas — only masked values.

Requirements: 20.1, 20.2, 20.3, 20.5, 20.6
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


# ──────────────────────────────────────────────────────────────────────
# SAP Connection Schemas
# ──────────────────────────────────────────────────────────────────────


class SAPConnectionResponse(BaseModel):
    """
    Response schema for SAP connection settings (GET).

    Credentials are masked — only last 4 characters are visible.
    """

    host: str = Field(default="", description="SAP host address")
    system_number: str = Field(default="00", description="SAP system number")
    client: str = Field(default="100", description="SAP client number")
    username: str = Field(default="", description="SAP username (masked)")
    password: str = Field(default="", description="SAP password (masked)")
    base_url: str = Field(default="", description="SAP API base URL")
    is_configured: bool = Field(default=False, description="Whether minimum config is set")
    last_successful_pull: datetime | None = Field(
        default=None, description="Last successful SAP data pull timestamp"
    )
    error_count: int = Field(default=0, description="Cumulative error count")


class SAPConnectionUpdateRequest(BaseModel):
    """
    Request body for updating SAP connection settings (PUT).

    All fields are optional — only provided fields will be updated.
    Credentials are stored encrypted.
    """

    host: str | None = Field(default=None, min_length=1, max_length=255, description="SAP host address")
    system_number: str | None = Field(
        default=None, min_length=1, max_length=5, description="SAP system number"
    )
    client: str | None = Field(
        default=None, min_length=1, max_length=10, description="SAP client number"
    )
    username: str | None = Field(
        default=None, min_length=1, max_length=255, description="SAP username"
    )
    password: str | None = Field(
        default=None, min_length=1, max_length=500, description="SAP password"
    )
    base_url: str | None = Field(
        default=None, min_length=1, max_length=500, description="SAP API base URL"
    )


# ──────────────────────────────────────────────────────────────────────
# SAP Connection Test Schemas
# ──────────────────────────────────────────────────────────────────────


class SAPConnectionTestResponse(BaseModel):
    """Response schema for SAP connection test (POST)."""

    success: bool = Field(..., description="Whether the connection test succeeded")
    message: str = Field(..., description="Human-readable test result message")
    response_time_ms: float = Field(default=0.0, description="Response time in milliseconds")


# ──────────────────────────────────────────────────────────────────────
# Field Mapping Schemas
# ──────────────────────────────────────────────────────────────────────


class FieldMappingEntry(BaseModel):
    """A single field mapping: SAP field → VLR internal field."""

    sap_field: str = Field(..., min_length=1, max_length=50, description="SAP field name (e.g., ZUONR)")
    internal_field: str = Field(
        ..., min_length=1, max_length=100, description="Internal field name (e.g., assignment_number)"
    )


class FieldMappingUpdateRequest(BaseModel):
    """Request body for updating SAP-to-VLR field mapping (PUT)."""

    mappings: list[FieldMappingEntry] = Field(
        ..., min_length=1, description="List of SAP-to-VLR field mappings"
    )


class FieldMappingResponse(BaseModel):
    """Response schema for field mapping configuration (GET via the PUT response)."""

    mappings: list[FieldMappingEntry] = Field(
        default_factory=list, description="Current field mappings"
    )
    updated_at: datetime | None = Field(default=None, description="Last update timestamp")


# ──────────────────────────────────────────────────────────────────────
# Generic Success Response
# ──────────────────────────────────────────────────────────────────────


class SettingsUpdateResponse(BaseModel):
    """Generic response for a successful settings update."""

    message: str = Field(default="Settings updated successfully.")
    updated_at: datetime | None = Field(default=None, description="Timestamp of the update")
