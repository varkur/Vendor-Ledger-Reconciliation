"""
Role and Permission domain entities.
Implements granular RBAC with menu, API, and field-level permissions.
"""

from dataclasses import dataclass, field
from enum import StrEnum
from uuid import UUID

from src.domain.entities.base_entity import BaseEntity


class PermissionScope(StrEnum):
    """Defines the scope at which a permission operates."""

    MENU = "MENU"       # UI menu/navigation visibility
    API = "API"         # API endpoint access
    FIELD = "FIELD"     # Field-level read/write control


class PermissionAction(StrEnum):
    """Standard CRUD + special actions."""

    CREATE = "CREATE"
    READ = "READ"
    UPDATE = "UPDATE"
    DELETE = "DELETE"
    EXECUTE = "EXECUTE"
    EXPORT = "EXPORT"
    IMPORT = "IMPORT"
    APPROVE = "APPROVE"


@dataclass
class Permission(BaseEntity):
    """
    A granular permission that can be attached to roles.

    Examples:
        - scope=MENU, resource="users", action=READ → can see Users menu
        - scope=API, resource="users", action=CREATE → can call POST /users
        - scope=FIELD, resource="users.salary", action=READ → can view salary field
    """

    code: str = field(default="")           # Unique permission code, e.g. "users.create"
    name: str = field(default="")           # Human-readable name
    description: str = field(default="")
    scope: str = field(default=PermissionScope.API)
    resource: str = field(default="")       # Resource identifier, e.g. "users", "reports.sales"
    action: str = field(default=PermissionAction.READ)
    is_active: bool = field(default=True)


@dataclass
class Role(BaseEntity):
    """
    Named role that groups permissions.
    Supports hierarchy via parent_role_id for permission inheritance.
    """

    code: str = field(default="")           # Unique role code, e.g. "ADMIN"
    name: str = field(default="")           # Display name
    description: str = field(default="")
    is_system: bool = field(default=False)  # System roles cannot be deleted
    is_active: bool = field(default=True)
    tenant_id: UUID | None = field(default=None)  # None = global role
    parent_role_id: UUID | None = field(default=None)  # For role inheritance
    permissions: list[Permission] = field(default_factory=list)

    def has_permission(self, permission_code: str) -> bool:
        """Check if role directly has a specific permission."""
        return any(
            p.code == permission_code and p.is_active
            for p in self.permissions
        )

    def get_permissions_by_scope(self, scope: PermissionScope) -> list[Permission]:
        """Get all permissions for a given scope."""
        return [
            p for p in self.permissions
            if p.scope == scope and p.is_active
        ]


@dataclass
class RoleAssignment(BaseEntity):
    """
    Links a user to a role, optionally scoped to a tenant.
    Supports time-bounded role assignments.
    """

    user_id: UUID = field(default=None)  # type: ignore[assignment]
    role_id: UUID = field(default=None)  # type: ignore[assignment]
    tenant_id: UUID | None = field(default=None)
    is_active: bool = field(default=True)
