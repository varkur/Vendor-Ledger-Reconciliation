"""
Data Transformation API endpoint.
Triggers the full transformation pipeline for a reconciliation case.

Routes:
- POST /api/v1/vlr/transform/{case_id}  — Trigger transformation pipeline

Requirements: 1.1, 2.1, 3.1, 4.1, 5.1, 6.1, 7.1
"""

import logging
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.v1.dependencies import get_current_active_user
from src.api.v1.schemas.vlr.transformation_schemas import TransformationSummaryResponse
from src.domain.entities.user import User
from src.domain.services.vlr.data_transformation_service import (
    DataTransformationService,
    LedgerEntry,
    RawSAPEntry,
)
from src.infrastructure.database.models.vlr.ledger_entry_model import LedgerEntryModel
from src.infrastructure.database.repositories.vlr.case_repository_impl import (
    CaseRepositoryImpl,
)
from src.infrastructure.database.repositories.vlr.config_repository_impl import (
    ConfigRepositoryImpl,
)
from src.infrastructure.database.repositories.vlr.ledger_entry_repository_impl import (
    LedgerEntryRepositoryImpl,
)
from src.infrastructure.database.session import get_db_session
from src.infrastructure.security.permission_manager import require_permission

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/vlr/transform", tags=["VLR - Data Transformation"])


# ──────────────────────────────────────────────────────────────────────
# Dependencies
# ──────────────────────────────────────────────────────────────────────


def _get_case_repository(
    session: AsyncSession = Depends(get_db_session),
) -> CaseRepositoryImpl:
    """FastAPI dependency — creates CaseRepository."""
    return CaseRepositoryImpl(session)


def _get_ledger_entry_repository(
    session: AsyncSession = Depends(get_db_session),
) -> LedgerEntryRepositoryImpl:
    """FastAPI dependency — creates LedgerEntryRepository."""
    return LedgerEntryRepositoryImpl(session)


def _get_config_repository(
    session: AsyncSession = Depends(get_db_session),
) -> ConfigRepositoryImpl:
    """FastAPI dependency — creates ConfigRepository."""
    return ConfigRepositoryImpl(session)


def _get_data_transformation_service(
    config_repo: ConfigRepositoryImpl = Depends(_get_config_repository),
) -> DataTransformationService:
    """FastAPI dependency — creates DataTransformationService with injected config repo."""
    return DataTransformationService(config_repository=config_repo)


# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────


def _model_to_raw_sap_entry(model: LedgerEntryModel) -> RawSAPEntry:
    """
    Convert a LedgerEntryModel to a RawSAPEntry for transformation processing.

    Maps model fields to the SAP entry structure expected by the
    DataTransformationService.
    """
    return RawSAPEntry(
        belnr=model.document_number or "",
        gjahr="",
        buzei="",
        zuonr=model.assignment_number or "",
        xblnr=model.reference_number or "",
        blart=model.document_type or "",
        budat=model.posting_date.isoformat() if model.posting_date else "",
        dmbtr=Decimal(str(model.amount)) if model.amount is not None else Decimal("0"),
        wrbtr=Decimal(str(model.amount)) if model.amount is not None else Decimal("0"),
        waers=model.currency or "INR",
        shkzg="",  # Will be determined from amount sign or existing indicator
        augbl=model.clearing_document or "",
        augdt=model.clearing_date.isoformat() if model.clearing_date else "",
        lifnr="",
        bukrs="",
    )


def _model_to_ledger_entry(model: LedgerEntryModel, adjusted_amount: Decimal) -> LedgerEntry:
    """
    Convert a LedgerEntryModel to a LedgerEntry for balance calculation.

    Uses the already-computed adjusted_amount for the entry.
    """
    return LedgerEntry(
        posting_date=model.posting_date,
        adjusted_amount=adjusted_amount,
        side=model.side,
        document_number=model.document_number or "",
        reference_number=model.reference_number or "",
        clearing_date=model.clearing_date,
        document_type=model.document_type or "",
        entry_id=str(model.id),
        transaction_currency=model.currency or "INR",
        local_currency_amount=None,
    )


# ──────────────────────────────────────────────────────────────────────
# Endpoints
# ──────────────────────────────────────────────────────────────────────


@router.post(
    "/{case_id}",
    response_model=TransformationSummaryResponse,
    status_code=status.HTTP_200_OK,
    summary="Trigger data transformation pipeline for a case",
    dependencies=[Depends(require_permission("vlr.cases.write"))],
)
async def trigger_transformation(
    case_id: UUID,
    current_user: User = Depends(get_current_active_user),
    case_repo: CaseRepositoryImpl = Depends(_get_case_repository),
    ledger_repo: LedgerEntryRepositoryImpl = Depends(_get_ledger_entry_repository),
    config_repo: ConfigRepositoryImpl = Depends(_get_config_repository),
    service: DataTransformationService = Depends(_get_data_transformation_service),
    session: AsyncSession = Depends(get_db_session),
) -> TransformationSummaryResponse:
    """
    POST /api/v1/vlr/transform/{case_id}

    Triggers the full data transformation pipeline for the specified
    reconciliation case. The pipeline:
    1. Derives invoice numbers for each entry (ZUONR > XBLNR > BELNR)
    2. Applies sign adjustment (H → positive, S → negative)
    3. Calculates opening/closing balances
    4. Tags TDS entries and links to parent invoices
    5. Classifies document types
    6. Handles multi-currency entries

    Updates all ledger entries in the database with transformation results
    and returns a summary of the operations performed.

    Requirements: 1.1, 2.1, 3.1, 4.1, 5.1, 6.1, 7.1
    """
    # ─── Verify case exists ─────────────────────────────────────────────
    case = await case_repo.get_by_id(case_id)
    if case is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Reconciliation case {case_id} not found.",
        )

    # ─── Load period dates from parent request ──────────────────────────
    from sqlalchemy import select
    from src.infrastructure.database.models.vlr.reconciliation_request_model import (
        ReconciliationRequestModel,
    )

    request_stmt = select(ReconciliationRequestModel).where(
        ReconciliationRequestModel.id == case.request_id
    )
    request_result = await session.execute(request_stmt)
    request_record = request_result.scalar_one_or_none()

    if request_record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Parent request for case {case_id} not found.",
        )

    period_start = request_record.period_start
    period_end = request_record.period_end

    # ─── Load all ledger entries for the case ───────────────────────────
    entries_stmt = select(LedgerEntryModel).where(
        LedgerEntryModel.case_id == case_id
    )
    entries_result = await session.execute(entries_stmt)
    all_entries = list(entries_result.scalars().all())

    if not all_entries:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"No ledger entries found for case {case_id}. Upload data before running transformation.",
        )

    # ─── Get TDS document types from config ─────────────────────────────
    tds_document_types = await config_repo.get_tds_document_types()

    # ─── Run transformation pipeline ────────────────────────────────────
    invoices_derived = 0
    sign_adjustments_applied = 0
    multi_currency_entries = 0
    document_types_classified = 0
    company_entries_count = 0
    vendor_entries_count = 0

    # Collect LedgerEntry objects for balance calculations
    transformed_ledger_entries: list[LedgerEntry] = []

    for entry_model in all_entries:
        raw_entry = _model_to_raw_sap_entry(entry_model)

        # Track sides
        if entry_model.side == "company":
            company_entries_count += 1
        elif entry_model.side == "vendor":
            vendor_entries_count += 1

        update_data: dict = {}

        # 1. Invoice Number Derivation (Req 1.1, 1.2, 1.3, 1.4, 1.5)
        derived = service.derive_invoice_number(raw_entry)
        update_data["derived_invoice_number"] = derived.invoice_number
        update_data["raw_reference"] = derived.raw_value
        update_data["invoice_source_field"] = (
            derived.source_field.value if derived.source_field else None
        )
        if derived.invoice_number:
            invoices_derived += 1

        # 2. Sign Adjustment (Req 2.1, 2.2, 2.3, 2.4)
        # Determine SHKZG from existing indicator or infer from amount sign
        shkzg = entry_model.shkzg_indicator or ""
        original_amount = Decimal(str(model_amount)) if (model_amount := entry_model.amount) is not None else Decimal("0")

        if not shkzg:
            # Infer from amount: positive → H (credit to vendor), negative → S (debit)
            shkzg = "H" if original_amount >= 0 else "S"

        try:
            adjusted = service.apply_sign_adjustment(abs(original_amount), shkzg)
            update_data["original_amount"] = abs(original_amount)
            update_data["shkzg_indicator"] = shkzg
            update_data["adjusted_amount"] = adjusted
            sign_adjustments_applied += 1
        except ValueError:
            # If sign adjustment fails, use original amount
            adjusted = original_amount
            update_data["original_amount"] = abs(original_amount)
            update_data["adjusted_amount"] = original_amount

        # 3. Multi-Currency Handling (Req 6.1)
        multi_currency = service.prepare_multi_currency_entry(raw_entry)
        update_data["transaction_currency"] = multi_currency.transaction_currency
        update_data["local_currency_amount"] = multi_currency.local_currency_amount
        if multi_currency.transaction_currency != "INR":
            multi_currency_entries += 1

        # 4. Document Type Classification (Req 7.1, 7.2, 7.3, 7.4)
        if entry_model.document_type:
            category = await service.classify_document_type_async(
                entry_model.document_type
            )
            update_data["document_category"] = category
            document_types_classified += 1

        # Apply update to the model directly (batch flush at end)
        for key, value in update_data.items():
            setattr(entry_model, key, value)

        # Build LedgerEntry for balance and TDS calculations
        ledger_entry = _model_to_ledger_entry(entry_model, adjusted)
        ledger_entry.local_currency_amount = multi_currency.local_currency_amount
        transformed_ledger_entries.append(ledger_entry)

    # 5. TDS Tagging and Linking (Req 5.1, 5.2, 5.3)
    service.tag_tds_entries(transformed_ledger_entries, tds_document_types)

    # Apply TDS tagging results back to models
    tds_entries_found = 0
    tds_entries_linked = 0
    for ledger_entry, entry_model in zip(
        transformed_ledger_entries, all_entries, strict=True
    ):
        entry_model.is_tds = ledger_entry.is_tds
        if ledger_entry.is_tds:
            tds_entries_found += 1
            if ledger_entry.tds_parent_entry_id:
                entry_model.tds_parent_entry_id = ledger_entry.tds_parent_entry_id
                tds_entries_linked += 1

    # 6. Calculate Opening/Closing Balances (Req 3.1, 3.2, 3.3, 4.1, 4.2, 4.3)
    company_opening = service.calculate_opening_balance(
        transformed_ledger_entries, period_start, "company"
    )
    company_closing = service.calculate_closing_balance(
        company_opening, transformed_ledger_entries, period_start, period_end, "company"
    )
    vendor_opening = service.calculate_opening_balance(
        transformed_ledger_entries, period_start, "vendor"
    )
    vendor_closing = service.calculate_closing_balance(
        vendor_opening, transformed_ledger_entries, period_start, period_end, "vendor"
    )

    # ─── Flush all changes to the database ──────────────────────────────
    await session.flush()

    logger.info(
        "Transformation pipeline completed: case_id=%s, entries=%d, "
        "invoices_derived=%d, tds_found=%d, multi_currency=%d",
        case_id,
        len(all_entries),
        invoices_derived,
        tds_entries_found,
        multi_currency_entries,
    )

    return TransformationSummaryResponse(
        case_id=case_id,
        entries_processed=len(all_entries),
        company_entries_processed=company_entries_count,
        vendor_entries_processed=vendor_entries_count,
        invoices_derived=invoices_derived,
        sign_adjustments_applied=sign_adjustments_applied,
        company_opening_balance=company_opening,
        company_closing_balance=company_closing,
        vendor_opening_balance=vendor_opening,
        vendor_closing_balance=vendor_closing,
        tds_entries_found=tds_entries_found,
        tds_entries_linked=tds_entries_linked,
        multi_currency_entries=multi_currency_entries,
        document_types_classified=document_types_classified,
        status="completed",
        message=(
            f"Transformation pipeline completed successfully. "
            f"Processed {len(all_entries)} entries "
            f"({company_entries_count} company, {vendor_entries_count} vendor)."
        ),
    )
