"""Create vlr_recovery_items and vlr_recovery_follow_ups tables.

Creates the recovery register tables for tracking amounts recoverable
from vendors and their follow-up action history.

Revision ID: j7e8f9a0b1c2
Revises: i6d7e8f9a0b1
Create Date: 2026-07-20

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


# revision identifiers, used by Alembic.
revision: str = "j7e8f9a0b1c2"
down_revision: Union[str, None] = "i6d7e8f9a0b1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ═══════════════════════════════════════════════════════════
    # 1. Create vlr_recovery_items table
    # ═══════════════════════════════════════════════════════════
    op.create_table(
        "vlr_recovery_items",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "case_id",
            UUID(as_uuid=True),
            sa.ForeignKey("vlr_reconciliation_cases.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "vendor_id",
            UUID(as_uuid=True),
            sa.ForeignKey("vlr_vendors.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "amount",
            sa.Numeric(15, 2),
            nullable=False,
            comment="Recoverable amount",
        ),
        sa.Column(
            "currency",
            sa.String(3),
            nullable=False,
            server_default="INR",
            comment="Currency code (default INR)",
        ),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="open",
            comment="Recovery status: open, in_progress, recovered, written_off",
        ),
        sa.Column(
            "identified_date",
            sa.Date(),
            nullable=False,
            comment="Date the recovery item was identified",
        ),
        sa.Column(
            "next_follow_up_date",
            sa.Date(),
            nullable=True,
            comment="Next scheduled follow-up date",
        ),
        sa.Column(
            "follow_up_interval_days",
            sa.Integer(),
            nullable=False,
            server_default="7",
            comment="Days between follow-up reminders",
        ),
        sa.Column(
            "notes",
            sa.Text(),
            nullable=True,
            comment="Additional notes about the recovery item",
        ),
        # Audit columns
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
        # Constraints
        sa.CheckConstraint(
            "status IN ('open', 'in_progress', 'recovered', 'written_off')",
            name="ck_vlr_recovery_item_valid_status",
        ),
    )

    # Indexes for vlr_recovery_items
    op.create_index("ix_vlr_recovery_items_case_id", "vlr_recovery_items", ["case_id"])
    op.create_index("ix_vlr_recovery_items_vendor_id", "vlr_recovery_items", ["vendor_id"])
    op.create_index("ix_vlr_recovery_items_status", "vlr_recovery_items", ["status"])
    op.create_index(
        "ix_vlr_recovery_items_next_follow_up",
        "vlr_recovery_items",
        ["next_follow_up_date"],
    )

    # ═══════════════════════════════════════════════════════════
    # 2. Create vlr_recovery_follow_ups table
    # ═══════════════════════════════════════════════════════════
    op.create_table(
        "vlr_recovery_follow_ups",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "recovery_item_id",
            UUID(as_uuid=True),
            sa.ForeignKey("vlr_recovery_items.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "action_taken",
            sa.Text(),
            nullable=False,
            comment="Description of the follow-up action taken",
        ),
        sa.Column(
            "action_by",
            sa.String(100),
            nullable=False,
            comment="User who performed the follow-up action",
        ),
        sa.Column(
            "action_date",
            sa.DateTime(timezone=True),
            nullable=False,
            comment="Timestamp when the action was performed",
        ),
        sa.Column(
            "next_follow_up_date",
            sa.Date(),
            nullable=True,
            comment="Scheduled date for the next follow-up",
        ),
        # Audit columns
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

    # Indexes for vlr_recovery_follow_ups
    op.create_index(
        "ix_vlr_recovery_follow_ups_item_id",
        "vlr_recovery_follow_ups",
        ["recovery_item_id"],
    )
    op.create_index(
        "ix_vlr_recovery_follow_ups_item_date",
        "vlr_recovery_follow_ups",
        ["recovery_item_id", "action_date"],
    )


def downgrade() -> None:
    # Drop vlr_recovery_follow_ups
    op.drop_index(
        "ix_vlr_recovery_follow_ups_item_date", table_name="vlr_recovery_follow_ups"
    )
    op.drop_index(
        "ix_vlr_recovery_follow_ups_item_id", table_name="vlr_recovery_follow_ups"
    )
    op.drop_table("vlr_recovery_follow_ups")

    # Drop vlr_recovery_items
    op.drop_index(
        "ix_vlr_recovery_items_next_follow_up", table_name="vlr_recovery_items"
    )
    op.drop_index("ix_vlr_recovery_items_status", table_name="vlr_recovery_items")
    op.drop_index("ix_vlr_recovery_items_vendor_id", table_name="vlr_recovery_items")
    op.drop_index("ix_vlr_recovery_items_case_id", table_name="vlr_recovery_items")
    op.drop_table("vlr_recovery_items")
