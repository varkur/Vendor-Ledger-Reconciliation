"""
User response schemas (Pydantic v2).
Never exposes password_hash.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class UserResponse(BaseModel):
    """User response with employee details."""

    id: UUID
    username: str
    is_active: bool
    is_blocked: bool
    is_validate_ad: bool
    employee_id: str | None = None
    employee_name: str | None = None
    email: str | None = None
    last_login: datetime | None = None
    created_by: str
    created_date: datetime
    modified_by: str
    modified_date: datetime


class UserDetailResponse(BaseModel):
    """Full user details (all fields from user_details table)."""

    id: UUID
    username: str
    is_active: bool
    is_blocked: bool
    is_validate_ad: bool
    employee_id: str | None = None
    employee_name: str | None = None
    first_name: str | None = None
    middle_name: str | None = None
    last_name: str | None = None
    email: str | None = None
    designation_title: str | None = None
    department: str | None = None
    business_unit: str | None = None
    group_company: str | None = None
    location: str | None = None
    region: str | None = None
    zone: str | None = None
    grade: str | None = None
    office_mobile_no: str | None = None
    personal_mobile_no: str | None = None
    date_of_joining: str | None = None
    reporting_manager: str | None = None
    direct_manager_employee_id: str | None = None
    direct_manager_name: str | None = None
    direct_manager_email: str | None = None
    sap_user_id: str | None = None
    division_id: str | None = None
    territory_id: str | None = None
    created_by: str
    created_date: datetime
    modified_by: str
    modified_date: datetime


class UserListResponse(BaseModel):
    """Paginated user list response."""

    users: list[UserResponse]
    total: int = Field(default=0)
    skip: int = Field(default=0)
    limit: int = Field(default=100)
