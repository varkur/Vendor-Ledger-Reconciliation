"""
Action Tracker Pydantic schemas (request/response).

Requirements: Action Tracker tab — per-request work queue of unmatched /
residual-difference ledger rows, grouped by Action Taken Status.
"""

from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field


# ──────────────────────────────────────────────────────────────────────
# Response Schemas
# ──────────────────────────────────────────────────────────────────────


class ActionTrackerSummaryRowResponse(BaseModel):
    """One row of the Action Tracker Summary screen."""

    action_taken_status: str
    number_of_records: int
    percentage: float
    amount: Decimal


class ActionTrackerSummaryResponse(BaseModel):
    """Full Action Tracker Summary response, including the Total row."""

    request_id: UUID
    rows: list[ActionTrackerSummaryRowResponse] = Field(default_factory=list)
    total_records: int = 0
    total_amount: Decimal = Decimal("0")


class ActionTrackerItemResponse(BaseModel):
    """One detail row of the Action Tracker grid."""

    row_key: str
    case_id: UUID
    vendor_code: str
    vendor_name: str
    company_id: str = ""
    party_id: str = ""
    match_id: str = ""
    status: str
    classification: str
    action_taken_status: str
    action_owner: str = "Unassigned"
    # Nullable-in-practice fields (narration/invoice detail only exist on
    # whichever side of the row is present) — accept None defensively even
    # though the service layer normalizes to "" before this schema is built,
    # so an unmatched entry never 500s on a missing narration/invoice value.
    company_invoice_date: str | None = ""
    company_invoice_number: str | None = ""
    company_doctype: str | None = ""
    company_original_doctype: str | None = ""
    company_narration: str | None = ""
    company_amount: str | None = ""
    party_invoice_date: str | None = ""
    party_invoice_number: str | None = ""
    party_doctype: str | None = ""
    party_original_doctype: str | None = ""
    party_narration: str | None = ""
    party_amount: str | None = ""
    difference: Decimal = Decimal("0")
    remarks: str | None = ""
    request_closed: bool = False
    action_taken_reference: str | None = ""
    action_taken_remark: str | None = ""
    reco_datetime: str | None = ""
    posting_date: str | None = ""
    clearing_date: str | None = ""
    clearing_document_number: str | None = ""
    tds_amount: str | None = ""


class ActionTrackerItemListResponse(BaseModel):
    """Paginated Action Tracker detail list."""

    items: list[ActionTrackerItemResponse]
    total: int = 0
    page: int = 1
    page_size: int = 50
    total_pages: int = 0


# ──────────────────────────────────────────────────────────────────────
# Request Schemas
# ──────────────────────────────────────────────────────────────────────


class UpdateActionTakenRequest(BaseModel):
    """Request body for updating one Action Tracker row's workflow fields."""

    case_id: UUID
    row_key: str
    action_owner: str | None = Field(default=None, max_length=100)
    action_taken_reference: str | None = Field(default=None, max_length=100)
    action_taken_remark: str | None = Field(default=None, max_length=2000)
    request_closed: bool | None = None


class BulkUpdateActionTakenRequest(BaseModel):
    """Request body for applying the same workflow update to multiple rows."""

    items: list[UpdateActionTakenRequest] = Field(..., min_length=1, max_length=500)


class BulkUpdateActionTakenResponse(BaseModel):
    """Response for a bulk workflow update."""

    updated: int
