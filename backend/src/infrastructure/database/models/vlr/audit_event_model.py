"""
Audit event model for immutable event logging.

This table is APPEND-ONLY — no UPDATE or DELETE operations are permitted.
At the database level, a REVOKE rule prevents UPDATE/DELETE on this table.
Retention policy: 7 years minimum.

Requirements: 38.1, 38.4
"""

from datetime import datetime

from sqlalchemy import DateTime, Index, String, Text
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.database.models.base_model import BaseModel


class AuditEventModel(BaseModel):
    """
    Immutable audit event log entry.

    Records all significant actions within the VLR system including
    login/logout, case lifecycle events, match overrides, approvals,
    rejections, and vendor portal interactions.

    NOTE: This table has a PostgreSQL REVOKE rule preventing UPDATE/DELETE.
    Retention: 7 years minimum (managed via partitioning or archival policy).
    """

    __tablename__ = "vlr_audit_events"

    actor_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        comment="User ID of the actor (null for system actions)",
    )
    actor_username: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Username or identifier of the actor",
    )
    event_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        comment="Type of event: login, logout, case_created, status_changed, match_override, approval, rejection, vendor_interaction",
    )
    case_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        index=True,
        comment="Associated reconciliation case ID (null for non-case events)",
    )
    event_details: Mapped[dict] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
        comment="Structured JSON details about the event",
    )
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
        comment="When the event occurred (UTC)",
    )
    ip_address: Mapped[str | None] = mapped_column(
        String(45),
        nullable=True,
        comment="IP address of the actor (supports IPv6)",
    )

    __table_args__ = (
        Index("ix_vlr_audit_events_actor_username", "actor_username"),
        Index("ix_vlr_audit_events_timestamp_event_type", "timestamp", "event_type"),
    )
