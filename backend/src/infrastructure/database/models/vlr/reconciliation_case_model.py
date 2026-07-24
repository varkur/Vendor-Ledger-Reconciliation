"""Reconciliation case model with status state machine and soft-delete."""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
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

    # Workflow tracking columns
    current_workflow_step: Mapped[str | None] = mapped_column(
        String(30),
        nullable=True,
        comment="Current step in the 10-step workflow",
    )
    step_entered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Timestamp when the current workflow step was entered",
    )
    sla_deadline: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="SLA deadline for the current workflow step",
    )
    is_overdue: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment="Whether the current step has exceeded its SLA deadline",
    )

    # Balance tracking columns
    company_opening_balance: Mapped[Decimal | None] = mapped_column(
        Numeric(15, 2), nullable=True, comment="Company-side opening balance"
    )
    company_closing_balance: Mapped[Decimal | None] = mapped_column(
        Numeric(15, 2), nullable=True, comment="Company-side closing balance"
    )
    vendor_opening_balance: Mapped[Decimal | None] = mapped_column(
        Numeric(15, 2), nullable=True, comment="Vendor-side opening balance"
    )
    vendor_closing_balance: Mapped[Decimal | None] = mapped_column(
        Numeric(15, 2), nullable=True, comment="Vendor-side closing balance"
    )
    net_difference: Mapped[Decimal | None] = mapped_column(
        Numeric(15, 2), nullable=True, comment="Net difference between company and vendor"
    )

    # Closure columns
    closure_type: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
        comment="Closure type: 'normal' or 'one_sided'",
    )
    closure_justification: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Justification text for one-sided closure",
    )
    closure_approved_by: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="Recon_Manager who approved one-sided closure",
    )

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
    workflow_step_history = relationship(
        "WorkflowStepHistoryModel", back_populates="case", lazy="noload"
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('created', 'ledger_confirmed', 'invited', 'data_received', "
            "'matching', 'matched', 'review', 'pending_approval', 'approved', "
            "'signed_off', 'closed', "
            "'mapping_pending', 'statement_mapped', 'in_progress', 'auto_completed', "
            "'review_pending', 'reviewed', 'signoff_requested', 'signoff_completed', "
            "'reco_rejected')",
            name="ck_vlr_case_valid_status",
        ),
        CheckConstraint(
            "case_type IN ('batch', 'direct')",
            name="ck_vlr_case_valid_type",
        ),
        Index("ix_vlr_cases_status", "status"),
        Index("ix_vlr_cases_created_date", "created_date"),
        Index("ix_vlr_cases_workflow_step", "current_workflow_step"),
        Index("ix_vlr_cases_is_overdue", "is_overdue"),
    )
