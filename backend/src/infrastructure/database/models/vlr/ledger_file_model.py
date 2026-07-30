"""Stores the ORIGINAL uploaded ledger file bytes, verbatim.

The reconciliation engine parses/normalises ledger data into
`vlr_ledger_entries`, but the user must be able to download the exact file
they uploaded (same format, same data — no transformation). This table keeps
the raw bytes per case + side so downloads are byte-for-byte identical.
"""

from sqlalchemy import ForeignKey, Index, LargeBinary, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.database.models.base_model import BaseModel


class LedgerFileModel(BaseModel):
    """Original uploaded ledger file (raw bytes) for a case + side."""

    __tablename__ = "vlr_ledger_files"

    case_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("vlr_reconciliation_cases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    side: Mapped[str] = mapped_column(String(10), nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(
        String(150), nullable=False, default="application/octet-stream"
    )
    content: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)

    __table_args__ = (
        # One stored original per case + side (re-upload replaces it).
        UniqueConstraint("case_id", "side", name="uq_vlr_ledger_file_case_side"),
        Index("ix_vlr_ledger_files_case_id", "case_id"),
    )
