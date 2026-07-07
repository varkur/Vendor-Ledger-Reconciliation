"""Approval record model for case approval workflow."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.database.models.base_model import BaseModel


class ApprovalRecordModel(BaseModel):
    """
    Record of an approval decision (approve, reject, request_changes).

    Tracks the approver, decision timestamp, and comments.
    """

    __tablename__ = "vlr_approval_records"

    case_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("vlr_reconciliation_cases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    decision: Mapped[str] = mapped_column(String(30), nullable=False)
    comments: Mapped[str | None] = mapped_column(Text, nullable=True)
    approver_id: Mapped[str] = mapped_column(UUID(as_uuid=True), nullable=False)
    approval_level: Mapped[str] = mapped_column(String(30), nullable=False, default="manager")
    decision_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    # Relationships
    case = relationship("ReconciliationCaseModel", back_populates="approval_records")
