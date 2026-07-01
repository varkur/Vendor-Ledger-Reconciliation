"""
Enterprise Permission Manager.
Provides granular permission checks for menu, API, and field-level access control.
Integrates with the role-permission database model and supports multi-tenancy.
"""

from typing import Callable
from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.domain.entities.role import PermissionAction, PermissionScope
from src.infrastructure.database.models.role_model import (
    PermissionModel,
    RoleAssignmentModel,
    RoleModel,
)
from src.infrastructure.database.session import get_db_session


class PermissionManager:
    """
    Centralized permission evaluation engine.

    Resolves a user's effective permissions by:
    1. Finding all active role assignments (optionally tenant-scoped)
    2. Collecting permissions from those roles + parent role inheritance
    3. Checking whether a specific permission is granted
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_user_permissions(
        self,
        user_id: UUID,
        tenant_id: UUID | None = None,
        scope: PermissionScope | None = None,
    ) -> list[PermissionModel]:
        """
        Retrieve all effective permissions for a user.

        Args:
            user_id: The user to check.
            tenant_id: Optional tenant scope filter.
            scope: Optional scope filter (MENU, API, FIELD).

        Returns:
            Deduplicated list of active PermissionModel instances.
        """
        # Get all active role assignments for the user
        stmt = (
            select(RoleAssignmentModel)
            .where(
                RoleAssignmentModel.user_id == str(user_id),
                RoleAssignmentModel.is_active == True,  # noqa: E712
            )
        )
        if tenant_id:
            # Include global roles (tenant_id IS NULL) + tenant-specific roles
            stmt = stmt.where(
                (RoleAssignmentModel.tenant_id == str(tenant_id))
                | (RoleAssignmentModel.tenant_id.is_(None))
            )

        result = await self._session.execute(stmt)
        assignments = result.scalars().all()

        if not assignments:
            return []

        role_ids = [a.role_id for a in assignments]

        # Fetch roles with their permissions (eager load)
        role_stmt = (
            select(RoleModel)
            .options(selectinload(RoleModel.permissions))
            .where(
                RoleModel.id.in_(role_ids),
                RoleModel.is_active == True,  # noqa: E712
            )
        )
        role_result = await self._session.execute(role_stmt)
        roles = role_result.scalars().all()

        # Collect all permissions, handling role inheritance
        seen_ids: set[str] = set()
        permissions: list[PermissionModel] = []

        for role in roles:
            for perm in role.permissions:
                if not perm.is_active:
                    continue
                if scope and perm.scope != scope:
                    continue
                perm_id = str(perm.id)
                if perm_id not in seen_ids:
                    seen_ids.add(perm_id)
                    permissions.append(perm)

            # Walk parent role chain (single level for performance)
            if role.parent_role_id:
                parent_stmt = (
                    select(RoleModel)
                    .options(selectinload(RoleModel.permissions))
                    .where(RoleModel.id == role.parent_role_id)
                )
                parent_result = await self._session.execute(parent_stmt)
                parent_role = parent_result.scalar_one_or_none()
                if parent_role and parent_role.is_active:
                    for perm in parent_role.permissions:
                        if not perm.is_active:
                            continue
                        if scope and perm.scope != scope:
                            continue
                        perm_id = str(perm.id)
                        if perm_id not in seen_ids:
                            seen_ids.add(perm_id)
                            permissions.append(perm)

        return permissions

    async def has_permission(
        self,
        user_id: UUID,
        permission_code: str,
        tenant_id: UUID | None = None,
    ) -> bool:
        """Check if user has a specific permission (by code)."""
        permissions = await self.get_user_permissions(user_id, tenant_id)
        return any(p.code == permission_code for p in permissions)

    async def has_api_access(
        self,
        user_id: UUID,
        resource: str,
        action: str | PermissionAction,
        tenant_id: UUID | None = None,
    ) -> bool:
        """Check if user has API-level access to a resource + action."""
        permissions = await self.get_user_permissions(
            user_id, tenant_id, scope=PermissionScope.API
        )
        return any(
            p.resource == resource and p.action == str(action)
            for p in permissions
        )

    async def get_menu_permissions(
        self,
        user_id: UUID,
        tenant_id: UUID | None = None,
    ) -> list[str]:
        """Get all menu resource keys the user can access."""
        permissions = await self.get_user_permissions(
            user_id, tenant_id, scope=PermissionScope.MENU
        )
        return list({p.resource for p in permissions})

    async def get_field_permissions(
        self,
        user_id: UUID,
        resource: str,
        tenant_id: UUID | None = None,
    ) -> dict[str, list[str]]:
        """
        Get field-level permissions for a resource.

        Returns:
            Dict mapping field names to allowed actions.
            e.g. {"salary": ["READ"], "email": ["READ", "UPDATE"]}
        """
        permissions = await self.get_user_permissions(
            user_id, tenant_id, scope=PermissionScope.FIELD
        )
        field_perms: dict[str, list[str]] = {}
        for p in permissions:
            # Resource format: "entity.field_name"
            if p.resource.startswith(f"{resource}."):
                field_name = p.resource.split(".", 1)[1]
                field_perms.setdefault(field_name, []).append(p.action)
        return field_perms


# ─── FastAPI Dependencies ───


def require_permission(permission_code: str) -> Callable:
    """
    FastAPI dependency factory for permission-based endpoint protection.

    Usage:
        @router.get("/sensitive", dependencies=[Depends(require_permission("reports.export"))])
    """
    from src.api.v1.dependencies import get_current_active_user
    from src.domain.entities.user import User

    async def permission_checker(
        current_user: User = Depends(get_current_active_user),
        session: AsyncSession = Depends(get_db_session),
    ) -> User:
        manager = PermissionManager(session)

        # Extract tenant_id from request if available (multi-tenant)
        has_perm = await manager.has_permission(
            user_id=current_user.id,
            permission_code=permission_code,
        )

        if not has_perm:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission '{permission_code}' required",
            )
        return current_user

    return permission_checker


def require_api_permission(resource: str, action: str | PermissionAction) -> Callable:
    """
    FastAPI dependency for API-level permission checks.

    Usage:
        @router.post("/users", dependencies=[Depends(require_api_permission("users", "CREATE"))])
    """
    from src.api.v1.dependencies import get_current_active_user
    from src.domain.entities.user import User

    async def api_permission_checker(
        current_user: User = Depends(get_current_active_user),
        session: AsyncSession = Depends(get_db_session),
    ) -> User:
        manager = PermissionManager(session)
        has_access = await manager.has_api_access(
            user_id=current_user.id,
            resource=resource,
            action=str(action),
        )

        if not has_access:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"API access denied: {resource}.{action}",
            )
        return current_user

    return api_permission_checker
