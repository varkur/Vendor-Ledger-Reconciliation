"""Ledger entry model for both company and vendor sides."""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.database.models.base_model import BaseModel


class LedgerEntryModel(BaseModel):
    """
    Individual financial ledger entry (company or vendor side).

    Stores match metadata (match_id, pass_number, confidence_score) when
    the entry is matched by the reconciliation engine.
    """

    __tablename__ = "vlr_ledger_entries"

    case_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("vlr_reconciliation_cases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    side: Mapped[str] = mapped_column(String(10), nullable=False)
    document_number: Mapped[str] = mapped_column(String(50), nullable=False)
    document_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    reference_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    posting_date: Mapped[date] = mapped_column(Date, nullable=False)
    clearing_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    clearing_document: Mapped[str | None] = mapped_column(String(50), nullable=True)
    amount: Mapped[float] = mapped_column(Numeric(15, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(10), nullable=False, default="INR")
    assignment_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Match metadata (populated by reconciliation engine)
    match_id: Mapped[str | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    pass_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    confidence_score: Mapped[float | None] = mapped_column(Numeric(5, 4), nullable=True)

    # Source tracking
    source: Mapped[str] = mapped_column(String(20), nullable=False, default="manual")

    # Data transformation output columns
    raw_reference: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="Original source value before CLEAN"
    )
    derived_invoice_number: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="After CLEAN function"
    )
    invoice_source_field: Mapped[str | None] = mapped_column(
        String(10), nullable=True, comment="ZUONR, XBLNR, or BELNR"
    )
    original_amount: Mapped[Decimal | None] = mapped_column(
        Numeric(15, 2), nullable=True, comment="Unsigned amount before sign adjustment"
    )
    shkzg_indicator: Mapped[str | None] = mapped_column(
        String(1), nullable=True, comment="H or S"
    )
    adjusted_amount: Mapped[Decimal | None] = mapped_column(
        Numeric(15, 2), nullable=True, comment="Signed amount after SHKZG adjustment"
    )
    transaction_currency: Mapped[str | None] = mapped_column(
        String(10), nullable=True, comment="Original transaction currency code"
    )
    local_currency_amount: Mapped[Decimal | None] = mapped_column(
        Numeric(15, 2), nullable=True, comment="INR equivalent amount"
    )
    document_category: Mapped[str | None] = mapped_column(
        String(30), nullable=True, comment="Invoice, Payment, Credit Note, etc."
    )
    is_tds: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false", comment="TDS tag"
    )
    tds_parent_entry_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=True), nullable=True, comment="Link to parent invoice entry"
    )

    # Full original uploaded row (header -> value), so the formatted export can
    # reproduce every column the user provided (SAP fields not otherwise modelled).
    raw_data: Mapped[dict | None] = mapped_column(
        JSON, nullable=True, comment="Original uploaded row, keyed by source header"
    )

    # Relationships
    case = relationship("ReconciliationCaseModel", back_populates="ledger_entries")

    __table_args__ = (
        Index("ix_vlr_ledger_entries_side", "side"),
        Index("ix_vlr_ledger_entries_match_id", "match_id"),
        Index("ix_vlr_ledger_entries_document_number", "document_number"),
        Index("ix_vlr_ledger_entries_derived_invoice", "derived_invoice_number"),
        Index("ix_vlr_ledger_entries_is_tds", "is_tds"),
    )
