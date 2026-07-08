"""Create vlr_document_type_mappings table for configurable document type classification.

Allows administrators to configure document type to category mappings
without code changes. Seeded with default mappings per BRD.

Revision ID: h5c6d7e8f9a0
Revises: g4b5c6d7e8f9
Create Date: 2026-07-15

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


# revision identifiers, used by Alembic.
revision: str = "h5c6d7e8f9a0"
down_revision: Union[str, None] = "g4b5c6d7e8f9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create the vlr_document_type_mappings table
    op.create_table(
        "vlr_document_type_mappings",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("document_type_code", sa.String(10), unique=True, nullable=False,
                  comment="SAP document type code (e.g., RE, KR, DR, ZP, KZ, ZV, KG, RV)"),
        sa.Column("category", sa.String(30), nullable=False,
                  comment="Classification category: Invoice, Payment, Credit Note, Debit Note, TDS, Other"),
        sa.Column("is_tds", sa.Boolean(), nullable=False, server_default="false",
                  comment="Whether this document type is a TDS entry"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true",
                  comment="Whether this mapping is active (allows soft-delete)"),
        sa.Column("created_by", sa.String(255), nullable=False, server_default="system"),
        sa.Column("created_date", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("modified_by", sa.String(255), nullable=False, server_default="system"),
        sa.Column("modified_date", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
    )

    # Create indexes
    op.create_index("ix_vlr_doc_type_mappings_code", "vlr_document_type_mappings", ["document_type_code"])
    op.create_index("ix_vlr_doc_type_mappings_category", "vlr_document_type_mappings", ["category"])
    op.create_index("ix_vlr_doc_type_mappings_active", "vlr_document_type_mappings", ["is_active"])

    # Seed default mappings per BRD
    op.execute("""
        INSERT INTO vlr_document_type_mappings (id, document_type_code, category, is_tds, is_active, created_by, modified_by)
        VALUES
            (gen_random_uuid(), 'RE', 'Invoice', false, true, 'system', 'system'),
            (gen_random_uuid(), 'KR', 'Invoice', false, true, 'system', 'system'),
            (gen_random_uuid(), 'DR', 'Invoice', false, true, 'system', 'system'),
            (gen_random_uuid(), 'ZP', 'Payment', false, true, 'system', 'system'),
            (gen_random_uuid(), 'KZ', 'Payment', false, true, 'system', 'system'),
            (gen_random_uuid(), 'ZV', 'Payment', false, true, 'system', 'system'),
            (gen_random_uuid(), 'KG', 'Credit Note', false, true, 'system', 'system'),
            (gen_random_uuid(), 'RV', 'Debit Note', false, true, 'system', 'system');
    """)


def downgrade() -> None:
    # Drop indexes
    op.drop_index("ix_vlr_doc_type_mappings_active", table_name="vlr_document_type_mappings")
    op.drop_index("ix_vlr_doc_type_mappings_category", table_name="vlr_document_type_mappings")
    op.drop_index("ix_vlr_doc_type_mappings_code", table_name="vlr_document_type_mappings")

    # Drop table
    op.drop_table("vlr_document_type_mappings")
