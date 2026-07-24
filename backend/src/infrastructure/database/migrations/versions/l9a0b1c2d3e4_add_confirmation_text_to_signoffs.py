"""add confirmation_text to vlr_portal_sign_offs

Revision ID: l9a0b1c2d3e4
Revises: k8f9a0b1c2d3
Create Date: 2026-07-20

Adds the confirmation_text column used to store the vendor's approval/dispute
note recorded during portal sign-off.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "l9a0b1c2d3e4"
down_revision: Union[str, None] = "k8f9a0b1c2d3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Idempotent: only add if it doesn't already exist (some environments were
    # patched manually before this migration existed).
    op.execute(
        "ALTER TABLE vlr_portal_sign_offs "
        "ADD COLUMN IF NOT EXISTS confirmation_text TEXT"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE vlr_portal_sign_offs DROP COLUMN IF EXISTS confirmation_text"
    )
