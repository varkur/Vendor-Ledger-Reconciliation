"""
Pydantic schemas for RBAC API endpoints.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


# ─── Permission Schemas ───


class PermissionCreate(BaseModel):
    """Create a new permission."""

    code: str = Field(..., min_length=3, max_length=100, examples=["users.create"])
    name: str = Field(..., min_length=1, max_length=255)
    description: str = Field(default="")
    scope: str = Field(..., pattern="^(MENU|API|FIELD)$")
    resource: str = Field(..., min_length=1, max_length=255)
    action: str = Field(
        ..., pattern="^(CREATE|READ|UPDATE|DELETE|EXECUTE|EXPORT|IMPORT|APPROVE)$"
    )


class PermissionResponse(BaseModel):
    """Permission read response."""

    id: UUID
    code: str
    name: str
    description: str
    scope: str
    resource: str
    action: str
    is_active: bool
    created_date: datetime

    model_config = {"from_attributes": True}


# ─── Role Schemas ───


class RoleCreate(BaseModel):
    """Create a new role."""

    code: str = Field(..., min_length=2, max_length=50)
    name: str = Field(..., min_length=1, max_length=255)
    description: str = Field(default="")
    tenant_id: UUID | None = Field(default=None)
    parent_role_id: UUID | None = Field(default=None)


class RoleUpdate(BaseModel):
    """Update an existing role."""

    name: str | None = Field(default=None, max_length=255)
    description: str | None = Field(default=None)
    is_active: bool | None = Field(default=None)
    parent_role_id: UUID | None = Field(default=None)


class RoleResponse(BaseModel):
    """Role read response."""

    id: UUID
    code: str
    name: str
    description: str
    is_system: bool
    is_active: bool
    tenant_id: UUID | None
    parent_role_id: UUID | None
    permissions: list[PermissionResponse] = []
    created_date: datetime
    modified_date: datetime

    model_config = {"from_attributes": True}


class RoleListResponse(BaseModel):
    """Paginated list of roles."""

    roles: list[RoleResponse]
    total: int


# ─── Role Assignment Schemas ───


class RoleAssignRequest(BaseModel):
    """Assign a role to a user."""

    user_id: UUID
    role_id: UUID
    tenant_id: UUID | None = Field(default=None)


class RoleRevokeRequest(BaseModel):
    """Revoke a role from a user."""

    user_id: UUID
    role_id: UUID
    tenant_id: UUID | None = Field(default=None)


class RoleAssignmentResponse(BaseModel):
    """Role assignment read response."""

    id: UUID
    user_id: UUID
    role_id: UUID
    tenant_id: UUID | None
    is_active: bool
    created_date: datetime

    model_config = {"from_attributes": True}


# ─── Permission Grant Schemas ───


class PermissionGrantRequest(BaseModel):
    """Grant a permission to a role."""

    role_id: UUID
    permission_id: UUID


class PermissionRevokeRequest(BaseModel):
    """Revoke a permission from a role."""

    role_id: UUID
    permission_id: UUID


# ─── Menu Permissions Response ───


class MenuPermissionsResponse(BaseModel):
    """User's menu access permissions for frontend consumption."""

    menu_keys: list[str]
    permissions: list[PermissionResponse]


# ─── Field Permissions Response ───


class FieldPermissionsResponse(BaseModel):
    """Field-level permissions for a specific resource."""

    resource: str
    fields: dict[str, list[str]]  # field_name → [allowed_actions]


# ─── Audit Log Schemas ───


class AuditLogResponse(BaseModel):
    """Audit log entry response."""

    id: UUID
    actor_id: UUID | None
    actor_username: str
    action: str
    resource_type: str
    resource_id: str
    tenant_id: UUID | None
    old_value: str | None
    new_value: str | None
    ip_address: str
    user_agent: str
    extra_data: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class AuditLogListResponse(BaseModel):
    """Paginated audit logs."""

    logs: list[AuditLogResponse]
    total: int
    skip: int
    limit: int
