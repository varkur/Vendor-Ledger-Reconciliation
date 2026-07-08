"""Portal sign-off model for vendor digital sign-off recording."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.database.models.base_model import BaseModel


class PortalSignOffModel(BaseModel):
    """
    Record of a vendor's digital sign-off on the reconciliation statement.

    Captures IP address, statement version, confirmation text, and timestamp
    for audit purposes.
    """

    __tablename__ = "vlr_portal_sign_offs"

    case_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("vlr_reconciliation_cases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    ip_address: Mapped[str] = mapped_column(String(45), nullable=False)
    statement_version: Mapped[str] = mapped_column(String(50), nullable=False)
    confirmation_text: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="Vendor confirmation/approval text"
    )
    signed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    # Relationships
    case = relationship("ReconciliationCaseModel", back_populates="portal_sign_offs")
