"""add tds_percentage_min, date_tolerance_days_min/max to vlr_reconciliation_requests

Revision ID: u8j9k0l1m2n3
Revises: t7i8j9k0l1m2
Create Date: 2026-08-22

The Reconciliation Settings screen (Request Statement > Configure) has
always shown a TDS Percentage Min/Max range and a Date Range Min/Max, but
only the Max values were ever wired to the backend — and even the Max date
tolerance was ignored, since case_controller.py hardcoded date_tolerance_days=15
regardless of what the request stored. This adds the missing columns so the
matching engine can actually try every rate/day-count within the configured
range instead of a single hardcoded/partial value.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "u8j9k0l1m2n3"
down_revision: Union[str, None] = "t7i8j9k0l1m2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "vlr_reconciliation_requests",
        sa.Column("tds_percentage_min", sa.Numeric(5, 2), nullable=True),
    )
    op.add_column(
        "vlr_reconciliation_requests",
        sa.Column("date_tolerance_days_min", sa.Integer(), nullable=True),
    )
    op.add_column(
        "vlr_reconciliation_requests",
        sa.Column("date_tolerance_days_max", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("vlr_reconciliation_requests", "date_tolerance_days_max")
    op.drop_column("vlr_reconciliation_requests", "date_tolerance_days_min")
    op.drop_column("vlr_reconciliation_requests", "tds_percentage_min")
