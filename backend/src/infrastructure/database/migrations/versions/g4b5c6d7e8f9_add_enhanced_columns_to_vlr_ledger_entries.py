"""Add enhanced columns to vlr_ledger_entries for data transformation output.

Adds columns: raw_reference, derived_invoice_number, invoice_source_field,
original_amount, shkzg_indicator, adjusted_amount, transaction_currency,
local_currency_amount, document_category, is_tds, tds_parent_entry_id.

Revision ID: g4b5c6d7e8f9
Revises: f3a4b5c6d7e8
Create Date: 2026-07-15

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


# revision identifiers, used by Alembic.
revision: str = "g4b5c6d7e8f9"
down_revision: Union[str, None] = "f3a4b5c6d7e8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add data transformation output columns to vlr_ledger_entries
    op.add_column(
        "vlr_ledger_entries",
        sa.Column("raw_reference", sa.String(255), nullable=True, comment="Original source value before CLEAN"),
    )
    op.add_column(
        "vlr_ledger_entries",
        sa.Column("derived_invoice_number", sa.String(255), nullable=True, comment="After CLEAN function"),
    )
    op.add_column(
        "vlr_ledger_entries",
        sa.Column("invoice_source_field", sa.String(10), nullable=True, comment="ZUONR, XBLNR, or BELNR"),
    )
    op.add_column(
        "vlr_ledger_entries",
        sa.Column("original_amount", sa.Numeric(15, 2), nullable=True, comment="Unsigned amount before sign adjustment"),
    )
    op.add_column(
        "vlr_ledger_entries",
        sa.Column("shkzg_indicator", sa.String(1), nullable=True, comment="H or S"),
    )
    op.add_column(
        "vlr_ledger_entries",
        sa.Column("adjusted_amount", sa.Numeric(15, 2), nullable=True, comment="Signed amount after SHKZG adjustment"),
    )
    op.add_column(
        "vlr_ledger_entries",
        sa.Column("transaction_currency", sa.String(10), nullable=True, comment="Original transaction currency code"),
    )
    op.add_column(
        "vlr_ledger_entries",
        sa.Column("local_currency_amount", sa.Numeric(15, 2), nullable=True, comment="INR equivalent amount"),
    )
    op.add_column(
        "vlr_ledger_entries",
        sa.Column("document_category", sa.String(30), nullable=True, comment="Invoice, Payment, Credit Note, etc."),
    )
    op.add_column(
        "vlr_ledger_entries",
        sa.Column("is_tds", sa.Boolean(), nullable=False, server_default="false", comment="TDS tag"),
    )
    op.add_column(
        "vlr_ledger_entries",
        sa.Column("tds_parent_entry_id", UUID(as_uuid=True), nullable=True, comment="Link to parent invoice entry"),
    )

    # Add indexes for commonly queried new columns
    op.create_index(
        "ix_vlr_ledger_entries_derived_invoice",
        "vlr_ledger_entries",
        ["derived_invoice_number"],
    )
    op.create_index(
        "ix_vlr_ledger_entries_is_tds",
        "vlr_ledger_entries",
        ["is_tds"],
    )


def downgrade() -> None:
    # Drop indexes first
    op.drop_index("ix_vlr_ledger_entries_is_tds", table_name="vlr_ledger_entries")
    op.drop_index("ix_vlr_ledger_entries_derived_invoice", table_name="vlr_ledger_entries")

    # Drop columns in reverse order
    op.drop_column("vlr_ledger_entries", "tds_parent_entry_id")
    op.drop_column("vlr_ledger_entries", "is_tds")
    op.drop_column("vlr_ledger_entries", "document_category")
    op.drop_column("vlr_ledger_entries", "local_currency_amount")
    op.drop_column("vlr_ledger_entries", "transaction_currency")
    op.drop_column("vlr_ledger_entries", "adjusted_amount")
    op.drop_column("vlr_ledger_entries", "shkzg_indicator")
    op.drop_column("vlr_ledger_entries", "original_amount")
    op.drop_column("vlr_ledger_entries", "invoice_source_field")
    op.drop_column("vlr_ledger_entries", "derived_invoice_number")
    op.drop_column("vlr_ledger_entries", "raw_reference")
