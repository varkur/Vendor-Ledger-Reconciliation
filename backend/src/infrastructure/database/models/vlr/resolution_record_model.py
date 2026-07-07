"""Resolution record model for exception resolutions."""

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.database.models.base_model import BaseModel


class ResolutionRecordModel(BaseModel):
    """
    Record of a resolution action applied to an exception.

    Tracks the action taken, who took it, and any associated comments.
    """

    __tablename__ = "vlr_resolution_records"

    exception_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("vlr_reco_exceptions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    comments: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolved_by: Mapped[str] = mapped_column(UUID(as_uuid=True), nullable=False)
    resolved_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    # Relationships
    exception = relationship("RecoExceptionModel", back_populates="resolutions")

    __table_args__ = (
        CheckConstraint(
            "action IN ('accept_company_match', 'request_document_vendor', "
            "'mark_tds_difference', 'mark_agreed_adjustment', 'write_off', 'escalate')",
            name="ck_vlr_resolution_valid_action",
        ),
    )
