"""
Column Mapping API endpoints.

Provides endpoints for mapping uploaded ledger file headers to standard fields
used by the reconciliation engine. Supports header extraction, auto-detection,
mapping persistence, and mapping application.

Routes:
- GET  /api/v1/vlr/column-mapping/{case_id}/headers  — Get raw file headers & sample values
- GET  /api/v1/vlr/column-mapping/{case_id}          — Get current column mapping
- POST /api/v1/vlr/column-mapping/{case_id}          — Save column mapping
- POST /api/v1/vlr/column-mapping/{case_id}/apply    — Apply mapping to ledger entries
"""

import json
import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel as PydanticBaseModel
from pydantic import Field
from sqlalchemy import and_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.v1.dependencies import get_current_active_user
from src.domain.entities.user import User
from src.domain.services.vlr.doc_type_mapping import DEFAULT_DOC_TYPE_MAP
from src.infrastructure.database.models.vlr.ledger_entry_model import LedgerEntryModel
from src.infrastructure.database.models.vlr.reconciliation_case_model import (
    ReconciliationCaseModel,
)
from src.infrastructure.database.models.vlr.setting_model import SettingModel
from src.infrastructure.database.repositories.vlr.setting_repository_impl import (
    SettingRepositoryImpl,
)
from src.infrastructure.database.session import get_db_session
from src.infrastructure.security.permission_manager import require_permission

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/vlr/column-mapping", tags=["VLR - Column Mapping"])


# ──────────────────────────────────────────────────────────────────────────────
# Pydantic Schemas
# ──────────────────────────────────────────────────────────────────────────────


class HeadersResponse(PydanticBaseModel):
    """Response schema for file headers endpoint."""

    headers: list[str]
    sample_values: dict[str, list[str]]
    row_count: int
    distinct_doc_types: list[str] = []


class ColumnMappingConfig(PydanticBaseModel):
    """Column mapping configuration for a ledger file."""

    invoice_no: str = Field(..., description="Header mapped to Invoice Number")
    invoice_date: str = Field(..., description="Header mapped to Invoice Date")
    document_type: str = Field(..., description="Header mapped to Voucher/Document Type")
    amount_format: str = Field(
        ...,
        description="Amount format: 'single' (one amount column) or 'double' (debit+credit)",
        pattern="^(single|double)$",
    )
    amount_field: str | None = Field(
        None, description="Header for single amount column (required if amount_format='single')"
    )
    debit_field: str | None = Field(
        None, description="Header for debit column (required if amount_format='double')"
    )
    credit_field: str | None = Field(
        None, description="Header for credit column (required if amount_format='double')"
    )
    party_code: str | None = Field(None, description="Header mapped to Party/Vendor Code")
    narration: str | None = Field(None, description="Header mapped to Narration/Description")
    clearing_doc_number: str | None = Field(
        None, description="Header mapped to Clearing Document Number"
    )
    clearing_date: str | None = Field(None, description="Header mapped to Clearing Date")
    tds_amount: str | None = Field(None, description="Header mapped to TDS Amount")
    posting_date: str | None = Field(None, description="Header mapped to Posting Date")


class SaveColumnMappingRequest(PydanticBaseModel):
    """Request body for saving a column mapping."""

    side: str = Field(..., description="Side: 'company' or 'vendor'", pattern="^(company|vendor)$")
    mappings: ColumnMappingConfig
    doc_type_mappings: dict[str, str] = Field(
        default_factory=dict,
        description="Document type code to category mappings (e.g. {'KR': 'Invoice'})",
    )


class SaveColumnMappingResponse(PydanticBaseModel):
    """Response schema for save mapping endpoint."""

    message: str
    case_id: str
    side: str


class GetColumnMappingResponse(PydanticBaseModel):
    """Response schema for get mapping endpoint."""

    case_id: str
    side: str
    mappings: ColumnMappingConfig | None = None
    doc_type_mappings: dict[str, str] = Field(default_factory=dict)
    is_default: bool = Field(
        default=False, description="True if using auto-detected defaults"
    )


class ApplyMappingRequest(PydanticBaseModel):
    """Request body for applying a column mapping."""

    side: str = Field(..., description="Side: 'company' or 'vendor'", pattern="^(company|vendor)$")


class ApplyMappingResponse(PydanticBaseModel):
    """Response schema for apply mapping endpoint."""

    message: str
    case_id: str
    side: str
    entries_updated: int


# ──────────────────────────────────────────────────────────────────────────────
# Auto-detection helpers
# ──────────────────────────────────────────────────────────────────────────────

# Known header aliases for auto-detection
HEADER_ALIASES: dict[str, list[str]] = {
    "invoice_no": [
        "invoice no", "invoice_no", "invoice number", "inv no", "bill no",
        "document number", "doc no", "belnr", "xblnr", "zuonr", "reference",
        "ref no", "reference number", "voucher no", "voucher number",
    ],
    "invoice_date": [
        "invoice date", "invoice_date", "doc date", "document date",
        "budat", "bldat", "posting date", "date", "voucher date", "bill date",
    ],
    "document_type": [
        "document type", "doc type", "blart", "voucher type", "type",
        "transaction type", "txn type",
    ],
    "amount_field": [
        "amount", "net amount", "total amount", "value", "dmbtr", "wrbtr",
        "transaction amount", "txn amount", "invoice amount", "bill amount",
    ],
    "debit_field": [
        "debit", "debit amount", "dr", "dr amount", "debit value",
    ],
    "credit_field": [
        "credit", "credit amount", "cr", "cr amount", "credit value",
    ],
    "party_code": [
        "party code", "vendor code", "vendor no", "party", "account",
        "lifnr", "account number", "vendor id",
    ],
    "narration": [
        "narration", "description", "remarks", "text", "sgtxt",
        "item text", "line text", "particulars", "details",
    ],
    "clearing_doc_number": [
        "clearing document", "clearing doc", "clearing number", "augbl",
        "clearing doc no", "clearing document number",
    ],
    "clearing_date": [
        "clearing date", "augdt", "clear date",
    ],
    "tds_amount": [
        "tds amount", "tds", "tds value", "withholding tax",
        "tax deducted", "tds deducted",
    ],
    "posting_date": [
        "posting date", "budat", "post date", "posted date",
    ],
}


def _auto_detect_mappings(headers: list[str]) -> ColumnMappingConfig | None:
    """
    Attempt to auto-detect column mappings based on header names.
    Returns None if required fields cannot be detected.
    """
    detected: dict[str, str | None] = {}
    headers_lower = [h.lower().strip() for h in headers]

    for field_name, aliases in HEADER_ALIASES.items():
        for alias in aliases:
            for i, header_lower in enumerate(headers_lower):
                if alias == header_lower or alias in header_lower:
                    detected[field_name] = headers[i]
                    break
            if field_name in detected:
                break

    # Determine amount format
    has_single = "amount_field" in detected
    has_double = "debit_field" in detected and "credit_field" in detected

    if has_double:
        amount_format = "double"
    elif has_single:
        amount_format = "single"
    else:
        return None

    # Check required fields
    if "invoice_no" not in detected or "invoice_date" not in detected:
        return None

    return ColumnMappingConfig(
        invoice_no=detected["invoice_no"],
        invoice_date=detected["invoice_date"],
        document_type=detected.get("document_type", ""),
        amount_format=amount_format,
        amount_field=detected.get("amount_field"),
        debit_field=detected.get("debit_field"),
        credit_field=detected.get("credit_field"),
        party_code=detected.get("party_code"),
        narration=detected.get("narration"),
        clearing_doc_number=detected.get("clearing_doc_number"),
        clearing_date=detected.get("clearing_date"),
        tds_amount=detected.get("tds_amount"),
        posting_date=detected.get("posting_date"),
    )


# ──────────────────────────────────────────────────────────────────────────────
# Helper functions
# ──────────────────────────────────────────────────────────────────────────────


def _setting_key(case_id: str, side: str) -> str:
    """Generate the vlr_settings key for a column mapping."""
    return f"column_mapping.{case_id}.{side}"


async def _get_case(session: AsyncSession, case_id: UUID) -> ReconciliationCaseModel:
    """Fetch and validate a reconciliation case exists."""
    stmt = select(ReconciliationCaseModel).where(ReconciliationCaseModel.id == case_id)
    result = await session.execute(stmt)
    case = result.scalar_one_or_none()
    if case is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Reconciliation case {case_id} not found.",
        )
    return case


# ──────────────────────────────────────────────────────────────────────────────
# Endpoints
# ──────────────────────────────────────────────────────────────────────────────


@router.get(
    "/{case_id}/headers",
    response_model=HeadersResponse,
    status_code=status.HTTP_200_OK,
    summary="Get raw file headers and sample values from uploaded ledger",
    dependencies=[Depends(require_permission("vlr.cases.read"))],
)
async def get_file_headers(
    case_id: UUID,
    side: str = Query(..., description="Side: 'company' or 'vendor'", pattern="^(company|vendor)$"),
    company_code: str = Query(..., description="Company code for tenant scoping"),
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db_session),
) -> HeadersResponse:
    """
    GET /api/v1/vlr/column-mapping/{case_id}/headers

    Reads ledger entries for the specified case and side, extracts unique field
    names (headers) from the stored data, and returns sample values for each
    header to assist in column mapping.
    """
    # Validate case exists
    await _get_case(session, case_id)

    # Try to load original file headers from settings (stored during upload)
    setting_repo = SettingRepositoryImpl(session)
    headers_key = f"file_headers.{case_id}.{side}"
    headers_setting = await setting_repo.get_by_key("__global__", headers_key)

    # Fetch ledger entries for this case/side (limit to first 50 for sampling)
    stmt = (
        select(LedgerEntryModel)
        .where(
            and_(
                LedgerEntryModel.case_id == str(case_id),
                LedgerEntryModel.side == side,
            )
        )
        .limit(50)
    )
    result = await session.execute(stmt)
    entries = list(result.scalars().all())

    if not entries:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No ledger entries found for case {case_id}, side '{side}'.",
        )

    # Get total count
    count_stmt = select(LedgerEntryModel.id).where(
        and_(
            LedgerEntryModel.case_id == str(case_id),
            LedgerEntryModel.side == side,
        )
    )
    count_result = await session.execute(count_stmt)
    row_count = len(count_result.all())

    headers: list[str] = []
    sample_values: dict[str, list[str]] = {}

    if headers_setting:
        # Preferred: show the ACTUAL original file column headers (includes Pan No, etc.)
        file_headers = json.loads(headers_setting.value)
        # Map known DB fields to sample values so we can show previews for recognized columns
        db_field_by_lower = {
            "document_number": ["invoice no", "doc no", "document number", "vch no.", "voucher no"],
            "document_type": ["document type", "doc type", "vch type", "type"],
            "reference_number": ["reference number", "reference", "particulars", "supplier"],
            "posting_date": ["document date", "posting date", "date", "doc dt."],
            "amount": ["amount", "amount in local currency", "amount in doc. curr.", "debit", "credit"],
            "clearing_document": ["clearing document", "clearing doc"],
            "clearing_date": ["clearing date"],
            "description": ["narration", "text", "description"],
        }
        for header in file_headers:
            headers.append(header)
            hl = header.lower().strip()
            # Find matching DB field for sample values
            matched_field = None
            for fld, aliases in db_field_by_lower.items():
                if any(hl == a or a in hl for a in aliases):
                    matched_field = fld
                    break
            values = []
            if matched_field:
                for entry in entries[:10]:
                    val = getattr(entry, matched_field, None)
                    if val is not None:
                        sv = str(val)
                        if sv and sv not in values:
                            values.append(sv)
            sample_values[header] = values[:5]
    else:
        # Fallback: use DB field display names if raw headers weren't stored
        field_mapping = {
            "document_number": "Invoice No",
            "document_type": "Document Type",
            "reference_number": "Reference Number",
            "posting_date": "Document Date",
            "clearing_date": "Clearing Date",
            "clearing_document": "Clearing Document",
            "amount": "Amount",
            "currency": "Currency",
            "assignment_number": "Assignment Number",
            "description": "Narration/Text",
        }
        for field_name, display_name in field_mapping.items():
            values = []
            for entry in entries[:10]:
                val = getattr(entry, field_name, None)
                if val is not None:
                    str_val = str(val)
                    if str_val and str_val not in values:
                        values.append(str_val)
            if values:
                headers.append(display_name)
                sample_values[display_name] = values[:5]

    # Compute DISTINCT document types directly from the DB (the actual doc type codes)
    dt_stmt = (
        select(LedgerEntryModel.document_type)
        .where(
            and_(
                LedgerEntryModel.case_id == str(case_id),
                LedgerEntryModel.side == side,
                LedgerEntryModel.document_type.isnot(None),
            )
        )
        .distinct()
    )
    dt_result = await session.execute(dt_stmt)
    distinct_doc_types = [r[0] for r in dt_result.all() if r[0]]

    logger.info(
        "Headers extracted: case_id=%s, side=%s, headers=%d, doc_types=%d, rows=%d, user=%s",
        case_id, side, len(headers), len(distinct_doc_types), row_count, current_user.username,
    )

    return HeadersResponse(
        headers=headers,
        sample_values=sample_values,
        row_count=row_count,
        distinct_doc_types=distinct_doc_types,
    )


@router.get(
    "/{case_id}",
    response_model=GetColumnMappingResponse,
    status_code=status.HTTP_200_OK,
    summary="Get current column mapping for a case",
    dependencies=[Depends(require_permission("vlr.cases.read"))],
)
async def get_column_mapping(
    case_id: UUID,
    side: str = Query(..., description="Side: 'company' or 'vendor'", pattern="^(company|vendor)$"),
    company_code: str = Query(..., description="Company code for tenant scoping"),
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db_session),
) -> GetColumnMappingResponse:
    """
    GET /api/v1/vlr/column-mapping/{case_id}

    Returns the saved column mapping for the specified case and side.
    If no mapping has been saved, attempts auto-detection from headers
    and returns defaults with is_default=True.
    """
    await _get_case(session, case_id)

    setting_repo = SettingRepositoryImpl(session)
    key = _setting_key(str(case_id), side)
    setting = await setting_repo.get_by_key(company_code, key)

    if setting:
        # Return saved mapping
        mapping_data = json.loads(setting.value)
        return GetColumnMappingResponse(
            case_id=str(case_id),
            side=side,
            mappings=ColumnMappingConfig(**mapping_data.get("mappings", {})),
            doc_type_mappings=mapping_data.get("doc_type_mappings", {}),
            is_default=False,
        )

    # No saved mapping — attempt auto-detection
    stmt = (
        select(LedgerEntryModel)
        .where(
            and_(
                LedgerEntryModel.case_id == str(case_id),
                LedgerEntryModel.side == side,
            )
        )
        .limit(10)
    )
    result = await session.execute(stmt)
    entries = list(result.scalars().all())

    if entries:
        # Build a pseudo-header list from fields that have data
        field_mapping = {
            "document_number": "Document Number",
            "document_type": "Document Type",
            "reference_number": "Reference Number",
            "posting_date": "Posting Date",
            "clearing_date": "Clearing Date",
            "clearing_document": "Clearing Document",
            "amount": "Amount",
            "assignment_number": "Assignment Number",
            "description": "Description/Narration",
        }
        available_headers = []
        for field_name, display_name in field_mapping.items():
            for entry in entries:
                if getattr(entry, field_name, None) is not None:
                    available_headers.append(display_name)
                    break

        auto_mapping = _auto_detect_mappings(available_headers)
        if auto_mapping:
            return GetColumnMappingResponse(
                case_id=str(case_id),
                side=side,
                mappings=auto_mapping,
                doc_type_mappings=DEFAULT_DOC_TYPE_MAP,
                is_default=True,
            )

    # No mapping and no auto-detection possible
    return GetColumnMappingResponse(
        case_id=str(case_id),
        side=side,
        mappings=None,
        doc_type_mappings=DEFAULT_DOC_TYPE_MAP,
        is_default=True,
    )


@router.post(
    "/{case_id}",
    response_model=SaveColumnMappingResponse,
    status_code=status.HTTP_200_OK,
    summary="Save column mapping for a case",
    dependencies=[Depends(require_permission("vlr.cases.write"))],
)
async def save_column_mapping(
    case_id: UUID,
    request: SaveColumnMappingRequest,
    company_code: str = Query(..., description="Company code for tenant scoping"),
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db_session),
) -> SaveColumnMappingResponse:
    """
    POST /api/v1/vlr/column-mapping/{case_id}

    Saves the column mapping configuration for the specified case and side.
    Stores in vlr_settings with key format: column_mapping.{case_id}.{side}
    """
    await _get_case(session, case_id)

    # Validate amount format consistency
    if request.mappings.amount_format == "single" and not request.mappings.amount_field:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="amount_field is required when amount_format is 'single'.",
        )
    if request.mappings.amount_format == "double":
        if not request.mappings.debit_field or not request.mappings.credit_field:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="debit_field and credit_field are required when amount_format is 'double'.",
            )

    # Serialize and store
    mapping_payload = {
        "mappings": request.mappings.model_dump(exclude_none=True),
        "doc_type_mappings": request.doc_type_mappings,
    }

    setting_repo = SettingRepositoryImpl(session)
    key = _setting_key(str(case_id), request.side)

    await setting_repo.upsert(
        company_code=company_code,
        key=key,
        value=json.dumps(mapping_payload),
        value_type="json",
        description=f"Column mapping for case {case_id}, side {request.side}",
    )

    await session.commit()

    logger.info(
        "Column mapping saved: case_id=%s, side=%s, company_code=%s, user=%s",
        case_id, request.side, company_code, current_user.username,
    )

    return SaveColumnMappingResponse(
        message=f"Column mapping saved successfully for case {case_id}, side '{request.side}'.",
        case_id=str(case_id),
        side=request.side,
    )


@router.post(
    "/{case_id}/apply",
    response_model=ApplyMappingResponse,
    status_code=status.HTTP_200_OK,
    summary="Apply column mapping to ledger entries",
    dependencies=[Depends(require_permission("vlr.cases.write"))],
)
async def apply_column_mapping(
    case_id: UUID,
    request: ApplyMappingRequest,
    company_code: str = Query(..., description="Company code for tenant scoping"),
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db_session),
) -> ApplyMappingResponse:
    """
    POST /api/v1/vlr/column-mapping/{case_id}/apply

    Applies the saved column mapping to the ledger entries for the specified
    case and side. Re-parses stored entries using the mapping configuration
    and updates derived fields (derived_invoice_number, document_category, etc.).

    After successful application, updates the case status to 'statement_mapped'.
    """
    case = await _get_case(session, case_id)

    # Load the saved mapping
    setting_repo = SettingRepositoryImpl(session)
    key = _setting_key(str(case_id), request.side)
    setting = await setting_repo.get_by_key(company_code, key)

    if not setting:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"No column mapping found for case {case_id}, side '{request.side}'. "
            "Please save a mapping first.",
        )

    mapping_data = json.loads(setting.value)
    mappings = ColumnMappingConfig(**mapping_data.get("mappings", {}))
    doc_type_mappings = mapping_data.get("doc_type_mappings", {})

    # Fetch all ledger entries for this case/side
    stmt = select(LedgerEntryModel).where(
        and_(
            LedgerEntryModel.case_id == str(case_id),
            LedgerEntryModel.side == request.side,
        )
    )
    result = await session.execute(stmt)
    entries = list(result.scalars().all())

    if not entries:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No ledger entries found for case {case_id}, side '{request.side}'.",
        )

    # Note: Party code is tracked at the case level (case.vendor_id). For the
    # vendor side it's the vendor's PAN (sent as "__fixed__:PAN"); no per-entry
    # storage is needed since all entries belong to one vendor.

    # Apply mapping to each entry - update derived fields
    entries_updated = 0
    for entry in entries:
        updated = False

        # Apply document category from doc_type_mappings
        if entry.document_type and doc_type_mappings:
            category = doc_type_mappings.get(entry.document_type)
            if category and category != entry.document_category:
                entry.document_category = category
                updated = True

        # Derive invoice number from the mapped field.
        # invoice_no is the file header the user selected — map it to a DB field.
        invoice_source = (mappings.invoice_no or "").lower().strip()
        if invoice_source:
            # Determine which stored field best matches the selected header
            if any(k in invoice_source for k in ["reference", "particulars", "supplier"]):
                model_field = "reference_number"
            elif "assignment" in invoice_source:
                model_field = "assignment_number"
            else:
                model_field = "document_number"

            source_value = getattr(entry, model_field, None)
            if source_value and source_value != entry.derived_invoice_number:
                entry.derived_invoice_number = str(source_value).strip()
                entry.invoice_source_field = model_field[:10]
                updated = True

        # Handle amount mapping for double format (debit/credit)
        if mappings.amount_format == "double" and entry.original_amount is not None:
            # If we have debit/credit indicators, apply sign
            if entry.shkzg_indicator == "H":
                # Credit side (H = Haben)
                adjusted = -abs(entry.original_amount)
            elif entry.shkzg_indicator == "S":
                # Debit side (S = Soll)
                adjusted = abs(entry.original_amount)
            else:
                adjusted = entry.original_amount

            if adjusted != entry.adjusted_amount:
                entry.adjusted_amount = adjusted
                updated = True

        if updated:
            entries_updated += 1

    # Update case status to indicate mapping is complete
    case.status = "statement_mapped"

    await session.commit()

    logger.info(
        "Column mapping applied: case_id=%s, side=%s, entries_updated=%d/%d, user=%s",
        case_id, request.side, entries_updated, len(entries), current_user.username,
    )

    return ApplyMappingResponse(
        message=(
            f"Column mapping applied successfully. "
            f"{entries_updated} of {len(entries)} entries updated."
        ),
        case_id=str(case_id),
        side=request.side,
        entries_updated=entries_updated,
    )
