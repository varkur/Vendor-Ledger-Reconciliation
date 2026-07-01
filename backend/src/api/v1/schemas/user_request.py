"""
User request schemas (Pydantic v2).
"""

from uuid import UUID

from pydantic import BaseModel, Field


class CreateUserRequest(BaseModel):
    """Request to create a new user."""

    username: str = Field(..., min_length=3, max_length=255)
    password: str = Field(..., min_length=8, max_length=128)
    is_validate_ad: bool = Field(default=True, description="If true, authenticate via Darwin AD")
    role_id: UUID | None = Field(default=None, description="Role ID to assign to the user")


class UpdateUserRequest(BaseModel):
    """Request to update user properties."""

    is_active: bool | None = None
    is_blocked: bool | None = None
    is_validate_ad: bool | None = None
    role_id: UUID | None = Field(default=None, description="Role ID to assign (replaces existing)")
