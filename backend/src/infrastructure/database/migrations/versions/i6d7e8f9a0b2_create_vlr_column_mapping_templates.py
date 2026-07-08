"""Create vlr_column_mapping_templates table for per-vendor column mapping persistence.

Stores column mapping configurations per vendor so that subsequent uploads
from the same vendor can be auto-mapped. Each vendor has at most one template
(enforced by unique constraint on vendor_id).

Revision ID: i6d7e8f9a0b1
Revises: h5c6d7e8f9a0
Create Date: 2026-07-16

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


# revision identifiers, used by Alembic.
revision: str = "i6d7e8f9a0b2"
down_revision: Union[str, None] = "h5c6d7e8f9a0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create the vlr_column_mapping_templates table
    op.create_table(
        "vlr_column_mapping_templates",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "vendor_id",
            UUID(as_uuid=True),
            sa.ForeignKey("vlr_vendors.id"),
            unique=True,
            nullable=False,
            comment="Reference to the vendor this template belongs to (one template per vendor)",
        ),
        sa.Column(
            "mapping_config",
            sa.JSON(),
            nullable=False,
            comment="Array of column mapping objects: [{column_index, header, tag, confidence}]",
        ),
        sa.Column(
            "created_by",
            sa.String(100),
            nullable=False,
            comment="User who created or last updated this template",
        ),
        sa.Column(
            "last_used_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Timestamp of last time this template was applied to an upload",
        ),
        sa.Column("created_date", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("modified_by", sa.String(255), nullable=False, server_default="system"),
        sa.Column("modified_date", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
    )

    # Create index on vendor_id for fast lookups
    op.create_index(
        "ix_vlr_column_mapping_templates_vendor_id",
        "vlr_column_mapping_templates",
        ["vendor_id"],
    )


def downgrade() -> None:
    # Drop index
    op.drop_index(
        "ix_vlr_column_mapping_templates_vendor_id",
        table_name="vlr_column_mapping_templates",
    )

    # Drop table
    op.drop_table("vlr_column_mapping_templates")
