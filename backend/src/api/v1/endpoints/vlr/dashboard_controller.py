"""
Dashboard API endpoints for VLR KPI widgets and recent confirmations.

Routes:
- GET /api/v1/vlr/dashboard/widgets             — All KPI widget data
- GET /api/v1/vlr/dashboard/recent-confirmations — Recent vendor sign-offs

Requirements: 26.1, 26.2, 26.3, 26.4, 26.5, 26.6, 26.7, 26.8
"""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_, case, extract, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.v1.schemas.vlr.dashboard_schemas import (
    DashboardWidgetsResponse,
    RecentConfirmationItem,
    RecentConfirmationsResponse,
)
from src.infrastructure.database.models.vlr.ledger_entry_model import LedgerEntryModel
from src.infrastructure.database.models.vlr.match_result_model import MatchResultModel
from src.infrastructure.database.models.vlr.portal_sign_off_model import PortalSignOffModel
from src.infrastructure.database.models.vlr.reconciliation_case_model import (
    ReconciliationCaseModel,
)
from src.infrastructure.database.models.vlr.vendor_model import VendorModel
from src.infrastructure.database.session import get_db_session
from src.infrastructure.security.permission_manager import require_permission

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/vlr/dashboard", tags=["VLR - Dashboard"])


# ──────────────────────────────────────────────────────────────────────
# Endpoints
# ──────────────────────────────────────────────────────────────────────


@router.get(
    "/widgets",
    response_model=DashboardWidgetsResponse,
    summary="Get all dashboard KPI widget data",
    dependencies=[Depends(require_permission("vlr.cases.read"))],
)
async def get_dashboard_widgets(
    company_code: str | None = Query(
        default=None, description="Optional company code filter"
    ),
    session: AsyncSession = Depends(get_db_session),
) -> DashboardWidgetsResponse:
    """
    GET /api/v1/vlr/dashboard/widgets

    Returns aggregated KPI metrics for the VLR dashboard:
    - Open Cases: active reconciliations not yet closed
    - Pending Vendor Upload: cases in vendor_engagement step with upload_count=0
    - Pending Finance Review: cases in finance_review or exception_resolution step
    - Overdue Cases: cases exceeding SLA
    - Cases Closed This Month: closed in current calendar month
    - Average Cycle Time: mean days from creation to closure
    - Auto-Match Rate: percentage matched by Pass 1+2 vs total entries
    """
    now = datetime.now(timezone.utc)

    # Base filter: non-deleted cases
    base_filter = ReconciliationCaseModel.is_deleted == False  # noqa: E712

    # ─── Open Cases (Req 26.1) ────────────────────────────────────────────
    open_cases_stmt = select(func.count(ReconciliationCaseModel.id)).where(
        and_(
            base_filter,
            ReconciliationCaseModel.status != "closed",
        )
    )
    if company_code:
        open_cases_stmt = open_cases_stmt.join(
            VendorModel, ReconciliationCaseModel.vendor_id == VendorModel.id
        ).where(VendorModel.company_code == company_code)
    open_cases = (await session.execute(open_cases_stmt)).scalar_one()

    # ─── Pending Vendor Upload (Req 26.2) ─────────────────────────────────
    pending_upload_stmt = select(func.count(ReconciliationCaseModel.id)).where(
        and_(
            base_filter,
            ReconciliationCaseModel.current_workflow_step == "vendor_engagement",
            ReconciliationCaseModel.upload_count == 0,
        )
    )
    if company_code:
        pending_upload_stmt = pending_upload_stmt.join(
            VendorModel, ReconciliationCaseModel.vendor_id == VendorModel.id
        ).where(VendorModel.company_code == company_code)
    pending_vendor_upload = (await session.execute(pending_upload_stmt)).scalar_one()

    # ─── Pending Finance Review (Req 26.3) ────────────────────────────────
    pending_review_stmt = select(func.count(ReconciliationCaseModel.id)).where(
        and_(
            base_filter,
            ReconciliationCaseModel.current_workflow_step.in_(
                ["finance_review", "exception_resolution"]
            ),
        )
    )
    if company_code:
        pending_review_stmt = pending_review_stmt.join(
            VendorModel, ReconciliationCaseModel.vendor_id == VendorModel.id
        ).where(VendorModel.company_code == company_code)
    pending_finance_review = (await session.execute(pending_review_stmt)).scalar_one()

    # ─── Overdue Cases (Req 26.4) ─────────────────────────────────────────
    overdue_stmt = select(func.count(ReconciliationCaseModel.id)).where(
        and_(
            base_filter,
            ReconciliationCaseModel.is_overdue == True,  # noqa: E712
        )
    )
    if company_code:
        overdue_stmt = overdue_stmt.join(
            VendorModel, ReconciliationCaseModel.vendor_id == VendorModel.id
        ).where(VendorModel.company_code == company_code)
    overdue_cases = (await session.execute(overdue_stmt)).scalar_one()

    # ─── Cases Closed This Month (Req 26.5) ───────────────────────────────
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    closed_month_stmt = select(func.count(ReconciliationCaseModel.id)).where(
        and_(
            base_filter,
            ReconciliationCaseModel.status == "closed",
            ReconciliationCaseModel.modified_date >= month_start,
        )
    )
    if company_code:
        closed_month_stmt = closed_month_stmt.join(
            VendorModel, ReconciliationCaseModel.vendor_id == VendorModel.id
        ).where(VendorModel.company_code == company_code)
    cases_closed_this_month = (await session.execute(closed_month_stmt)).scalar_one()

    # ─── Average Cycle Time (Req 26.6) ────────────────────────────────────
    # Mean days from case creation (created_date) to closure (modified_date for closed cases)
    cycle_time_stmt = select(
        func.avg(
            extract(
                "epoch",
                ReconciliationCaseModel.modified_date - ReconciliationCaseModel.created_date,
            )
            / 86400.0  # Convert seconds to days
        )
    ).where(
        and_(
            base_filter,
            ReconciliationCaseModel.status == "closed",
        )
    )
    if company_code:
        cycle_time_stmt = cycle_time_stmt.join(
            VendorModel, ReconciliationCaseModel.vendor_id == VendorModel.id
        ).where(VendorModel.company_code == company_code)
    avg_cycle_time_result = (await session.execute(cycle_time_stmt)).scalar_one()
    average_cycle_time_days = (
        round(float(avg_cycle_time_result), 1) if avg_cycle_time_result else None
    )

    # ─── Auto-Match Rate (Req 26.7) ───────────────────────────────────────
    # Percentage of entries matched by Pass 1 (Exact) + Pass 2 (Tolerance) vs total entries
    total_entries_stmt = select(func.count(LedgerEntryModel.id))
    if company_code:
        total_entries_stmt = total_entries_stmt.join(
            ReconciliationCaseModel, LedgerEntryModel.case_id == ReconciliationCaseModel.id
        ).join(
            VendorModel, ReconciliationCaseModel.vendor_id == VendorModel.id
        ).where(VendorModel.company_code == company_code)
    total_entries = (await session.execute(total_entries_stmt)).scalar_one()

    auto_match_rate: float | None = None
    if total_entries > 0:
        auto_matched_stmt = select(func.count(LedgerEntryModel.id)).where(
            and_(
                LedgerEntryModel.match_id.isnot(None),
                LedgerEntryModel.pass_number.in_([1, 2]),
            )
        )
        if company_code:
            auto_matched_stmt = auto_matched_stmt.join(
                ReconciliationCaseModel,
                LedgerEntryModel.case_id == ReconciliationCaseModel.id,
            ).join(
                VendorModel, ReconciliationCaseModel.vendor_id == VendorModel.id
            ).where(VendorModel.company_code == company_code)
        auto_matched = (await session.execute(auto_matched_stmt)).scalar_one()
        auto_match_rate = round((auto_matched / total_entries) * 100, 2)

    return DashboardWidgetsResponse(
        open_cases=open_cases,
        pending_vendor_upload=pending_vendor_upload,
        pending_finance_review=pending_finance_review,
        overdue_cases=overdue_cases,
        cases_closed_this_month=cases_closed_this_month,
        average_cycle_time_days=average_cycle_time_days,
        auto_match_rate=auto_match_rate,
    )


@router.get(
    "/recent-confirmations",
    response_model=RecentConfirmationsResponse,
    summary="Get recent vendor sign-off confirmations",
    dependencies=[Depends(require_permission("vlr.cases.read"))],
)
async def get_recent_confirmations(
    limit: int = Query(default=10, ge=1, le=50, description="Number of recent confirmations"),
    company_code: str | None = Query(
        default=None, description="Optional company code filter"
    ),
    session: AsyncSession = Depends(get_db_session),
) -> RecentConfirmationsResponse:
    """
    GET /api/v1/vlr/dashboard/recent-confirmations

    Returns the last N vendor sign-offs with vendor name, date, and case ID.
    Default limit is 10 per BRD Section 10.1.

    Requirement 26.8: Recent Confirmations table with sortable columns.
    """
    # Build the query joining sign-offs with cases and vendors
    stmt = (
        select(
            PortalSignOffModel.case_id,
            PortalSignOffModel.signed_at,
            PortalSignOffModel.statement_version,
            PortalSignOffModel.confirmation_text,
            VendorModel.name.label("vendor_name"),
        )
        .join(
            ReconciliationCaseModel,
            PortalSignOffModel.case_id == ReconciliationCaseModel.id,
        )
        .join(
            VendorModel,
            ReconciliationCaseModel.vendor_id == VendorModel.id,
        )
        .where(ReconciliationCaseModel.is_deleted == False)  # noqa: E712
        .order_by(PortalSignOffModel.signed_at.desc())
        .limit(limit)
    )

    if company_code:
        stmt = stmt.where(VendorModel.company_code == company_code)

    result = await session.execute(stmt)
    rows = result.all()

    # Get total count
    count_stmt = (
        select(func.count(PortalSignOffModel.id))
        .join(
            ReconciliationCaseModel,
            PortalSignOffModel.case_id == ReconciliationCaseModel.id,
        )
        .where(ReconciliationCaseModel.is_deleted == False)  # noqa: E712
    )
    if company_code:
        count_stmt = count_stmt.join(
            VendorModel,
            ReconciliationCaseModel.vendor_id == VendorModel.id,
        ).where(VendorModel.company_code == company_code)
    total = (await session.execute(count_stmt)).scalar_one()

    items = [
        RecentConfirmationItem(
            case_id=row.case_id,
            vendor_name=row.vendor_name,
            signed_at=row.signed_at,
            statement_version=row.statement_version,
            confirmation_text=row.confirmation_text,
        )
        for row in rows
    ]

    return RecentConfirmationsResponse(items=items, total=total)
