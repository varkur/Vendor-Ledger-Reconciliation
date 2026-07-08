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
