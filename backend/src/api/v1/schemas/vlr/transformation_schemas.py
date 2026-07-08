"""
Response schemas for the Data Transformation API endpoint.

Requirements: 1.1, 2.1, 3.1, 4.1, 5.1, 6.1, 7.1
"""

from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field


class TransformationSummaryResponse(BaseModel):
    """Response model for the transformation pipeline execution summary."""

    case_id: UUID = Field(..., description="The reconciliation case ID")
    entries_processed: int = Field(
        ..., description="Total number of ledger entries processed"
    )
    company_entries_processed: int = Field(
        ..., description="Number of company-side entries processed"
    )
    vendor_entries_processed: int = Field(
        ..., description="Number of vendor-side entries processed"
    )
    invoices_derived: int = Field(
        ..., description="Number of entries with successfully derived invoice numbers"
    )
    sign_adjustments_applied: int = Field(
        ..., description="Number of entries with sign adjustment applied"
    )
    company_opening_balance: Decimal | None = Field(
        None, description="Calculated opening balance for company side"
    )
    company_closing_balance: Decimal | None = Field(
        None, description="Calculated closing balance for company side"
    )
    vendor_opening_balance: Decimal | None = Field(
        None, description="Calculated opening balance for vendor side"
    )
    vendor_closing_balance: Decimal | None = Field(
        None, description="Calculated closing balance for vendor side"
    )
    tds_entries_found: int = Field(
        ..., description="Number of entries tagged as TDS"
    )
    tds_entries_linked: int = Field(
        ..., description="Number of TDS entries linked to parent invoices"
    )
    multi_currency_entries: int = Field(
        ..., description="Number of entries with non-INR transaction currency"
    )
    document_types_classified: int = Field(
        ..., description="Number of entries with document type classification applied"
    )
    status: str = Field(
        ..., description="Transformation status: 'completed' or 'partial'"
    )
    message: str = Field(..., description="Summary message")

    model_config = {"from_attributes": True}
