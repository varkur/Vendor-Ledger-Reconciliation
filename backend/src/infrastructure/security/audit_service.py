"""
Audit logging service.
Records all security-relevant operations to the audit_logs table.
Designed to be non-blocking — audit failures do not break business flows.
"""

import json
import logging
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.entities.audit_log import AuditAction, AuditLog
from src.infrastructure.database.models.audit_log_model import AuditLogModel

logger = logging.getLogger(__name__)


class AuditService:
    """
    Appends immutable audit entries for security-sensitive operations.

    Usage:
        audit = AuditService(db_session)
        await audit.log_role_change(actor, action, role, old_state, new_state, request)
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def log(
        self,
        *,
        actor_id: UUID | None = None,
        actor_username: str = "system",
        action: str | AuditAction,
        resource_type: str,
        resource_id: str = "",
        tenant_id: UUID | None = None,
        old_value: dict | None = None,
        new_value: dict | None = None,
        ip_address: str = "",
        user_agent: str = "",
        metadata: dict | None = None,
    ) -> None:
        """
        Write a single audit log entry.

        This method catches and logs internal errors — it never raises
        to avoid disrupting the calling business operation.
        """
        try:
            entry = AuditLogModel(
                actor_id=str(actor_id) if actor_id else None,
                actor_username=actor_username,
                action=str(action),
                resource_type=resource_type,
                resource_id=str(resource_id),
                tenant_id=str(tenant_id) if tenant_id else None,
                old_value=json.dumps(old_value) if old_value else None,
                new_value=json.dumps(new_value) if new_value else None,
                ip_address=ip_address,
                user_agent=user_agent,
                extra_data=json.dumps(metadata) if metadata else None,
            )
            self._session.add(entry)
            await self._session.flush()
        except Exception as exc:
            logger.error("Failed to write audit log: %s", exc, exc_info=True)

    # ─── Convenience methods ───

    async def log_role_assigned(
        self,
        *,
        actor_id: UUID,
        actor_username: str,
        user_id: UUID,
        role_id: UUID,
        role_code: str,
        tenant_id: UUID | None = None,
        ip_address: str = "",
    ) -> None:
        """Log a role being assigned to a user."""
        await self.log(
            actor_id=actor_id,
            actor_username=actor_username,
            action=AuditAction.ROLE_ASSIGNED,
            resource_type="RoleAssignment",
            resource_id=str(user_id),
            tenant_id=tenant_id,
            new_value={"user_id": str(user_id), "role_id": str(role_id), "role_code": role_code},
            ip_address=ip_address,
        )

    async def log_role_revoked(
        self,
        *,
        actor_id: UUID,
        actor_username: str,
        user_id: UUID,
        role_id: UUID,
        role_code: str,
        tenant_id: UUID | None = None,
        ip_address: str = "",
    ) -> None:
        """Log a role being revoked from a user."""
        await self.log(
            actor_id=actor_id,
            actor_username=actor_username,
            action=AuditAction.ROLE_REVOKED,
            resource_type="RoleAssignment",
            resource_id=str(user_id),
            tenant_id=tenant_id,
            old_value={"user_id": str(user_id), "role_id": str(role_id), "role_code": role_code},
            ip_address=ip_address,
        )

    async def log_permission_change(
        self,
        *,
        actor_id: UUID,
        actor_username: str,
        action: AuditAction,
        role_id: UUID,
        permission_code: str,
        tenant_id: UUID | None = None,
        ip_address: str = "",
    ) -> None:
        """Log a permission being granted to or revoked from a role."""
        await self.log(
            actor_id=actor_id,
            actor_username=actor_username,
            action=action,
            resource_type="RolePermission",
            resource_id=str(role_id),
            tenant_id=tenant_id,
            new_value={"role_id": str(role_id), "permission_code": permission_code},
            ip_address=ip_address,
        )

    async def log_login(
        self,
        *,
        user_id: UUID | None,
        username: str,
        success: bool,
        ip_address: str = "",
        user_agent: str = "",
        reason: str = "",
    ) -> None:
        """Log an authentication attempt."""
        action = AuditAction.LOGIN_SUCCESS if success else AuditAction.LOGIN_FAILED
        await self.log(
            actor_id=user_id,
            actor_username=username,
            action=action,
            resource_type="Authentication",
            resource_id=username,
            ip_address=ip_address,
            user_agent=user_agent,
            metadata={"reason": reason} if reason else None,
        )
