"""
VLR Report API endpoints with export capabilities.
Thin controller — delegates report generation to ReportService.

Routes:
- GET  /api/v1/vlr/reports/reconciliation-summary             — Aggregate reconciliation summary (paginated)
- GET  /api/v1/vlr/reports/reconciliation-summary/{case_id}  — Reconciliation summary (10-row)
- GET  /api/v1/vlr/reports/reconciliation-statement/{case_id} — Full reconciliation statement
- GET  /api/v1/vlr/reports/aging-analysis                    — Aging analysis report
- GET  /api/v1/vlr/reports/exceptions                        — Exception report with history
- GET  /api/v1/vlr/reports/vendor-status                     — Vendor status tracking
- GET  /api/v1/vlr/reports/mis                               — Monthly MIS report
- POST /api/v1/vlr/reports/generate                          — Generate exportable report
- GET  /api/v1/vlr/reports/export/{report_id}                — Download generated report

Requirements: 16, 27.1, 27.2, 27.3, 28.1, 28.2, 28.3, 29.1, 29.2, 29.3, 29.4
"""

from __future__ import annotations

import io
import json
import logging
import uuid as uuid_module
from dataclasses import asdict
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.v1.dependencies import get_current_active_user
from src.api.v1.schemas.vlr.report_schemas import (
    AgingAnalysisResponse,
    AggregateReconciliationSummaryResponse,
    AggregateRecoSummaryRow,
    EnhancedExceptionReportResponse,
    ExceptionReportResponse,
    GenerateReportRequest,
    GenerateReportResponse,
    MonthlyMISReportResponse,
    ReconciliationStatementResponse,
    ReconciliationSummaryResponse,
    VendorStatusReportResponse,
)
from src.domain.entities.user import User
from src.domain.services.vlr.report_service import (
    AgingFilters,
    ReportService,
)
from src.infrastructure.database.repositories.vlr.case_repository_impl import (
    CaseRepositoryImpl,
)
from src.infrastructure.database.repositories.vlr.exception_repository_impl import (
    ExceptionRepositoryImpl,
)
from src.infrastructure.database.repositories.vlr.ledger_entry_repository_impl import (
    LedgerEntryRepositoryImpl,
)
from src.infrastructure.database.repositories.vlr.match_result_repository_impl import (
    MatchResultRepositoryImpl,
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

router = APIRouter(prefix="/vlr/reports", tags=["VLR - Reports"])


# ──────────────────────────────────────────────────────────────────────
# Export Format Enum
# ──────────────────────────────────────────────────────────────────────


class ExportFormat(str, Enum):
    """Supported export formats."""

    PDF = "pdf"
    EXCEL = "excel"


# ──────────────────────────────────────────────────────────────────────
# In-Memory Report Store (for generate/download pattern)
# ──────────────────────────────────────────────────────────────────────

# Simple in-memory store for generated reports. In production, this would
# use a persistent store (S3, database blob, etc.)
_generated_reports: dict[str, dict] = {}


# ──────────────────────────────────────────────────────────────────────
# Dependencies
# ──────────────────────────────────────────────────────────────────────


def _get_report_service(
    session: AsyncSession = Depends(get_db_session),
) -> ReportService:
    """FastAPI dependency — creates ReportService with injected repositories."""
    return ReportService(
        case_repository=CaseRepositoryImpl(session),
        exception_repository=ExceptionRepositoryImpl(session),
        ledger_entry_repository=LedgerEntryRepositoryImpl(session),
        match_result_repository=MatchResultRepositoryImpl(session),
        request_repository=RequestRepositoryImpl(session),
        vendor_repository=VendorRepositoryImpl(session),
    )


# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────


class _DecimalEncoder(json.JSONEncoder):
    """JSON encoder that handles Decimal and datetime types."""

    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        if isinstance(obj, UUID):
            return str(obj)
        return super().default(obj)


def _dataclass_to_dict(obj) -> dict:
    """Convert a dataclass to a serializable dictionary."""
    raw = asdict(obj)
    return json.loads(json.dumps(raw, cls=_DecimalEncoder))


# ──────────────────────────────────────────────────────────────────────
# Endpoints: Reconciliation Summary (Requirement 27.1)
# ──────────────────────────────────────────────────────────────────────


@router.get(
    "/reconciliation-summary",
    response_model=AggregateReconciliationSummaryResponse,
    summary="Get aggregate reconciliation summary across all cases",
    dependencies=[Depends(require_permission("vlr.reports.read"))],
)
async def get_aggregate_reconciliation_summary(
    company_code: str = Query(..., min_length=1, description="Company code"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Page size"),
    date_from: date | None = Query(None, description="Filter: start date (created_date >=)"),
    date_to: date | None = Query(None, description="Filter: end date (created_date <=)"),
    current_user: User = Depends(get_current_active_user),
    service: ReportService = Depends(_get_report_service),
) -> AggregateReconciliationSummaryResponse:
    """
    GET /api/v1/vlr/reports/reconciliation-summary

    Returns a paginated aggregate reconciliation summary across all cases
    for the given company_code, optionally filtered by date range.

    Requirement 16: Reports Page — Reconciliation Summary.
    """
    result = await service.generate_aggregate_reconciliation_summary(
        company_code=company_code,
        page=page,
        page_size=page_size,
        date_from=date_from,
        date_to=date_to,
    )

    items = [
        AggregateRecoSummaryRow(
            id=row.id,
            vendor_name=row.vendor_name,
            opening_balance=row.opening_balance,
            invoices=row.invoices,
            payments=row.payments,
            adjustments=row.adjustments,
            closing_balance=row.closing_balance,
            difference=row.difference,
            status=row.status,
        )
        for row in result.items
    ]

    total_pages = (result.total + page_size - 1) // page_size if result.total > 0 else 0

    return AggregateReconciliationSummaryResponse(
        items=items,
        total=result.total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.get(
    "/reconciliation-summary/{case_id}",
    response_model=ReconciliationSummaryResponse,
    summary="Generate reconciliation summary (10-row format) for a case",
    dependencies=[Depends(require_permission("vlr.reports.read"))],
)
async def get_reconciliation_summary(
    case_id: UUID,
    current_user: User = Depends(get_current_active_user),
    service: ReportService = Depends(_get_report_service),
) -> ReconciliationSummaryResponse:
    """
    GET /api/v1/vlr/reports/reconciliation-summary/{case_id}

    Generates the 10-row reconciliation summary report.
    Requirements: 27.1, 27.2
    """
    report = await service.generate_reconciliation_summary(case_id)

    return ReconciliationSummaryResponse(
        case_id=report.case_id,
        generated_at=report.generated_at,
        rows=[
            {"row_number": r.row_number, "description": r.description, "amount": r.amount}
            for r in report.rows
        ],
        company_closing_balance=report.company_closing_balance,
        vendor_closing_balance=report.vendor_closing_balance,
        net_difference=report.net_difference,
    )


# ──────────────────────────────────────────────────────────────────────
# Endpoints: Aging Analysis (Requirements 28.1, 28.2)
# ──────────────────────────────────────────────────────────────────────


@router.get(
    "/aging-analysis",
    response_model=AgingAnalysisResponse,
    summary="Generate aging analysis report",
    dependencies=[Depends(require_permission("vlr.reports.read"))],
)
async def get_aging_analysis(
    company_code: str = Query(..., min_length=1, description="Company code"),
    vendor_id: UUID | None = Query(None, description="Filter by vendor ID"),
    report_status: str | None = Query(None, alias="status", description="Filter by case status"),
    as_of_date: date | None = Query(None, description="Reference date (defaults to today)"),
    current_user: User = Depends(get_current_active_user),
    service: ReportService = Depends(_get_report_service),
) -> AgingAnalysisResponse:
    """
    GET /api/v1/vlr/reports/aging-analysis

    Generates aging analysis report with grouping by vendor, bucket, status.
    Buckets: 0-30 days, 31-60 days, 61-90 days, 91-180 days, 180+ days.

    Requirements: 28.1, 28.2
    """
    filters = AgingFilters(
        vendor_id=vendor_id,
        company_code=company_code,
        status=report_status,
        as_of_date=as_of_date,
    )
    report = await service.generate_aging_analysis(
        company_code=company_code, filters=filters
    )

    return AgingAnalysisResponse(
        generated_at=report.generated_at,
        as_of_date=report.as_of_date,
        total_items=report.total_items,
        total_amount=report.total_amount,
        bucket_summaries=[
            {"bucket": s.bucket, "count": s.count, "total_amount": s.total_amount}
            for s in report.bucket_summaries
        ],
        by_vendor={
            k: [{"bucket": s.bucket, "count": s.count, "total_amount": s.total_amount} for s in v]
            for k, v in report.by_vendor.items()
        },
        by_status={
            k: [{"bucket": s.bucket, "count": s.count, "total_amount": s.total_amount} for s in v]
            for k, v in report.by_status.items()
        },
        items=[
            {
                "entry_id": i.entry_id,
                "case_id": i.case_id,
                "vendor_id": i.vendor_id,
                "vendor_name": i.vendor_name,
                "amount": i.amount,
                "posting_date": i.posting_date,
                "reference_number": i.reference_number,
                "status": i.status,
                "age_days": i.age_days,
                "aging_bucket": i.aging_bucket,
            }
            for i in report.items
        ],
    )


# ──────────────────────────────────────────────────────────────────────
# Endpoints: Exception Report with History (Requirement 29.1)
# ──────────────────────────────────────────────────────────────────────


@router.get(
    "/exceptions",
    response_model=EnhancedExceptionReportResponse,
    summary="Generate exception report with resolution history",
    dependencies=[Depends(require_permission("vlr.reports.read"))],
)
async def get_exception_report(
    company_code: str = Query(..., min_length=1, description="Company code"),
    case_id: UUID | None = Query(None, description="Filter by case ID"),
    current_user: User = Depends(get_current_active_user),
    service: ReportService = Depends(_get_report_service),
) -> EnhancedExceptionReportResponse:
    """
    GET /api/v1/vlr/reports/exceptions

    Generates exception report listing all unmatched and disputed items
    with their resolution history.

    Requirement 29.1
    """
    report = await service.generate_enhanced_exception_report(
        company_code=company_code,
        case_id=case_id,
    )

    return EnhancedExceptionReportResponse(
        generated_at=report.generated_at,
        total_exceptions=report.total_exceptions,
        exceptions_by_status=report.exceptions_by_status,
        exceptions_by_category=report.exceptions_by_category,
        items=[
            {
                "exception_id": i.exception_id,
                "case_id": i.case_id,
                "amount": i.amount,
                "severity": i.severity,
                "category": i.category,
                "status": i.status,
                "first_flagged_date": i.first_flagged_date,
                "resolution_history": [
                    {
                        "action": h.action,
                        "action_by": h.action_by,
                        "action_date": h.action_date,
                        "notes": h.notes,
                    }
                    for h in i.resolution_history
                ],
            }
            for i in report.items
        ],
        total_amount=report.total_amount,
    )


# ──────────────────────────────────────────────────────────────────────
# Endpoints: Vendor Status (Requirement 29.2)
# ──────────────────────────────────────────────────────────────────────


@router.get(
    "/vendor-status",
    response_model=VendorStatusReportResponse,
    summary="Generate vendor status tracking report",
    dependencies=[Depends(require_permission("vlr.reports.read"))],
)
async def get_vendor_status(
    company_code: str = Query(..., min_length=1, description="Company code"),
    current_user: User = Depends(get_current_active_user),
    service: ReportService = Depends(_get_report_service),
) -> VendorStatusReportResponse:
    """
    GET /api/v1/vlr/reports/vendor-status

    Generates vendor status tracking report showing each vendor's
    reconciliation progress.

    Requirement 29.2
    """
    report = await service.generate_vendor_status_tracking(
        company_code=company_code,
    )

    return VendorStatusReportResponse(
        request_id=report.request_id,
        generated_at=report.generated_at,
        total_vendors=report.total_vendors,
        responded_count=report.responded_count,
        response_rate=report.response_rate,
        uploaded_count=report.uploaded_count,
        upload_rate=report.upload_rate,
        signed_off_count=report.signed_off_count,
        sign_off_rate=report.sign_off_rate,
        vendor_entries=[
            {
                "vendor_id": e.vendor_id,
                "vendor_name": e.vendor_name,
                "case_id": e.case_id,
                "case_status": e.case_status,
                "upload_count": e.upload_count,
                "has_responded": e.has_responded,
                "sign_off_status": e.sign_off_status,
                "last_activity_date": e.last_activity_date,
            }
            for e in report.vendor_entries
        ],
    )


# ──────────────────────────────────────────────────────────────────────
# Endpoints: Monthly MIS (Requirement 29.3)
# ──────────────────────────────────────────────────────────────────────


@router.get(
    "/mis",
    response_model=MonthlyMISReportResponse,
    summary="Generate monthly MIS report",
    dependencies=[Depends(require_permission("vlr.reports.read"))],
)
async def get_mis_report(
    company_code: str = Query(..., min_length=1, description="Company code"),
    period_start: date | None = Query(None, description="Period start (defaults to 1st of current month)"),
    period_end: date | None = Query(None, description="Period end (defaults to today)"),
    current_user: User = Depends(get_current_active_user),
    service: ReportService = Depends(_get_report_service),
) -> MonthlyMISReportResponse:
    """
    GET /api/v1/vlr/reports/mis

    Generates monthly MIS report summarizing reconciliation activity.

    Requirement 29.3
    """
    if period_start and period_end and period_start > period_end:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="period_start must be before or equal to period_end",
        )

    report = await service.generate_mis_report(
        company_code=company_code,
        period_start=period_start,
        period_end=period_end,
    )

    return MonthlyMISReportResponse(
        company_code=report.company_code,
        period_start=report.period_start,
        period_end=report.period_end,
        generated_at=report.generated_at,
        total_requests=report.total_requests,
        total_cases=report.total_cases,
        total_entries_processed=report.total_entries_processed,
        total_matched=report.total_matched,
        total_unmatched=report.total_unmatched,
        overall_match_rate=report.overall_match_rate,
        match_rate_by_pass=report.match_rate_by_pass,
        total_exceptions=report.total_exceptions,
        exceptions_resolved=report.exceptions_resolved,
        exceptions_open=report.exceptions_open,
        resolution_rate=report.resolution_rate,
        exception_trends=report.exception_trends,
        ageing_analysis=report.ageing_analysis,
        ageing_amounts=report.ageing_amounts,
        average_resolution_days=report.average_resolution_days,
        cases_by_status=report.cases_by_status,
    )


# ──────────────────────────────────────────────────────────────────────
# Endpoints: Report Generation & Export (Requirements 27.3, 28.3, 29.4)
# ──────────────────────────────────────────────────────────────────────


@router.post(
    "/generate",
    response_model=GenerateReportResponse,
    summary="Trigger report generation for export",
    dependencies=[Depends(require_permission("vlr.reports.read"))],
)
async def generate_report(
    request: GenerateReportRequest,
    current_user: User = Depends(get_current_active_user),
    service: ReportService = Depends(_get_report_service),
) -> GenerateReportResponse:
    """
    POST /api/v1/vlr/reports/generate

    Triggers generation of an exportable report. Returns a report_id
    that can be used to download the generated file.

    Requirements: 27.3, 28.3, 29.4
    """
    report_id = str(uuid_module.uuid4())
    export_format = request.format or "excel"
    company_code = request.company_code or "default"

    # Generate the appropriate report
    report_obj: object
    title: str

    if request.report_type == "reconciliation_summary":
        if not request.case_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="case_id is required for reconciliation_summary report",
            )
        report_obj = await service.generate_reconciliation_summary(request.case_id)
        title = "Reconciliation Summary"

    elif request.report_type == "aging_analysis":
        filters = AgingFilters(company_code=company_code)
        report_obj = await service.generate_aging_analysis(
            company_code=company_code, filters=filters
        )
        title = "Aging Analysis"

    elif request.report_type == "exception_report":
        report_obj = await service.generate_enhanced_exception_report(
            company_code=company_code, case_id=request.case_id
        )
        title = "Exception Report"

    elif request.report_type == "vendor_status":
        report_obj = await service.generate_vendor_status_tracking(
            company_code=company_code
        )
        title = "Vendor Status"

    elif request.report_type == "monthly_mis":
        report_obj = await service.generate_mis_report(
            company_code=company_code,
            period_start=request.period_start,
            period_end=request.period_end,
        )
        title = "Monthly MIS Report"

    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown report_type: {request.report_type}. "
                   f"Valid types: reconciliation_summary, aging_analysis, "
                   f"exception_report, vendor_status, monthly_mis",
        )

    # Export to the requested format
    if export_format == "pdf":
        content = service.export_to_pdf(report_obj, title=title)
        extension = "pdf"
        media_type = "application/pdf"
    else:
        content = service.export_to_excel(report_obj, sheet_name=title)
        extension = "xlsx"
        media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

    filename = f"{request.report_type}_{report_id}.{extension}"

    # Store generated report for download
    _generated_reports[report_id] = {
        "content": content,
        "filename": filename,
        "media_type": media_type,
        "report_type": request.report_type,
        "format": export_format,
    }

    return GenerateReportResponse(
        report_id=report_id,
        report_type=request.report_type,
        format=export_format,
        status="generated",
        download_url=f"/api/v1/vlr/reports/export/{report_id}",
    )


@router.get(
    "/export/{report_id}",
    summary="Download a previously generated report",
    dependencies=[Depends(require_permission("vlr.reports.read"))],
)
async def download_report(
    report_id: str,
    current_user: User = Depends(get_current_active_user),
) -> StreamingResponse:
    """
    GET /api/v1/vlr/reports/export/{report_id}

    Downloads a previously generated report (PDF or Excel).

    Requirements: 27.3, 28.3, 29.4
    """
    stored = _generated_reports.get(report_id)
    if not stored:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Report {report_id} not found. It may have expired or not been generated.",
        )

    content = stored["content"]
    filename = stored["filename"]
    media_type = stored["media_type"]

    return StreamingResponse(
        io.BytesIO(content),
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Length": str(len(content)),
        },
    )


# ──────────────────────────────────────────────────────────────────────
# Legacy Endpoints (kept for backward compatibility)
# ──────────────────────────────────────────────────────────────────────


@router.get(
    "/reconciliation-statement/{case_id}",
    response_model=ReconciliationStatementResponse,
    summary="Generate reconciliation statement for a case",
    dependencies=[Depends(require_permission("vlr.reports.read"))],
)
async def get_reconciliation_statement(
    case_id: UUID,
    current_user: User = Depends(get_current_active_user),
    service: ReportService = Depends(_get_report_service),
) -> ReconciliationStatementResponse:
    """
    GET /api/v1/vlr/reports/reconciliation-statement/{case_id}

    Generates a complete reconciliation statement including entries,
    matches, exceptions summary, and Row_10 balance.

    Requirement 9.1
    """
    report = await service.generate_reconciliation_statement(case_id)

    return ReconciliationStatementResponse(
        case_id=report.case_id,
        generated_at=report.generated_at,
        company_entries=[
            {
                "entry_id": e.entry_id,
                "side": e.side,
                "amount": e.amount,
                "reference_number": e.reference_number,
                "posting_date": e.posting_date,
                "match_status": e.match_status,
                "match_id": e.match_id,
                "pass_number": e.pass_number,
                "confidence_score": e.confidence_score,
            }
            for e in report.company_entries
        ],
        vendor_entries=[
            {
                "entry_id": e.entry_id,
                "side": e.side,
                "amount": e.amount,
                "reference_number": e.reference_number,
                "posting_date": e.posting_date,
                "match_status": e.match_status,
                "match_id": e.match_id,
                "pass_number": e.pass_number,
                "confidence_score": e.confidence_score,
            }
            for e in report.vendor_entries
        ],
        matched_pairs_count=report.matched_pairs_count,
        matched_groups_count=report.matched_groups_count,
        unmatched_company_count=report.unmatched_company_count,
        unmatched_vendor_count=report.unmatched_vendor_count,
        company_total=report.company_total,
        vendor_total=report.vendor_total,
        resolved_adjustments=report.resolved_adjustments,
        row_10_balance=report.row_10_balance,
        exceptions_summary=report.exceptions_summary,
        match_statistics=report.match_statistics,
    )


@router.get(
    "/exception-report/{case_id}",
    response_model=ExceptionReportResponse,
    summary="Generate exception report for a case (legacy)",
    dependencies=[Depends(require_permission("vlr.reports.read"))],
)
async def get_legacy_exception_report(
    case_id: UUID,
    current_user: User = Depends(get_current_active_user),
    service: ReportService = Depends(_get_report_service),
) -> ExceptionReportResponse:
    """
    GET /api/v1/vlr/reports/exception-report/{case_id}

    Legacy endpoint - generates exception report with ageing.
    Requirement 9.2
    """
    report = await service.generate_exception_report(case_id)

    return ExceptionReportResponse(
        case_id=report.case_id,
        request_id=report.request_id,
        generated_at=report.generated_at,
        total_exceptions=report.total_exceptions,
        exceptions_by_severity=report.exceptions_by_severity,
        exceptions_by_category=report.exceptions_by_category,
        exceptions_by_status=report.exceptions_by_status,
        ageing_buckets=report.ageing_buckets,
        ageing_amounts=report.ageing_amounts,
        entries=[
            {
                "exception_id": e.exception_id,
                "case_id": e.case_id,
                "amount": e.amount,
                "severity": e.severity,
                "category": e.category,
                "status": e.status,
                "first_flagged_date": e.first_flagged_date,
                "age_days": e.age_days,
                "ageing_bucket": e.ageing_bucket,
            }
            for e in report.entries
        ],
        total_exception_amount=report.total_exception_amount,
    )


@router.get(
    "/vendor-status/{request_id}",
    response_model=VendorStatusReportResponse,
    summary="Generate vendor status report by request (legacy)",
    dependencies=[Depends(require_permission("vlr.reports.read"))],
)
async def get_vendor_status_by_request(
    request_id: UUID,
    company_code: str = Query(..., min_length=1, description="Company code"),
    current_user: User = Depends(get_current_active_user),
    service: ReportService = Depends(_get_report_service),
) -> VendorStatusReportResponse:
    """
    GET /api/v1/vlr/reports/vendor-status/{request_id}

    Legacy endpoint - vendor status by request.
    Requirement 9.3
    """
    report = await service.generate_vendor_status_report(
        request_id=request_id,
        company_code=company_code,
    )

    return VendorStatusReportResponse(
        request_id=report.request_id,
        generated_at=report.generated_at,
        total_vendors=report.total_vendors,
        responded_count=report.responded_count,
        response_rate=report.response_rate,
        uploaded_count=report.uploaded_count,
        upload_rate=report.upload_rate,
        signed_off_count=report.signed_off_count,
        sign_off_rate=report.sign_off_rate,
        vendor_entries=[
            {
                "vendor_id": e.vendor_id,
                "vendor_name": e.vendor_name,
                "case_id": e.case_id,
                "case_status": e.case_status,
                "upload_count": e.upload_count,
                "has_responded": e.has_responded,
                "sign_off_status": e.sign_off_status,
                "last_activity_date": e.last_activity_date,
            }
            for e in report.vendor_entries
        ],
    )


@router.get(
    "/monthly-mis",
    response_model=MonthlyMISReportResponse,
    summary="Generate monthly MIS report (legacy)",
    dependencies=[Depends(require_permission("vlr.reports.read"))],
)
async def get_monthly_mis_report(
    company_code: str = Query(..., min_length=1, description="Company code"),
    period_start: date = Query(..., description="Period start date (YYYY-MM-DD)"),
    period_end: date = Query(..., description="Period end date (YYYY-MM-DD)"),
    current_user: User = Depends(get_current_active_user),
    service: ReportService = Depends(_get_report_service),
) -> MonthlyMISReportResponse:
    """
    GET /api/v1/vlr/reports/monthly-mis

    Legacy endpoint - monthly MIS report with required date parameters.
    Requirement 9.4
    """
    if period_start > period_end:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="period_start must be before or equal to period_end",
        )

    report = await service.generate_monthly_mis_report(
        company_code=company_code,
        period_start=period_start,
        period_end=period_end,
    )

    return MonthlyMISReportResponse(
        company_code=report.company_code,
        period_start=report.period_start,
        period_end=report.period_end,
        generated_at=report.generated_at,
        total_requests=report.total_requests,
        total_cases=report.total_cases,
        total_entries_processed=report.total_entries_processed,
        total_matched=report.total_matched,
        total_unmatched=report.total_unmatched,
        overall_match_rate=report.overall_match_rate,
        match_rate_by_pass=report.match_rate_by_pass,
        total_exceptions=report.total_exceptions,
        exceptions_resolved=report.exceptions_resolved,
        exceptions_open=report.exceptions_open,
        resolution_rate=report.resolution_rate,
        exception_trends=report.exception_trends,
        ageing_analysis=report.ageing_analysis,
        ageing_amounts=report.ageing_amounts,
        average_resolution_days=report.average_resolution_days,
        cases_by_status=report.cases_by_status,
    )
