"""relax vlr_reconciliation_cases status check constraint

Revision ID: m0b1c2d3e4f5
Revises: l9a0b1c2d3e4
Create Date: 2026-07-22

Widens ck_vlr_case_valid_status to include the workflow statuses used by the
application (mapping_pending, statement_mapped, in_progress, auto_completed,
review_pending, reviewed, signoff_requested, signoff_completed, reco_rejected).
Older schemas only allowed the legacy status set, which caused 500 errors when
the app set a newer status (e.g. on reupload / start-reconciliation / review).
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "m0b1c2d3e4f5"
down_revision: Union[str, None] = "l9a0b1c2d3e4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_ALL_STATUSES = (
    "'created','ledger_confirmed','invited','data_received','matching','matched',"
    "'review','pending_approval','approved','signed_off','closed',"
    "'mapping_pending','statement_mapped','in_progress','auto_completed',"
    "'review_pending','reviewed','signoff_requested','signoff_completed','reco_rejected'"
)

_LEGACY_STATUSES = (
    "'created','ledger_confirmed','invited','data_received','matching','matched',"
    "'review','pending_approval','approved','signed_off','closed'"
)


def upgrade() -> None:
    op.execute(
        "ALTER TABLE vlr_reconciliation_cases "
        "DROP CONSTRAINT IF EXISTS ck_vlr_case_valid_status"
    )
    op.execute(
        f"ALTER TABLE vlr_reconciliation_cases ADD CONSTRAINT ck_vlr_case_valid_status "
        f"CHECK (status IN ({_ALL_STATUSES}))"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE vlr_reconciliation_cases "
        "DROP CONSTRAINT IF EXISTS ck_vlr_case_valid_status"
    )
    op.execute(
        f"ALTER TABLE vlr_reconciliation_cases ADD CONSTRAINT ck_vlr_case_valid_status "
        f"CHECK (status IN ({_LEGACY_STATUSES}))"
    )
