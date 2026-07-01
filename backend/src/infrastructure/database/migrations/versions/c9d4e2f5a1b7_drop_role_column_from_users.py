"""Drop role column from users table.

The legacy role column is replaced by the role_assignments table
which supports multiple roles per user via the RBAC system.

Revision ID: c9d4e2f5a1b7
Revises: b7e2f1c4d9a3
Create Date: 2026-06-19
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = "c9d4e2f5a1b7"
down_revision = "b7e2f1c4d9a3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Remove the legacy role column from users table."""
    op.drop_column("users", "role")


def downgrade() -> None:
    """Re-add the role column (default USER)."""
    op.add_column(
        "users",
        sa.Column("role", sa.String(50), nullable=False, server_default="USER"),
    )
