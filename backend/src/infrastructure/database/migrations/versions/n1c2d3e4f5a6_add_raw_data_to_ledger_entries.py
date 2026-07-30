"""add raw_data JSON column to vlr_ledger_entries

Revision ID: n1c2d3e4f5a6
Revises: m0b1c2d3e4f5
Create Date: 2026-07-24

Stores the full original uploaded row (header -> value) for each ledger entry
so the formatted Excel export can reproduce every column the user provided,
including SAP fields the reconciliation engine does not otherwise model.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSON

# revision identifiers, used by Alembic.
revision: str = "n1c2d3e4f5a6"
down_revision: Union[str, None] = "m0b1c2d3e4f5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "vlr_ledger_entries",
        sa.Column("raw_data", JSON, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("vlr_ledger_entries", "raw_data")
