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
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from pydantic import BaseModel as PydanticBaseModel
from pydantic import Field
from sqlalchemy import and_, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.v1.dependencies import get_current_active_user
from src.domain.entities.user import User
from src.domain.services.vlr.doc_type_mapping import DEFAULT_DOC_TYPE_MAP
from src.infrastructure.database.models.vlr.ledger_entry_model import LedgerEntryModel
from src.infrastructure.database.models.vlr.ledger_file_model import LedgerFileModel
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


class DocTypeSummary(PydanticBaseModel):
    """Per-document-type line item count and total amount, for the Map
    Document Type table (lets the reviewer verify entry counts/amounts
    line up with the source file before committing the mapping)."""

    doc_type: str
    count: int
    amount: float


class HeadersResponse(PydanticBaseModel):
    """Response schema for file headers endpoint."""

    headers: list[str]
    sample_values: dict[str, list[str]]
    row_count: int
    distinct_doc_types: list[str] = []
    doc_type_summary: list[DocTypeSummary] = []


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
        # On SAP-style company ledgers, "Assignment" (SAP field ZUONR) is
        # where the vendor's actual invoice number is recorded — "Document
        # Number" (BELNR) is SAP's own internal accounting document number,
        # NOT the vendor's invoice number. Checked first so it wins over the
        # generic/legacy aliases below whenever a file has both columns.
        "assignment", "assignment number", "zuonr",
        "invoice no", "invoice_no", "invoice number", "inv no", "bill no",
        "document number", "doc no", "belnr", "xblnr", "reference",
        "ref no", "reference number", "voucher no", "voucher number",
    ],
    "invoice_date": [
        # "Document Date" (BLDAT) is the invoice's own date; "Posting Date"
        # (BUDAT) is when it was posted into the books, which is often
        # several days later and skews date-based matching if used instead.
        # Checked first so it wins whenever a file has both columns.
        "document date", "doc date", "invoice date", "invoice_date",
        "bldat", "voucher date", "bill date",
        "budat", "posting date", "date",
    ],
    "document_type": [
        "document type", "doc type", "blart", "voucher type", "type",
        "transaction type", "txn type",
    ],
    "amount_field": [
        "amount", "amount in local currency", "amount in doc. curr",
        "amount in doc curr", "net amount", "total amount", "value",
        "dmbtr", "wrbtr", "transaction amount", "txn amount",
        "invoice amount", "bill amount",
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


def _clean_number(raw: Any) -> str:
    """Strip currency noise / placeholders from a numeric cell value."""
    if raw is None:
        return ""
    v = str(raw).strip()
    if v in ("None", "-", "--", "N/A", "NA", ""):
        return ""
    for ch in (",", "\u20b9", "$", " "):
        v = v.replace(ch, "")
    if v.startswith("(") and v.endswith(")"):
        v = "-" + v[1:-1]
    return v


def _lookup_raw(raw_data: dict | None, header: str | None) -> Any:
    """
    Fetch a value from the stored raw_data row by header, tolerant of
    case/whitespace differences between the mapping header and stored keys.
    """
    if not raw_data or not header:
        return None
    target = header.strip().lower()
    for k, v in raw_data.items():
        if k is not None and str(k).strip().lower() == target:
            return v
    return None


def _parse_date_value(value: Any):
    """
    Parse a date from a raw cell value using the same formats the file parser
    supports (incl. Excel serial numbers). Returns a datetime.date or None.
    """
    from datetime import date as _date
    from datetime import datetime as _datetime
    from datetime import timedelta as _timedelta

    if value is None:
        return None
    s = str(value).strip()
    if not s or s.lower() == "none":
        return None
    if " " in s:
        s = s.split(" ")[0]

    # Excel serial number
    try:
        serial = int(float(s))
        if 30000 < serial < 60000:
            return _date(1899, 12, 30) + _timedelta(days=serial)
    except (ValueError, OverflowError):
        pass

    for fmt in (
        "%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%m/%d/%Y", "%d.%m.%Y",
        "%Y/%m/%d", "%d-%b-%Y", "%d-%b-%y", "%b %d, %Y",
    ):
        try:
            return _datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _amount_from_mapping(entry: LedgerEntryModel, mappings: "ColumnMappingConfig") -> Decimal | None:
    """
    Recompute the signed amount for a ledger entry from the columns the user
    mapped, reading the original values out of entry.raw_data.

    - single: use amount_field directly.
    - double: debit_field - credit_field (debit positive, credit negative).

    Returns the computed Decimal, or None if it can't be determined (so the
    caller can leave the existing amount untouched).
    """
    raw = entry.raw_data
    if not raw:
        return None

    if mappings.amount_format == "double":
        debit_str = _clean_number(_lookup_raw(raw, mappings.debit_field))
        credit_str = _clean_number(_lookup_raw(raw, mappings.credit_field))
        if not debit_str and not credit_str:
            return None
        try:
            debit_val = Decimal(debit_str) if debit_str else Decimal(0)
            credit_val = Decimal(credit_str) if credit_str else Decimal(0)
            return debit_val - credit_val
        except (InvalidOperation, ValueError):
            return None

    # single
    amount_str = _clean_number(_lookup_raw(raw, mappings.amount_field))
    if not amount_str:
        return None
    try:
        return Decimal(amount_str)
    except (InvalidOperation, ValueError):
        return None


def _clip(value, limit: int):
    """Truncate a string value to the DB column limit (None-safe). Prevents
    StringDataRightTruncation 500s when a source file has an over-length value."""
    if value is None:
        return None
    s = str(value)
    return s[:limit] if len(s) > limit else s


def _guess_content_type(filename: str) -> str:
    """Map a filename extension to a content type for downloads."""
    name = (filename or "").lower()
    if name.endswith(".xlsx"):
        return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    if name.endswith(".xls"):
        return "application/vnd.ms-excel"
    if name.endswith(".csv"):
        return "text/csv"
    return "application/octet-stream"


async def store_original_ledger_file(
    session: AsyncSession,
    case_id,
    side: str,
    filename: str,
    content: bytes,
    modified_by: str = "system",
) -> None:
    """
    Persist (or replace) the ORIGINAL uploaded ledger file bytes for a case+side
    so downloads can return the exact file the user uploaded, unchanged.

    Best-effort: storing the original is a convenience for downloads and must
    never fail the actual ledger upload. Runs inside a SAVEPOINT so any error
    (e.g. the vlr_ledger_files table not yet migrated on this environment)
    rolls back only this sub-operation, leaving the upload transaction intact.
    """
    from sqlalchemy import delete as _sql_delete

    try:
        async with session.begin_nested():
            # Replace any existing original for this case+side (re-upload).
            await session.execute(
                _sql_delete(LedgerFileModel).where(
                    and_(
                        LedgerFileModel.case_id == str(case_id),
                        LedgerFileModel.side == side,
                    )
                )
            )
            session.add(LedgerFileModel(
                case_id=str(case_id),
                side=side,
                filename=filename or f"{side}_ledger",
                content_type=_guess_content_type(filename or ""),
                content=content,
                created_by=modified_by,
                modified_by=modified_by,
            ))
    except Exception:  # noqa: BLE001
        logger.warning(
            "Could not store original ledger file for case=%s side=%s "
            "(continuing; download will use the reconstructed fallback).",
            case_id, side, exc_info=True,
        )


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

    # Compute DISTINCT document types directly from the DB (the actual doc
    # type codes), together with the line-item count and total signed
    # amount for each — shown as "Count"/"Amount" columns on the Map
    # Document Type table so the reviewer can verify the file's totals per
    # doc type before committing the mapping.
    dt_stmt = (
        select(
            LedgerEntryModel.document_type,
            func.count(LedgerEntryModel.id),
            func.coalesce(func.sum(LedgerEntryModel.amount), 0),
        )
        .where(
            and_(
                LedgerEntryModel.case_id == str(case_id),
                LedgerEntryModel.side == side,
                LedgerEntryModel.document_type.isnot(None),
            )
        )
        .group_by(LedgerEntryModel.document_type)
    )
    dt_result = await session.execute(dt_stmt)
    dt_rows = [r for r in dt_result.all() if r[0]]
    distinct_doc_types = [r[0] for r in dt_rows]
    doc_type_summary = [
        DocTypeSummary(doc_type=r[0], count=r[1], amount=float(r[2]))
        for r in dt_rows
    ]

    logger.info(
        "Headers extracted: case_id=%s, side=%s, headers=%d, doc_types=%d, rows=%d, user=%s",
        case_id, side, len(headers), len(distinct_doc_types), row_count, current_user.username,
    )

    return HeadersResponse(
        headers=headers,
        sample_values=sample_values,
        row_count=row_count,
        distinct_doc_types=distinct_doc_types,
        doc_type_summary=doc_type_summary,
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
        # Return saved mapping. A small number of legacy rows persisted a
        # field as the raw dropdown option object (e.g. {"label": "Select",
        # "value": ""}) instead of a plain string — self-heal those on read
        # so the mapping screen doesn't 500/422-loop for that case forever.
        mapping_data = json.loads(setting.value)
        raw_mappings = mapping_data.get("mappings", {})
        cleaned_mappings = {
            k: (v if isinstance(v, str) or v is None else None)
            for k, v in raw_mappings.items()
        }
        return GetColumnMappingResponse(
            case_id=str(case_id),
            side=side,
            mappings=ColumnMappingConfig(**cleaned_mappings),
            doc_type_mappings=mapping_data.get("doc_type_mappings", {}),
            is_default=False,
        )

    # No saved mapping — attempt auto-detection using the REAL original file
    # headers (the same list the Map Columns dropdowns are populated from —
    # see get_file_headers above), not a hardcoded pseudo-header list. The
    # previous fallback built its own generic field-name list ("Document
    # Number", "Posting Date", "Assignment Number", ...) that never
    # included "Document Date" and could never match a real "Assignment"
    # header, so the default could never land on the columns this business
    # rule requires (Assignment -> Invoice No, Document Date -> Invoice
    # Date) no matter what HEADER_ALIASES said — it always fell back to
    # Document Number / Posting Date because those were the only names
    # available to match against.
    file_headers: list[str] = []
    headers_setting = await setting_repo.get_by_key(
        "__global__", f"file_headers.{case_id}.{side}"
    )
    if headers_setting:
        file_headers = json.loads(headers_setting.value)

    if file_headers:
        auto_mapping = _auto_detect_mappings(file_headers)
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

        # Derive invoice number from the mapped header, reading the ORIGINAL
        # value out of raw_data. The parser may have stored a placeholder
        # (e.g. "BAL_ROW_13") in document_number when it couldn't recognise the
        # file's invoice column, so reading raw_data by the header the user
        # actually selected is what makes the mapping authoritative.
        invoice_header = (mappings.invoice_no or "").strip()
        if invoice_header:
            raw_val = _lookup_raw(entry.raw_data, invoice_header)
            if raw_val is None or str(raw_val).strip() == "":
                # Fallback for entries without raw_data (pre-existing uploads):
                # map the header to the closest stored DB column.
                inv_lower = invoice_header.lower()
                if any(k in inv_lower for k in ["reference", "particulars", "supplier"]):
                    model_field = "reference_number"
                elif "assignment" in inv_lower:
                    model_field = "assignment_number"
                else:
                    model_field = "document_number"
                raw_val = getattr(entry, model_field, None)

            if raw_val is not None and str(raw_val).strip():
                new_invoice = str(raw_val).strip()
                if new_invoice != entry.derived_invoice_number:
                    entry.derived_invoice_number = new_invoice
                    entry.invoice_source_field = "mapped"
                    updated = True
                # Replace the placeholder document_number so the output/export
                # and unmatched screens show the real invoice number, not BAL_ROW_*.
                if (entry.document_number or "").startswith("BAL_ROW_"):
                    entry.document_number = new_invoice[:50]
                    updated = True

        # Derive document type from the mapped header if present in raw_data.
        dtype_header = (mappings.document_type or "").strip()
        if dtype_header:
            raw_dtype = _lookup_raw(entry.raw_data, dtype_header)
            if raw_dtype is not None and str(raw_dtype).strip():
                new_dtype = str(raw_dtype).strip()[:20]
                if new_dtype != entry.document_type:
                    entry.document_type = new_dtype
                    updated = True
                    # Re-apply category mapping for the corrected type
                    if doc_type_mappings:
                        cat = doc_type_mappings.get(new_dtype)
                        if cat:
                            entry.document_category = cat

        # Derive invoice/posting date from the mapped header. "Invoice Date"
        # (invoice_date) is the PRIMARY reconciliation date — it's the field
        # the user actively selects on the Map Columns screen (e.g. mapping
        # it to a "Document Date" column). posting_date is a separate,
        # auto-detected/saved field that is populated on essentially every
        # case regardless of what the user intended for Invoice Date — an
        # earlier version of this code let posting_date win whenever it was
        # present, which silently overrode the user's explicit Document Date
        # choice on both sides and skewed match dates by the SAP posting-vs-
        # document-date gap (confirmed on real data: same invoice dated
        # 19-Apr on "document date" but 02-May on "posting date" — a 13 day
        # gap that pushed genuine same-invoice matches into weaker
        # date-tolerance passes instead of being recognized immediately).
        # posting_date is now only used as a fallback when invoice_date isn't
        # mapped at all.
        date_header = (mappings.invoice_date or mappings.posting_date or "").strip()
        if date_header:
            raw_date = _lookup_raw(entry.raw_data, date_header)
            parsed_date = _parse_date_value(raw_date)
            if parsed_date is not None and parsed_date != entry.posting_date:
                entry.posting_date = parsed_date
                updated = True

        # Derive narration/description from the mapped header (optional field).
        narration_header = (mappings.narration or "").strip()
        if narration_header:
            raw_narr = _lookup_raw(entry.raw_data, narration_header)
            if raw_narr is not None and str(raw_narr).strip():
                new_narr = str(raw_narr).strip()
                if new_narr != entry.description:
                    entry.description = new_narr
                    updated = True

        # Derive clearing document number / clearing date (optional fields).
        clr_doc_header = (mappings.clearing_doc_number or "").strip()
        if clr_doc_header:
            raw_clr = _lookup_raw(entry.raw_data, clr_doc_header)
            if raw_clr is not None and str(raw_clr).strip():
                new_clr = str(raw_clr).strip()[:50]
                if new_clr != entry.clearing_document:
                    entry.clearing_document = new_clr
                    updated = True

        clr_date_header = (mappings.clearing_date or "").strip()
        if clr_date_header:
            raw_clr_date = _lookup_raw(entry.raw_data, clr_date_header)
            parsed_clr_date = _parse_date_value(raw_clr_date)
            if parsed_clr_date is not None and parsed_clr_date != entry.clearing_date:
                entry.clearing_date = parsed_clr_date
                updated = True

        # Recompute the amount from the mapped column(s), reading the original
        # values from raw_data. This is what actually feeds the reconciliation
        # engine (it matches on entry.amount), so the mapping the user chooses
        # on this page — single amount column, or Dr/Cr split — takes effect here.
        computed = _amount_from_mapping(entry, mappings)
        if computed is not None:
            computed_f = float(computed)
            if entry.amount is None or float(entry.amount) != computed_f:
                entry.amount = computed_f
                updated = True
            # Keep the transformation columns consistent for the export/audit.
            entry.original_amount = abs(computed)
            entry.adjusted_amount = computed

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


# ──────────────────────────────────────────────────────────────────────────────
# Ledger file management: download, delete, re-upload
# ──────────────────────────────────────────────────────────────────────────────


@router.get(
    "/{case_id}/download",
    summary="Download the original uploaded ledger file (verbatim)",
    dependencies=[Depends(require_permission("vlr.cases.read"))],
)
async def download_ledger(
    case_id: UUID,
    side: str = Query(..., description="'company' or 'vendor'"),
    company_code: str = Query(..., description="Company code for tenant scoping"),
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db_session),
):
    """
    GET /api/v1/vlr/column-mapping/{case_id}/download?side=company|vendor

    Returns the EXACT original file the user uploaded (same format, same data).
    Falls back to a reconstructed CSV only for legacy cases uploaded before the
    original bytes were stored.
    """
    import csv
    import io as _io

    from fastapi.responses import Response

    if side not in ("company", "vendor"):
        raise HTTPException(status_code=400, detail="side must be 'company' or 'vendor'.")

    await _get_case(session, case_id)

    # Preferred: return the original uploaded file, byte-for-byte.
    file_stmt = select(LedgerFileModel).where(
        and_(
            LedgerFileModel.case_id == str(case_id),
            LedgerFileModel.side == side,
        )
    )
    original = (await session.execute(file_stmt)).scalar_one_or_none()
    if original is not None and original.content:
        from urllib.parse import quote
        safe_name = quote(original.filename or f"{side}_ledger")
        return Response(
            content=original.content,
            media_type=original.content_type or "application/octet-stream",
            headers={
                "Content-Disposition": f"attachment; filename*=UTF-8''{safe_name}",
            },
        )

    # ── Legacy fallback: reconstruct a CSV from stored entries ──
    stmt = (
        select(LedgerEntryModel)
        .where(
            and_(
                LedgerEntryModel.case_id == str(case_id),
                LedgerEntryModel.side == side,
            )
        )
        .order_by(LedgerEntryModel.posting_date.asc())
    )
    result = await session.execute(stmt)
    entries = list(result.scalars().all())

    if not entries:
        raise HTTPException(
            status_code=404,
            detail=f"No {side} ledger found for this case.",
        )

    buffer = _io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow([
        "Document Number", "Document Type", "Reference Number", "Posting Date",
        "Clearing Date", "Amount", "Currency", "Assignment Number",
        "Description", "Document Category",
    ])
    for e in entries:
        writer.writerow([
            e.document_number or "",
            e.document_type or "",
            e.reference_number or "",
            e.posting_date.isoformat() if e.posting_date else "",
            e.clearing_date.isoformat() if e.clearing_date else "",
            str(e.amount if e.amount is not None else ""),
            e.currency or "",
            e.assignment_number or "",
            e.description or "",
            e.document_category or "",
        ])

    csv_bytes = buffer.getvalue().encode("utf-8-sig")
    filename = f"{side}_ledger_{case_id}.csv"
    return Response(
        content=csv_bytes,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.delete(
    "/{case_id}/ledger",
    response_model=None,
    summary="Delete all ledger entries for a side (allows re-upload)",
    dependencies=[Depends(require_permission("vlr.cases.write"))],
)
async def delete_ledger(
    case_id: UUID,
    side: str = Query(..., description="'company' or 'vendor'"),
    company_code: str = Query(..., description="Company code for tenant scoping"),
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    """
    DELETE /api/v1/vlr/column-mapping/{case_id}/ledger?side=company|vendor

    Removes all stored ledger entries for the given side and clears any match
    data, so a fresh file can be re-uploaded and reconciliation re-run.
    """
    from sqlalchemy import delete as sql_delete

    from src.infrastructure.database.models.vlr.match_result_model import (
        MatchResultModel,
    )

    if side not in ("company", "vendor"):
        raise HTTPException(status_code=400, detail="side must be 'company' or 'vendor'.")

    case = await _get_case(session, case_id)

    # Clear match results for the whole case (matches span both sides)
    await session.execute(
        sql_delete(MatchResultModel).where(MatchResultModel.case_id == str(case_id))
    )

    # Reset match metadata on remaining (other-side) entries so nothing points
    # at now-deleted matches.
    await session.execute(
        update(LedgerEntryModel)
        .where(LedgerEntryModel.case_id == str(case_id))
        .values(match_id=None, pass_number=None, confidence_score=None)
    )

    # Delete the entries for the requested side
    del_result = await session.execute(
        sql_delete(LedgerEntryModel).where(
            and_(
                LedgerEntryModel.case_id == str(case_id),
                LedgerEntryModel.side == side,
            )
        )
    )

    # Remove the stored original file for this side too.
    await session.execute(
        sql_delete(LedgerFileModel).where(
            and_(
                LedgerFileModel.case_id == str(case_id),
                LedgerFileModel.side == side,
            )
        )
    )

    # Clear the saved column mapping AND cached file headers for this side —
    # neither was being cleared here before, so after deleting a ledger the
    # Map Columns screen would still show the PREVIOUS file's saved mapping
    # (pointing at header names that may not exist in whatever gets
    # re-uploaded next) instead of resetting to fresh auto-detection.
    setting_repo = SettingRepositoryImpl(session)
    await setting_repo.delete_by_key(company_code, _setting_key(str(case_id), side))
    await setting_repo.delete_by_key("__global__", f"file_headers.{case_id}.{side}")

    # Move the case back to mapping_pending and clear stale match statistics so
    # the UI's Match Results panel refreshes (shows nothing) after deletion.
    case.status = "mapping_pending"
    case.match_statistics = None
    case.modified_by = current_user.username

    await session.commit()

    deleted = del_result.rowcount or 0
    logger.info(
        "Ledger deleted: case_id=%s, side=%s, deleted=%d, user=%s",
        case_id, side, deleted, current_user.username,
    )
    return {
        "message": f"Deleted {deleted} {side} ledger entries. You can now re-upload.",
        "case_id": str(case_id),
        "side": side,
        "deleted": deleted,
    }


@router.post(
    "/{case_id}/reupload",
    summary="Re-upload a ledger file for a side",
    dependencies=[Depends(require_permission("vlr.cases.write"))],
)
async def reupload_ledger(
    case_id: UUID,
    side: str = Query(..., description="'company' or 'vendor'"),
    company_code: str = Query(..., description="Company code for tenant scoping"),
    file: UploadFile = File(..., description="Ledger file (CSV, XLSX, or XLS)"),
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    """
    POST /api/v1/vlr/column-mapping/{case_id}/reupload?side=company|vendor

    Replaces the ledger entries for a side with the contents of the uploaded
    file (.csv/.xlsx/.xls), clears prior match data, and sets the case back to
    mapping_pending so reconciliation can be re-run.
    """
    import json as _json

    from sqlalchemy import delete as sql_delete

    from src.domain.exceptions.vlr import FileValidationException
    from src.domain.services.vlr.file_parser_service import FileParserService
    from src.infrastructure.database.models.vlr.match_result_model import (
        MatchResultModel,
    )

    if side not in ("company", "vendor"):
        raise HTTPException(status_code=400, detail="side must be 'company' or 'vendor'.")

    case = await _get_case(session, case_id)

    filename = file.filename or ""
    if not filename.lower().endswith((".csv", ".xlsx", ".xls")):
        raise HTTPException(
            status_code=400,
            detail="Unsupported file type. Upload .csv, .xlsx, or .xls.",
        )

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    max_size = 50 * 1024 * 1024
    parser = FileParserService(max_file_size_bytes=max_size)
    try:
        result = parser.validate_and_parse(content, filename)
    except FileValidationException as e:
        raise HTTPException(
            status_code=422,
            detail=f"File validation failed: {'; '.join(e.errors)}",
        )
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=422, detail=f"Failed to parse file: {str(e)}")

    if not result.entries:
        raise HTTPException(status_code=422, detail="No valid entries found in the file.")

    # Clear match data (spans both sides) and existing entries for this side.
    await session.execute(
        sql_delete(MatchResultModel).where(MatchResultModel.case_id == str(case_id))
    )
    await session.execute(
        update(LedgerEntryModel)
        .where(LedgerEntryModel.case_id == str(case_id))
        .values(match_id=None, pass_number=None, confidence_score=None)
    )
    await session.execute(
        sql_delete(LedgerEntryModel).where(
            and_(
                LedgerEntryModel.case_id == str(case_id),
                LedgerEntryModel.side == side,
            )
        )
    )

    # Store new entries. Clip string fields to their DB column limits so a
    # single over-length value in the source file can't 500 the whole upload.
    for entry in result.entries:
        session.add(LedgerEntryModel(
            case_id=str(case_id),
            side=side,
            document_number=_clip(entry.document_number, 50),
            document_type=_clip(entry.document_type, 20),
            reference_number=_clip(entry.reference_number, 100),
            posting_date=entry.posting_date,
            clearing_date=entry.clearing_date,
            clearing_document=_clip(entry.clearing_document, 50),
            amount=float(entry.amount),
            currency=_clip(entry.currency, 10),
            assignment_number=_clip(entry.assignment_number, 100),
            description=entry.description,
            raw_data=getattr(entry, "raw_data", None),
            source="upload",
            created_by=current_user.username,
            modified_by=current_user.username,
        ))

    # Store the ORIGINAL uploaded file bytes so downloads return it verbatim.
    await store_original_ledger_file(
        session, case_id, side, filename, content, modified_by=current_user.username,
    )

    # Clear the PREVIOUS file's saved column mapping before storing the new
    # headers — otherwise GET .../column-mapping/{case_id} keeps returning
    # the old mapping (pointing at header names from the previous file) since
    # that lookup returns the saved mapping unconditionally whenever one
    # exists, regardless of whether the underlying file/headers changed.
    # Clearing it here forces fresh auto-detection against the new file's
    # actual headers, same as a case that's never been mapped before.
    headers_repo = SettingRepositoryImpl(session)
    await headers_repo.delete_by_key(company_code, _setting_key(str(case_id), side))

    # Save raw headers for the column-mapping UI.
    if result.raw_headers:
        await headers_repo.upsert(
            company_code="__global__",
            key=f"file_headers.{case_id}.{side}",
            value=_json.dumps(result.raw_headers),
            value_type="json",
            description=f"Original file headers from {side} ledger re-upload",
        )

    # Back to mapping_pending for re-reconciliation; clear stale match stats.
    case.status = "mapping_pending"
    case.match_statistics = None
    case.modified_by = current_user.username

    try:
        await session.commit()
    except Exception as exc:  # noqa: BLE001
        await session.rollback()
        logger.exception(
            "Failed to save re-uploaded ledger: case_id=%s, side=%s, file=%s",
            case_id, side, filename,
        )
        raise HTTPException(
            status_code=422,
            detail=(
                "Could not save the uploaded ledger. The file may contain a value "
                f"the system cannot store. Details: {type(exc).__name__}: {str(exc)[:300]}"
            ),
        )

    logger.info(
        "Ledger re-uploaded: case_id=%s, side=%s, entries=%d, file=%s, user=%s",
        case_id, side, len(result.entries), filename, current_user.username,
    )
    return {
        "message": f"Re-uploaded {len(result.entries)} {side} entries from '{filename}'.",
        "case_id": str(case_id),
        "side": side,
        "entries_parsed": len(result.entries),
    }
