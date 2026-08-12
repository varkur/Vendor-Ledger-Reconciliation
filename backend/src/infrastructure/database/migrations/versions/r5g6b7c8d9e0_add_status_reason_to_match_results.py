"""add status_reason to vlr_match_results

Revision ID: r5g6b7c8d9e0
Revises: q4f5a6b7c8d9
Create Date: 2026-08-12

Stores the mandatory reason a reviewer selects when manually linking two
unmatched entries together (see docs/Update Status.xlsx for the fixed list
of reasons). NULL for all non-manual (auto-matched) match records.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "r5g6b7c8d9e0"
down_revision: Union[str, None] = "q4f5a6b7c8d9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "vlr_match_results",
        sa.Column(
            "status_reason",
            sa.String(length=100),
            nullable=True,
            comment="Reviewer-selected reason for a manual link (see docs/Update Status.xlsx)",
        ),
    )


def downgrade() -> None:
    op.drop_column("vlr_match_results", "status_reason")
