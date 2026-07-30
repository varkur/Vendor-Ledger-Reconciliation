"""add vlr_ledger_files table for original uploaded file bytes

Revision ID: p3e4f5a6b7c8
Revises: o2d3e4f5a6b7
Create Date: 2026-07-29

Stores the raw bytes of each uploaded ledger file (per case + side) so the
download returns the exact original file — same format and data — instead of
a CSV reconstructed from the transformed ledger entries.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision: str = "p3e4f5a6b7c8"
down_revision: Union[str, None] = "o2d3e4f5a6b7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "vlr_ledger_files",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("case_id", UUID(as_uuid=True), nullable=False),
        sa.Column("side", sa.String(length=10), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=150), nullable=False,
                  server_default="application/octet-stream"),
        sa.Column("content", sa.LargeBinary(), nullable=False),
        sa.Column("created_by", sa.String(length=255), nullable=False, server_default="system"),
        sa.Column("created_date", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("modified_by", sa.String(length=255), nullable=False, server_default="system"),
        sa.Column("modified_date", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["case_id"], ["vlr_reconciliation_cases.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("case_id", "side", name="uq_vlr_ledger_file_case_side"),
    )
    op.create_index("ix_vlr_ledger_files_case_id", "vlr_ledger_files", ["case_id"])


def downgrade() -> None:
    op.drop_index("ix_vlr_ledger_files_case_id", table_name="vlr_ledger_files")
    op.drop_table("vlr_ledger_files")
