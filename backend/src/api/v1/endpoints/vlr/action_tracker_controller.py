"""
Action Tracker API endpoints.

Routes:
- GET   /api/v1/vlr/action-tracker/requests/{request_id}/summary — grouped counts/%/amount
- GET   /api/v1/vlr/action-tracker/requests/{request_id}/items   — paginated detail rows
- GET   /api/v1/vlr/action-tracker/requests/{request_id}/export  — download .xlsx
- PATCH /api/v1/vlr/action-tracker/items                         — update one row's workflow fields
- POST  /api/v1/vlr/action-tracker/items/bulk-update              — update many rows at once
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.v1.dependencies import get_current_active_user
from src.api.v1.schemas.vlr.action_tracker_schemas import (
    ActionTrackerItemListResponse,
    ActionTrackerItemResponse,
    ActionTrackerSummaryResponse,
    ActionTrackerSummaryRowResponse,
    BulkUpdateActionTakenRequest,
    BulkUpdateActionTakenResponse,
    UpdateActionTakenRequest,
)
from src.domain.entities.user import User
from src.domain.services.vlr.action_tracker_service import ActionTrackerService
from src.infrastructure.database.models.vlr.reconciliation_request_model import ReconciliationRequestModel
from src.infrastructure.database.session import get_db_session
from src.infrastructure.security.permission_manager import require_permission

router = APIRouter(prefix="/vlr/action-tracker", tags=["VLR - Action Tracker"])


async def _verify_request_exists(request_id: UUID, company_code: str, session: AsyncSession) -> None:
    res = await session.execute(
        select(ReconciliationRequestModel).where(
            ReconciliationRequestModel.id == str(request_id),
            ReconciliationRequestModel.company_code == company_code,
        )
    )
    if res.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Reconciliation request not found")


@router.get(
    "/requests/{request_id}/summary",
    response_model=ActionTrackerSummaryResponse,
    summary="Action Tracker summary — counts/%/amount grouped by Action Taken Status",
    dependencies=[Depends(require_permission("vlr.cases.read"))],
)
async def get_action_tracker_summary(
    request_id: UUID,
    company_code: str = Query(..., min_length=1, description="Company code"),
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db_session),
) -> ActionTrackerSummaryResponse:
    """GET /api/v1/vlr/action-tracker/requests/{request_id}/summary"""
    await _verify_request_exists(request_id, company_code, session)

    service = ActionTrackerService(session)
    summary = await service.build_summary(request_id)

    return ActionTrackerSummaryResponse(
        request_id=request_id,
        rows=[
            ActionTrackerSummaryRowResponse(
                action_taken_status=r.action_taken_status,
                number_of_records=r.number_of_records,
                percentage=r.percentage,
                amount=r.amount,
            )
            for r in summary.rows
        ],
        total_records=summary.total_records,
        total_amount=summary.total_amount,
    )


@router.get(
    "/requests/{request_id}/items",
    response_model=ActionTrackerItemListResponse,
    summary="Action Tracker detail rows (paginated, filterable)",
    dependencies=[Depends(require_permission("vlr.cases.read"))],
)
async def list_action_tracker_items(
    request_id: UUID,
    company_code: str = Query(..., min_length=1, description="Company code"),
    action_taken_status: str | None = Query(default=None, description="Filter by Action Taken Status"),
    status_filter: str | None = Query(default=None, alias="status", description="Filter by reconciliation Status"),
    action_owner: str | None = Query(default=None, description="Filter by Action Owner"),
    search: str | None = Query(default=None, description="Search party code/name"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=200),
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db_session),
) -> ActionTrackerItemListResponse:
    """GET /api/v1/vlr/action-tracker/requests/{request_id}/items"""
    await _verify_request_exists(request_id, company_code, session)

    service = ActionTrackerService(session)
    rows = await service.build_rows(request_id)

    if action_taken_status:
        rows = [r for r in rows if r.action_taken_status == action_taken_status]
    if status_filter:
        rows = [r for r in rows if r.status == status_filter]
    if action_owner:
        rows = [r for r in rows if r.action_owner == action_owner]
    if search:
        needle = search.lower()
        rows = [
            r for r in rows
            if needle in r.vendor_code.lower() or needle in r.vendor_name.lower()
        ]

    total = len(rows)
    total_pages = (total + page_size - 1) // page_size if page_size else 0
    start = (page - 1) * page_size
    page_rows = rows[start : start + page_size]

    return ActionTrackerItemListResponse(
        items=[
            ActionTrackerItemResponse(
                row_key=r.row_key,
                case_id=r.case_id,
                vendor_code=r.vendor_code,
                vendor_name=r.vendor_name,
                company_id=r.company_id,
                party_id=r.party_id,
                match_id=r.match_id,
                status=r.status,
                classification=r.classification,
                action_taken_status=r.action_taken_status,
                action_owner=r.action_owner,
                company_invoice_date=r.company_invoice_date,
                company_invoice_number=r.company_invoice_number,
                company_doctype=r.company_doctype,
                company_original_doctype=r.company_original_doctype,
                company_narration=r.company_narration,
                company_amount=str(r.company_amount),
                party_invoice_date=r.party_invoice_date,
                party_invoice_number=r.party_invoice_number,
                party_doctype=r.party_doctype,
                party_original_doctype=r.party_original_doctype,
                party_narration=r.party_narration,
                party_amount=str(r.party_amount),
                difference=r.difference,
                remarks=r.remarks,
                request_closed=r.request_closed,
                action_taken_reference=r.action_taken_reference,
                action_taken_remark=r.action_taken_remark,
                reco_datetime=r.reco_datetime,
                posting_date=r.posting_date,
                clearing_date=r.clearing_date,
                clearing_document_number=r.clearing_document_number,
                tds_amount=str(r.tds_amount),
            )
            for r in page_rows
        ],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.get(
    "/requests/{request_id}/export",
    summary="Download Action Tracker detail grid as .xlsx",
    dependencies=[Depends(require_permission("vlr.cases.read"))],
)
async def export_action_tracker(
    request_id: UUID,
    company_code: str = Query(..., min_length=1, description="Company code"),
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db_session),
) -> Response:
    """GET /api/v1/vlr/action-tracker/requests/{request_id}/export"""
    await _verify_request_exists(request_id, company_code, session)

    res = await session.execute(
        select(ReconciliationRequestModel).where(ReconciliationRequestModel.id == str(request_id))
    )
    req_obj = res.scalar_one_or_none()
    title = getattr(req_obj, "title", None) or getattr(req_obj, "request_number", None) or str(request_id)

    service = ActionTrackerService(session)
    xlsx_bytes = await service.build_export(request_id, request_title=title)

    safe_title = "".join(c for c in str(title) if c.isalnum() or c in (" ", "-", "_")).strip() or str(request_id)
    filename = f"Action Tracker_{safe_title}.xlsx"

    return Response(
        content=xlsx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.patch(
    "/items",
    response_model=BulkUpdateActionTakenResponse,
    summary="Update one Action Tracker row's workflow fields (owner/reference/remark/closed)",
    dependencies=[Depends(require_permission("vlr.cases.write"))],
)
async def update_action_tracker_item(
    request_id: UUID = Query(..., description="Reconciliation request ID"),
    body: UpdateActionTakenRequest = ...,
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db_session),
) -> BulkUpdateActionTakenResponse:
    """PATCH /api/v1/vlr/action-tracker/items?request_id=..."""
    service = ActionTrackerService(session)
    await service.update_item(
        request_id,
        body.case_id,
        body.row_key,
        action_owner=body.action_owner,
        action_taken_reference=body.action_taken_reference,
        action_taken_remark=body.action_taken_remark,
        request_closed=body.request_closed,
        updated_by=str(getattr(current_user, "email", None) or getattr(current_user, "id", "system")),
    )
    await session.commit()
    return BulkUpdateActionTakenResponse(updated=1)


@router.post(
    "/items/bulk-update",
    response_model=BulkUpdateActionTakenResponse,
    summary="Update multiple Action Tracker rows' workflow fields at once",
    dependencies=[Depends(require_permission("vlr.cases.write"))],
)
async def bulk_update_action_tracker_items(
    request_id: UUID = Query(..., description="Reconciliation request ID"),
    body: BulkUpdateActionTakenRequest = ...,
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db_session),
) -> BulkUpdateActionTakenResponse:
    """POST /api/v1/vlr/action-tracker/items/bulk-update?request_id=..."""
    service = ActionTrackerService(session)
    updated_by = str(getattr(current_user, "email", None) or getattr(current_user, "id", "system"))
    count = 0
    for item in body.items:
        await service.update_item(
            request_id,
            item.case_id,
            item.row_key,
            action_owner=item.action_owner,
            action_taken_reference=item.action_taken_reference,
            action_taken_remark=item.action_taken_remark,
            request_closed=item.request_closed,
            updated_by=updated_by,
        )
        count += 1
    await session.commit()
    return BulkUpdateActionTakenResponse(updated=count)
