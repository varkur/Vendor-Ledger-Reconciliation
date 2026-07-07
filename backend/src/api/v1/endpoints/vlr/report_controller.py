"""
VLR Report API endpoints with export capabilities.
Thin controller — delegates report generation to ReportService.

Routes:
- GET  /api/v1/vlr/reports/reconciliation-statement/{case_id}  — Get reconciliation statement
- GET  /api/v1/vlr/reports/exception-report/{case_id}          — Get exception report
- GET  /api/v1/vlr/reports/vendor-status/{request_id}          — Get vendor status report
- GET  /api/v1/vlr/reports/monthly-mis                         — Get monthly MIS report
- GET  /api/v1/vlr/reports/export/{report_type}/{resource_id}  — Export report to PDF/Excel

Requirements: 9.1-9.6, 9.8, 11.2
"""

from __future__ import annotations

import io
import json
import logging
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
    ExceptionReportResponse,
    MonthlyMISReportResponse,
    ReconciliationStatementResponse,
    VendorStatusReportResponse,
)
from src.domain.entities.user import User
from src.domain.services.vlr.report_service import ReportService
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
    # Convert Decimal/UUID/date/datetime to JSON-safe values
    return json.loads(json.dumps(raw, cls=_DecimalEncoder))


def _generate_excel_bytes(report_data: dict, sheet_name: str = "Report") -> bytes:
    """
    Generate an Excel file from report data.

    Uses CSV format as a fallback if openpyxl is not available.
    Requirement 9.5: Export to Excel format.
    """
    try:
        from openpyxl import Workbook

        wb = Workbook()
        ws = wb.active
        ws.title = sheet_name

        # Write summary fields as header rows
        row_num = 1
        for key, value in report_data.items():
            if isinstance(value, (list, dict)):
                continue
            ws.cell(row=row_num, column=1, value=str(key))
            ws.cell(row=row_num, column=2, value=str(value) if value is not None else "")
            row_num += 1

        # Write list data (entries) as table
        list_fields = {k: v for k, v in report_data.items() if isinstance(v, list) and v}
        for field_name, items in list_fields.items():
            row_num += 1
            ws.cell(row=row_num, column=1, value=f"--- {field_name} ---")
            row_num += 1

            if items and isinstance(items[0], dict):
                # Write headers
                headers = list(items[0].keys())
                for col_num, header in enumerate(headers, 1):
                    ws.cell(row=row_num, column=col_num, value=header)
                row_num += 1

                # Write data rows
                for item in items:
                    for col_num, header in enumerate(headers, 1):
                        val = item.get(header, "")
                        ws.cell(row=row_num, column=col_num, value=str(val) if val is not None else "")
                    row_num += 1

        buffer = io.BytesIO()
        wb.save(buffer)
        buffer.seek(0)
        return buffer.getvalue()

    except ImportError:
        # Fallback: generate CSV if openpyxl not available
        import csv

        buffer = io.StringIO()
        writer = csv.writer(buffer)

        for key, value in report_data.items():
            if isinstance(value, (list, dict)):
                continue
            writer.writerow([key, str(value) if value is not None else ""])

        list_fields = {k: v for k, v in report_data.items() if isinstance(v, list) and v}
        for field_name, items in list_fields.items():
            writer.writerow([])
            writer.writerow([f"--- {field_name} ---"])
            if items and isinstance(items[0], dict):
                headers = list(items[0].keys())
                writer.writerow(headers)
                for item in items:
                    writer.writerow([str(item.get(h, "")) for h in headers])

        return buffer.getvalue().encode("utf-8")


def _generate_pdf_bytes(report_data: dict, title: str = "VLR Report") -> bytes:
    """
    Generate a PDF file from report data.

    Uses a simple text-based PDF if reportlab is not available.
    Requirement 9.6: Export to PDF format.
    """
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
        from reportlab.lib import colors

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4)
        styles = getSampleStyleSheet()
        elements = []

        # Title
        elements.append(Paragraph(title, styles["Title"]))
        elements.append(Spacer(1, 12))

        # Summary fields
        for key, value in report_data.items():
            if isinstance(value, (list, dict)):
                continue
            elements.append(
                Paragraph(f"<b>{key}:</b> {value}", styles["Normal"])
            )

        elements.append(Spacer(1, 12))

        # Table data for lists
        list_fields = {k: v for k, v in report_data.items() if isinstance(v, list) and v}
        for field_name, items in list_fields.items():
            elements.append(Paragraph(f"<b>{field_name}</b>", styles["Heading2"]))
            elements.append(Spacer(1, 6))

            if items and isinstance(items[0], dict):
                headers = list(items[0].keys())
                table_data = [headers]
                for item in items[:100]:  # Limit rows for PDF
                    table_data.append(
                        [str(item.get(h, ""))[:50] for h in headers]
                    )

                table = Table(table_data)
                table.setStyle(TableStyle([
                    ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                    ("FONTSIZE", (0, 0), (-1, -1), 7),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
                ]))
                elements.append(table)
                elements.append(Spacer(1, 12))

        doc.build(elements)
        buffer.seek(0)
        return buffer.getvalue()

    except ImportError:
        # Fallback: generate a plain text representation as "PDF"
        lines = [f"=== {title} ===", ""]
        for key, value in report_data.items():
            if isinstance(value, (list, dict)):
                continue
            lines.append(f"{key}: {value}")

        lines.append("")
        list_fields = {k: v for k, v in report_data.items() if isinstance(v, list) and v}
        for field_name, items in list_fields.items():
            lines.append(f"--- {field_name} ---")
            if items and isinstance(items[0], dict):
                headers = list(items[0].keys())
                lines.append("\t".join(headers))
                for item in items:
                    lines.append("\t".join(str(item.get(h, "")) for h in headers))
            lines.append("")

        return "\n".join(lines).encode("utf-8")


# ──────────────────────────────────────────────────────────────────────
# Endpoints
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

    Requirement 9.1: Statement with entries, matches, exceptions, Row_10.
    Requirement 9.9: Include pass-level match statistics.
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
    summary="Generate exception report for a case",
    dependencies=[Depends(require_permission("vlr.reports.read"))],
)
async def get_exception_report(
    case_id: UUID,
    current_user: User = Depends(get_current_active_user),
    service: ReportService = Depends(_get_report_service),
) -> ExceptionReportResponse:
    """
    GET /api/v1/vlr/reports/exception-report/{case_id}

    Generates an exception report with ageing analysis, category breakdown,
    and resolution status.

    Requirement 9.2: Ageing analysis, category breakdown, resolution status.
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
    summary="Generate vendor status tracking report",
    dependencies=[Depends(require_permission("vlr.reports.read"))],
)
async def get_vendor_status_report(
    request_id: UUID,
    company_code: str = Query(..., min_length=1, description="Company code"),
    current_user: User = Depends(get_current_active_user),
    service: ReportService = Depends(_get_report_service),
) -> VendorStatusReportResponse:
    """
    GET /api/v1/vlr/reports/vendor-status/{request_id}

    Generates vendor status tracking report with response rates,
    upload status, and sign-off progress.

    Requirement 9.3: Response rates, upload status, sign-off tracking.
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
    summary="Generate monthly MIS report",
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

    Generates monthly MIS report with volumes, match rates,
    exception trends, and ageing analysis.

    Requirement 9.4: Monthly MIS with volumes, match rates,
                     exception trends, ageing analysis.
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


@router.get(
    "/export/reconciliation-statement/{case_id}",
    summary="Export reconciliation statement to PDF or Excel",
    dependencies=[Depends(require_permission("vlr.reports.read"))],
)
async def export_reconciliation_statement(
    case_id: UUID,
    format: ExportFormat = Query(ExportFormat.EXCEL, description="Export format: pdf or excel"),
    current_user: User = Depends(get_current_active_user),
    service: ReportService = Depends(_get_report_service),
) -> StreamingResponse:
    """
    GET /api/v1/vlr/reports/export/reconciliation-statement/{case_id}

    Exports reconciliation statement in the requested format.

    Requirement 9.5: Export to Excel.
    Requirement 9.6: Export to PDF.
    """
    report = await service.generate_reconciliation_statement(case_id)
    report_data = _dataclass_to_dict(report)

    return _build_export_response(
        report_data=report_data,
        format=format,
        filename_base=f"reconciliation_statement_{case_id}",
        title="Reconciliation Statement",
    )


@router.get(
    "/export/exception-report/{case_id}",
    summary="Export exception report to PDF or Excel",
    dependencies=[Depends(require_permission("vlr.reports.read"))],
)
async def export_exception_report(
    case_id: UUID,
    format: ExportFormat = Query(ExportFormat.EXCEL, description="Export format: pdf or excel"),
    current_user: User = Depends(get_current_active_user),
    service: ReportService = Depends(_get_report_service),
) -> StreamingResponse:
    """
    GET /api/v1/vlr/reports/export/exception-report/{case_id}

    Exports exception report in the requested format.

    Requirement 9.5: Export to Excel.
    Requirement 9.6: Export to PDF.
    """
    report = await service.generate_exception_report(case_id)
    report_data = _dataclass_to_dict(report)

    return _build_export_response(
        report_data=report_data,
        format=format,
        filename_base=f"exception_report_{case_id}",
        title="Exception Report",
    )


@router.get(
    "/export/vendor-status/{request_id}",
    summary="Export vendor status report to PDF or Excel",
    dependencies=[Depends(require_permission("vlr.reports.read"))],
)
async def export_vendor_status_report(
    request_id: UUID,
    company_code: str = Query(..., min_length=1, description="Company code"),
    format: ExportFormat = Query(ExportFormat.EXCEL, description="Export format: pdf or excel"),
    current_user: User = Depends(get_current_active_user),
    service: ReportService = Depends(_get_report_service),
) -> StreamingResponse:
    """
    GET /api/v1/vlr/reports/export/vendor-status/{request_id}

    Exports vendor status report in the requested format.

    Requirement 9.5: Export to Excel.
    Requirement 9.6: Export to PDF.
    """
    report = await service.generate_vendor_status_report(
        request_id=request_id,
        company_code=company_code,
    )
    report_data = _dataclass_to_dict(report)

    return _build_export_response(
        report_data=report_data,
        format=format,
        filename_base=f"vendor_status_{request_id}",
        title="Vendor Status Report",
    )


@router.get(
    "/export/monthly-mis",
    summary="Export monthly MIS report to PDF or Excel",
    dependencies=[Depends(require_permission("vlr.reports.read"))],
)
async def export_monthly_mis_report(
    company_code: str = Query(..., min_length=1, description="Company code"),
    period_start: date = Query(..., description="Period start date (YYYY-MM-DD)"),
    period_end: date = Query(..., description="Period end date (YYYY-MM-DD)"),
    format: ExportFormat = Query(ExportFormat.EXCEL, description="Export format: pdf or excel"),
    current_user: User = Depends(get_current_active_user),
    service: ReportService = Depends(_get_report_service),
) -> StreamingResponse:
    """
    GET /api/v1/vlr/reports/export/monthly-mis

    Exports monthly MIS report in the requested format.

    Requirement 9.5: Export to Excel.
    Requirement 9.6: Export to PDF.
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
    report_data = _dataclass_to_dict(report)

    return _build_export_response(
        report_data=report_data,
        format=format,
        filename_base=f"monthly_mis_{company_code}_{period_start}_{period_end}",
        title="Monthly MIS Report",
    )


# ──────────────────────────────────────────────────────────────────────
# Export Helper
# ──────────────────────────────────────────────────────────────────────


def _build_export_response(
    report_data: dict,
    format: ExportFormat,
    filename_base: str,
    title: str,
) -> StreamingResponse:
    """Build a StreamingResponse with the exported file."""
    if format == ExportFormat.EXCEL:
        content = _generate_excel_bytes(report_data, sheet_name=title)
        media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        extension = "xlsx"
    else:
        content = _generate_pdf_bytes(report_data, title=title)
        media_type = "application/pdf"
        extension = "pdf"

    filename = f"{filename_base}.{extension}"

    return StreamingResponse(
        io.BytesIO(content),
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Length": str(len(content)),
        },
    )
