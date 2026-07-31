"""add reco_type to vlr_reconciliation_requests

Revision ID: q4f5a6b7c8d9
Revises: p3e4f5a6b7c8
Create Date: 2026-07-30

Distinguishes bulk request-statement reconciliations ('bulk') from
single-vendor direct reconciliations ('direct'). Track Reconciliation lists
both; Direct Reconciliation lists only 'direct'.

Existing rows are backfilled: any request whose cases are case_type='direct'
becomes 'direct'; everything else stays 'bulk'.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "q4f5a6b7c8d9"
down_revision: Union[str, None] = "p3e4f5a6b7c8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "vlr_reconciliation_requests",
        sa.Column("reco_type", sa.String(length=10), nullable=False, server_default="bulk"),
    )
    op.create_index(
        "ix_vlr_requests_reco_type", "vlr_reconciliation_requests", ["reco_type"]
    )
    # Backfill: mark requests that own a direct case as 'direct'.
    op.execute(
        """
        UPDATE vlr_reconciliation_requests r
        SET reco_type = 'direct'
        WHERE EXISTS (
            SELECT 1 FROM vlr_reconciliation_cases c
            WHERE c.request_id = r.id AND c.case_type = 'direct'
        )
        """
    )


def downgrade() -> None:
    op.drop_index("ix_vlr_requests_reco_type", table_name="vlr_reconciliation_requests")
    op.drop_column("vlr_reconciliation_requests", "reco_type")
