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
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.v1.dependencies import get_current_active_user
from src.api.v1.schemas.vlr.reconciliation_output_schemas import (
    BalanceComparison,
    ConfirmAction,
    ConfirmMatchRequest,
    ConfirmMatchResponse,
    ConfirmationEntryResponse,
    ConfirmationItemsResponse,
    AnalyticsRow,
    DifferencesSummaryResponse,
    EntryColumns,
    MatchedEntryResponse,
    MatchedItemsResponse,
    PaginationMeta,
    ParticularsChild,
    ParticularsGroup,
    ParticularsSummaryResponse,
    ReconciliationAnalyticsResponse,
    SortOrder,
    TypeTotal,
    UnmatchedCompanyEntryResponse,
    UnmatchedCompanyResponse,
    UnmatchedVendorEntryResponse,
    UnmatchedVendorResponse,
)
from src.domain.entities.user import User
from src.domain.services.vlr.entry_columns import build_entry_columns, invoice_number
from src.domain.services.vlr.reconciliation_engine_service import MatchPassType
from src.domain.services.vlr.status_reasons import STATUS_REASONS, VALID_STATUS_REASONS
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


# Document categories that are NOT genuine cross-ledger differences: balance
# markers and knock-off / reversal (SAP "AB") entries. Knock-off entries net
# ONLY within their own side (per the Vendor Ledger Mapping Rules doc) —
# matched knock-off pairs already get a match_id via _reversal_match, so
# match_id IS NULL alone already excludes them; this list additionally
# excludes them by category/doc-type as defense in depth.
#
# "Other entry" (SA / Adjusted) rows are DELIBERATELY NOT in this list.
# Client-confirmed bug: an unpaired SA entry (e.g. "MSME Interest", no
# same-side netting counterpart) was blanket-excluded from ever appearing
# as unmatched purely by category/doc-type, regardless of whether it
# actually netted against anything — hiding a genuine open item. A SA entry
# that DID net via _other_entry_match already carries a match_id (set by
# bulk_update_match), so match_id IS NULL alone correctly identifies only
# the genuinely UNPAIRED SA entries here, which per the mapping doc's Open
# Item Status section ("Remaining entries open from Emcure/vendor, then
# other entry not booked by vendor/company") are real differences and must
# surface in the unmatched list. Kept in sync with
# reconciliation_export_service._special_classification.
_NON_DIFFERENCE_CATEGORIES = ["Opening Balance", "Closing Balance", "Knocking Off"]
_NON_DIFFERENCE_DOC_TYPES = ["AB"]

# Pass-number groups for "auto-accepted" vs "needs finance confirmation",
# mirroring the engine's is_auto_accepted logic in
# ReconciliationEngineService._persist_results. AMOUNT_DATE (1.5) and
# TDS_GST (2.5) are high-confidence sub-passes that auto-accept alongside
# EXACT/TOLERANCE; TOLERANCE_DATE (6.5) is the weakest tier and always needs
# review alongside FUZZY_REFERENCE/ONE_TO_MANY/MANY_TO_ONE/DATE_PROXIMITY.
# Same-side netting passes (9=Knocking Off, 13=Other entry/SA) are their own
# entry-intrinsic category — excluded from both these lists (they aren't
# counted as "Matched" so they don't inflate the Matched-rate KPI). Knock-off
# (pass 9) is additionally excluded from the unmatched list by category/doc-
# type via _NON_DIFFERENCE_CATEGORIES/_NON_DIFFERENCE_DOC_TYPES above; "Other
# entry"/SA (pass 13) is excluded from unmatched ONLY via match_id IS NOT
# NULL (an unpaired SA entry with no match_id is a genuine open item and
# must appear in the unmatched list — see _NON_DIFFERENCE_CATEGORIES comment
# above).
# Defined once here so every "Matched" / "Recommended" count across the
# dashboard, analytics, and tab endpoints stays in sync — previously these
# were hardcoded as raw [1, 2] / [3, 4, 5, 6] lists that silently excluded
# any entry matched by a newly added pass number.
_AUTO_ACCEPTED_PASSES = [
    MatchPassType.EXACT, MatchPassType.TOLERANCE,
    MatchPassType.AMOUNT_DATE, MatchPassType.TDS_GST,
    14,  # TDS_LINK_PASS — deterministic TDS-entry-to-parent-pair link, auto-accepted
]
_NEEDS_CONFIRMATION_PASSES = [
    MatchPassType.FUZZY_REFERENCE, MatchPassType.ONE_TO_MANY,
    MatchPassType.MANY_TO_ONE, MatchPassType.DATE_PROXIMITY,
    MatchPassType.TOLERANCE_DATE,
    # Same invoice number + same date, but the gap is unexplained (see
    # _amount_mismatch_match) — always needs Finance review, never
    # auto-accepted.
    MatchPassType.AMOUNT_MISMATCH,
]


def _genuine_unmatched_conditions(case_id: UUID, side: str) -> list:
    """
    SQL conditions selecting *genuine* unmatched entries for one side:
      • no match (match_id IS NULL),
      • not an Opening/Closing Balance row,
      • not a knock-off / reversal (category "Knocking Off" or doc type "AB").

    This is the single source of truth for "unmatched" so the unmatched
    screens, analytics counts, and the reconciliation statement stay in lock-step.
    """
    conds = [
        LedgerEntryModel.case_id == str(case_id),
        LedgerEntryModel.side == side,
        LedgerEntryModel.match_id.is_(None),
        func.coalesce(LedgerEntryModel.document_category, "").notin_(
            _NON_DIFFERENCE_CATEGORIES
        ),
        func.coalesce(LedgerEntryModel.document_type, "").notin_(
            _NON_DIFFERENCE_DOC_TYPES
        ),
    ]
    return conds


def _particulars_group_for_entry(entry) -> str | None:
    """
    Classify one unmatched ledger entry into its Particulars-statement
    difference group label (e.g. "Invoice Difference", "Other Differences"),
    mirroring the exact bucketing logic used by
    get_reconciliation_particulars's local `_bucket()` closure. Returns None
    for entries that endpoint excludes entirely (balance rows, reversals).

    Used to filter the unmatched-company/unmatched-vendor "View" drill-in so
    each Particulars group's View link shows only ITS OWN entries instead of
    the full unmatched list — bug fix: previously every group's View button
    routed to the same unfiltered unmatched-company view, so every group
    "tab" displayed identical invoices.
    """
    from src.domain.services.vlr.reconciliation_export_service import (
        CATEGORY_TO_SUMMARY,
        DEFAULT_SUMMARY,
        _special_classification,
    )

    cat = (getattr(entry, "document_category", "") or "").strip()
    if cat in ("Opening Balance", "Closing Balance"):
        return None
    special = _special_classification(entry)
    if special in ("Opening Balance", "Closing Balance", "Reversal Entries"):
        return None
    # Bug fix: this was missing the same TDS special-case override that
    # get_reconciliation_particulars's own _bucket() closure applies — an
    # unmatched TDS entry (detected via _special_classification, NOT its raw
    # document_category) rolls up under the dedicated "TDS / TCS Difference"
    # group there. Without this override here, the SAME entry computed a
    # DIFFERENT group (whatever its raw document_category maps to via
    # CATEGORY_TO_SUMMARY/DEFAULT_SUMMARY), so it silently failed the
    # group_filter match and never showed up when a user clicked "View" on
    # TDS / TCS Difference — the statement's count included it, but the
    # drill-in returned zero results for that entry.
    if special == "TDS Booked by Party":
        info = CATEGORY_TO_SUMMARY["TDS Adjusted"]
    else:
        info = CATEGORY_TO_SUMMARY.get(cat, DEFAULT_SUMMARY)
    return info["group"]


async def _load_tax_config(case, session: AsyncSession) -> tuple[float, float, float]:
    """
    Load (tds_percentage_max, tds_percentage_min, gst_percentage) from the
    case's parent request. Needed to compute the same Status/Classification
    labels ("TDS Booked by Company", "Write off / Rounding off",
    "Unexplained Amount Gap") that the Excel export and the Particulars
    statement use, so drill-in filters agree with what's shown.
    """
    if not getattr(case, "request_id", None):
        return 0.0, 0.0, 0.0
    from src.infrastructure.database.models.vlr.reconciliation_request_model import (
        ReconciliationRequestModel,
    )
    pres = await session.execute(
        select(ReconciliationRequestModel).where(
            ReconciliationRequestModel.id == str(case.request_id)
        )
    )
    parent = pres.scalar_one_or_none()
    if parent is None:
        return 0.0, 0.0, 0.0
    return (
        float(getattr(parent, "tds_percentage", 0) or 0),
        float(getattr(parent, "tds_percentage_min", 0) or 0),
        float(getattr(parent, "gst_percentage", 0) or 0),
    )


async def _filter_matches_by_computed_status(
    matches: list["MatchResultModel"],
    computed_status_filter: str,
    tds_max: float,
    tds_min: float,
    gst_pct: float,
    session: AsyncSession,
) -> list["MatchResultModel"]:
    """
    Filter matches to those whose computed row-level Status OR Classification
    equals `computed_status_filter` (e.g. "TDS Booked by Company", "Write
    off / Rounding off", "Unexplained Amount Gap", "Amount Mismatch").

    Bug fix: the Particulars/Differences statement only ever itemised
    UNMATCHED entries — a matched PAIR that still carries a genuine residual
    (TDS deducted, a rounding write-off, an unexplained gap, or a same-
    invoice amount mismatch) never appeared in the statement at all, even
    though the Excel export already surfaces these via
    matched_residual_bucket. Client: "are the matched columns not a part of
    these particulars and differences? we also need those". This helper
    powers the "View" drill-in for those newly-surfaced matched-residual
    rows, reusing the SAME _status()/_classification() functions the export
    service and the statement's own totals are built from, so the drill-in
    list always agrees with what the statement shows.
    """
    from src.domain.services.vlr.reconciliation_export_service import (
        _classification,
        _status,
    )

    filtered: list[MatchResultModel] = []
    for m in matches:
        ce = await _get_first_entry(m.company_entry_ids, session)
        ve = await _get_first_entry(m.vendor_entry_ids, session)
        diff = m.difference_amount
        if diff is None:
            c_amt = float(ce.amount) if ce and ce.amount is not None else 0.0
            v_amt = float(ve.amount) if ve and ve.amount is not None else 0.0
            diff = (c_amt + v_amt) if (ce and ve) else 0.0
        computed_status = _status(m.pass_number, ce, ve, float(diff), tds_max, gst_pct, tds_min)
        computed_classification = _classification(m.pass_number)
        if computed_status == computed_status_filter or computed_classification == computed_status_filter:
            filtered.append(m)
    return filtered


def _build_pagination(page: int, page_size: int, total: int) -> PaginationMeta:
    """Build pagination metadata."""
    return PaginationMeta(
        page=page,
        page_size=page_size,
        total_items=total,
        total_pages=max(1, math.ceil(total / page_size)),
    )


async def _get_first_entry(
    entry_ids: list | None, session: AsyncSession
) -> LedgerEntryModel | None:
    """Load the first ledger entry from a list of entry IDs."""
    if not entry_ids:
        return None
    first_id = entry_ids[0]
    if first_id is None:
        return None
    stmt = select(LedgerEntryModel).where(LedgerEntryModel.id == str(first_id))
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def _get_entry_reference(
    entry_ids: list | None, session: AsyncSession
) -> tuple[str | None, Decimal | None]:
    """Get first entry's reference and amount from a list of entry IDs."""
    entry = await _get_first_entry(entry_ids, session)
    if entry is None:
        return None, None
    # Use the shared invoice_number helper so synthetic BAL_ROW_* placeholders
    # are never surfaced (recovers the real number from raw_data instead).
    ref = invoice_number(entry) or entry.reference_number
    amount = Decimal(str(entry.amount)) if entry.amount is not None else None
    return ref, amount


async def _filter_matches_by_search(
    matches: list["MatchResultModel"],
    search: str,
    session: AsyncSession,
) -> list["MatchResultModel"]:
    """
    Filter a list of MatchResultModel rows to only those whose linked
    company or vendor ledger entry has a reference/invoice/document number
    containing `search` (case-insensitive).

    Bug fix: the "Search by reference..." box on the Matched Items and
    Confirmation tabs sent a `search` query param that the backend never
    declared or read at all — every keystroke round-tripped to the server
    and came back completely unfiltered. The reference/invoice number for
    a match lives on the LINKED LedgerEntryModel row(s) (via
    company_entry_ids/vendor_entry_ids, a JSON array of entry IDs), not on
    MatchResultModel itself, so this can't be a simple SQL WHERE on the
    match table — each match's linked entries have to be loaded and
    compared. Pagination/counting for a search request therefore filters
    over the full (unpaginated) result set rather than a single SQL page.
    """
    term = search.strip().lower()
    if not term:
        return matches
    filtered: list[MatchResultModel] = []
    for m in matches:
        ce = await _get_first_entry(m.company_entry_ids, session)
        ve = await _get_first_entry(m.vendor_entry_ids, session)
        haystacks = []
        for e in (ce, ve):
            if e is None:
                continue
            haystacks.append(invoice_number(e) or "")
            haystacks.append(e.reference_number or "")
            haystacks.append(e.document_number or "")
        if any(term in h.lower() for h in haystacks if h):
            filtered.append(m)
    return filtered


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
    page_size: int = Query(20, ge=1, le=1000, description="Items per page"),
    sort_by: str = Query("pass_number", description="Sort field"),
    sort_order: SortOrder = Query(SortOrder.ASC, description="Sort direction"),
    match_type_filter: str | None = Query(None, description="Filter by match type"),
    status_reason_filter: str | None = Query(
        None, description="Filter to manual links (pass 8) with this exact status_reason"
    ),
    manual_only: bool = Query(
        False, description="Filter to all manual links (pass 8), regardless of status_reason"
    ),
    search: str | None = Query(
        None, description="Search by company/vendor invoice or reference number"
    ),
    computed_status_filter: str | None = Query(
        None,
        description=(
            "Filter to matches whose computed Status/Classification equals "
            "this value, e.g. 'TDS Booked by Company', 'Write off / "
            "Rounding off', 'Unexplained Amount Gap', 'Amount Mismatch' — "
            "used by the Particulars statement's matched-residual drill-in"
        ),
    ),
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db_session),
) -> MatchedItemsResponse:
    """
    GET /api/v1/vlr/reconciliation/{case_id}/matched

    Returns all Pass 1 and Pass 2 matches (confirmed matches).
    Supports pagination, sorting, and filtering.

    Requirement 18.1: Display matched items with match type and confidence.
    """
    case = await _verify_case_exists(case_id, session)

    # Build base query: confirmed / auto-accepted matches. A status_reason
    # filter (or manual_only) is only meaningful for manual links (pass 8,
    # which isn't part of the normal auto-accepted set) — used by the
    # "Manually Mapped" Particulars drill-in, so swap the pass filter to
    # pass==8 in that case.
    if status_reason_filter:
        base_query = select(MatchResultModel).where(
            and_(
                MatchResultModel.case_id == str(case_id),
                MatchResultModel.pass_number == 8,
                MatchResultModel.status_reason == status_reason_filter,
            )
        )
    elif manual_only:
        base_query = select(MatchResultModel).where(
            and_(
                MatchResultModel.case_id == str(case_id),
                MatchResultModel.pass_number == 8,
            )
        )
    else:
        base_query = select(MatchResultModel).where(
            and_(
                MatchResultModel.case_id == str(case_id),
                MatchResultModel.is_confirmed == True,  # noqa: E712
                MatchResultModel.pass_number.in_(_AUTO_ACCEPTED_PASSES),
            )
        )

    if match_type_filter:
        base_query = base_query.where(
            MatchResultModel.match_type == match_type_filter
        )

    # Apply sorting (applied before the search filter so a searched result
    # set still comes back in the requested order).
    sort_column = getattr(MatchResultModel, sort_by, MatchResultModel.pass_number)
    if sort_order == SortOrder.DESC:
        base_query = base_query.order_by(sort_column.desc())
    else:
        base_query = base_query.order_by(sort_column.asc())

    if (search and search.strip()) or computed_status_filter:
        # Reference/invoice number lives on the LINKED ledger entries, not
        # on MatchResultModel itself — load every candidate match (no SQL
        # LIMIT yet), filter in Python, then paginate the filtered list.
        # Same approach for computed_status_filter: Status/Classification
        # ("TDS Booked by Company", "Write off / Rounding off", ...) is
        # computed on the fly by _status()/_classification(), not a stored
        # column, so it can't be a SQL WHERE either.
        all_result = await session.execute(base_query)
        all_matches = list(all_result.scalars().all())
        if search and search.strip():
            all_matches = await _filter_matches_by_search(all_matches, search, session)
        if computed_status_filter:
            tds_max, tds_min, gst_pct = await _load_tax_config(case, session)
            all_matches = await _filter_matches_by_computed_status(
                all_matches, computed_status_filter, tds_max, tds_min, gst_pct, session
            )
        total = len(all_matches)
        offset = (page - 1) * page_size
        matches = all_matches[offset:offset + page_size]
    else:
        # Count total
        count_stmt = select(func.count()).select_from(base_query.subquery())
        total_result = await session.execute(count_stmt)
        total = total_result.scalar() or 0

        # Apply pagination
        offset = (page - 1) * page_size
        base_query = base_query.offset(offset).limit(page_size)

        result = await session.execute(base_query)
        matches = list(result.scalars().all())

    # Build response items
    from src.domain.services.vlr.reconciliation_export_service import _rule_code

    items: list[MatchedEntryResponse] = []
    for match in matches:
        company_entry = await _get_first_entry(match.company_entry_ids, session)
        vendor_entry = await _get_first_entry(match.vendor_entry_ids, session)

        cl_ref = (
            invoice_number(company_entry) or company_entry.reference_number
        ) if company_entry else None
        cl_amount = (
            Decimal(str(company_entry.amount)) if company_entry and company_entry.amount is not None else None
        )
        vl_ref = (
            invoice_number(vendor_entry) or vendor_entry.reference_number
        ) if vendor_entry else None
        vl_amount = (
            Decimal(str(vendor_entry.amount)) if vendor_entry and vendor_entry.amount is not None else None
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
                company_columns=EntryColumns(**build_entry_columns(company_entry)) if company_entry else None,
                party_columns=EntryColumns(**build_entry_columns(vendor_entry)) if vendor_entry else None,
                matched_rule=_rule_code(match.pass_number),
                status_reason=match.status_reason,
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
    page_size: int = Query(20, ge=1, le=1000, description="Items per page"),
    sort_by: str = Query("pass_number", description="Sort field"),
    sort_order: SortOrder = Query(SortOrder.ASC, description="Sort direction"),
    match_type_filter: str | None = Query(None, description="Filter by match type"),
    search: str | None = Query(
        None, description="Search by company/vendor invoice or reference number"
    ),
    computed_status_filter: str | None = Query(
        None,
        description=(
            "Filter to matches whose computed Status/Classification equals "
            "this value, e.g. 'Amount Mismatch' — used by the Particulars "
            "statement's matched-residual drill-in"
        ),
    ),
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db_session),
) -> ConfirmationItemsResponse:
    """
    GET /api/v1/vlr/reconciliation/{case_id}/confirmation

    Returns all Pass 3, 4, 5, 6 matches that are not yet confirmed.
    These require finance user review (Accept/Reject/Clarify).

    Requirement 19.1: Display matches needing manual review.
    """
    case = await _verify_case_exists(case_id, session)

    base_query = select(MatchResultModel).where(
        and_(
            MatchResultModel.case_id == str(case_id),
            MatchResultModel.is_confirmed == False,  # noqa: E712
            MatchResultModel.pass_number.in_(_NEEDS_CONFIRMATION_PASSES),
        )
    )

    if match_type_filter:
        base_query = base_query.where(
            MatchResultModel.match_type == match_type_filter
        )

    # Apply sorting (before the search filter, so a searched result set
    # still comes back in the requested order).
    sort_column = getattr(MatchResultModel, sort_by, MatchResultModel.pass_number)
    if sort_order == SortOrder.DESC:
        base_query = base_query.order_by(sort_column.desc())
    else:
        base_query = base_query.order_by(sort_column.asc())

    if (search and search.strip()) or computed_status_filter:
        # Reference/invoice number lives on the LINKED ledger entries — see
        # _filter_matches_by_search for why this can't be a plain SQL WHERE.
        # Same for computed_status_filter — see _filter_matches_by_computed_status.
        all_result = await session.execute(base_query)
        all_matches = list(all_result.scalars().all())
        if search and search.strip():
            all_matches = await _filter_matches_by_search(all_matches, search, session)
        if computed_status_filter:
            tds_max, tds_min, gst_pct = await _load_tax_config(case, session)
            all_matches = await _filter_matches_by_computed_status(
                all_matches, computed_status_filter, tds_max, tds_min, gst_pct, session
            )
        total = len(all_matches)
        offset = (page - 1) * page_size
        matches = all_matches[offset:offset + page_size]
    else:
        # Count total
        count_stmt = select(func.count()).select_from(base_query.subquery())
        total_result = await session.execute(count_stmt)
        total = total_result.scalar() or 0

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
    page_size: int = Query(20, ge=1, le=1000, description="Items per page"),
    sort_by: str = Query("posting_date", description="Sort field"),
    sort_order: SortOrder = Query(SortOrder.ASC, description="Sort direction"),
    document_type_filter: str | None = Query(
        None, description="Filter by document type"
    ),
    search: str | None = Query(
        None, description="Search by reference/invoice/document number"
    ),
    group_filter: str | None = Query(
        None,
        description=(
            "Filter to entries belonging to this Particulars-statement "
            "difference group (e.g. 'Invoice Difference', 'Other Differences')"
        ),
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
        and_(*_genuine_unmatched_conditions(case_id, "company"))
    )

    if document_type_filter:
        base_query = base_query.where(
            LedgerEntryModel.document_type == document_type_filter
        )

    # Bug fix: the "Search by reference..." box sent a `search` query param
    # that this endpoint never declared, so it round-tripped unfiltered on
    # every keystroke. Matches against any of the reference/invoice/document
    # number columns (case-insensitive substring).
    if search and search.strip():
        term = f"%{search.strip()}%"
        base_query = base_query.where(
            or_(
                LedgerEntryModel.reference_number.ilike(term),
                LedgerEntryModel.document_number.ilike(term),
                LedgerEntryModel.derived_invoice_number.ilike(term),
            )
        )

    # Apply sorting (before the group filter, so a group-filtered result set
    # still comes back in the requested order).
    sort_column = getattr(LedgerEntryModel, sort_by, LedgerEntryModel.posting_date)
    if sort_order == SortOrder.DESC:
        base_query = base_query.order_by(sort_column.desc())
    else:
        base_query = base_query.order_by(sort_column.asc())

    if group_filter and group_filter.strip():
        # Bug fix: every difference group's "View" link on the Particulars
        # statement routed here with NO group filter at all, so every group
        # ("Invoice Difference", "Other Differences", "TDS / TCS
        # Difference", ...) showed the exact same full unmatched-company
        # list. The group label depends on document_category classification
        # logic (_particulars_group_for_entry, mirroring the Particulars
        # endpoint's own bucketing) — not a plain SQL column — so filter in
        # Python: load all candidates, classify each, then paginate.
        all_result = await session.execute(base_query)
        all_entries = list(all_result.scalars().all())
        entries_filtered = [
            e for e in all_entries
            if _particulars_group_for_entry(e) == group_filter.strip()
        ]
        total = len(entries_filtered)
        offset = (page - 1) * page_size
        entries = entries_filtered[offset:offset + page_size]
    else:
        # Count total
        count_stmt = select(func.count()).select_from(base_query.subquery())
        total_result = await session.execute(count_stmt)
        total = total_result.scalar() or 0

        # Apply pagination
        offset = (page - 1) * page_size
        base_query = base_query.offset(offset).limit(page_size)

        result = await session.execute(base_query)
        entries = list(result.scalars().all())

    items = [
        UnmatchedCompanyEntryResponse(
            entry_id=entry.id,
            document_number=invoice_number(entry),
            document_type=entry.document_type,
            document_category=entry.document_category,
            reference_number=entry.reference_number,
            posting_date=entry.posting_date,
            amount=Decimal(str(entry.amount)),
            currency=entry.currency,
            description=entry.description,
            columns=EntryColumns(**build_entry_columns(entry)),
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
    page_size: int = Query(20, ge=1, le=1000, description="Items per page"),
    sort_by: str = Query("posting_date", description="Sort field"),
    sort_order: SortOrder = Query(SortOrder.ASC, description="Sort direction"),
    document_type_filter: str | None = Query(
        None, description="Filter by document type"
    ),
    search: str | None = Query(
        None, description="Search by reference/invoice/document number"
    ),
    group_filter: str | None = Query(
        None,
        description=(
            "Filter to entries belonging to this Particulars-statement "
            "difference group (e.g. 'Invoice Difference', 'Other Differences')"
        ),
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
        and_(*_genuine_unmatched_conditions(case_id, "vendor"))
    )

    if document_type_filter:
        base_query = base_query.where(
            LedgerEntryModel.document_type == document_type_filter
        )

    # Bug fix: same as unmatched-company — the `search` param was never
    # declared/read here, so it round-tripped unfiltered on every keystroke.
    if search and search.strip():
        term = f"%{search.strip()}%"
        base_query = base_query.where(
            or_(
                LedgerEntryModel.reference_number.ilike(term),
                LedgerEntryModel.document_number.ilike(term),
                LedgerEntryModel.derived_invoice_number.ilike(term),
            )
        )

    # Apply sorting (before the group filter, so a group-filtered result set
    # still comes back in the requested order).
    sort_column = getattr(LedgerEntryModel, sort_by, LedgerEntryModel.posting_date)
    if sort_order == SortOrder.DESC:
        base_query = base_query.order_by(sort_column.desc())
    else:
        base_query = base_query.order_by(sort_column.asc())

    if group_filter and group_filter.strip():
        # Bug fix: same as unmatched-company — see _particulars_group_for_entry.
        all_result = await session.execute(base_query)
        all_entries = list(all_result.scalars().all())
        entries_filtered = [
            e for e in all_entries
            if _particulars_group_for_entry(e) == group_filter.strip()
        ]
        total = len(entries_filtered)
        offset = (page - 1) * page_size
        entries = entries_filtered[offset:offset + page_size]
    else:
        # Count total
        count_stmt = select(func.count()).select_from(base_query.subquery())
        total_result = await session.execute(count_stmt)
        total = total_result.scalar() or 0

        # Apply pagination
        offset = (page - 1) * page_size
        base_query = base_query.offset(offset).limit(page_size)

        result = await session.execute(base_query)
        entries = list(result.scalars().all())

    items = [
        UnmatchedVendorEntryResponse(
            entry_id=entry.id,
            document_number=invoice_number(entry),
            document_type=entry.document_type,
            document_category=entry.document_category,
            reference_number=entry.reference_number,
            posting_date=entry.posting_date,
            amount=Decimal(str(entry.amount)),
            currency=entry.currency,
            description=entry.description,
            columns=EntryColumns(**build_entry_columns(entry)),
        )
        for entry in entries
    ]

    return UnmatchedVendorResponse(
        items=items,
        pagination=_build_pagination(page, page_size, total),
    )


# ──────────────────────────────────────────────────────────────────────
# Knocking Off (reversal / AB) entries — informational list
# ──────────────────────────────────────────────────────────────────────


@router.get(
    "/{case_id}/knocking",
    response_model=UnmatchedVendorResponse,
    status_code=status.HTTP_200_OK,
    summary="Get knock-off / reversal (AB) entries for review",
    dependencies=[Depends(require_permission("vlr.cases.read"))],
)
async def get_knocking_entries(
    case_id: UUID,
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=1000, description="Items per page"),
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db_session),
) -> UnmatchedVendorResponse:
    """
    GET /api/v1/vlr/reconciliation/{case_id}/knocking

    Returns all knock-off / reversal entries (SAP doc type "AB" or category
    "Knocking Off") from BOTH sides, so users can inspect them and verify the
    residue nets to zero. These are excluded from the unmatched difference
    screens because they offset within a single ledger.
    """
    await _verify_case_exists(case_id, session)

    base_query = select(LedgerEntryModel).where(
        and_(
            LedgerEntryModel.case_id == str(case_id),
            or_(
                func.upper(func.coalesce(LedgerEntryModel.document_type, "")) == "AB",
                func.lower(func.coalesce(LedgerEntryModel.document_category, "")) == "knocking off",
            ),
        )
    ).order_by(LedgerEntryModel.posting_date.asc())

    count_stmt = select(func.count()).select_from(base_query.subquery())
    total = (await session.execute(count_stmt)).scalar() or 0

    offset = (page - 1) * page_size
    result = await session.execute(base_query.offset(offset).limit(page_size))
    entries = list(result.scalars().all())

    items = [
        UnmatchedVendorEntryResponse(
            entry_id=entry.id,
            document_number=invoice_number(entry),
            document_type=entry.document_type,
            document_category=entry.document_category,
            reference_number=entry.reference_number,
            posting_date=entry.posting_date,
            amount=Decimal(str(entry.amount)),
            currency=entry.currency,
            description=entry.description,
            columns=EntryColumns(**build_entry_columns(entry)),
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

    # Count matched entries (confirmed / auto-accepted)
    matched_count_stmt = select(func.count()).where(
        and_(
            MatchResultModel.case_id == str(case_id),
            MatchResultModel.is_confirmed == True,  # noqa: E712
            MatchResultModel.pass_number.in_(_AUTO_ACCEPTED_PASSES),
        )
    )
    matched_result = await session.execute(matched_count_stmt)
    total_matched = matched_result.scalar() or 0

    # Count unmatched company entries (genuine differences only)
    unmatched_company_stmt = select(func.count()).where(
        and_(*_genuine_unmatched_conditions(case_id, "company"))
    )
    unmatched_company_result = await session.execute(unmatched_company_stmt)
    total_unmatched_company = unmatched_company_result.scalar() or 0

    # Count unmatched vendor entries (genuine differences only)
    unmatched_vendor_stmt = select(func.count()).where(
        and_(*_genuine_unmatched_conditions(case_id, "vendor"))
    )
    unmatched_vendor_result = await session.execute(unmatched_vendor_stmt)
    total_unmatched_vendor = unmatched_vendor_result.scalar() or 0

    # Count pending confirmation entries
    pending_stmt = select(func.count()).where(
        and_(
            MatchResultModel.case_id == str(case_id),
            MatchResultModel.is_confirmed == False,  # noqa: E712
            MatchResultModel.pass_number.in_(_NEEDS_CONFIRMATION_PASSES),
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
        and_(*_genuine_unmatched_conditions(case_id, "company"))
    )
    unmatched_company_amount = Decimal(
        str((await session.execute(unmatched_company_amt_stmt)).scalar() or 0)
    )

    unmatched_vendor_amt_stmt = select(
        func.coalesce(func.sum(LedgerEntryModel.amount), 0)
    ).where(
        and_(*_genuine_unmatched_conditions(case_id, "vendor"))
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
# Reconciliation Analytics (Firmway-style summary table)
# ──────────────────────────────────────────────────────────────────────


@router.get(
    "/{case_id}/analytics",
    response_model=ReconciliationAnalyticsResponse,
    status_code=status.HTTP_200_OK,
    summary="Reconciliation analytics summary (matched/unmatched counts by side)",
    dependencies=[Depends(require_permission("vlr.cases.read"))],
)
async def get_reconciliation_analytics(
    case_id: UUID,
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db_session),
) -> ReconciliationAnalyticsResponse:
    """
    GET /api/v1/vlr/reconciliation/{case_id}/analytics

    Returns the Reconciliation Analytics table: per-side counts and percentages
    for Matched / Unmatched / Recommended Matched / Amount Mismatch, plus header
    metadata (party, period, status). Drives the summary-first View page.
    """
    case = await _verify_case_exists(case_id, session)

    async def _count(side: str, matched: bool | None, passes: list[int] | None = None) -> int:
        conds = [
            LedgerEntryModel.case_id == str(case_id),
            LedgerEntryModel.side == side,
            # Exclude balance markers and knock-off / reversal entries from all
            # analytics counts so they never inflate the totals or "unmatched".
            func.coalesce(LedgerEntryModel.document_category, "").notin_(
                _NON_DIFFERENCE_CATEGORIES
            ),
            func.coalesce(LedgerEntryModel.document_type, "").notin_(
                _NON_DIFFERENCE_DOC_TYPES
            ),
        ]
        if matched is True:
            conds.append(LedgerEntryModel.match_id.isnot(None))
        elif matched is False:
            conds.append(LedgerEntryModel.match_id.is_(None))
        if passes is not None:
            conds.append(LedgerEntryModel.pass_number.in_(passes))
        stmt = select(func.count()).where(and_(*conds))
        return int((await session.execute(stmt)).scalar() or 0)

    # Totals per side (all transactional entries)
    company_total = await _count("company", None)
    party_total = await _count("vendor", None)

    # Auto-accepted matches (Exact/Tolerance/Amount+Date/TDS-GST + manual) = "Matched"
    comp_matched = await _count("company", True, _AUTO_ACCEPTED_PASSES + [8])
    party_matched = await _count("vendor", True, _AUTO_ACCEPTED_PASSES + [8])
    # Recommended (needs-confirmation passes)
    comp_recommended = await _count("company", True, _NEEDS_CONFIRMATION_PASSES)
    party_recommended = await _count("vendor", True, _NEEDS_CONFIRMATION_PASSES)
    # Unmatched
    comp_unmatched = await _count("company", False)
    party_unmatched = await _count("vendor", False)

    def _pct(n: int, total: int) -> float:
        return round((n / total) * 100, 0) if total else 0.0

    rows = [
        AnalyticsRow(
            particulars="Matched",
            company_numbers=comp_matched, company_percentage=_pct(comp_matched, company_total),
            party_numbers=party_matched, party_percentage=_pct(party_matched, party_total),
            view_key="matched",
        ),
        AnalyticsRow(
            particulars="Unmatched",
            company_numbers=comp_unmatched, company_percentage=_pct(comp_unmatched, company_total),
            party_numbers=party_unmatched, party_percentage=_pct(party_unmatched, party_total),
            view_key="unmatched",
        ),
        AnalyticsRow(
            particulars="Recommended Matched",
            company_numbers=comp_recommended, company_percentage=_pct(comp_recommended, company_total),
            party_numbers=party_recommended, party_percentage=_pct(party_recommended, party_total),
            view_key="recommended",
        ),
    ]

    # Party metadata
    party_code = ""
    party_name = ""
    if case.vendor_id:
        from src.infrastructure.database.models.vlr.vendor_model import VendorModel
        vres = await session.execute(
            select(VendorModel).where(VendorModel.id == str(case.vendor_id))
        )
        vendor = vres.scalar_one_or_none()
        if vendor:
            party_code = vendor.vendor_code or ""
            party_name = vendor.name or ""

    # Period from parent request
    period_start = None
    period_end = None
    if case.request_id:
        from src.infrastructure.database.models.vlr.reconciliation_request_model import (
            ReconciliationRequestModel,
        )
        pres = await session.execute(
            select(ReconciliationRequestModel).where(
                ReconciliationRequestModel.id == str(case.request_id)
            )
        )
        parent = pres.scalar_one_or_none()
        if parent:
            period_start = parent.period_start
            period_end = parent.period_end

    return ReconciliationAnalyticsResponse(
        case_id=case_id,
        party_code=party_code,
        party_name=party_name,
        party_type="Vendor",
        reco_type="Ledger",
        reco_status=case.status or "",
        period_start=period_start,
        period_end=period_end,
        updated_at=getattr(case, "modified_date", None),
        rows=rows,
        total_company_numbers=company_total,
        total_party_numbers=party_total,
    )


# ──────────────────────────────────────────────────────────────────────
# Reconciliation Particulars (reconciliation statement table)
# ──────────────────────────────────────────────────────────────────────


@router.get(
    "/{case_id}/particulars",
    response_model=ParticularsSummaryResponse,
    status_code=status.HTTP_200_OK,
    summary="Reconciliation statement (Particulars: closing-balance & transaction differences)",
    dependencies=[Depends(require_permission("vlr.cases.read"))],
)
async def get_reconciliation_particulars(
    case_id: UUID,
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db_session),
) -> ParticularsSummaryResponse:
    """
    GET /api/v1/vlr/reconciliation/{case_id}/particulars

    Builds the Firmway-style reconciliation statement:
      • Closing Balance Difference (company vs party closing balances)
      • One "<Category> Difference" group per document category that has
        unmatched entries, with children split by which side did not book
        the entry ("not booked by Company" / "not booked by Party")
      • Calculated Balance = sum of all transaction-difference groups, which
        reconciles the closing-balance gap.
    """
    case = await _verify_case_exists(case_id, session)
    cid = str(case_id)

    # Reuse the SAME classification logic as the Excel export so the on-screen
    # statement and the downloaded workbook never disagree.
    from src.domain.services.vlr.reconciliation_export_service import (
        CATEGORY_TO_SUMMARY,
        DEFAULT_SUMMARY,
        ReconciliationExportService,
        _closing,
        _closing_count,
        _company_closing,
        _num,
        _special_classification,
        matched_residual_bucket,
    )

    # Load full ledgers (ORM entries) for both sides.
    comp_res = await session.execute(
        select(LedgerEntryModel).where(
            and_(LedgerEntryModel.case_id == cid, LedgerEntryModel.side == "company")
        )
    )
    company_entries = list(comp_res.scalars().all())
    party_res = await session.execute(
        select(LedgerEntryModel).where(
            and_(LedgerEntryModel.case_id == cid, LedgerEntryModel.side == "vendor")
        )
    )
    vendor_entries = list(party_res.scalars().all())

    groups: list[ParticularsGroup] = []

    # ── Closing Balance Difference (from the actual closing-balance rows) ──
    # Party amounts are stored with the opposite sign, so the difference is the
    # SUM of the two sides (mirrors the export service).
    company_closing = _company_closing(company_entries)
    party_closing = _closing(vendor_entries)
    n_company_closing = _closing_count(company_entries)
    n_party_closing = _closing_count(vendor_entries)
    closing_diff = company_closing + party_closing

    if n_company_closing or n_party_closing:
        groups.append(
            ParticularsGroup(
                label="Closing Balance Difference",
                amount=closing_diff,
                no_of_entries=n_company_closing + n_party_closing,
                view_key="closing_balance",
                children=[
                    ParticularsChild(
                        label="Closing Balance as per Company",
                        amount=company_closing,
                        no_of_entries=n_company_closing,
                        side="company",
                        document_category="Closing Balance",
                        view_key="closing_company",
                    ),
                    ParticularsChild(
                        label="Closing Balance as per Party",
                        amount=party_closing,
                        no_of_entries=n_party_closing,
                        side="vendor",
                        document_category="Closing Balance",
                        view_key="closing_party",
                    ),
                ],
            )
        )

    # ── Difference buckets (unmatched, excluding balances & knock-offs) ──
    # An entry is a genuine cross-ledger difference only when it is unmatched
    # AND is not an entry-intrinsic class (Opening/Closing Balance, Reversal).
    def _bucket(entries, side: str):
        """Returns {(group, label): [amount, count]} for one side."""
        out: dict[tuple[str, str], list] = {}
        for e in entries:
            if getattr(e, "match_id", None):
                continue
            cat = (getattr(e, "document_category", "") or "").strip()
            if cat in ("Opening Balance", "Closing Balance"):
                continue
            special = _special_classification(e)
            if special in ("Opening Balance", "Closing Balance", "Reversal Entries"):
                continue
            # Bug fix: an unmatched TDS entry must roll up under "TDS / TCS
            # Difference" regardless of its raw document_category (the
            # export service's own bucket() closure already does this via
            # CATEGORY_TO_SUMMARY["TDS Adjusted"] — this endpoint was
            # missing the same special-case, so unmatched TDS entries fell
            # through to "Other Differences" on-screen while the exported
            # workbook correctly grouped them under TDS / TCS Difference).
            if special == "TDS Booked by Party":
                info = CATEGORY_TO_SUMMARY["TDS Adjusted"]
            else:
                info = CATEGORY_TO_SUMMARY.get(cat, DEFAULT_SUMMARY)
            # An entry open on the company side is missing on the party side,
            # and vice versa (see Emcure mapping rules doc + export service).
            label = info["party_missing"] if side == "company" else info["company_missing"]
            grp = info["group"]
            agg = out.setdefault((grp, label), [Decimal("0"), 0])
            agg[0] += Decimal(str(_num(getattr(e, "amount", 0))))
            agg[1] += 1
        return out

    comp_buckets = _bucket(company_entries, "company")
    party_buckets = _bucket(vendor_entries, "party")

    # Reference display order for the difference groups.
    group_order = [
        "Invoice Difference",
        "Debit Note / Credit Note Difference",
        "Payment / receipt Difference",
        "Other Differences",
        "TDS / TCS Difference",
        "Amount Mismatch Difference",
        "Write Off / Rounding Off Difference",
        "Unexplained Amount Gap Difference",
    ]
    lines_by_group: dict[str, list[ParticularsChild]] = {}
    for (grp, label), (amt, cnt) in {**comp_buckets, **party_buckets}.items():
        # Bug fix: a line labeled "... not booked by Party" comes from
        # _bucket(company_entries, ...) — the underlying rows physically
        # live in the COMPANY ledger (company booked it, party hasn't), so
        # its drill-in view is unmatched-company. Conversely "... not
        # booked by Company" rows live in the VENDOR ledger. This was
        # inverted (checked "by Company" -> side="company"), which silently
        # pointed the child-row "View" action at the wrong ledger side.
        side = "company" if "by Party" in label else "vendor"
        lines_by_group.setdefault(grp, []).append(
            ParticularsChild(
                label=label,
                amount=amt,
                no_of_entries=cnt,
                side=side,
                document_category=grp,
                # Bug fix: this was hardcoded to the generic "unmatched"
                # placeholder for every group, so the frontend's "View" slug
                # resolver had no way to tell "Invoice Difference" apart
                # from "Other Differences" or any other group — every group's
                # View link ended up pointing at the exact same full
                # unmatched-company list. view_key now carries the actual
                # Particulars group label, which the frontend passes through
                # as the `group_filter` query param on unmatched-company/
                # unmatched-vendor so each group's View only shows its own
                # entries.
                view_key=grp,
            )
        )

    # ── Matched-pair residuals (TDS deducted, rounding write-off, unexplained
    # gap, amount mismatch) ──
    # Bug fix: the statement above only ever itemised UNMATCHED (one-sided)
    # entries — a matched PAIR that still carries a genuine residual gap
    # never appeared here at all, even though the Excel export already
    # surfaces these via matched_residual_bucket. Client: "are the matched
    # columns not a part of these particulars and differences? we also need
    # those". Build the same row dicts the export service computes Status/
    # Classification from, then fold matched_residual_bucket's output into
    # the same groups so "TDS / TCS Difference", "Write Off / Rounding Off
    # Difference", "Unexplained Amount Gap Difference", and "Amount Mismatch
    # Difference" now include BOTH the unmatched entries above AND matched
    # pairs with a residual, exactly like the downloaded workbook.
    mr_res = await session.execute(
        select(MatchResultModel).where(MatchResultModel.case_id == cid)
    )
    match_results = list(mr_res.scalars().all())
    tds_max, tds_min, gst_pct = await _load_tax_config(case, session)
    export_svc = ReconciliationExportService()
    export_svc._tds_percentage_value = tds_max
    export_svc._tds_percentage_min_value = tds_min
    export_svc._gst_percentage_value = gst_pct
    by_id = {str(e.id): e for e in company_entries + vendor_entries}
    recon_rows = export_svc._build_recon_rows(company_entries, vendor_entries, match_results, by_id)
    matched_residuals = matched_residual_bucket(recon_rows)
    for (grp, label, _action), (amt, cnt) in matched_residuals.items():
        lines_by_group.setdefault(grp, []).append(
            ParticularsChild(
                label=label,
                amount=amt,
                no_of_entries=cnt,
                side="",
                document_category=grp,
                view_key=grp,
                is_matched_residual=True,
                matched_status=label,
            )
        )

    calculated_balance = Decimal("0")
    ordered = group_order + [g for g in lines_by_group if g not in group_order]
    for grp in ordered:
        children = lines_by_group.get(grp)
        if not children:
            continue
        grp_amount = sum((c.amount for c in children), Decimal("0"))
        grp_count = sum((c.no_of_entries for c in children), 0)
        groups.append(
            ParticularsGroup(
                label=grp,
                amount=grp_amount,
                no_of_entries=grp_count,
                # See comment above on the child view_key — same fix at the
                # group level, so the group-row "View" (the one shown in the
                # collapsed table before expanding) also gets its own
                # dedicated drill-in instead of the shared "unmatched" slug.
                view_key=grp,
                # True only when every child is a matched residual (no
                # unmatched component) — lets the frontend route the
                # group-level View straight to the Matched/Recommended tab.
                is_matched_residual=all(c.is_matched_residual for c in children),
                children=children,
            )
        )
        calculated_balance += grp_amount

    # ── Knocking Off section (informational) ──
    # Reversal / knock-off entries (SAP doc type "AB" / category "Knocking Off")
    # net within the company ledger. They aren't a cross-ledger difference, but
    # users want to inspect them and confirm the residue is zero. Shown as its
    # own group with a "Knocking Residue" total; it does NOT feed the Calculated
    # Balance because a fully-paired knock-off nets to zero.
    def _is_knockoff(e) -> bool:
        cat = (getattr(e, "document_category", "") or "").strip().lower()
        dtype = (getattr(e, "document_type", "") or "").strip().upper()
        return cat == "knocking off" or dtype == "AB" or _special_classification(e) == "Reversal Entries"

    knock_company = [e for e in company_entries if _is_knockoff(e)]
    knock_party = [e for e in vendor_entries if _is_knockoff(e)]

    if knock_company or knock_party:
        knock_company_amt = sum(
            (Decimal(str(_num(getattr(e, "amount", 0)))) for e in knock_company), Decimal("0")
        )
        knock_party_amt = sum(
            (Decimal(str(_num(getattr(e, "amount", 0)))) for e in knock_party), Decimal("0")
        )
        knock_children: list[ParticularsChild] = []
        if knock_company:
            knock_children.append(
                ParticularsChild(
                    label="Knocking Off as per Company",
                    amount=knock_company_amt,
                    no_of_entries=len(knock_company),
                    side="company",
                    document_category="Knocking Off",
                    view_key="knocking",
                )
            )
        if knock_party:
            knock_children.append(
                ParticularsChild(
                    label="Knocking Off as per Party",
                    amount=knock_party_amt,
                    no_of_entries=len(knock_party),
                    side="vendor",
                    document_category="Knocking Off",
                    view_key="knocking",
                )
            )
        # Residue: sum of all knock-off amounts. Should be 0 when fully paired.
        knock_residue = knock_company_amt + knock_party_amt
        knock_children.append(
            ParticularsChild(
                label="Knocking Residue",
                amount=knock_residue,
                no_of_entries=len(knock_company) + len(knock_party),
                side="",
                document_category="Knocking Off",
                view_key="knocking",
            )
        )
        groups.append(
            ParticularsGroup(
                label="Knocking Off",
                amount=knock_residue,
                no_of_entries=len(knock_company) + len(knock_party),
                view_key="knocking",
                children=knock_children,
            )
        )

    # ── Manually Mapped section ──
    # Reviewer-linked entries (pass 8) grouped by the mandatory status_reason
    # selected at link time (see manual_link / docs/Update Status.xlsx). Each
    # reason becomes a child row with its own amount total and entry count.
    manual_res = await session.execute(
        select(MatchResultModel).where(
            and_(
                MatchResultModel.case_id == cid,
                MatchResultModel.pass_number == 8,
            )
        )
    )
    manual_matches = list(manual_res.scalars().all())

    if manual_matches:
        reason_buckets: dict[str, list] = {}
        for m in manual_matches:
            reason = m.status_reason or "Unspecified"
            n_entries = len(m.company_entry_ids or []) + len(m.vendor_entry_ids or [])
            agg = reason_buckets.setdefault(reason, [Decimal("0"), 0])
            agg[0] += Decimal(str(_num(m.matched_amount)))
            agg[1] += n_entries

        manual_children = [
            ParticularsChild(
                label=reason,
                amount=amt,
                no_of_entries=cnt,
                side="",
                document_category="Manually Mapped",
                view_key="manually_mapped",
            )
            for reason, (amt, cnt) in sorted(reason_buckets.items())
        ]
        manual_total_amount = sum((c.amount for c in manual_children), Decimal("0"))
        manual_total_entries = sum((c.no_of_entries for c in manual_children), 0)

        groups.append(
            ParticularsGroup(
                label="Manually Mapped",
                amount=manual_total_amount,
                no_of_entries=manual_total_entries,
                view_key="manually_mapped",
                children=manual_children,
            )
        )

    return ParticularsSummaryResponse(
        case_id=case_id,
        closing_balance_company=company_closing,
        closing_balance_party=party_closing,
        groups=groups,
        calculated_balance=calculated_balance,
    )


# ──────────────────────────────────────────────────────────────────────
# Excel Export (Firmway-format multi-sheet workbook)
# ──────────────────────────────────────────────────────────────────────


@router.get(
    "/{case_id}/export",
    summary="Export reconciliation as a formatted Excel workbook",
    dependencies=[Depends(require_permission("vlr.cases.read"))],
)
async def export_reconciliation(
    case_id: UUID,
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db_session),
):
    """
    GET /api/v1/vlr/reconciliation/{case_id}/export

    Builds a multi-sheet Excel workbook (Summary + Reconciliation + annexures +
    Party) matching the reference reconciliation export format.
    """
    from datetime import datetime, timezone

    from fastapi.responses import Response

    from src.domain.services.vlr.reconciliation_export_service import (
        ReconciliationExportService,
    )
    from src.infrastructure.database.models.vlr.vendor_model import VendorModel
    from src.infrastructure.database.models.vlr.reconciliation_request_model import (
        ReconciliationRequestModel,
    )

    case = await _verify_case_exists(case_id, session)

    # Vendor
    vendor = None
    if case.vendor_id:
        vres = await session.execute(
            select(VendorModel).where(VendorModel.id == str(case.vendor_id))
        )
        vendor = vres.scalar_one_or_none()

    # Parent request (period + tolerances)
    parent = None
    if case.request_id:
        pres = await session.execute(
            select(ReconciliationRequestModel).where(
                ReconciliationRequestModel.id == str(case.request_id)
            )
        )
        parent = pres.scalar_one_or_none()

    # Ledger entries
    ce_res = await session.execute(
        select(LedgerEntryModel).where(
            and_(LedgerEntryModel.case_id == str(case_id), LedgerEntryModel.side == "company")
        )
    )
    company_entries = list(ce_res.scalars().all())

    ve_res = await session.execute(
        select(LedgerEntryModel).where(
            and_(LedgerEntryModel.case_id == str(case_id), LedgerEntryModel.side == "vendor")
        )
    )
    vendor_entries = list(ve_res.scalars().all())

    # Match results
    mr_res = await session.execute(
        select(MatchResultModel).where(MatchResultModel.case_id == str(case_id))
    )
    match_results = list(mr_res.scalars().all())

    # Tolerances (as display strings)
    tol_amt = f"{float(parent.tolerance_amount or 0)} Rs" if parent else "0 Rs"
    tds_min_display = float(getattr(parent, "tds_percentage_min", 0) or 0) if parent else 0.0
    tds_max_display = float(getattr(parent, "tds_percentage", 0) or 0) if parent else 0.0
    tds_pct = f"{tds_min_display} - {tds_max_display}"
    party_code = getattr(vendor, "vendor_code", "") or ""
    party_name = getattr(vendor, "name", "reconciliation") or "reconciliation"

    service = ReconciliationExportService()
    xlsx_bytes = service.build(
        case=case,
        vendor=vendor,
        company_entries=company_entries,
        vendor_entries=vendor_entries,
        match_results=match_results,
        reco_datetime=datetime.now(timezone.utc),
        period_start=getattr(parent, "period_start", None),
        period_end=getattr(parent, "period_end", None),
        party_code=party_code,
        tolerance_amount=tol_amt,
        tds_percentage=tds_pct,
        tds_percentage_value=tds_max_display,
        tds_percentage_min_value=tds_min_display,
        gst_percentage_value=float(getattr(parent, "gst_percentage", 0) or 0) if parent else 0.0,
    )

    def _san(s: str) -> str:
        return "".join(ch if ch.isalnum() else "-" for ch in str(s)).strip("-")

    filename = f"Reconciliation-{_san(party_name)}.xlsx"
    return Response(
        content=xlsx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
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
    """Request to manually link unmatched company + vendor entries.

    status_reason is MANDATORY: the reviewer must select why these two
    entries are being linked, from the fixed list in
    docs/Update Status.xlsx (see status_reasons.STATUS_REASONS).
    """
    company_entry_ids: list[str]
    vendor_entry_ids: list[str]
    status_reason: str
    notes: str | None = None


class ManualLinkResponse(_LinkBaseModel):
    match_id: str
    company_amount: float
    vendor_amount: float
    difference: float
    status_reason: str
    message: str


class StatusReasonsResponse(_LinkBaseModel):
    """List of valid reasons a reviewer may select for a manual link."""
    reasons: list[str]


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

    reason = (request.status_reason or "").strip()
    if not reason:
        raise HTTPException(
            status_code=422,
            detail="status_reason is required — select why these entries are being linked.",
        )
    if reason not in VALID_STATUS_REASONS:
        raise HTTPException(
            status_code=422,
            detail=f"'{reason}' is not a recognized status reason. See GET /status-reasons for the valid list.",
        )

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
        status_reason=reason,
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
            "status_reason": reason,
            "notes": request.notes or "",
        },
    ))

    await session.commit()

    return ManualLinkResponse(
        match_id=str(match_id),
        company_amount=float(company_amount),
        vendor_amount=float(vendor_amount),
        difference=float(difference),
        status_reason=reason,
        message=(
            f"Linked {len(company_entries)} company + {len(vendor_entries)} vendor "
            f"entries. Net difference: {float(difference):.2f}"
        ),
    )


@router.get(
    "/status-reasons",
    response_model=StatusReasonsResponse,
    status_code=status.HTTP_200_OK,
    summary="List valid manual-link status reasons",
    dependencies=[Depends(require_permission("vlr.cases.read"))],
)
async def get_status_reasons(
    current_user: User = Depends(get_current_active_user),
) -> StatusReasonsResponse:
    """
    GET /api/v1/vlr/reconciliation/status-reasons

    Returns the fixed list of reasons a reviewer must choose from when
    manually linking two unmatched entries (see docs/Update Status.xlsx).
    Not case-scoped — the list is the same across all cases.
    """
    return StatusReasonsResponse(reasons=STATUS_REASONS)


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

