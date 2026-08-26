"""Reconciliation request model with status state machine constraints."""

from datetime import date, datetime

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    Index,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.database.models.base_model import BaseModel


class ReconciliationRequestModel(BaseModel):
    """
    A batch reconciliation request grouping multiple vendor cases.

    Status transitions are enforced at the database level via CHECK constraint:
    draft -> active -> in_progress -> review -> sign_off -> closed
    (with review -> in_progress for change requests)
    """

    __tablename__ = "vlr_reconciliation_requests"

    company_code: Mapped[str] = mapped_column(String(20), nullable=False)
    fiscal_year: Mapped[str] = mapped_column(String(10), nullable=False)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    # Reconciliation type: 'bulk' (request-statement flow) or 'direct'
    # (single-vendor dual-upload). Track Reconciliation shows both; Direct
    # Reconciliation shows only 'direct'.
    reco_type: Mapped[str] = mapped_column(
        String(10), nullable=False, default="bulk", server_default="bulk", index=True
    )
    # Human-friendly request identifier: "{company_code}-{5-digit serial}"
    # e.g. EPL-00094. Generated on create, unique per company code.
    request_number: Mapped[str | None] = mapped_column(String(30), nullable=True, index=True)
    # User-provided title/name for the request (shown in Track Reconciliation).
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # When vendor invites were sent (null = "Not Sent").
    sent_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    tolerance_amount: Mapped[float | None] = mapped_column(Numeric(15, 2), nullable=True)
    # tds_percentage is kept as the MAX of the configured TDS range for
    # backward compatibility (existing rows / callers treat it as a single
    # rate). tds_percentage_min is the range's lower bound — the engine now
    # tries every rate between min and max (see mapping doc: TDS gaps are
    # checked against 0.1%, 2%, 10% tiers, not one fixed rate).
    tds_percentage: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    tds_percentage_min: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    gst_percentage: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    # Date-tolerance range (in days) for date-proximity/date-range matching
    # passes. Previously hardcoded to a flat 15 days in case_controller.py,
    # ignoring whatever the user configured on the Reconciliation Settings
    # screen entirely.
    date_tolerance_days_min: Mapped[int | None] = mapped_column(nullable=True)
    date_tolerance_days_max: Mapped[int | None] = mapped_column(nullable=True)
    matching_preferences: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    assigned_manager_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )

    # Relationships
    cases = relationship("ReconciliationCaseModel", back_populates="request", lazy="noload")

    __table_args__ = (
        CheckConstraint(
            "status IN ('draft', 'active', 'in_progress', 'review', 'sign_off', 'closed')",
            name="ck_vlr_request_valid_status",
        ),
        Index("ix_vlr_requests_status", "status"),
        Index("ix_vlr_requests_company_code", "company_code"),
        Index("ix_vlr_requests_created_date", "created_date"),
    )
