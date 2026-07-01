"""
SQLAlchemy ORM models for Role, Permission, and their associations.
"""

from sqlalchemy import Boolean, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.database.models.base_model import BaseModel


class PermissionModel(BaseModel):
    """Permission database table."""

    __tablename__ = "permissions"

    code: Mapped[str] = mapped_column(
        String(100), unique=True, nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    scope: Mapped[str] = mapped_column(
        String(20), nullable=False, index=True
    )  # MENU, API, FIELD
    resource: Mapped[str] = mapped_column(
        String(255), nullable=False, index=True
    )  # e.g. "users", "reports.sales"
    action: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # CREATE, READ, UPDATE, DELETE, etc.
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class RoleModel(BaseModel):
    """Role database table with permission associations."""

    __tablename__ = "roles"

    code: Mapped[str] = mapped_column(
        String(50), unique=True, nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    tenant_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    parent_role_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("roles.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Many-to-many: roles ↔ permissions
    permissions = relationship(
        "PermissionModel",
        secondary="role_permissions",
        backref="roles",
        lazy="selectin",
    )


class RolePermissionModel(BaseModel):
    """Association table: role ↔ permission (many-to-many)."""

    __tablename__ = "role_permissions"

    role_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("roles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    permission_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("permissions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )


class RoleAssignmentModel(BaseModel):
    """Links users to roles, optionally scoped by tenant."""

    __tablename__ = "role_assignments"

    user_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("roles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    tenant_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
