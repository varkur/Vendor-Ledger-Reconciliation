"""Create vlr_audit_events table (append-only, immutable).

Creates the audit trail table for recording all significant actions
in the VLR system. This table is APPEND-ONLY — UPDATE and DELETE
operations are revoked at the database level.

Retention Policy: 7 years minimum. Events should be archived to
cold storage after 2 years but retained for a minimum of 7 years
to meet regulatory compliance requirements.

Revision ID: k8f9a0b1c2d3
Revises: j7e8f9a0b1c2
Create Date: 2026-07-21

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSON, UUID


# revision identifiers, used by Alembic.
revision: str = "k8f9a0b1c2d3"
down_revision: Union[str, None] = "j7e8f9a0b1c2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ═══════════════════════════════════════════════════════════
    # Create vlr_audit_events table (APPEND-ONLY)
    # ═══════════════════════════════════════════════════════════
    op.create_table(
        "vlr_audit_events",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "actor_id",
            UUID(as_uuid=True),
            nullable=True,
            comment="User ID of the actor (null for system actions)",
        ),
        sa.Column(
            "actor_username",
            sa.String(100),
            nullable=False,
            comment="Username or identifier of the actor",
        ),
        sa.Column(
            "event_type",
            sa.String(50),
            nullable=False,
            comment="Event type: login, logout, case_created, status_changed, match_override, approval, rejection, vendor_interaction",
        ),
        sa.Column(
            "case_id",
            UUID(as_uuid=True),
            nullable=True,
            comment="Associated reconciliation case ID (null for non-case events)",
        ),
        sa.Column(
            "event_details",
            JSON,
            nullable=False,
            server_default="{}",
            comment="Structured JSON details about the event",
        ),
        sa.Column(
            "timestamp",
            sa.DateTime(timezone=True),
            nullable=False,
            comment="When the event occurred (UTC)",
        ),
        sa.Column(
            "ip_address",
            sa.String(45),
            nullable=True,
            comment="IP address of the actor (supports IPv6)",
        ),
        # Audit columns (from BaseModel)
        sa.Column("created_by", sa.String(255), nullable=False, server_default="system"),
        sa.Column(
            "created_date",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("modified_by", sa.String(255), nullable=False, server_default="system"),
        sa.Column(
            "modified_date",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    # ─── Indexes ──────────────────────────────────────────────────────────
    op.create_index("ix_vlr_audit_events_event_type", "vlr_audit_events", ["event_type"])
    op.create_index("ix_vlr_audit_events_case_id", "vlr_audit_events", ["case_id"])
    op.create_index("ix_vlr_audit_events_timestamp", "vlr_audit_events", ["timestamp"])
    op.create_index(
        "ix_vlr_audit_events_actor_username", "vlr_audit_events", ["actor_username"]
    )
    op.create_index(
        "ix_vlr_audit_events_timestamp_event_type",
        "vlr_audit_events",
        ["timestamp", "event_type"],
    )

    # ─── REVOKE UPDATE/DELETE (Append-Only Enforcement) ───────────────────
    # This ensures the table is immutable at the database level.
    # The application user cannot UPDATE or DELETE rows from this table.
    # NOTE: Replace 'app_user' with the actual PostgreSQL role used by the application.
    op.execute(
        "REVOKE UPDATE, DELETE ON vlr_audit_events FROM PUBLIC;"
    )

    # ─── Retention Policy Comment ─────────────────────────────────────────
    # 7-year retention policy:
    # - Active data (0-2 years): Kept in primary table, fully queryable
    # - Archive data (2-7 years): Consider partitioning by year or
    #   moving to a separate archive table with compressed storage
    # - Purge data (>7 years): May be purged per regulatory approval
    #
    # Implementation options:
    # 1. PostgreSQL table partitioning by timestamp (RANGE partitioning)
    # 2. Periodic archival job moving old events to vlr_audit_events_archive
    # 3. pg_partman extension for automated partition management
    op.execute(
        "COMMENT ON TABLE vlr_audit_events IS "
        "'Immutable audit trail. 7-year retention policy. No UPDATE/DELETE permitted.';"
    )


def downgrade() -> None:
    # Re-grant permissions before dropping
    op.execute("GRANT UPDATE, DELETE ON vlr_audit_events TO PUBLIC;")

    # Drop indexes
    op.drop_index("ix_vlr_audit_events_timestamp_event_type", table_name="vlr_audit_events")
    op.drop_index("ix_vlr_audit_events_actor_username", table_name="vlr_audit_events")
    op.drop_index("ix_vlr_audit_events_timestamp", table_name="vlr_audit_events")
    op.drop_index("ix_vlr_audit_events_case_id", table_name="vlr_audit_events")
    op.drop_index("ix_vlr_audit_events_event_type", table_name="vlr_audit_events")

    # Drop table
    op.drop_table("vlr_audit_events")
