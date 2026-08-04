"""
Request/Response schemas for the Reconciliation Output API endpoints.

Covers the 5-tab reconciliation output view:
- Tab 1: Matched Items
- Tab 2: Finance Confirmation Required
- Tab 3: Unmatched Company Ledger
- Tab 4: Unmatched Vendor Ledger
- Tab 5: Differences Summary

Plus the confirm/reject action endpoint.

Requirements: 18.1, 19.1, 20.1, 21.1, 22.1
"""

from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, Field


# ──────────────────────────────────────────────────────────────────────
# Enums
# ──────────────────────────────────────────────────────────────────────


class MatchType(str, Enum):
    """Types of matches produced by the reconciliation engine."""

    EXACT = "exact"
    TOLERANCE = "tolerance"
    FUZZY_REFERENCE = "fuzzy_reference"
    ONE_TO_MANY = "one_to_many"
    MANY_TO_ONE = "many_to_one"
    DATE_PROXIMITY = "date_proximity"


class ConfirmAction(str, Enum):
    """Actions that can be taken on a match in the confirmation tab."""

    ACCEPT = "accept"
    REJECT = "reject"
    CLARIFY = "clarify"


class SortOrder(str, Enum):
    """Sort direction."""

    ASC = "asc"
    DESC = "desc"


# ──────────────────────────────────────────────────────────────────────
# Common / Pagination
# ──────────────────────────────────────────────────────────────────────


class PaginationMeta(BaseModel):
    """Pagination metadata for list responses."""

    page: int = Field(..., description="Current page number (1-based)")
    page_size: int = Field(..., description="Items per page")
    total_items: int = Field(..., description="Total items matching the query")
    total_pages: int = Field(..., description="Total number of pages")


class EntryColumns(BaseModel):
    """
    Full ledger-entry column set (matches the Excel export). Derived from the
    original uploaded row (raw_data) with modelled fields as fallback, via
    domain.services.vlr.entry_columns.build_entry_columns.
    """

    statement_type: str = ""
    invoice_date: str = ""
    invoice_number: str = ""
    doctype: str = ""
    original_doctype: str = ""
    narration: str = ""
    amount: float = 0.0
    daybook_name: str = ""
    clearing_document_number: str = ""
    clearing_date: str = ""
    tds_amount: str = ""
    posting_date: str = ""
    company_code: str = ""
    supplier: str = ""
    document_number: str = ""
    business_area: str = ""
    assignment: str = ""
    document_header_text: str = ""
    tax_code: str = ""
    year_month: str = ""
    reference: str = ""
    profit_center: str = ""
    amount_in_doc_curr: float = 0.0
    document_currency: str = ""
    local_currency: str = ""
    entry_date: str = ""
    withhldg_tax_base_amount: str = ""
    payment_date: str = ""


# ──────────────────────────────────────────────────────────────────────
# Tab 1: Matched Items
# ──────────────────────────────────────────────────────────────────────


class MatchedEntryResponse(BaseModel):
    """A single matched entry pair/group in Tab 1."""

    match_id: UUID = Field(..., description="Unique match result ID")
    cl_reference: str | None = Field(None, description="Company ledger reference number")
    cl_amount: Decimal | None = Field(None, description="Company ledger amount")
    vl_reference: str | None = Field(None, description="Vendor ledger reference number")
    vl_amount: Decimal | None = Field(None, description="Vendor ledger amount")
    difference: Decimal | None = Field(None, description="Difference between CL and VL amounts")
    match_type: str = Field(..., description="Type of match (exact, tolerance, fuzzy, etc.)")
    match_score: float = Field(..., description="Confidence score of the match [0.0, 1.0]")
    pass_number: int = Field(..., description="Pass number that produced the match")
    matched_amount: Decimal = Field(..., description="The matched amount")
    company_columns: EntryColumns | None = Field(None, description="Full company-side column set")
    party_columns: EntryColumns | None = Field(None, description="Full party-side column set")
    matched_rule: str | None = Field(None, description="Derived rule code for the match")

    model_config = {"from_attributes": True}


class MatchedItemsResponse(BaseModel):
    """Response for Tab 1: Matched Items listing."""

    items: list[MatchedEntryResponse] = Field(
        default_factory=list, description="List of matched entry pairs"
    )
    pagination: PaginationMeta = Field(..., description="Pagination metadata")


# ──────────────────────────────────────────────────────────────────────
# Tab 2: Finance Confirmation Required
# ──────────────────────────────────────────────────────────────────────


class ConfirmationEntryResponse(BaseModel):
    """A single entry awaiting finance confirmation in Tab 2."""

    match_id: UUID = Field(..., description="Unique match result ID")
    cl_reference: str | None = Field(None, description="Company ledger reference number")
    cl_amount: Decimal | None = Field(None, description="Company ledger amount")
    vl_reference: str | None = Field(None, description="Vendor ledger reference number")
    vl_amount: Decimal | None = Field(None, description="Vendor ledger amount")
    difference: Decimal | None = Field(None, description="Difference between CL and VL amounts")
    match_type: str = Field(..., description="Type of match")
    match_score: float = Field(..., description="Confidence score of the match")
    pass_number: int = Field(..., description="Pass number that produced the match")

    model_config = {"from_attributes": True}


class ConfirmationItemsResponse(BaseModel):
    """Response for Tab 2: Finance Confirmation Required listing."""

    items: list[ConfirmationEntryResponse] = Field(
        default_factory=list, description="List of entries awaiting confirmation"
    )
    pagination: PaginationMeta = Field(..., description="Pagination metadata")


# ──────────────────────────────────────────────────────────────────────
# Tab 3: Unmatched Company Ledger
# ──────────────────────────────────────────────────────────────────────


class UnmatchedCompanyEntryResponse(BaseModel):
    """A single unmatched company ledger entry in Tab 3."""

    entry_id: UUID = Field(..., description="Ledger entry ID")
    document_number: str = Field(..., description="Document number")
    document_type: str | None = Field(None, description="Document type code")
    document_category: str | None = Field(None, description="Document category (Invoice, Payment, etc.)")
    reference_number: str | None = Field(None, description="Reference number")
    posting_date: date = Field(..., description="Posting date")
    amount: Decimal = Field(..., description="Entry amount")
    currency: str = Field(..., description="Currency code")
    description: str | None = Field(None, description="Entry description")
    columns: EntryColumns | None = Field(None, description="Full column set (matches export)")

    model_config = {"from_attributes": True}


class UnmatchedCompanyResponse(BaseModel):
    """Response for Tab 3: Unmatched Company Ledger listing."""

    items: list[UnmatchedCompanyEntryResponse] = Field(
        default_factory=list, description="List of unmatched company entries"
    )
    pagination: PaginationMeta = Field(..., description="Pagination metadata")


# ──────────────────────────────────────────────────────────────────────
# Tab 4: Unmatched Vendor Ledger
# ──────────────────────────────────────────────────────────────────────


class UnmatchedVendorEntryResponse(BaseModel):
    """A single unmatched vendor ledger entry in Tab 4."""

    entry_id: UUID = Field(..., description="Ledger entry ID")
    document_number: str = Field(..., description="Document number")
    document_type: str | None = Field(None, description="Document type code")
    document_category: str | None = Field(None, description="Document category (Invoice, Payment, etc.)")
    reference_number: str | None = Field(None, description="Reference number")
    posting_date: date = Field(..., description="Posting date")
    amount: Decimal = Field(..., description="Entry amount")
    currency: str = Field(..., description="Currency code")
    description: str | None = Field(None, description="Entry description")
    columns: EntryColumns | None = Field(None, description="Full column set (matches export)")

    model_config = {"from_attributes": True}


class UnmatchedVendorResponse(BaseModel):
    """Response for Tab 4: Unmatched Vendor Ledger listing."""

    items: list[UnmatchedVendorEntryResponse] = Field(
        default_factory=list, description="List of unmatched vendor entries"
    )
    pagination: PaginationMeta = Field(..., description="Pagination metadata")


# ──────────────────────────────────────────────────────────────────────
# Tab 5: Differences Summary
# ──────────────────────────────────────────────────────────────────────


class BalanceComparison(BaseModel):
    """Opening or closing balance comparison between company and vendor."""

    company_balance: Decimal | None = Field(None, description="Company-side balance")
    vendor_balance: Decimal | None = Field(None, description="Vendor-side balance")
    difference: Decimal | None = Field(None, description="Difference (company - vendor)")


class TypeTotal(BaseModel):
    """Totals for a specific document/transaction type."""

    type_name: str = Field(..., description="Transaction type (Invoice, Payment, Credit Note, Debit Note)")
    company_total: Decimal = Field(..., description="Company-side total for this type")
    vendor_total: Decimal = Field(..., description="Vendor-side total for this type")
    difference: Decimal = Field(..., description="Difference (company - vendor)")


class DifferencesSummaryResponse(BaseModel):
    """Response for Tab 5: Differences Summary."""

    case_id: UUID = Field(..., description="Reconciliation case ID")
    opening_balance: BalanceComparison = Field(
        ..., description="Opening balance comparison"
    )
    closing_balance: BalanceComparison = Field(
        ..., description="Closing balance comparison"
    )
    totals_by_type: list[TypeTotal] = Field(
        default_factory=list, description="Totals grouped by transaction type"
    )
    net_difference: Decimal | None = Field(
        None, description="Net difference between company and vendor ledgers"
    )
    total_matched: int = Field(0, description="Total number of matched entries")
    total_unmatched_company: int = Field(0, description="Total unmatched company entries")
    total_unmatched_vendor: int = Field(0, description="Total unmatched vendor entries")
    total_pending_confirmation: int = Field(
        0, description="Total entries pending finance confirmation"
    )
    unmatched_company_amount: Decimal = Field(
        Decimal("0"), description="Sum of unmatched company entry amounts (excl. balances)"
    )
    unmatched_vendor_amount: Decimal = Field(
        Decimal("0"), description="Sum of unmatched vendor entry amounts (excl. balances)"
    )
    residual_difference: Decimal = Field(
        Decimal("0"), description="Net residual difference from unmatched items (company - vendor)"
    )

    model_config = {"from_attributes": True}


# ──────────────────────────────────────────────────────────────────────
# Confirm/Reject Action
# ──────────────────────────────────────────────────────────────────────


class ConfirmMatchRequest(BaseModel):
    """Request body for confirming or rejecting a match."""

    match_id: UUID = Field(..., description="ID of the match result to act on")
    action: ConfirmAction = Field(
        ..., description="Action to take: accept, reject, or clarify"
    )
    notes: str | None = Field(
        None, description="Optional notes/justification for the action"
    )


class ConfirmMatchResponse(BaseModel):
    """Response after confirming or rejecting a match."""

    match_id: UUID = Field(..., description="ID of the match result acted upon")
    action: ConfirmAction = Field(..., description="Action that was taken")
    success: bool = Field(..., description="Whether the action was successful")
    message: str = Field(..., description="Status message")

    model_config = {"from_attributes": True}


# ──────────────────────────────────────────────────────────────────────
# Reconciliation Analytics (Firmway-style summary view)
# ──────────────────────────────────────────────────────────────────────


class AnalyticsRow(BaseModel):
    """One row of the Reconciliation Analytics table."""

    particulars: str = Field(..., description="Row label (Matched, Unmatched, etc.)")
    company_numbers: int = Field(0, description="Count on the company side")
    company_percentage: float = Field(0.0, description="Company count as % of company total")
    party_numbers: int = Field(0, description="Count on the party side")
    party_percentage: float = Field(0.0, description="Party count as % of party total")
    # Drill-in key so the UI knows which tab/filter to open on "View".
    view_key: str = Field("", description="Identifier for the drill-in view")


class ReconciliationAnalyticsResponse(BaseModel):
    """Response for the Reconciliation Analytics summary table."""

    case_id: UUID
    party_code: str = ""
    party_name: str = ""
    party_type: str = "Vendor"
    reco_type: str = "Ledger"
    reco_status: str = ""
    period_start: date | None = None
    period_end: date | None = None
    updated_at: datetime | None = None
    rows: list[AnalyticsRow] = Field(default_factory=list)
    total_company_numbers: int = 0
    total_party_numbers: int = 0

    model_config = {"from_attributes": True}


# ──────────────────────────────────────────────────────────────────────
# Reconciliation Particulars (Firmway-style reconciliation statement)
# ──────────────────────────────────────────────────────────────────────


class ParticularsChild(BaseModel):
    """A child (leaf) row under a Particulars group."""

    label: str = Field(..., description="Row label, e.g. 'Invoice not booked by Company'")
    amount: Decimal = Field(Decimal("0"), description="Signed amount for this line")
    no_of_entries: int = Field(0, description="Number of ledger entries in this line")
    side: str = Field("", description="Which side the entries belong to (company/vendor)")
    document_category: str = Field("", description="Document category filter for drill-in")
    view_key: str = Field("", description="Drill-in identifier for the 'View' action")


class ParticularsGroup(BaseModel):
    """A parent group in the reconciliation statement (sum of its children)."""

    label: str = Field(..., description="Group label, e.g. 'Invoice Difference'")
    amount: Decimal = Field(Decimal("0"), description="Net signed amount of the group")
    no_of_entries: int = Field(0, description="Total entries across all children")
    children: list[ParticularsChild] = Field(default_factory=list)
    view_key: str = Field("", description="Drill-in identifier for the 'View' action")


class ParticularsSummaryResponse(BaseModel):
    """Response for the reconciliation Particulars statement table."""

    case_id: UUID
    closing_balance_company: Decimal | None = None
    closing_balance_party: Decimal | None = None
    groups: list[ParticularsGroup] = Field(default_factory=list)
    calculated_balance: Decimal = Field(
        Decimal("0"),
        description="Closing balance difference reconciled by the transaction differences",
    )

    model_config = {"from_attributes": True}
