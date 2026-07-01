"""
Audit Log domain entity.
Captures all security-relevant operations: role changes, permission grants, etc.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from uuid import UUID, uuid4


class AuditAction(StrEnum):
    """Enumeration of auditable actions."""

    # Generic CRUD (used by automatic audit listener)
    INSERT = "INSERT"
    UPDATE = "UPDATE"
    DELETE = "DELETE"

    # Role operations
    ROLE_CREATED = "ROLE_CREATED"
    ROLE_UPDATED = "ROLE_UPDATED"
    ROLE_DELETED = "ROLE_DELETED"
    ROLE_ASSIGNED = "ROLE_ASSIGNED"
    ROLE_REVOKED = "ROLE_REVOKED"

    # Permission operations
    PERMISSION_CREATED = "PERMISSION_CREATED"
    PERMISSION_UPDATED = "PERMISSION_UPDATED"
    PERMISSION_DELETED = "PERMISSION_DELETED"
    PERMISSION_GRANTED = "PERMISSION_GRANTED"
    PERMISSION_REVOKED = "PERMISSION_REVOKED"

    # User state changes
    USER_BLOCKED = "USER_BLOCKED"
    USER_UNBLOCKED = "USER_UNBLOCKED"
    USER_ACTIVATED = "USER_ACTIVATED"
    USER_DEACTIVATED = "USER_DEACTIVATED"

    # Authentication events
    LOGIN_SUCCESS = "LOGIN_SUCCESS"
    LOGIN_FAILED = "LOGIN_FAILED"
    TOKEN_REFRESHED = "TOKEN_REFRESHED"

    # Tenant operations
    TENANT_CREATED = "TENANT_CREATED"
    TENANT_UPDATED = "TENANT_UPDATED"


@dataclass
class AuditLog:
    """
    Immutable audit log entry.
    Once created, audit logs are never modified or deleted.

    Attributes:
        actor_id: The user who performed the action.
        actor_username: Denormalized for fast querying/display.
        action: What happened (enum value).
        resource_type: What type of entity was affected (e.g. "Role", "Permission").
        resource_id: ID of the affected entity.
        tenant_id: Tenant context (None for global operations).
        old_value: JSON-serialized previous state (for change tracking).
        new_value: JSON-serialized new state (for change tracking).
        ip_address: Client IP for security forensics.
        user_agent: Client user-agent string.
        metadata: Additional structured data (JSON).
    """

    id: UUID = field(default_factory=uuid4)
    actor_id: UUID | None = field(default=None)
    actor_username: str = field(default="system")
    action: str = field(default="")
    resource_type: str = field(default="")
    resource_id: str = field(default="")
    tenant_id: UUID | None = field(default=None)
    old_value: str | None = field(default=None)  # JSON string
    new_value: str | None = field(default=None)  # JSON string
    ip_address: str = field(default="")
    user_agent: str = field(default="")
    extra_data: str | None = field(default=None)   # JSON string
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
