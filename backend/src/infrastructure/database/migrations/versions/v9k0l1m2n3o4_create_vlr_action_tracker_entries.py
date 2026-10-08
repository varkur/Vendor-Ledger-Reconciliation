"""create vlr_action_tracker_entries table

Revision ID: v9k0l1m2n3o4
Revises: u8j9k0l1m2n3
Create Date: 2026-10-05

The Action Tracker tab's diagnosis columns (Status, Classification, both-side
invoice detail) are all computed live from ledger entries + match results by
ReconciliationExportService — never persisted. This table stores only the
human-entered workflow fields (action owner, action-taken reference/remark,
closed flag) for a row, keyed by a stable row_key so notes survive the
diagnosis being recomputed on every read.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "v9k0l1m2n3o4"
down_revision: Union[str, None] = "u8j9k0l1m2n3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "vlr_action_tracker_entries",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_by", sa.String(255), nullable=False, server_default="system"),
        sa.Column("created_date", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("modified_by", sa.String(255), nullable=False, server_default="system"),
        sa.Column("modified_date", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("request_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("case_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("row_key", sa.String(150), nullable=False),
        sa.Column("action_owner", sa.String(100), nullable=True),
        sa.Column("action_taken_reference", sa.String(100), nullable=True),
        sa.Column("action_taken_remark", sa.Text(), nullable=True),
        sa.Column("request_closed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["request_id"], ["vlr_reconciliation_requests.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["case_id"], ["vlr_reconciliation_cases.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("case_id", "row_key", name="uq_vlr_action_tracker_case_row"),
    )
    op.create_index(
        "ix_vlr_action_tracker_entries_request_id", "vlr_action_tracker_entries", ["request_id"]
    )
    op.create_index(
        "ix_vlr_action_tracker_entries_case_id", "vlr_action_tracker_entries", ["case_id"]
    )
    op.create_index(
        "ix_vlr_action_tracker_entries_row_key", "vlr_action_tracker_entries", ["row_key"]
    )


def downgrade() -> None:
    op.drop_index("ix_vlr_action_tracker_entries_row_key", table_name="vlr_action_tracker_entries")
    op.drop_index("ix_vlr_action_tracker_entries_case_id", table_name="vlr_action_tracker_entries")
    op.drop_index("ix_vlr_action_tracker_entries_request_id", table_name="vlr_action_tracker_entries")
    op.drop_table("vlr_action_tracker_entries")
