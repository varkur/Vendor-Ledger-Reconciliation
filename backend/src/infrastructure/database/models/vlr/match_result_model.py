"""Match result model produced by the reconciliation engine."""

from sqlalchemy import Boolean, ForeignKey, Index, Integer, Numeric, String
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.database.models.base_model import BaseModel


class MatchResultModel(BaseModel):
    """
    Result of a matching pass, linking company and vendor entries.

    Stores the pass number, confidence score, and the IDs of entries
    on both sides that participated in the match.
    """

    __tablename__ = "vlr_match_results"

    case_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("vlr_reconciliation_cases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    pass_number: Mapped[int] = mapped_column(Integer, nullable=False)
    match_type: Mapped[str] = mapped_column(String(30), nullable=False)
    confidence_score: Mapped[float] = mapped_column(Numeric(5, 4), nullable=False)
    is_confirmed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    company_entry_ids: Mapped[list | None] = mapped_column(JSON, nullable=True)
    vendor_entry_ids: Mapped[list | None] = mapped_column(JSON, nullable=True)
    matched_amount: Mapped[float] = mapped_column(Numeric(15, 2), nullable=False)
    difference_amount: Mapped[float | None] = mapped_column(Numeric(15, 2), nullable=True)

    # Relationships
    case = relationship("ReconciliationCaseModel", back_populates="match_results")

    __table_args__ = (
        Index("ix_vlr_match_results_pass_number", "pass_number"),
    )
