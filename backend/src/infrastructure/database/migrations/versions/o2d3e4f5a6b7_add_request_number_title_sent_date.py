"""add request_number, title, sent_date to vlr_reconciliation_requests

Revision ID: o2d3e4f5a6b7
Revises: n1c2d3e4f5a6
Create Date: 2026-07-29

Adds human-friendly request numbering ("{company_code}-{5-digit serial}"),
a user-provided title, and a sent_date timestamp (null = invites not sent)
so the Track Reconciliation list can show one row per request with these
columns.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "o2d3e4f5a6b7"
down_revision: Union[str, None] = "n1c2d3e4f5a6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "vlr_reconciliation_requests",
        sa.Column("request_number", sa.String(length=30), nullable=True),
    )
    op.add_column(
        "vlr_reconciliation_requests",
        sa.Column("title", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "vlr_reconciliation_requests",
        sa.Column("sent_date", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_vlr_requests_request_number",
        "vlr_reconciliation_requests",
        ["request_number"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_vlr_requests_request_number",
        table_name="vlr_reconciliation_requests",
    )
    op.drop_column("vlr_reconciliation_requests", "sent_date")
    op.drop_column("vlr_reconciliation_requests", "title")
    op.drop_column("vlr_reconciliation_requests", "request_number")
