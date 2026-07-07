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
    tolerance_amount: Mapped[float | None] = mapped_column(Numeric(15, 2), nullable=True)
    tds_percentage: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    gst_percentage: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
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
