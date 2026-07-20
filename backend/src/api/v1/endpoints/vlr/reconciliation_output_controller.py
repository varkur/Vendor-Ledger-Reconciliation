"""
Reconciliation Output API endpoints.
Thin controller — queries match results and ledger entries for the 5-tab output view.

Routes:
- GET  /api/v1/vlr/reconciliation/{case_id}/matched           — Tab 1: Matched items
- GET  /api/v1/vlr/reconciliation/{case_id}/confirmation      — Tab 2: Needs confirmation
- GET  /api/v1/vlr/reconciliation/{case_id}/unmatched-company — Tab 3: Unmatched CL
- GET  /api/v1/vlr/reconciliation/{case_id}/unmatched-vendor  — Tab 4: Unmatched VL
- GET  /api/v1/vlr/reconciliation/{case_id}/summary           — Tab 5: Differences
- POST /api/v1/vlr/reconciliation/{case_id}/confirm           — Accept/reject match

Requirements: 18.1, 19.1, 20.1, 21.1, 22.1
"""

import logging
import math
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.v1.dependencies import get_current_active_user
from src.api.v1.schemas.vlr.reconciliation_output_schemas import (
    BalanceComparison,
    ConfirmAction,
    ConfirmMatchRequest,
    ConfirmMatchResponse,
    ConfirmationEntryResponse,
    ConfirmationItemsResponse,
    DifferencesSummaryResponse,
    MatchedEntryResponse,
    MatchedItemsResponse,
    PaginationMeta,
    SortOrder,
    TypeTotal,
    UnmatchedCompanyEntryResponse,
    UnmatchedCompanyResponse,
    UnmatchedVendorEntryResponse,
    UnmatchedVendorResponse,
)
from src.domain.entities.user import User
from src.infrastructure.database.models.vlr.ledger_entry_model import LedgerEntryModel
from src.infrastructure.database.models.vlr.match_result_model import MatchResultModel
from src.infrastructure.database.models.vlr.reconciliation_case_model import (
    ReconciliationCaseModel,
)
from src.infrastructure.database.session import get_db_session
from src.infrastructure.security.permission_manager import require_permission
from src.domain.services.vlr.audit_trail_service import (
    AuditEvent,
    AuditEventType,
    AuditTrailService,
)
from src.infrastructure.database.repositories.vlr.audit_trail_repository_impl import (
    AuditTrailRepositoryImpl,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/vlr/reconciliation", tags=["VLR - Reconciliation Output"]
)


# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────


async def _verify_case_exists(
    case_id: UUID, session: AsyncSession
) -> ReconciliationCaseModel:
    """Verify a reconciliation case exists and is not deleted."""
    stmt = select(ReconciliationCaseModel).where(
        and_(
            ReconciliationCaseModel.id == str(case_id),
            ReconciliationCaseModel.is_deleted == False,  # noqa: E712
        )
    )
    result = await session.execute(stmt)
    case = result.scalar_one_or_none()
    if case is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Reconciliation case '{case_id}' not found.",
        )
    return case


def _build_pagination(page: int, page_size: int, total: int) -> PaginationMeta:
    """Build pagination metadata."""
    return PaginationMeta(
        page=page,
        page_size=page_size,
        total_items=total,
        total_pages=max(1, math.ceil(total / page_size)),
    )


async def _get_entry_reference(
    entry_ids: list | None, session: AsyncSession
) -> tuple[str | None, Decimal | None]:
    """Get first entry's reference and amount from a list of entry IDs."""
    if not entry_ids:
        return None, None
    first_id = entry_ids[0] if entry_ids else None
    if first_id is None:
        return None, None
    stmt = select(LedgerEntryModel).where(LedgerEntryModel.id == str(first_id))
    result = await session.execute(stmt)
    entry = result.scalar_one_or_none()
    if entry is None:
        return None, None
    ref = entry.derived_invoice_number or entry.reference_number or entry.document_number
    amount = Decimal(str(entry.amount)) if entry.amount is not None else None
    return ref, amount


# ──────────────────────────────────────────────────────────────────────
# Tab 1: Matched Items
# ──────────────────────────────────────────────────────────────────────


@router.get(
    "/{case_id}/matched",
    response_model=MatchedItemsResponse,
    status_code=status.HTTP_200_OK,
    summary="Get matched items (Tab 1)",
    dependencies=[Depends(require_permission("vlr.cases.read"))],
)
async def get_matched_items(
    case_id: UUID,
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    sort_by: str = Query("pass_number", description="Sort field"),
    sort_order: SortOrder = Query(SortOrder.ASC, description="Sort direction"),
    match_type_filter: str | None = Query(None, description="Filter by match type"),
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db_session),
) -> MatchedItemsResponse:
    """
    GET /api/v1/vlr/reconciliation/{case_id}/matched

    Returns all Pass 1 and Pass 2 matches (confirmed matches).
    Supports pagination, sorting, and filtering.

    Requirement 18.1: Display matched items with match type and confidence.
    """
    await _verify_case_exists(case_id, session)

    # Build base query: confirmed matches (Pass 1 & 2) OR all confirmed
    base_query = select(MatchResultModel).where(
        and_(
            MatchResultModel.case_id == str(case_id),
            MatchResultModel.is_confirmed == True,  # noqa: E712
            MatchResultModel.pass_number.in_([1, 2]),
        )
    )

    if match_type_filter:
        base_query = base_query.where(
            MatchResultModel.match_type == match_type_filter
        )

    # Count total
    count_stmt = select(func.count()).select_from(base_query.subquery())
    total_result = await session.execute(count_stmt)
    total = total_result.scalar() or 0

    # Apply sorting
    sort_column = getattr(MatchResultModel, sort_by, MatchResultModel.pass_number)
    if sort_order == SortOrder.DESC:
        base_query = base_query.order_by(sort_column.desc())
    else:
        base_query = base_query.order_by(sort_column.asc())

    # Apply pagination
    offset = (page - 1) * page_size
    base_query = base_query.offset(offset).limit(page_size)

    result = await session.execute(base_query)
    matches = list(result.scalars().all())

    # Build response items
    items: list[MatchedEntryResponse] = []
    for match in matches:
        cl_ref, cl_amount = await _get_entry_reference(
            match.company_entry_ids, session
        )
        vl_ref, vl_amount = await _get_entry_reference(
            match.vendor_entry_ids, session
        )
        difference = match.difference_amount
        if difference is None and cl_amount is not None and vl_amount is not None:
            difference = cl_amount - vl_amount

        items.append(
            MatchedEntryResponse(
                match_id=match.id,
                cl_reference=cl_ref,
                cl_amount=cl_amount,
                vl_reference=vl_ref,
                vl_amount=vl_amount,
                difference=Decimal(str(difference)) if difference is not None else None,
                match_type=match.match_type,
                match_score=float(match.confidence_score),
                pass_number=match.pass_number,
                matched_amount=Decimal(str(match.matched_amount)),
            )
        )

    return MatchedItemsResponse(
        items=items,
        pagination=_build_pagination(page, page_size, total),
    )


# ──────────────────────────────────────────────────────────────────────
# Tab 2: Finance Confirmation Required
# ──────────────────────────────────────────────────────────────────────


@router.get(
    "/{case_id}/confirmation",
    response_model=ConfirmationItemsResponse,
    status_code=status.HTTP_200_OK,
    summary="Get entries awaiting finance confirmation (Tab 2)",
    dependencies=[Depends(require_permission("vlr.cases.read"))],
)
async def get_confirmation_items(
    case_id: UUID,
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    sort_by: str = Query("pass_number", description="Sort field"),
    sort_order: SortOrder = Query(SortOrder.ASC, description="Sort direction"),
    match_type_filter: str | None = Query(None, description="Filter by match type"),
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db_session),
) -> ConfirmationItemsResponse:
    """
    GET /api/v1/vlr/reconciliation/{case_id}/confirmation

    Returns all Pass 3, 4, 5, 6 matches that are not yet confirmed.
    These require finance user review (Accept/Reject/Clarify).

    Requirement 19.1: Display matches needing manual review.
    """
    await _verify_case_exists(case_id, session)

    base_query = select(MatchResultModel).where(
        and_(
            MatchResultModel.case_id == str(case_id),
            MatchResultModel.is_confirmed == False,  # noqa: E712
            MatchResultModel.pass_number.in_([3, 4, 5, 6]),
        )
    )

    if match_type_filter:
        base_query = base_query.where(
            MatchResultModel.match_type == match_type_filter
        )

    # Count total
    count_stmt = select(func.count()).select_from(base_query.subquery())
    total_result = await session.execute(count_stmt)
    total = total_result.scalar() or 0

    # Apply sorting
    sort_column = getattr(MatchResultModel, sort_by, MatchResultModel.pass_number)
    if sort_order == SortOrder.DESC:
        base_query = base_query.order_by(sort_column.desc())
    else:
        base_query = base_query.order_by(sort_column.asc())

    # Apply pagination
    offset = (page - 1) * page_size
    base_query = base_query.offset(offset).limit(page_size)

    result = await session.execute(base_query)
    matches = list(result.scalars().all())

    items: list[ConfirmationEntryResponse] = []
    for match in matches:
        cl_ref, cl_amount = await _get_entry_reference(
            match.company_entry_ids, session
        )
        vl_ref, vl_amount = await _get_entry_reference(
            match.vendor_entry_ids, session
        )
        difference = match.difference_amount
        if difference is None and cl_amount is not None and vl_amount is not None:
            difference = cl_amount - vl_amount

        items.append(
            ConfirmationEntryResponse(
                match_id=match.id,
                cl_reference=cl_ref,
                cl_amount=cl_amount,
                vl_reference=vl_ref,
                vl_amount=vl_amount,
                difference=Decimal(str(difference)) if difference is not None else None,
                match_type=match.match_type,
                match_score=float(match.confidence_score),
                pass_number=match.pass_number,
            )
        )

    return ConfirmationItemsResponse(
        items=items,
        pagination=_build_pagination(page, page_size, total),
    )


# ──────────────────────────────────────────────────────────────────────
# Tab 3: Unmatched Company Ledger
# ──────────────────────────────────────────────────────────────────────


@router.get(
    "/{case_id}/unmatched-company",
    response_model=UnmatchedCompanyResponse,
    status_code=status.HTTP_200_OK,
    summary="Get unmatched company ledger entries (Tab 3)",
    dependencies=[Depends(require_permission("vlr.cases.read"))],
)
async def get_unmatched_company(
    case_id: UUID,
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    sort_by: str = Query("posting_date", description="Sort field"),
    sort_order: SortOrder = Query(SortOrder.ASC, description="Sort direction"),
    document_type_filter: str | None = Query(
        None, description="Filter by document type"
    ),
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db_session),
) -> UnmatchedCompanyResponse:
    """
    GET /api/v1/vlr/reconciliation/{case_id}/unmatched-company

    Returns company ledger entries with no vendor match (match_id IS NULL).
    Actions available: Mark as Accepted, Raise as Dispute, Request Vendor to Add.

    Requirement 20.1: Display unmatched company entries.
    """
    await _verify_case_exists(case_id, session)

    base_query = select(LedgerEntryModel).where(
        and_(
            LedgerEntryModel.case_id == str(case_id),
            LedgerEntryModel.side == "company",
            LedgerEntryModel.match_id.is_(None),
        )
    )

    if document_type_filter:
        base_query = base_query.where(
            LedgerEntryModel.document_type == document_type_filter
        )

    # Count total
    count_stmt = select(func.count()).select_from(base_query.subquery())
    total_result = await session.execute(count_stmt)
    total = total_result.scalar() or 0

    # Apply sorting
    sort_column = getattr(LedgerEntryModel, sort_by, LedgerEntryModel.posting_date)
    if sort_order == SortOrder.DESC:
        base_query = base_query.order_by(sort_column.desc())
    else:
        base_query = base_query.order_by(sort_column.asc())

    # Apply pagination
    offset = (page - 1) * page_size
    base_query = base_query.offset(offset).limit(page_size)

    result = await session.execute(base_query)
    entries = list(result.scalars().all())

    items = [
        UnmatchedCompanyEntryResponse(
            entry_id=entry.id,
            document_number=entry.document_number,
            document_type=entry.document_type,
            document_category=entry.document_category,
            reference_number=entry.reference_number,
            posting_date=entry.posting_date,
            amount=Decimal(str(entry.amount)),
            currency=entry.currency,
            description=entry.description,
        )
        for entry in entries
    ]

    return UnmatchedCompanyResponse(
        items=items,
        pagination=_build_pagination(page, page_size, total),
    )


# ──────────────────────────────────────────────────────────────────────
# Tab 4: Unmatched Vendor Ledger
# ──────────────────────────────────────────────────────────────────────


@router.get(
    "/{case_id}/unmatched-vendor",
    response_model=UnmatchedVendorResponse,
    status_code=status.HTTP_200_OK,
    summary="Get unmatched vendor ledger entries (Tab 4)",
    dependencies=[Depends(require_permission("vlr.cases.read"))],
)
async def get_unmatched_vendor(
    case_id: UUID,
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    sort_by: str = Query("posting_date", description="Sort field"),
    sort_order: SortOrder = Query(SortOrder.ASC, description="Sort direction"),
    document_type_filter: str | None = Query(
        None, description="Filter by document type"
    ),
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db_session),
) -> UnmatchedVendorResponse:
    """
    GET /api/v1/vlr/reconciliation/{case_id}/unmatched-vendor

    Returns vendor ledger entries with no company match (match_id IS NULL).
    Actions available: Accept and Post Adjustment, Reject, Request Clarification.

    Requirement 21.1: Display unmatched vendor entries.
    """
    await _verify_case_exists(case_id, session)

    base_query = select(LedgerEntryModel).where(
        and_(
            LedgerEntryModel.case_id == str(case_id),
            LedgerEntryModel.side == "vendor",
            LedgerEntryModel.match_id.is_(None),
        )
    )

    if document_type_filter:
        base_query = base_query.where(
            LedgerEntryModel.document_type == document_type_filter
        )

    # Count total
    count_stmt = select(func.count()).select_from(base_query.subquery())
    total_result = await session.execute(count_stmt)
    total = total_result.scalar() or 0

    # Apply sorting
    sort_column = getattr(LedgerEntryModel, sort_by, LedgerEntryModel.posting_date)
    if sort_order == SortOrder.DESC:
        base_query = base_query.order_by(sort_column.desc())
    else:
        base_query = base_query.order_by(sort_column.asc())

    # Apply pagination
    offset = (page - 1) * page_size
    base_query = base_query.offset(offset).limit(page_size)

    result = await session.execute(base_query)
    entries = list(result.scalars().all())

    items = [
        UnmatchedVendorEntryResponse(
            entry_id=entry.id,
            document_number=entry.document_number,
            document_type=entry.document_type,
            document_category=entry.document_category,
            reference_number=entry.reference_number,
            posting_date=entry.posting_date,
            amount=Decimal(str(entry.amount)),
            currency=entry.currency,
            description=entry.description,
        )
        for entry in entries
    ]

    return UnmatchedVendorResponse(
        items=items,
        pagination=_build_pagination(page, page_size, total),
    )


# ──────────────────────────────────────────────────────────────────────
# Tab 5: Differences Summary
# ──────────────────────────────────────────────────────────────────────


@router.get(
    "/{case_id}/summary",
    response_model=DifferencesSummaryResponse,
    status_code=status.HTTP_200_OK,
    summary="Get differences summary (Tab 5)",
    dependencies=[Depends(require_permission("vlr.cases.read"))],
)
async def get_differences_summary(
    case_id: UUID,
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db_session),
) -> DifferencesSummaryResponse:
    """
    GET /api/v1/vlr/reconciliation/{case_id}/summary

    Returns the differences summary including opening/closing balance
    comparisons, totals by type, and net difference.

    Requirement 22.1: Display balance comparisons and net difference.
    """
    case = await _verify_case_exists(case_id, session)

    # Build balance comparisons from case model
    company_opening = (
        Decimal(str(case.company_opening_balance))
        if case.company_opening_balance is not None
        else None
    )
    vendor_opening = (
        Decimal(str(case.vendor_opening_balance))
        if case.vendor_opening_balance is not None
        else None
    )
    company_closing = (
        Decimal(str(case.company_closing_balance))
        if case.company_closing_balance is not None
        else None
    )
    vendor_closing = (
        Decimal(str(case.vendor_closing_balance))
        if case.vendor_closing_balance is not None
        else None
    )

    opening_diff = None
    if company_opening is not None and vendor_opening is not None:
        opening_diff = company_opening - vendor_opening

    closing_diff = None
    if company_closing is not None and vendor_closing is not None:
        closing_diff = company_closing - vendor_closing

    opening_balance = BalanceComparison(
        company_balance=company_opening,
        vendor_balance=vendor_opening,
        difference=opening_diff,
    )
    closing_balance = BalanceComparison(
        company_balance=company_closing,
        vendor_balance=vendor_closing,
        difference=closing_diff,
    )

    # Calculate totals by document category/type — dynamically from all categories present
    cat_stmt = (
        select(LedgerEntryModel.document_category)
        .where(
            and_(
                LedgerEntryModel.case_id == str(case_id),
                LedgerEntryModel.document_category.isnot(None),
            )
        )
        .distinct()
    )
    cat_result = await session.execute(cat_stmt)
    doc_types = sorted({r[0] for r in cat_result.all() if r[0]})
    # Exclude balance rows from the transaction-type totals (they're shown separately)
    doc_types = [d for d in doc_types if d not in ("Opening Balance", "Closing Balance")]
    totals_by_type: list[TypeTotal] = []

    for doc_type in doc_types:
        # Company side total
        company_sum_stmt = select(func.coalesce(func.sum(LedgerEntryModel.amount), 0)).where(
            and_(
                LedgerEntryModel.case_id == str(case_id),
                LedgerEntryModel.side == "company",
                LedgerEntryModel.document_category == doc_type,
            )
        )
        company_sum_result = await session.execute(company_sum_stmt)
        company_total = Decimal(str(company_sum_result.scalar() or 0))

        # Vendor side total
        vendor_sum_stmt = select(func.coalesce(func.sum(LedgerEntryModel.amount), 0)).where(
            and_(
                LedgerEntryModel.case_id == str(case_id),
                LedgerEntryModel.side == "vendor",
                LedgerEntryModel.document_category == doc_type,
            )
        )
        vendor_sum_result = await session.execute(vendor_sum_stmt)
        vendor_total = Decimal(str(vendor_sum_result.scalar() or 0))

        totals_by_type.append(
            TypeTotal(
                type_name=doc_type,
                company_total=company_total,
                vendor_total=vendor_total,
                difference=company_total - vendor_total,
            )
        )

    # Count matched entries (confirmed, pass 1 & 2)
    matched_count_stmt = select(func.count()).where(
        and_(
            MatchResultModel.case_id == str(case_id),
            MatchResultModel.is_confirmed == True,  # noqa: E712
            MatchResultModel.pass_number.in_([1, 2]),
        )
    )
    matched_result = await session.execute(matched_count_stmt)
    total_matched = matched_result.scalar() or 0

    # Count unmatched company entries
    unmatched_company_stmt = select(func.count()).where(
        and_(
            LedgerEntryModel.case_id == str(case_id),
            LedgerEntryModel.side == "company",
            LedgerEntryModel.match_id.is_(None),
        )
    )
    unmatched_company_result = await session.execute(unmatched_company_stmt)
    total_unmatched_company = unmatched_company_result.scalar() or 0

    # Count unmatched vendor entries
    unmatched_vendor_stmt = select(func.count()).where(
        and_(
            LedgerEntryModel.case_id == str(case_id),
            LedgerEntryModel.side == "vendor",
            LedgerEntryModel.match_id.is_(None),
        )
    )
    unmatched_vendor_result = await session.execute(unmatched_vendor_stmt)
    total_unmatched_vendor = unmatched_vendor_result.scalar() or 0

    # Count pending confirmation entries
    pending_stmt = select(func.count()).where(
        and_(
            MatchResultModel.case_id == str(case_id),
            MatchResultModel.is_confirmed == False,  # noqa: E712
            MatchResultModel.pass_number.in_([3, 4, 5, 6]),
        )
    )
    pending_result = await session.execute(pending_stmt)
    total_pending = pending_result.scalar() or 0

    net_diff = (
        Decimal(str(case.net_difference))
        if case.net_difference is not None
        else None
    )

    # Sum of unmatched amounts on each side (excluding balance rows), so the
    # residual reconciliation difference is fully explained.
    unmatched_company_amt_stmt = select(
        func.coalesce(func.sum(LedgerEntryModel.amount), 0)
    ).where(
        and_(
            LedgerEntryModel.case_id == str(case_id),
            LedgerEntryModel.side == "company",
            LedgerEntryModel.match_id.is_(None),
            LedgerEntryModel.document_category.notin_(["Opening Balance", "Closing Balance"]),
        )
    )
    unmatched_company_amount = Decimal(
        str((await session.execute(unmatched_company_amt_stmt)).scalar() or 0)
    )

    unmatched_vendor_amt_stmt = select(
        func.coalesce(func.sum(LedgerEntryModel.amount), 0)
    ).where(
        and_(
            LedgerEntryModel.case_id == str(case_id),
            LedgerEntryModel.side == "vendor",
            LedgerEntryModel.match_id.is_(None),
            LedgerEntryModel.document_category.notin_(["Opening Balance", "Closing Balance"]),
        )
    )
    unmatched_vendor_amount = Decimal(
        str((await session.execute(unmatched_vendor_amt_stmt)).scalar() or 0)
    )

    # Residual difference: company and vendor use opposite signs, so the
    # net gap is the sum of both sides' unmatched amounts.
    residual_difference = unmatched_company_amount + unmatched_vendor_amount

    return DifferencesSummaryResponse(
        case_id=case_id,
        opening_balance=opening_balance,
        closing_balance=closing_balance,
        totals_by_type=totals_by_type,
        net_difference=net_diff,
        total_matched=total_matched,
        total_unmatched_company=total_unmatched_company,
        total_unmatched_vendor=total_unmatched_vendor,
        total_pending_confirmation=total_pending,
        unmatched_company_amount=unmatched_company_amount,
        unmatched_vendor_amount=unmatched_vendor_amount,
        residual_difference=residual_difference,
    )


# ──────────────────────────────────────────────────────────────────────
# Confirm/Reject Match Action
# ──────────────────────────────────────────────────────────────────────


@router.post(
    "/{case_id}/confirm",
    response_model=ConfirmMatchResponse,
    status_code=status.HTTP_200_OK,
    summary="Accept or reject a match",
    dependencies=[Depends(require_permission("vlr.cases.write"))],
)
async def confirm_match(
    case_id: UUID,
    request: ConfirmMatchRequest,
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db_session),
) -> ConfirmMatchResponse:
    """
    POST /api/v1/vlr/reconciliation/{case_id}/confirm

    Accept, reject, or request clarification on a match result.
    - Accept: Sets is_confirmed=True, moves to confirmed matches.
    - Reject: Removes the match, moves entries back to unmatched pool.
    - Clarify: Flags for vendor clarification (no state change yet).

    Requirement 19.3: Accept moves to confirmed.
    Requirement 19.4: Reject returns entries to unmatched.
    """
    await _verify_case_exists(case_id, session)

    # Find the match result
    match_stmt = select(MatchResultModel).where(
        and_(
            MatchResultModel.id == str(request.match_id),
            MatchResultModel.case_id == str(case_id),
        )
    )
    result = await session.execute(match_stmt)
    match_record = result.scalar_one_or_none()

    if match_record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Match result '{request.match_id}' not found for case '{case_id}'.",
        )

    if request.action == ConfirmAction.ACCEPT:
        # Mark match as confirmed
        match_record.is_confirmed = True
        session.add(match_record)
        await session.flush()
        message = "Match accepted and confirmed."

    elif request.action == ConfirmAction.REJECT:
        # Clear match_id from all associated entries to return them to unmatched
        all_entry_ids = []
        if match_record.company_entry_ids:
            all_entry_ids.extend(match_record.company_entry_ids)
        if match_record.vendor_entry_ids:
            all_entry_ids.extend(match_record.vendor_entry_ids)

        for entry_id in all_entry_ids:
            entry_stmt = select(LedgerEntryModel).where(
                LedgerEntryModel.id == str(entry_id)
            )
            entry_result = await session.execute(entry_stmt)
            entry = entry_result.scalar_one_or_none()
            if entry:
                entry.match_id = None
                entry.pass_number = None
                entry.confidence_score = None
                session.add(entry)

        # Delete the match result
        await session.delete(match_record)
        await session.flush()
        message = "Match rejected. Entries returned to unmatched pool."

    elif request.action == ConfirmAction.CLARIFY:
        # Flag for clarification — no state change to the match itself
        # In a full implementation this would create a clarification request
        message = "Clarification requested for this match."

    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid action: {request.action}",
        )

    # Emit audit event for match override/confirmation (Requirement 38.2)
    audit_service = AuditTrailService(audit_repository=AuditTrailRepositoryImpl(session))
    await audit_service.log_event(AuditEvent(
        actor_username=current_user.username or str(current_user.id),
        actor_id=current_user.id,
        event_type=AuditEventType.MATCH_OVERRIDE,
        case_id=case_id,
        event_details={
            "action": request.action.value if hasattr(request.action, "value") else str(request.action),
            "match_id": str(request.match_id),
            "message": message,
        },
    ))

    await session.commit()

    return ConfirmMatchResponse(
        match_id=request.match_id,
        action=request.action,
        success=True,
        message=message,
    )


# ──────────────────────────────────────────────────────────────────────
# Manual Link / Unlink (reviewer pairs unmatched entries)
# ──────────────────────────────────────────────────────────────────────

from pydantic import BaseModel as _LinkBaseModel  # noqa: E402
from uuid import uuid4 as _uuid4  # noqa: E402


class ManualLinkRequest(_LinkBaseModel):
    """Request to manually link unmatched company + vendor entries."""
    company_entry_ids: list[str]
    vendor_entry_ids: list[str]
    notes: str | None = None


class ManualLinkResponse(_LinkBaseModel):
    match_id: str
    company_amount: float
    vendor_amount: float
    difference: float
    message: str


class UnlinkRequest(_LinkBaseModel):
    """Request to remove a manual/auto match, returning entries to unmatched."""
    match_id: str


@router.post(
    "/{case_id}/link",
    response_model=ManualLinkResponse,
    status_code=status.HTTP_200_OK,
    summary="Manually link unmatched company + vendor entries",
    dependencies=[Depends(require_permission("vlr.cases.write"))],
)
async def manual_link(
    case_id: UUID,
    request: ManualLinkRequest,
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db_session),
) -> ManualLinkResponse:
    """
    POST /api/v1/vlr/reconciliation/{case_id}/link

    Creates a confirmed manual match linking the selected company and vendor
    entries. Entries must currently be unmatched (match_id is NULL).
    """
    await _verify_case_exists(case_id, session)

    if not request.company_entry_ids and not request.vendor_entry_ids:
        raise HTTPException(status_code=400, detail="Select at least one entry to link.")

    # Load and validate the selected entries
    all_ids = request.company_entry_ids + request.vendor_entry_ids
    stmt = select(LedgerEntryModel).where(
        and_(
            LedgerEntryModel.case_id == str(case_id),
            LedgerEntryModel.id.in_(all_ids),
        )
    )
    result = await session.execute(stmt)
    entries = list(result.scalars().all())

    company_entries = [e for e in entries if e.side == "company"]
    vendor_entries = [e for e in entries if e.side == "vendor"]

    # Guard: don't re-link already matched entries
    already = [e for e in entries if e.match_id is not None]
    if already:
        raise HTTPException(
            status_code=409,
            detail="One or more selected entries are already matched. Unlink them first.",
        )

    company_amount = sum(Decimal(str(e.amount or 0)) for e in company_entries)
    vendor_amount = sum(Decimal(str(e.amount or 0)) for e in vendor_entries)
    # Company and vendor use opposite signs; difference is the net residual
    difference = company_amount + vendor_amount

    match_id = _uuid4()
    match_type = "manual"
    if len(company_entries) == 1 and len(vendor_entries) == 1:
        match_type = "manual_pair"
    elif len(company_entries) > 1 or len(vendor_entries) > 1:
        match_type = "manual_group"

    match_record = MatchResultModel(
        id=match_id,
        case_id=str(case_id),
        pass_number=8,  # 8 = manual
        match_type=match_type,
        confidence_score=1.0,  # manual = fully confirmed
        is_confirmed=True,
        company_entry_ids=[str(e.id) for e in company_entries],
        vendor_entry_ids=[str(e.id) for e in vendor_entries],
        matched_amount=float(abs(company_amount) or abs(vendor_amount)),
        difference_amount=float(difference),
    )
    session.add(match_record)

    # Stamp match_id on each entry so they leave the unmatched pool
    for e in entries:
        e.match_id = match_id
        e.pass_number = 8
        e.confidence_score = 1.0
        session.add(e)

    await session.flush()

    # Audit
    audit_service = AuditTrailService(audit_repository=AuditTrailRepositoryImpl(session))
    await audit_service.log_event(AuditEvent(
        actor_username=current_user.username or str(current_user.id),
        actor_id=current_user.id,
        event_type=AuditEventType.MATCH_OVERRIDE,
        case_id=case_id,
        event_details={
            "action": "manual_link",
            "match_id": str(match_id),
            "company_entries": len(company_entries),
            "vendor_entries": len(vendor_entries),
            "difference": float(difference),
            "notes": request.notes or "",
        },
    ))

    await session.commit()

    return ManualLinkResponse(
        match_id=str(match_id),
        company_amount=float(company_amount),
        vendor_amount=float(vendor_amount),
        difference=float(difference),
        message=(
            f"Linked {len(company_entries)} company + {len(vendor_entries)} vendor "
            f"entries. Net difference: {float(difference):.2f}"
        ),
    )


@router.post(
    "/{case_id}/unlink",
    status_code=status.HTTP_200_OK,
    summary="Unlink a match, returning entries to the unmatched pool",
    dependencies=[Depends(require_permission("vlr.cases.write"))],
)
async def manual_unlink(
    case_id: UUID,
    request: UnlinkRequest,
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    """
    POST /api/v1/vlr/reconciliation/{case_id}/unlink

    Removes a match (manual or auto) and returns its entries to unmatched.
    """
    await _verify_case_exists(case_id, session)

    match_stmt = select(MatchResultModel).where(
        and_(
            MatchResultModel.id == str(request.match_id),
            MatchResultModel.case_id == str(case_id),
        )
    )
    match_record = (await session.execute(match_stmt)).scalar_one_or_none()
    if match_record is None:
        raise HTTPException(status_code=404, detail="Match not found.")

    entry_ids = list(match_record.company_entry_ids or []) + list(match_record.vendor_entry_ids or [])
    for entry_id in entry_ids:
        e_stmt = select(LedgerEntryModel).where(LedgerEntryModel.id == str(entry_id))
        entry = (await session.execute(e_stmt)).scalar_one_or_none()
        if entry:
            entry.match_id = None
            entry.pass_number = None
            entry.confidence_score = None
            session.add(entry)

    await session.delete(match_record)
    await session.flush()
    await session.commit()

    return {"success": True, "message": "Match unlinked. Entries returned to unmatched pool."}
