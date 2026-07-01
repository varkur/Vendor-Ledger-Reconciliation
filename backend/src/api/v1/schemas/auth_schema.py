"""
Authentication request and response schemas (Pydantic v2).
"""

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    """Login request payload."""

    username: str = Field(..., min_length=3, max_length=255, description="Username")
    password: str = Field(..., min_length=1, description="Password")


class RefreshRequest(BaseModel):
    """Token refresh request payload."""

    refresh_token: str = Field(..., description="Valid refresh token")


class TokenResponse(BaseModel):
    """Authentication token response."""

    access_token: str = Field(..., description="JWT access token")
    refresh_token: str = Field(..., description="JWT refresh token")
    token_type: str = Field(default="Bearer", description="Token type")
    expires_in: int = Field(..., description="Access token expiry in seconds")


class ErrorResponse(BaseModel):
    """Standard error response."""

    success: bool = Field(default=False)
    message: str = Field(..., description="Error message")
    correlation_id: str = Field(default="", description="Request correlation ID")
