"""RBAC Application Service."""

from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.domain.entities.audit_log import AuditAction
from src.domain.entities.role import PermissionScope
from src.domain.entities.user import User
from src.infrastructure.database.models.audit_log_model import AuditLogModel
from src.infrastructure.database.models.role_model import (
    PermissionModel,
    RoleAssignmentModel,
    RoleModel,
    RolePermissionModel,
)
from src.infrastructure.security.audit_service import AuditService
from src.infrastructure.security.permission_manager import PermissionManager


class RbacService:
    """Application service for RBAC management."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ═══════════════════════════════════════════════════════════════════
    # PERMISSIONS
    # ═══════════════════════════════════════════════════════════════════

    async def list_permissions(self, scope: str | None = None) -> list[PermissionModel]:
        """List permissions, optionally filtered by scope."""
        stmt = select(PermissionModel).where(PermissionModel.is_active == True)  # noqa: E712
        if scope:
            stmt = stmt.where(PermissionModel.scope == scope)
        stmt = stmt.order_by(PermissionModel.scope, PermissionModel.resource)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def create_permission(
        self,
        *,
        code: str,
        name: str,
        description: str | None,
        scope: str,
        resource: str,
        action: str,
        actor_id: UUID,
        actor_username: str,
        ip_address: str,
    ) -> PermissionModel:
        """Create a new permission definition."""
        # Check uniqueness
        existing = await self._session.execute(
            select(PermissionModel).where(PermissionModel.code == code)
        )
        if existing.scalar_one_or_none():
            raise ValueError(f"Permission code '{code}' already exists")

        perm = PermissionModel(
            id=uuid4(),
            code=code,
            name=name,
            description=description,
            scope=scope,
            resource=resource,
            action=action,
            is_active=True,
            created_by=actor_username,
            modified_by=actor_username,
        )
        self._session.add(perm)

        # Audit log
        audit = AuditService(self._session)
        await audit.log(
            actor_id=actor_id,
            actor_username=actor_username,
            action=AuditAction.PERMISSION_CREATED,
            resource_type="Permission",
            resource_id=str(perm.id),
            new_value={"code": perm.code, "scope": perm.scope, "resource": perm.resource, "action": perm.action},
            ip_address=ip_address,
        )

        await self._session.commit()
        await self._session.refresh(perm)
        return perm

    # ═══════════════════════════════════════════════════════════════════
    # ROLES
    # ═══════════════════════════════════════════════════════════════════

    async def list_roles(self, tenant_id: UUID | None = None) -> dict:
        """List roles with their permissions. Returns dict with roles list and total."""
        stmt = (
            select(RoleModel)
            .options(selectinload(RoleModel.permissions))
            .where(RoleModel.is_active == True)  # noqa: E712
        )
        if tenant_id:
            stmt = stmt.where(
                (RoleModel.tenant_id == str(tenant_id)) | (RoleModel.tenant_id.is_(None))
            )
        stmt = stmt.order_by(RoleModel.code)
        result = await self._session.execute(stmt)
        roles = list(result.scalars().all())
        return {"roles": roles, "total": len(roles)}

    async def create_role(
        self,
        *,
        code: str,
        name: str,
        description: str | None,
        tenant_id: UUID | None,
        parent_role_id: UUID | None,
        actor_id: UUID,
        actor_username: str,
        ip_address: str,
    ) -> RoleModel:
        """Create a new role."""
        existing = await self._session.execute(
            select(RoleModel).where(RoleModel.code == code)
        )
        if existing.scalar_one_or_none():
            raise ValueError(f"Role code '{code}' already exists")

        role = RoleModel(
            id=uuid4(),
            code=code,
            name=name,
            description=description,
            is_system=False,
            is_active=True,
            tenant_id=str(tenant_id) if tenant_id else None,
            parent_role_id=str(parent_role_id) if parent_role_id else None,
            created_by=actor_username,
            modified_by=actor_username,
        )
        self._session.add(role)

        audit = AuditService(self._session)
        await audit.log(
            actor_id=actor_id,
            actor_username=actor_username,
            action=AuditAction.ROLE_CREATED,
            resource_type="Role",
            resource_id=str(role.id),
            tenant_id=tenant_id,
            new_value={"code": role.code, "name": role.name},
            ip_address=ip_address,
        )

        await self._session.commit()
        await self._session.refresh(role)
        return role

    async def update_role(
        self,
        *,
        role_id: UUID,
        name: str | None = None,
        description: str | None = None,
        is_active: bool | None = None,
        parent_role_id: UUID | None = None,
        actor_id: UUID,
        actor_username: str,
        ip_address: str,
    ) -> RoleModel:
        """Update role properties."""
        stmt = (
            select(RoleModel)
            .options(selectinload(RoleModel.permissions))
            .where(RoleModel.id == str(role_id))
        )
        result = await self._session.execute(stmt)
        role = result.scalar_one_or_none()

        if not role:
            raise ValueError("Role not found")
        if role.is_system:
            raise ValueError("System roles cannot be modified")

        old_value = {"name": role.name, "description": role.description, "is_active": role.is_active}

        if name is not None:
            role.name = name
        if description is not None:
            role.description = description
        if is_active is not None:
            role.is_active = is_active
        if parent_role_id is not None:
            role.parent_role_id = str(parent_role_id)

        role.modified_by = actor_username

        audit = AuditService(self._session)
        await audit.log(
            actor_id=actor_id,
            actor_username=actor_username,
            action=AuditAction.ROLE_UPDATED,
            resource_type="Role",
            resource_id=str(role_id),
            old_value=old_value,
            new_value={"name": role.name, "description": role.description, "is_active": role.is_active},
            ip_address=ip_address,
        )

        await self._session.commit()
        await self._session.refresh(role)
        return role

    # ═══════════════════════════════════════════════════════════════════
    # PERMISSION GRANT / REVOKE ON ROLES
    # ═══════════════════════════════════════════════════════════════════

    async def grant_permission(
        self,
        *,
        role_id: UUID,
        permission_id: UUID,
        actor_id: UUID,
        actor_username: str,
        ip_address: str,
    ) -> dict:
        """Grant a permission to a role."""
        role = await self._session.get(RoleModel, str(role_id))
        if not role:
            raise ValueError("Role not found")

        perm = await self._session.get(PermissionModel, str(permission_id))
        if not perm:
            raise ValueError("Permission not found")

        # Check if already granted
        existing = await self._session.execute(
            select(RolePermissionModel).where(
                RolePermissionModel.role_id == str(role_id),
                RolePermissionModel.permission_id == str(permission_id),
            )
        )
        if existing.scalar_one_or_none():
            raise ValueError("Permission already granted to this role")

        rp = RolePermissionModel(
            id=uuid4(),
            role_id=str(role_id),
            permission_id=str(permission_id),
            created_by=actor_username,
            modified_by=actor_username,
        )
        self._session.add(rp)

        audit = AuditService(self._session)
        await audit.log_permission_change(
            actor_id=actor_id,
            actor_username=actor_username,
            action=AuditAction.PERMISSION_GRANTED,
            role_id=role_id,
            permission_code=perm.code,
            ip_address=ip_address,
        )

        await self._session.commit()
        return {"detail": f"Permission '{perm.code}' granted to role '{role.code}'"}

    async def revoke_permission(
        self,
        *,
        role_id: UUID,
        permission_id: UUID,
        actor_id: UUID,
        actor_username: str,
        ip_address: str,
    ) -> dict:
        """Revoke a permission from a role."""
        stmt = select(RolePermissionModel).where(
            RolePermissionModel.role_id == str(role_id),
            RolePermissionModel.permission_id == str(permission_id),
        )
        result = await self._session.execute(stmt)
        rp = result.scalar_one_or_none()

        if not rp:
            raise ValueError("Permission not assigned to this role")

        # Get permission code for audit
        perm = await self._session.get(PermissionModel, str(permission_id))

        await self._session.delete(rp)

        audit = AuditService(self._session)
        await audit.log_permission_change(
            actor_id=actor_id,
            actor_username=actor_username,
            action=AuditAction.PERMISSION_REVOKED,
            role_id=role_id,
            permission_code=perm.code if perm else str(permission_id),
            ip_address=ip_address,
        )

        await self._session.commit()
        return {"detail": "Permission revoked"}

    # ═══════════════════════════════════════════════════════════════════
    # ROLE ASSIGNMENTS (User ↔ Role)
    # ═══════════════════════════════════════════════════════════════════

    async def assign_role(
        self,
        *,
        user_id: UUID,
        role_id: UUID,
        tenant_id: UUID | None,
        actor_id: UUID,
        actor_username: str,
        ip_address: str,
    ) -> RoleAssignmentModel:
        """Assign a role to a user."""
        role = await self._session.get(RoleModel, str(role_id))
        if not role:
            raise ValueError("Role not found")

        # Check duplicate
        existing = await self._session.execute(
            select(RoleAssignmentModel).where(
                RoleAssignmentModel.user_id == str(user_id),
                RoleAssignmentModel.role_id == str(role_id),
                RoleAssignmentModel.is_active == True,  # noqa: E712
            )
        )
        if existing.scalar_one_or_none():
            raise ValueError("Role already assigned to this user")

        assignment = RoleAssignmentModel(
            id=uuid4(),
            user_id=str(user_id),
            role_id=str(role_id),
            tenant_id=str(tenant_id) if tenant_id else None,
            is_active=True,
            created_by=actor_username,
            modified_by=actor_username,
        )
        self._session.add(assignment)

        audit = AuditService(self._session)
        await audit.log_role_assigned(
            actor_id=actor_id,
            actor_username=actor_username,
            user_id=user_id,
            role_id=role_id,
            role_code=role.code,
            tenant_id=tenant_id,
            ip_address=ip_address,
        )

        await self._session.commit()
        await self._session.refresh(assignment)
        return assignment

    async def revoke_role(
        self,
        *,
        user_id: UUID,
        role_id: UUID,
        tenant_id: UUID | None,
        actor_id: UUID,
        actor_username: str,
        ip_address: str,
    ) -> dict:
        """Revoke a role from a user."""
        stmt = select(RoleAssignmentModel).where(
            RoleAssignmentModel.user_id == str(user_id),
            RoleAssignmentModel.role_id == str(role_id),
            RoleAssignmentModel.is_active == True,  # noqa: E712
        )
        result = await self._session.execute(stmt)
        assignment = result.scalar_one_or_none()

        if not assignment:
            raise ValueError("Active role assignment not found")

        assignment.is_active = False
        assignment.modified_by = actor_username

        role = await self._session.get(RoleModel, str(role_id))

        audit = AuditService(self._session)
        await audit.log_role_revoked(
            actor_id=actor_id,
            actor_username=actor_username,
            user_id=user_id,
            role_id=role_id,
            role_code=role.code if role else str(role_id),
            tenant_id=tenant_id,
            ip_address=ip_address,
        )

        await self._session.commit()
        return {"detail": "Role revoked"}

    # ═══════════════════════════════════════════════════════════════════
    # USER PERMISSION QUERIES
    # ═══════════════════════════════════════════════════════════════════

    async def get_my_menu_permissions(self, current_user: User) -> dict:
        """Get menu permissions for a user. Returns dict with menu_keys and permissions."""
        manager = PermissionManager(self._session)
        permissions = await manager.get_user_permissions(
            current_user.id, scope=PermissionScope.MENU
        )
        menu_keys = list({p.resource for p in permissions})
        return {"menu_keys": menu_keys, "permissions": permissions}

    async def get_my_all_permissions(self, current_user: User) -> dict:
        """Get all permissions for the current user (debug/introspection)."""
        manager = PermissionManager(self._session)

        # Get role assignments for this user
        assign_result = await self._session.execute(
            select(RoleAssignmentModel).where(RoleAssignmentModel.user_id == str(current_user.id))
        )
        assignments = assign_result.scalars().all()

        # Get role details
        role_ids = [a.role_id for a in assignments]
        roles_info = []
        if role_ids:
            role_result = await self._session.execute(
                select(RoleModel).options(selectinload(RoleModel.permissions)).where(RoleModel.id.in_(role_ids))
            )
            roles = role_result.scalars().all()
            for r in roles:
                roles_info.append({
                    "id": str(r.id),
                    "code": r.code,
                    "name": r.name,
                    "is_active": r.is_active,
                    "permission_count": len(r.permissions),
                    "permissions": [
                        {"code": p.code, "scope": p.scope, "resource": p.resource, "action": p.action}
                        for p in r.permissions
                    ],
                })

        permissions = await manager.get_user_permissions(current_user.id)
        return {
            "user_id": str(current_user.id),
            "username": current_user.username,
            "legacy_role": current_user.role,
            "role_assignments": [
                {
                    "role_id": str(a.role_id),
                    "is_active": a.is_active,
                    "tenant_id": str(a.tenant_id) if a.tenant_id else None,
                }
                for a in assignments
            ],
            "assigned_roles": roles_info,
            "total_effective_permissions": len(permissions),
            "effective_permissions": [
                {
                    "code": p.code,
                    "scope": p.scope,
                    "resource": p.resource,
                    "action": p.action,
                }
                for p in permissions
            ],
        }

    async def get_my_field_permissions(self, current_user: User, resource: str) -> dict:
        """Get field-level permissions for a user on a specific resource."""
        manager = PermissionManager(self._session)
        field_perms = await manager.get_field_permissions(current_user.id, resource)
        return {"resource": resource, "fields": field_perms}

    # ═══════════════════════════════════════════════════════════════════
    # AUDIT LOGS
    # ═══════════════════════════════════════════════════════════════════

    async def list_audit_logs(
        self,
        *,
        action: str | None = None,
        actor_username: str | None = None,
        resource_type: str | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> dict:
        """Query audit logs with filters. Returns dict with logs, total, skip, limit."""
        stmt = select(AuditLogModel)
        count_stmt = select(func.count()).select_from(AuditLogModel)

        if action:
            stmt = stmt.where(AuditLogModel.action == action)
            count_stmt = count_stmt.where(AuditLogModel.action == action)
        if actor_username:
            stmt = stmt.where(AuditLogModel.actor_username == actor_username)
            count_stmt = count_stmt.where(AuditLogModel.actor_username == actor_username)
        if resource_type:
            stmt = stmt.where(AuditLogModel.resource_type == resource_type)
            count_stmt = count_stmt.where(AuditLogModel.resource_type == resource_type)

        stmt = stmt.order_by(AuditLogModel.created_at.desc()).offset(skip).limit(limit)

        result = await self._session.execute(stmt)
        total_result = await self._session.execute(count_stmt)

        logs = list(result.scalars().all())
        total = total_result.scalar() or 0

        return {"logs": logs, "total": total, "skip": skip, "limit": limit}
