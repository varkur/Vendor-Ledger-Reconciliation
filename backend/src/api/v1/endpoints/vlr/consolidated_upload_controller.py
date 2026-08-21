"""
Consolidated multi-vendor ledger upload — auto-detect flow.

Lets a user upload a single company ledger covering MANY vendors (identified
by a PAN or vendor/party-code column) WITHOUT manually selecting each vendor
first. The vendor list is derived from the file itself by matching each
unique PAN against the vendor master.

Flow:
  1. POST /preview-ledger-upload   — parse + match against vendor master.
     Nothing is created yet. Returns matched vendors, and any PANs in the
     file that don't exist in the vendor master ("missing_vendors").
  2. If there are missing_vendors, the frontend shows a popup:
       - "Proceed anyway" -> POST /confirm-ledger-upload {proceed_with_missing: true}
       - "Fix masters first" -> DELETE /discard-ledger-upload/{staging_id}
     If there are no missing_vendors, the frontend can confirm immediately.
  3. POST /confirm-ledger-upload — creates the ReconciliationRequest + one
     case per MATCHED vendor (missing ones are always excluded — there's no
     vendor record to attach a case to), splits the ledger rows into the
     right case, and optionally sends vendor invites.

Nothing touches vlr_reconciliation_requests / vlr_reconciliation_cases until
step 3 runs, so discarding at step 2 leaves no partial state behind.
"""

import json
import logging
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID, uuid4

from typing import Self

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.v1.dependencies import get_current_active_user
from src.api.v1.schemas.vlr.request_schemas import (
    MatchingPreferencesSchema,
    ReconciliationRequestResponse,
)
from src.domain.entities.user import User
from src.domain.exceptions.vlr import FileValidationException, OverlappingPeriodException
from src.domain.services.vlr.company_ledger_split_service import (
    build_split_ledger_file,
    match_entries_to_vendors,
)
from src.domain.services.vlr.file_parser_service import FileParserService
from src.domain.services.vlr.ledger_ingestion_service import (
    save_company_file_headers,
    store_company_entries,
)
from src.domain.services.vlr.request_manager_service import (
    MatchingPreferences,
    RequestCreateDTO,
    RequestManagerService,
)
from src.infrastructure.database.models.vlr.ledger_upload_staging_model import (
    LedgerUploadStagingModel,
)
from src.infrastructure.database.models.vlr.reconciliation_case_model import (
    ReconciliationCaseModel,
)
from src.infrastructure.database.models.vlr.vendor_model import VendorModel
from src.infrastructure.database.repositories.vlr.case_repository_impl import (
    CaseRepositoryImpl,
)
from src.infrastructure.database.repositories.vlr.request_repository_impl import (
    RequestRepositoryImpl,
)
from src.infrastructure.database.repositories.vlr.vendor_repository_impl import (
    VendorRepositoryImpl,
)
from src.infrastructure.database.session import get_db_session
from src.infrastructure.security.permission_manager import require_permission

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/vlr/reconciliation-requests",
    tags=["VLR - Consolidated Ledger Upload"],
)

MAX_FILE_SIZE = 50 * 1024 * 1024
ALLOWED_EXTENSIONS = (".csv", ".xlsx", ".xls")
STAGING_TTL_HOURS = 24


# ──────────────────────────────────────────────────────────────────────
# Schemas
# ──────────────────────────────────────────────────────────────────────


class LedgerUploadRequestConfig(BaseModel):
    """Request settings for the auto-detected multi-vendor request (everything
    the manual CreateRequestRequest needs, except vendor_ids)."""

    company_code: str = Field(..., min_length=1, max_length=20)
    fiscal_year: str = Field(..., min_length=1, max_length=10)
    period_start: date
    period_end: date
    title: str | None = Field(default=None, max_length=255)
    tolerance_amount: Decimal = Field(default=Decimal("0"), ge=0)
    tds_percentage: Decimal = Field(default=Decimal("0"), ge=0, le=100)
    gst_percentage: Decimal = Field(default=Decimal("0"), ge=0, le=100)
    matching_preferences: MatchingPreferencesSchema | None = None
    assigned_manager_id: UUID | None = None

    @model_validator(mode="after")
    def validate_date_range(self) -> Self:
        if self.period_start >= self.period_end:
            raise ValueError("period_start must be before period_end")
        if self.period_end > date.today():
            raise ValueError("period_end cannot be in the future")
        return self


class MatchedVendorInfo(BaseModel):
    """A vendor found in the master data for a PAN/code detected in the file."""

    vendor_id: UUID
    vendor_code: str
    vendor_name: str
    identifier_value: str
    entry_count: int
    is_active: bool


class MissingVendorInfo(BaseModel):
    """A PAN/vendor-code found in the file with NO matching vendor master record."""

    identifier_value: str
    entry_count: int


class PreviewLedgerUploadResponse(BaseModel):
    """Result of parsing + matching a consolidated ledger, before any request/case is created."""

    staging_id: UUID
    filename: str
    identifier_column: str | None
    total_entries: int
    matched_vendors: list[MatchedVendorInfo] = Field(default_factory=list)
    missing_vendors: list[MissingVendorInfo] = Field(default_factory=list)
    blank_identifier_entry_count: int = 0
    expires_at: datetime


class ConfirmLedgerUploadRequest(BaseModel):
    """Body for confirming (or the user choosing to proceed with) a staged upload."""

    staging_id: UUID
    proceed_with_missing: bool = Field(
        default=False,
        description=(
            "If the preview reported missing_vendors, this must be true to "
            "proceed anyway (excluding those vendors). If false and there "
            "were missing vendors, the confirm call is rejected — the "
            "frontend should call discard instead."
        ),
    )
    auto_notify_vendors: bool = Field(default=False)


class ConfirmLedgerUploadResponse(BaseModel):
    """Result of confirming a staged consolidated upload."""

    request_id: UUID
    request_number: str | None = None
    matched_vendor_count: int
    entries_stored: int
    skipped_missing_vendor_count: int
    invites_sent: int = 0


# ──────────────────────────────────────────────────────────────────────
# Preview
# ──────────────────────────────────────────────────────────────────────


@router.post(
    "/preview-ledger-upload",
    response_model=PreviewLedgerUploadResponse,
    summary="Preview a consolidated multi-vendor ledger upload (no request created yet)",
    dependencies=[Depends(require_permission("vlr.requests.write"))],
)
async def preview_ledger_upload(
    file: UploadFile = File(..., description="Consolidated company ledger file (CSV, XLSX, or XLS)"),
    config: str = Form(..., description="JSON-encoded LedgerUploadRequestConfig"),
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db_session),
) -> PreviewLedgerUploadResponse:
    """
    POST /api/v1/vlr/reconciliation-requests/preview-ledger-upload

    Parses the uploaded file, detects the PAN/vendor-code column, and matches
    each unique value against the vendor master for `company_code`. No
    request or cases are created — the result is staged so a follow-up call
    to /confirm-ledger-upload (or /discard-ledger-upload) can act on it.
    """
    try:
        cfg_data = json.loads(config)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid JSON in 'config' field: {exc.msg}",
        )
    try:
        request_config = LedgerUploadRequestConfig(**cfg_data)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Configuration validation failed: {exc}",
        )

    filename = file.filename or ""
    if not filename.lower().endswith(ALLOWED_EXTENSIONS):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type. Please upload one of: {', '.join(ALLOWED_EXTENSIONS)}",
        )

    file_content = await file.read()
    if not file_content:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded file is empty.")
    if len(file_content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="File size exceeds the maximum allowed size of 50MB.",
        )

    parser = FileParserService(max_file_size_bytes=MAX_FILE_SIZE)
    try:
        result = parser.validate_and_parse(file_content, filename)
    except FileValidationException as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"File validation failed: {'; '.join(e.errors)}",
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Failed to parse file: {str(e)}",
        )

    if not result.is_valid:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"File validation errors: {'; '.join(result.errors)}",
        )
    if not result.entries:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No valid entries found in the uploaded file.",
        )

    # Match against the FULL vendor master for this company (any status —
    # inactive-vendor rejection happens at confirm time, same as the manual
    # vendor-selection flow, so the preview can still show the user what
    # would happen).
    vendor_stmt = select(VendorModel).where(
        VendorModel.company_code == request_config.company_code,
        VendorModel.is_deleted == False,  # noqa: E712
    )
    vendor_result = await session.execute(vendor_stmt)
    all_vendors = list(vendor_result.scalars().all())

    match = match_entries_to_vendors(result.entries, result.raw_headers, all_vendors)

    if match.identifier_column is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "Couldn't automatically detect a PAN or vendor/party code "
                "column in this file. Add a 'PAN' (or 'Vendor Code') column "
                "identifying which vendor each row belongs to, or upload "
                "this file against a single vendor's request instead."
            ),
        )

    vendors_by_id = {v.id: v for v in all_vendors}
    matched_vendors: list[MatchedVendorInfo] = []
    for vendor_id, entries in match.matched_by_vendor_id.items():
        vendor = vendors_by_id[vendor_id]
        # Show whichever field actually matched (PAN might be stored in
        # vendor_code for some vendors, or vice versa — see match_entries_to_vendors).
        identifier_value = vendor.pan or vendor.vendor_code or ""
        matched_vendors.append(MatchedVendorInfo(
            vendor_id=vendor.id,
            vendor_code=vendor.vendor_code,
            vendor_name=vendor.name,
            identifier_value=identifier_value or "",
            entry_count=len(entries),
            is_active=(vendor.status == "active"),
        ))
    matched_vendors.sort(key=lambda v: v.vendor_name)

    missing_vendors = [
        MissingVendorInfo(identifier_value=key, entry_count=len(entries))
        for key, entries in sorted(match.unmatched_by_identifier.items())
    ]

    # ─── Stage the upload (nothing created in requests/cases yet) ─────────
    expires_at = datetime.now(timezone.utc) + timedelta(hours=STAGING_TTL_HOURS)
    staging = LedgerUploadStagingModel(
        company_code=request_config.company_code,
        filename=filename,
        content_type=file.content_type or "application/octet-stream",
        content=file_content,
        request_params=cfg_data,
        expires_at=expires_at,
        created_by=current_user.username,
        modified_by=current_user.username,
    )
    session.add(staging)
    await session.flush()
    await session.commit()

    return PreviewLedgerUploadResponse(
        staging_id=staging.id,
        filename=filename,
        identifier_column=match.identifier_column,
        total_entries=len(result.entries),
        matched_vendors=matched_vendors,
        missing_vendors=missing_vendors,
        blank_identifier_entry_count=len(match.blank_identifier_entries),
        expires_at=expires_at,
    )


# ──────────────────────────────────────────────────────────────────────
# Confirm
# ──────────────────────────────────────────────────────────────────────


@router.post(
    "/confirm-ledger-upload",
    response_model=ConfirmLedgerUploadResponse,
    summary="Confirm a staged consolidated ledger upload — creates the request + cases",
    dependencies=[Depends(require_permission("vlr.requests.write"))],
)
async def confirm_ledger_upload(
    body: ConfirmLedgerUploadRequest,
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db_session),
) -> ConfirmLedgerUploadResponse:
    """
    POST /api/v1/vlr/reconciliation-requests/confirm-ledger-upload

    Re-parses the staged file, re-matches against the (possibly just-fixed)
    vendor master, creates the ReconciliationRequest + one case per matched
    vendor, splits the ledger rows into the right case, and deletes the
    staging row. Vendors that still don't match are always skipped (there's
    no vendor record to attach a case to) — `proceed_with_missing` only
    controls whether that's allowed to happen silently or rejected.
    """
    staging_stmt = select(LedgerUploadStagingModel).where(
        LedgerUploadStagingModel.id == body.staging_id
    )
    staging_result = await session.execute(staging_stmt)
    staging = staging_result.scalar_one_or_none()
    if staging is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Staged upload not found or already confirmed/discarded. Please re-upload.",
        )

    if staging.expires_at < datetime.now(timezone.utc):
        await session.delete(staging)
        await session.commit()
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="This staged upload has expired. Please re-upload the file.",
        )

    request_config = LedgerUploadRequestConfig(**staging.request_params)

    parser = FileParserService(max_file_size_bytes=MAX_FILE_SIZE)
    try:
        result = parser.validate_and_parse(staging.content, staging.filename)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Failed to re-parse staged file: {str(e)}",
        )

    vendor_stmt = select(VendorModel).where(
        VendorModel.company_code == request_config.company_code,
        VendorModel.is_deleted == False,  # noqa: E712
    )
    vendor_result = await session.execute(vendor_stmt)
    all_vendors = list(vendor_result.scalars().all())

    match = match_entries_to_vendors(result.entries, result.raw_headers, all_vendors)

    if not match.matched_by_vendor_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="None of the PANs/vendor codes in this file match any vendor in the master data.",
        )

    if match.unmatched_by_identifier and not body.proceed_with_missing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"{len(match.unmatched_by_identifier)} PAN(s)/vendor code(s) in this file "
                "don't exist in the vendor master. Fix the vendor master and re-upload, "
                "or resubmit with proceed_with_missing=true to continue with only the "
                "matched vendors."
            ),
        )

    vendors_by_id = {v.id: v for v in all_vendors}
    matching_prefs = None
    if request_config.matching_preferences:
        matching_prefs = MatchingPreferences(
            exact_match_enabled=request_config.matching_preferences.exact_match_enabled,
            tolerance_match_enabled=request_config.matching_preferences.tolerance_match_enabled,
            fuzzy_reference_enabled=request_config.matching_preferences.fuzzy_reference_enabled,
            one_to_many_enabled=request_config.matching_preferences.one_to_many_enabled,
            many_to_one_enabled=request_config.matching_preferences.many_to_one_enabled,
        )

    dto = RequestCreateDTO(
        company_code=request_config.company_code,
        fiscal_year=request_config.fiscal_year,
        period_start=request_config.period_start,
        period_end=request_config.period_end,
        vendor_ids=list(match.matched_by_vendor_id.keys()),
        title=request_config.title,
        tolerance_amount=request_config.tolerance_amount,
        tds_percentage=request_config.tds_percentage,
        gst_percentage=request_config.gst_percentage,
        matching_preferences=matching_prefs,
        assigned_manager_id=request_config.assigned_manager_id,
        created_by=current_user.username or str(current_user.id),
    )

    service = RequestManagerService(
        request_repository=RequestRepositoryImpl(session),
        case_repository=CaseRepositoryImpl(session),
        vendor_repository=VendorRepositoryImpl(session),
    )

    try:
        request_obj = await service.create_request(dto)
    except OverlappingPeriodException as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=e.message or "One or more matched vendors already have an overlapping request for this period.",
        )
    except Exception as e:
        from src.domain.exceptions.vlr import VendorInactiveException
        if isinstance(e, VendorInactiveException):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=e.message)
        logger.exception("Unexpected error confirming consolidated ledger upload: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected error occurred while creating the request: {str(e)}",
        )

    request_id = request_obj.id

    # ─── Fetch the newly created cases (one per matched vendor) ───────────
    case_stmt = select(ReconciliationCaseModel).where(
        ReconciliationCaseModel.request_id == request_id,
        ReconciliationCaseModel.is_deleted == False,  # noqa: E712
    )
    case_result = await session.execute(case_stmt)
    cases = list(case_result.scalars().all())
    case_by_vendor_id = {c.vendor_id: c for c in cases}

    entries_stored = 0
    notified_case_ids: list[UUID] = []
    import os as _os

    from src.api.v1.endpoints.vlr.column_mapping_controller import (
        store_original_ledger_file,
    )

    for vendor_id, entries in match.matched_by_vendor_id.items():
        case = case_by_vendor_id.get(vendor_id)
        if case is None:
            continue
        store_company_entries(session, case.id, entries, current_user.username)
        entries_stored += len(entries)
        await save_company_file_headers(session, case.id, result.raw_headers)
        # Store ONLY this vendor's rows, not the consolidated file's raw
        # bytes — otherwise "Download" would return every other vendor's
        # entries too (see build_split_ledger_file). Format (xlsx/csv) is
        # preserved from the original upload instead of always writing CSV.
        split_bytes, split_filename = build_split_ledger_file(
            entries, result.raw_headers, staging.filename,
        )
        await store_original_ledger_file(
            session, case.id, "company", split_filename, split_bytes,
            modified_by=current_user.username,
        )
        notified_case_ids.append(case.id)

    await session.delete(staging)
    await session.flush()
    await session.commit()

    # Auto-send the vendor ledger request invite to every case just created
    # from this consolidated upload — primary contact "To", every other
    # vendor contact CC'd — same as the plain create-request flow. No
    # longer gated behind auto_notify_vendors (which defaulted to false and
    # every frontend call site omitted it, so invites never went out
    # automatically here). Best-effort: email misconfiguration or SMTP
    # failure must not fail the upload confirmation, since the request/
    # cases are already committed above.
    invites_sent = 0
    if notified_case_ids:
        from src.api.v1.endpoints.vlr.request_controller import _send_invites_for_cases

        notify_cases = [c for c in cases if c.id in notified_case_ids]
        try:
            invite_response = await _send_invites_for_cases(
                session, request_id, request_config.company_code, request_obj,
                notify_cases, [], "",
            )
            invites_sent = invite_response.emails_sent
        except HTTPException as e:
            logger.warning(
                "Auto-invite skipped for consolidated-upload request %s: %s",
                request_id, e.detail,
            )
        except Exception:
            logger.exception(
                "Auto-invite failed for consolidated-upload request %s", request_id
            )

    return ConfirmLedgerUploadResponse(
        request_id=request_id,
        request_number=getattr(request_obj, "request_number", None),
        matched_vendor_count=len(match.matched_by_vendor_id),
        entries_stored=entries_stored,
        skipped_missing_vendor_count=len(match.unmatched_by_identifier),
        invites_sent=invites_sent,
    )


# ──────────────────────────────────────────────────────────────────────
# Discard
# ──────────────────────────────────────────────────────────────────────


@router.delete(
    "/discard-ledger-upload/{staging_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Discard a staged consolidated ledger upload without creating anything",
    dependencies=[Depends(require_permission("vlr.requests.write"))],
)
async def discard_ledger_upload(
    staging_id: UUID,
    session: AsyncSession = Depends(get_db_session),
) -> None:
    """
    DELETE /api/v1/vlr/reconciliation-requests/discard-ledger-upload/{staging_id}

    Used when the user chooses "fix vendor masters first" in response to a
    preview that reported missing vendors. Since nothing was ever created in
    vlr_reconciliation_requests / vlr_reconciliation_cases, this is a plain
    delete of the staged upload — no rollback of business data needed.
    """
    staging_stmt = select(LedgerUploadStagingModel).where(
        LedgerUploadStagingModel.id == staging_id
    )
    staging_result = await session.execute(staging_stmt)
    staging = staging_result.scalar_one_or_none()
    if staging is not None:
        await session.delete(staging)
        await session.commit()
