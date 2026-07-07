"""Reconciliation exception model for unmatched entries."""

from datetime import date

from sqlalchemy import CheckConstraint, Date, ForeignKey, Index, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.database.models.base_model import BaseModel


class RecoExceptionModel(BaseModel):
    """
    Exception record for an unmatched ledger entry.

    Categorized by severity (critical, high, medium, low) based on
    amount and age thresholds.
    """

    __tablename__ = "vlr_reco_exceptions"

    case_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("vlr_reconciliation_cases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    ledger_entry_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("vlr_ledger_entries.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    amount: Mapped[float] = mapped_column(Numeric(15, 2), nullable=False)
    first_flagged_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="open")

    # Relationships
    case = relationship("ReconciliationCaseModel", back_populates="exceptions")
    resolutions = relationship("ResolutionRecordModel", back_populates="exception", lazy="selectin")

    __table_args__ = (
        CheckConstraint(
            "severity IN ('critical', 'high', 'medium', 'low')",
            name="ck_vlr_exception_valid_severity",
        ),
        Index("ix_vlr_exceptions_severity", "severity"),
        Index("ix_vlr_exceptions_status", "status"),
    )
