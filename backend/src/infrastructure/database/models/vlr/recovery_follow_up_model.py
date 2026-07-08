"""Recovery follow-up model for tracking actions taken on recovery items."""

from datetime import date, datetime

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.database.models.base_model import BaseModel


class RecoveryFollowUpModel(BaseModel):
    """
    Records follow-up actions taken for a recovery item.

    Each entry logs who took what action, when, and optionally
    schedules the next follow-up date.
    """

    __tablename__ = "vlr_recovery_follow_ups"

    recovery_item_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("vlr_recovery_items.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    action_taken: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Description of the follow-up action taken",
    )
    action_by: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="User who performed the follow-up action",
    )
    action_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="Timestamp when the action was performed",
    )
    next_follow_up_date: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
        comment="Scheduled date for the next follow-up",
    )

    # Relationships
    recovery_item = relationship("RecoveryItemModel", back_populates="follow_ups")

    __table_args__ = (
        Index("ix_vlr_recovery_follow_ups_item_date", "recovery_item_id", "action_date"),
    )
