"""
Automatic audit logging via SQLAlchemy session events.

Hooks into `before_flush` to capture before/after snapshots for every
INSERT, UPDATE, and DELETE across all models that inherit from BaseModel.

The audit_logs table itself is excluded to prevent infinite recursion.

Usage:
    from src.infrastructure.database.audit_listener import register_audit_listener
    register_audit_listener(async_session_factory)

To set the current actor context (who is making the change):
    from src.infrastructure.database.audit_context import set_audit_context
    set_audit_context(actor_id=user.id, actor_username=user.username, ip_address=request_ip)
"""

import json
import logging
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import event, inspect
from sqlalchemy.orm import Session

from src.infrastructure.database.models.audit_log_model import AuditLogModel
from src.infrastructure.database.models.base_model import BaseModel
from src.infrastructure.database.audit_context import get_audit_context

logger = logging.getLogger(__name__)

# Tables to exclude from audit logging (to prevent recursion)
EXCLUDED_TABLES = {"audit_logs"}


def _serialize_value(value) -> str | None:
    """Convert a column value to a JSON-safe representation."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    if hasattr(value, "hex"):  # UUID
        return str(value)
    if isinstance(value, bytes):
        return "<binary>"
    return str(value)


def _model_to_dict(instance) -> dict:
    """Serialize a model instance to a dictionary of column_name: value."""
    mapper = inspect(type(instance))
    result = {}
    for col in mapper.columns:
        key = col.key
        value = getattr(instance, key, None)
        result[key] = _serialize_value(value)
    return result


def _get_old_values(instance) -> dict:
    """Get the previous (committed) values for a modified instance."""
    state = inspect(instance)
    old_values = {}
    for attr in state.attrs:
        hist = attr.history
        if hist.deleted:
            old_values[attr.key] = _serialize_value(hist.deleted[0])
        else:
            # No change for this attribute — use the current value
            old_values[attr.key] = _serialize_value(attr.value)
    return old_values


def _get_changed_columns(instance) -> list[str]:
    """Return list of column names that have been modified."""
    state = inspect(instance)
    changed = []
    for attr in state.attrs:
        hist = attr.history
        if hist.has_changes():
            changed.append(attr.key)
    return changed


def _create_audit_entry(
    action: str,
    table_name: str,
    resource_id: str,
    old_value: dict | None,
    new_value: dict | None,
    changed_columns: list[str] | None = None,
) -> AuditLogModel:
    """Create an AuditLogModel instance for a detected change."""
    ctx = get_audit_context()

    extra_data = None
    if changed_columns:
        extra_data = json.dumps({"changed_columns": changed_columns})

    return AuditLogModel(
        id=uuid4(),
        actor_id=str(ctx.actor_id) if ctx.actor_id else None,
        actor_username=ctx.actor_username,
        action=action,
        resource_type=table_name,
        resource_id=resource_id,
        tenant_id=str(ctx.tenant_id) if ctx.tenant_id else None,
        old_value=json.dumps(old_value) if old_value else None,
        new_value=json.dumps(new_value) if new_value else None,
        ip_address=ctx.ip_address,
        user_agent=ctx.user_agent,
        extra_data=extra_data,
        created_at=datetime.now(timezone.utc),
    )


def _get_resource_id(instance) -> str:
    """Extract the primary key value from a model instance."""
    mapper = inspect(type(instance))
    pk_cols = mapper.primary_key
    if pk_cols:
        pk_value = getattr(instance, pk_cols[0].key, None)
        return str(pk_value) if pk_value else ""
    return ""


def _before_flush(session: Session, flush_context, instances) -> None:
    """
    SQLAlchemy event handler: captures audit snapshots before flush.

    Iterates over new, dirty, and deleted objects in the session and
    creates audit log entries with before/after state.
    """
    audit_entries = []

    # --- INSERTS ---
    for instance in session.new:
        if not isinstance(instance, BaseModel):
            continue
        table_name = instance.__tablename__
        if table_name in EXCLUDED_TABLES:
            continue

        new_value = _model_to_dict(instance)
        resource_id = _get_resource_id(instance)

        audit_entries.append(
            _create_audit_entry(
                action="INSERT",
                table_name=table_name,
                resource_id=resource_id,
                old_value=None,
                new_value=new_value,
            )
        )

    # --- UPDATES ---
    for instance in session.dirty:
        if not isinstance(instance, BaseModel):
            continue
        table_name = instance.__tablename__
        if table_name in EXCLUDED_TABLES:
            continue

        # Only log if there are actual attribute changes
        if not session.is_modified(instance, include_collections=False):
            continue

        changed_columns = _get_changed_columns(instance)
        if not changed_columns:
            continue

        old_value = _get_old_values(instance)
        new_value = _model_to_dict(instance)
        resource_id = _get_resource_id(instance)

        audit_entries.append(
            _create_audit_entry(
                action="UPDATE",
                table_name=table_name,
                resource_id=resource_id,
                old_value=old_value,
                new_value=new_value,
                changed_columns=changed_columns,
            )
        )

    # --- DELETES ---
    for instance in session.deleted:
        if not isinstance(instance, BaseModel):
            continue
        table_name = instance.__tablename__
        if table_name in EXCLUDED_TABLES:
            continue

        old_value = _model_to_dict(instance)
        resource_id = _get_resource_id(instance)

        audit_entries.append(
            _create_audit_entry(
                action="DELETE",
                table_name=table_name,
                resource_id=resource_id,
                old_value=old_value,
                new_value=None,
            )
        )

    # Add all audit entries to the session (they'll be committed in the same tx)
    for entry in audit_entries:
        session.add(entry)


def register_audit_listener() -> None:
    """
    Register the before_flush audit listener on the sync Session class.

    SQLAlchemy async sessions delegate flush operations to an internal
    sync Session, so we listen on the Session class itself which covers
    both sync and async usage.

    Call this once during application startup after creating the session factory.
    """
    event.listen(Session, "before_flush", _before_flush)
    logger.info("Automatic audit logging registered on Session class")
