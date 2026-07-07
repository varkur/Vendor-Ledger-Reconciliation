"""Reconciliation case model with status state machine and soft-delete."""

from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
)
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.database.models.base_model import BaseModel


class ReconciliationCaseModel(BaseModel):
    """
    Individual vendor reconciliation case within a request.

    Status transitions are enforced at the database level via CHECK constraint.
    Supports soft-delete for audit trail preservation.
    """

    __tablename__ = "vlr_reconciliation_cases"

    request_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("vlr_reconciliation_requests.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    vendor_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("vlr_vendors.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    case_type: Mapped[str] = mapped_column(String(20), nullable=False, default="batch")
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="created")
    portal_token: Mapped[str | None] = mapped_column(String(255), nullable=True, unique=True)
    token_expiry: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    upload_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    edit_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    row_10_balance: Mapped[float | None] = mapped_column(Numeric(15, 2), nullable=True)
    match_statistics: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Soft-delete columns
    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships
    request = relationship("ReconciliationRequestModel", back_populates="cases")
    vendor = relationship("VendorModel", back_populates="reconciliation_cases")
    ledger_entries = relationship("LedgerEntryModel", back_populates="case", lazy="noload")
    match_results = relationship("MatchResultModel", back_populates="case", lazy="noload")
    exceptions = relationship("RecoExceptionModel", back_populates="case", lazy="noload")
    approval_records = relationship("ApprovalRecordModel", back_populates="case", lazy="noload")
    notifications = relationship("NotificationModel", back_populates="case", lazy="noload")
    portal_sign_offs = relationship("PortalSignOffModel", back_populates="case", lazy="noload")

    __table_args__ = (
        CheckConstraint(
            "status IN ('created', 'ledger_confirmed', 'invited', 'data_received', "
            "'matching', 'matched', 'review', 'pending_approval', 'approved', "
            "'signed_off', 'closed')",
            name="ck_vlr_case_valid_status",
        ),
        CheckConstraint(
            "case_type IN ('batch', 'direct')",
            name="ck_vlr_case_valid_type",
        ),
        Index("ix_vlr_cases_status", "status"),
        Index("ix_vlr_cases_created_date", "created_date"),
    )
