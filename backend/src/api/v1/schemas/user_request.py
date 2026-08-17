"""
User request schemas (Pydantic v2).
"""

from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class CreateUserRequest(BaseModel):
    """Request to create a new user with full profile data."""

    username: str = Field(..., min_length=3, max_length=255)
    password: str | None = Field(
        default=None,
        min_length=8,
        max_length=128,
        description="If omitted, falls back to settings.DARWINBOX_DEFAULT_PASSWORD",
    )
    is_validate_ad: bool = Field(default=True, description="If true, authenticate via Darwin AD")
    role_id: UUID | None = Field(default=None, description="Role ID to assign to the user")

    # Profile fields (persisted into user_details)
    name: str = Field(..., min_length=1, max_length=255)
    email: EmailStr
    department: str = Field(..., min_length=1, max_length=255)
    designation_title: str = Field(default="", max_length=255)
    reporting_manager: str = Field(default="", max_length=255)
    employee_id: str | None = Field(
        default=None, max_length=50, description="Defaults to username when omitted"
    )


class ImportFromDarwinboxRequest(BaseModel):
    """Request to import a single employee's profile from Darwinbox/AD by employee ID."""

    employee_id: str = Field(..., min_length=1, max_length=50)


class UpdateUserRequest(BaseModel):
    """Request to update user properties."""

    is_active: bool | None = None
    is_blocked: bool | None = None
    is_validate_ad: bool | None = None
    role_id: UUID | None = Field(default=None, description="Role ID to assign (replaces existing)")
