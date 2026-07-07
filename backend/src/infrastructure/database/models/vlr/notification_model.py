"""Notification model for tracking all system notifications."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.database.models.base_model import BaseModel


class NotificationModel(BaseModel):
    """
    Notification record for emails sent by the system.

    Tracks delivery status, retry count, and scheduled next retry for failed deliveries.
    """

    __tablename__ = "vlr_notifications"

    case_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("vlr_reconciliation_cases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    type: Mapped[str] = mapped_column(String(30), nullable=False)
    recipient_email: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    template_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    context_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    sent_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    next_retry_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships
    case = relationship("ReconciliationCaseModel", back_populates="notifications")

    __table_args__ = (
        Index("ix_vlr_notifications_type", "type"),
        Index("ix_vlr_notifications_status", "status"),
    )
