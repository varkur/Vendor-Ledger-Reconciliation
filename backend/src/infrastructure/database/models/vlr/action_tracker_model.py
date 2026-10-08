"""
Action Tracker workflow model.

The Action Tracker tab shows, per reconciliation request, every unmatched /
residual-difference row produced by ReconciliationExportService's row-building
logic (status, classification, both-side invoice detail — all computed live
from ledger entries + match results, never persisted). This model stores only
the small set of fields a human actually types into that grid: who owns the
action, what reference/remark they recorded, and whether the row is closed.

Rows are keyed by `row_key`, a stable identity derived from the case and the
one or two ledger entry ids the row represents (see
ActionTrackerService._row_key), so a workflow note survives being
re-generated on every read without needing to persist the diagnosis itself.
"""

from sqlalchemy import Boolean, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.database.models.base_model import BaseModel


class ActionTrackerModel(BaseModel):
    """Human-entered workflow state for a single Action Tracker row."""

    __tablename__ = "vlr_action_tracker_entries"

    request_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("vlr_reconciliation_requests.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    case_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("vlr_reconciliation_cases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    row_key: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
        index=True,
        comment="Stable identity: case_id + company/party ledger entry ids",
    )
    action_owner: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="Assigned user/email; null = Unassigned"
    )
    action_taken_reference: Mapped[str | None] = mapped_column(String(100), nullable=True)
    action_taken_remark: Mapped[str | None] = mapped_column(Text, nullable=True)
    request_closed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    __table_args__ = (
        UniqueConstraint("case_id", "row_key", name="uq_vlr_action_tracker_case_row"),
    )
