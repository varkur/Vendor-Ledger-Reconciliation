"""Recovery item model for tracking amounts recoverable from vendors."""

from datetime import date
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.database.models.base_model import BaseModel


class RecoveryItemModel(BaseModel):
    """
    Tracks individual recovery items identified during reconciliation.

    Status transitions: open → in_progress → recovered | written_off
    Each item is linked to a case and vendor, with configurable follow-up intervals.
    """

    __tablename__ = "vlr_recovery_items"

    case_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("vlr_reconciliation_cases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    vendor_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("vlr_vendors.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    amount: Mapped[Decimal] = mapped_column(
        Numeric(15, 2),
        nullable=False,
        comment="Recoverable amount",
    )
    currency: Mapped[str] = mapped_column(
        String(3),
        nullable=False,
        default="INR",
        comment="Currency code (default INR)",
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="open",
        comment="Recovery status: open, in_progress, recovered, written_off",
    )
    identified_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
        comment="Date the recovery item was identified",
    )
    next_follow_up_date: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
        comment="Next scheduled follow-up date",
    )
    follow_up_interval_days: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=7,
        comment="Days between follow-up reminders",
    )
    notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Additional notes about the recovery item",
    )

    # Relationships
    case = relationship("ReconciliationCaseModel", backref="recovery_items", lazy="noload")
    vendor = relationship("VendorModel", backref="recovery_items", lazy="noload")
    follow_ups = relationship(
        "RecoveryFollowUpModel",
        back_populates="recovery_item",
        lazy="noload",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('open', 'in_progress', 'recovered', 'written_off')",
            name="ck_vlr_recovery_item_valid_status",
        ),
        Index("ix_vlr_recovery_items_status", "status"),
        Index("ix_vlr_recovery_items_next_follow_up", "next_follow_up_date"),
    )
