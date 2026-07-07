"""
SAP Pull API endpoint.

Provides the POST /api/v1/vlr/requests/{id}/sap-pull endpoint to trigger
asynchronous SAP data extraction via Celery task.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.v1.dependencies import get_current_active_user
from src.domain.entities.user import User
from src.infrastructure.background.celery_app import celery_app
from src.infrastructure.database.models.vlr.reconciliation_case_model import (
    ReconciliationCaseModel,
)
from src.infrastructure.database.models.vlr.reconciliation_request_model import (
    ReconciliationRequestModel,
)
from src.infrastructure.database.models.vlr.vendor_model import VendorModel
from src.infrastructure.database.session import get_db_session
from src.infrastructure.tasks.vlr.sap_tasks import sap_pull_task

router = APIRouter(prefix="/vlr/requests", tags=["VLR - SAP Integration"])


# ---------------------------------------------------------------------------
# Request/Response Schemas
# ---------------------------------------------------------------------------


class SAPPullRequest(BaseModel):
    """Request body for triggering a SAP data pull."""

    vendor_codes: list[str] | None = Field(
        default=None,
        description=(
            "Optional list of vendor codes to pull data for. "
            "If not provided, pulls data for all vendors in the request."
        ),
    )


class SAPPullResponse(BaseModel):
    """Response for a triggered SAP pull task."""

    task_id: str = Field(description="Celery task ID for tracking progress")
    request_id: str = Field(description="Reconciliation request ID")
    status: str = Field(description="Task dispatch status")
    message: str = Field(description="Human-readable status message")
    vendor_count: int = Field(description="Number of vendors queued for extraction")


class SAPPullStatusResponse(BaseModel):
    """Response for SAP pull task status check."""

    task_id: str
    status: str
    progress: dict | None = None
    result: dict | None = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/{request_id}/sap-pull",
    response_model=SAPPullResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Trigger SAP data extraction",
    description=(
        "Triggers an asynchronous SAP data extraction for the given reconciliation "
        "request. Extracts vendor ledger entries from SAP and stores them in the "
        "database. Returns a task ID for progress tracking."
    ),
)
async def trigger_sap_pull(
    request_id: UUID,
    body: SAPPullRequest | None = None,
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db_session),
) -> SAPPullResponse:
    """
    POST /api/v1/vlr/requests/{id}/sap-pull

    Triggers SAP data extraction for the reconciliation request.
    The extraction runs asynchronously as a Celery task.
    """
    # Fetch the reconciliation request
    stmt = select(ReconciliationRequestModel).where(
        ReconciliationRequestModel.id == str(request_id)
    )
    result = await session.execute(stmt)
    request_model = result.scalar_one_or_none()

    if request_model is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Reconciliation request {request_id} not found.",
        )

    # Validate request status - must be in active or in_progress
    allowed_statuses = ("active", "in_progress", "draft")
    if request_model.status not in allowed_statuses:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Cannot trigger SAP pull for request in '{request_model.status}' status. "
                f"Request must be in one of: {', '.join(allowed_statuses)}."
            ),
        )

    # Determine vendor codes to extract
    if body and body.vendor_codes:
        vendor_codes = body.vendor_codes
    else:
        # Get all vendor codes from cases in this request
        cases_stmt = (
            select(VendorModel.vendor_code)
            .join(
                ReconciliationCaseModel,
                ReconciliationCaseModel.vendor_id == VendorModel.id,
            )
            .where(
                and_(
                    ReconciliationCaseModel.request_id == str(request_id),
                    ReconciliationCaseModel.is_deleted == False,  # noqa: E712
                )
            )
        )
        cases_result = await session.execute(cases_stmt)
        vendor_codes = [row[0] for row in cases_result.all()]

    if not vendor_codes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No vendors found for this request. Please add vendors first.",
        )

    # Dispatch Celery task
    task = sap_pull_task.delay(
        request_id=str(request_id),
        company_code=request_model.company_code,
        vendor_codes=vendor_codes,
        period_start=request_model.period_start.isoformat(),
        period_end=request_model.period_end.isoformat(),
        triggered_by=current_user.username,
    )

    return SAPPullResponse(
        task_id=task.id,
        request_id=str(request_id),
        status="accepted",
        message=f"SAP data extraction queued for {len(vendor_codes)} vendor(s).",
        vendor_count=len(vendor_codes),
    )


@router.get(
    "/{request_id}/sap-pull/{task_id}",
    response_model=SAPPullStatusResponse,
    summary="Check SAP pull task status",
    description="Check the progress and result of a SAP data extraction task.",
)
async def get_sap_pull_status(
    request_id: UUID,
    task_id: str,
    current_user: User = Depends(get_current_active_user),
) -> SAPPullStatusResponse:
    """
    GET /api/v1/vlr/requests/{id}/sap-pull/{task_id}

    Returns the current status and progress of a SAP pull task.
    """
    async_result = celery_app.AsyncResult(task_id)

    response = SAPPullStatusResponse(
        task_id=task_id,
        status=async_result.status,
    )

    if async_result.status == "PROGRESS":
        response.progress = async_result.info
    elif async_result.status == "SUCCESS":
        response.result = async_result.result
    elif async_result.status == "FAILURE":
        response.result = {"error": str(async_result.result)}

    return response
