"""add vlr_ledger_upload_staging table for consolidated multi-vendor uploads

Revision ID: s6h7c8d9e0f1
Revises: r5g6b7c8d9e0
Create Date: 2026-08-12

Staging area for a consolidated (multi-vendor, PAN-per-row) company ledger
uploaded BEFORE any request/cases are created. The upload is parsed and
matched against the vendor master first; only once the user confirms
(optionally after fixing missing vendors in the master) do we actually
create the ReconciliationRequest + one case per matched vendor.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSON, UUID

# revision identifiers, used by Alembic.
revision: str = "s6h7c8d9e0f1"
down_revision: Union[str, None] = "r5g6b7c8d9e0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "vlr_ledger_upload_staging",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("company_code", sa.String(length=20), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=150), nullable=False,
                  server_default="application/octet-stream"),
        sa.Column("content", sa.LargeBinary(), nullable=False),
        sa.Column("request_params", JSON, nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(length=255), nullable=False, server_default="system"),
        sa.Column("created_date", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("modified_by", sa.String(length=255), nullable=False, server_default="system"),
        sa.Column("modified_date", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )
    op.create_index(
        "ix_vlr_ledger_upload_staging_company_code",
        "vlr_ledger_upload_staging",
        ["company_code"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_vlr_ledger_upload_staging_company_code",
        table_name="vlr_ledger_upload_staging",
    )
    op.drop_table("vlr_ledger_upload_staging")
