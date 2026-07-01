"""Create commission_claims table (example module).

Revision ID: e2f3a4b5c6d7
Revises: d1e2f3a4b5c6
Create Date: 2026-06-24
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "e2f3a4b5c6d7"
down_revision = "d1e2f3a4b5c6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "commission_claims",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("claim_number", sa.String(50), unique=True, nullable=False, index=True),
        sa.Column("employee_id", UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("employee_name", sa.String(255), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("company", sa.String(100), nullable=False),
        sa.Column("department", sa.String(100), server_default="", nullable=False),
        sa.Column("region", sa.String(100), server_default="", nullable=False),
        sa.Column("description", sa.Text, server_default="", nullable=False),
        sa.Column("status", sa.String(30), server_default="DRAFT", nullable=False, index=True),
        sa.Column("workflow_instance_id", UUID(as_uuid=True), nullable=True),
        sa.Column("created_by", sa.String(255), server_default="system", nullable=False),
        sa.Column("created_date", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("modified_by", sa.String(255), server_default="system", nullable=False),
        sa.Column("modified_date", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("commission_claims")
