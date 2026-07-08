"""
VLR Audit Trail API endpoints.
Thin controller — delegates audit trail operations to AuditTrailService.

Routes:
- GET   /api/v1/vlr/audit          — Search audit events with pagination
- GET   /api/v1/vlr/audit/export   — Export filtered results (Excel/CSV)

Requirements: 39.1, 39.2, 39.3
"""

from __future__ import annotations

import logging
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.v1.dependencies import get_current_active_user
from src.api.v1.schemas.vlr.audit_schemas import (
    AuditEventListResponse,
    AuditEventResponse,
)
from src.domain.entities.user import User
from src.domain.repositories.vlr.audit_trail_repository import AuditSearchFilters
from src.domain.repositories.vlr.vendor_repository import PaginationParams
from src.domain.services.vlr.audit_trail_service import (
    AuditTrailService,
    ExportFormat,
)
from src.infrastructure.database.repositories.vlr.audit_trail_repository_impl import (
    AuditTrailRepositoryImpl,
)
from src.infrastructure.database.session import get_db_session
from src.infrastructure.security.permission_manager import require_permission

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/vlr/audit", tags=["VLR - Audit Trail"])


# ──────────────────────────────────────────────────────────────────────
# Dependencies
# ──────────────────────────────────────────────────────────────────────


def _get_audit_service(
    session: AsyncSession = Depends(get_db_session),
) -> AuditTrailService:
    """FastAPI dependency — creates AuditTrailService with injected repository."""
    return AuditTrailService(
        audit_repository=AuditTrailRepositoryImpl(session),
    )


# ──────────────────────────────────────────────────────────────────────
# Endpoints
# ──────────────────────────────────────────────────────────────────────


@router.get(
    "",
    response_model=AuditEventListResponse,
    summary="Search audit events with pagination",
    dependencies=[Depends(require_permission("vlr.audit.read"))],
)
async def search_audit_events(
    actor_username: str | None = Query(None, description="Filter by actor username (partial match)"),
    event_type: str | None = Query(None, description="Filter by event type"),
    case_id: UUID | None = Query(None, description="Filter by case ID"),
    date_from: datetime | None = Query(None, description="Filter from date (inclusive)"),
    date_to: datetime | None = Query(None, description="Filter to date (inclusive)"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(50, ge=1, le=200, description="Items per page"),
    current_user: User = Depends(get_current_active_user),
    service: AuditTrailService = Depends(_get_audit_service),
) -> AuditEventListResponse:
    """
    GET /api/v1/vlr/audit

    Search audit events with optional filtering by user, date range,
    case_id, and event_type. Results are paginated and ordered by
    timestamp descending (most recent first).

    Requirements: 39.1, 39.3
    """
    filters = AuditSearchFilters(
        actor_username=actor_username,
        event_type=event_type,
        case_id=case_id,
        date_from=date_from,
        date_to=date_to,
    )
    pagination = PaginationParams(page=page, page_size=page_size)

    result = await service.search(filters=filters, pagination=pagination)

    return AuditEventListResponse(
        items=[
            AuditEventResponse.model_validate(event) for event in result.items
        ],
        total=result.total,
        page=result.page,
        page_size=result.page_size,
        total_pages=result.total_pages,
    )


@router.get(
    "/export",
    summary="Export filtered audit events (Excel/CSV)",
    dependencies=[Depends(require_permission("vlr.audit.read"))],
)
async def export_audit_events(
    actor_username: str | None = Query(None, description="Filter by actor username (partial match)"),
    event_type: str | None = Query(None, description="Filter by event type"),
    case_id: UUID | None = Query(None, description="Filter by case ID"),
    date_from: datetime | None = Query(None, description="Filter from date (inclusive)"),
    date_to: datetime | None = Query(None, description="Filter to date (inclusive)"),
    format: str = Query("csv", description="Export format: csv or excel"),
    current_user: User = Depends(get_current_active_user),
    service: AuditTrailService = Depends(_get_audit_service),
) -> Response:
    """
    GET /api/v1/vlr/audit/export

    Export filtered audit events as CSV or Excel file download.
    Supports the same filters as the search endpoint.

    Requirements: 39.2, 39.3
    """
    filters = AuditSearchFilters(
        actor_username=actor_username,
        event_type=event_type,
        case_id=case_id,
        date_from=date_from,
        date_to=date_to,
    )

    # Determine export format
    export_format = ExportFormat.EXCEL if format.lower() == "excel" else ExportFormat.CSV

    # Generate export
    content = await service.export(filters=filters, export_format=export_format)

    # Return as file download
    if export_format == ExportFormat.EXCEL:
        return Response(
            content=content,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": "attachment; filename=audit_events.xlsx",
            },
        )
    else:
        return Response(
            content=content,
            media_type="text/csv",
            headers={
                "Content-Disposition": "attachment; filename=audit_events.csv",
            },
        )
