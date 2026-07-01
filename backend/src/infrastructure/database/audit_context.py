"""
Request-scoped audit context using Python contextvars.

Stores the current actor (user) info so that the audit listener
can attribute changes to the correct user without passing context
through every function call.

Usage in middleware or dependency:
    from src.infrastructure.database.audit_context import set_audit_context, clear_audit_context

    # At request start (after authentication):
    set_audit_context(
        actor_id=current_user.id,
        actor_username=current_user.username,
        ip_address=request.client.host,
        user_agent=request.headers.get("user-agent", ""),
        tenant_id=current_user.tenant_id,
    )

    # At request end:
    clear_audit_context()
"""

from contextvars import ContextVar
from dataclasses import dataclass, field
from uuid import UUID


@dataclass(frozen=True)
class AuditContext:
    """Immutable snapshot of who is performing the current operation."""

    actor_id: UUID | None = field(default=None)
    actor_username: str = field(default="system")
    ip_address: str = field(default="")
    user_agent: str = field(default="")
    tenant_id: UUID | None = field(default=None)


# Default context for background jobs / system operations
_DEFAULT_CONTEXT = AuditContext()

# Context variable — one value per async task / thread
_audit_context_var: ContextVar[AuditContext] = ContextVar(
    "audit_context", default=_DEFAULT_CONTEXT
)


def set_audit_context(
    *,
    actor_id: UUID | None = None,
    actor_username: str = "system",
    ip_address: str = "",
    user_agent: str = "",
    tenant_id: UUID | None = None,
) -> None:
    """Set the audit context for the current request/task."""
    ctx = AuditContext(
        actor_id=actor_id,
        actor_username=actor_username,
        ip_address=ip_address,
        user_agent=user_agent,
        tenant_id=tenant_id,
    )
    _audit_context_var.set(ctx)


def get_audit_context() -> AuditContext:
    """Get the current audit context. Returns default 'system' context if not set."""
    return _audit_context_var.get()


def clear_audit_context() -> None:
    """Reset audit context to default (e.g., at end of request)."""
    _audit_context_var.set(_DEFAULT_CONTEXT)
