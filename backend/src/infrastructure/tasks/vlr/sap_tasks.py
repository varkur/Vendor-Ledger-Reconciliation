"""
SAP data extraction Celery tasks.

Provides async task execution for SAP data pulls, preventing API request
blocking for large extractions (up to 10,000 entries within 60 seconds).

On completion, records extraction timestamp, row count, and status
in the audit log.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import date, datetime, timezone
from uuid import UUID, uuid4

from celery import Task

from src.infrastructure.background.celery_app import celery_app

logger = logging.getLogger(__name__)


class SAPPullTask(Task):
    """Custom base task class with error handling for SAP pulls."""

    name = "vlr.sap_pull"
    max_retries = 3
    default_retry_delay = 30  # seconds

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """Log task failure."""
        logger.error(
            "SAP pull task failed: task_id=%s, request_id=%s, error=%s",
            task_id,
            kwargs.get("request_id") or (args[0] if args else "unknown"),
            str(exc),
        )

    def on_success(self, retval, task_id, args, kwargs):
        """Log task success."""
        logger.info(
            "SAP pull task completed: task_id=%s, request_id=%s",
            task_id,
            kwargs.get("request_id") or (args[0] if args else "unknown"),
        )


@celery_app.task(
    base=SAPPullTask,
    bind=True,
    name="vlr.sap_pull",
    acks_late=True,
    time_limit=120,  # Hard limit: 2 minutes
    soft_time_limit=90,  # Soft limit: 1.5 minutes (allows cleanup)
)
def sap_pull_task(
    self: SAPPullTask,
    request_id: str,
    company_code: str,
    vendor_codes: list[str],
    period_start: str,
    period_end: str,
    triggered_by: str,
) -> dict:
    """
    Async Celery task for SAP data extraction.

    Extracts ledger entries from SAP for each vendor in the request,
    stores them in the database, and records the result in the audit log.

    Args:
        request_id: UUID of the reconciliation request.
        company_code: Company code for SAP extraction.
        vendor_codes: List of vendor codes to extract data for.
        period_start: Start date (ISO format YYYY-MM-DD).
        period_end: End date (ISO format YYYY-MM-DD).
        triggered_by: Username of the user who triggered the pull.

    Returns:
        Dict with extraction results including row counts and status.
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        result = loop.run_until_complete(
            _execute_sap_pull(
                task=self,
                request_id=request_id,
                company_code=company_code,
                vendor_codes=vendor_codes,
                period_start=period_start,
                period_end=period_end,
                triggered_by=triggered_by,
            )
        )
        return result
    finally:
        loop.close()


async def _execute_sap_pull(
    task: SAPPullTask,
    request_id: str,
    company_code: str,
    vendor_codes: list[str],
    period_start: str,
    period_end: str,
    triggered_by: str,
) -> dict:
    """
    Execute SAP pull for all vendors in the request.

    Connects to the database, pulls data from SAP, stores ledger entries,
    updates request/case status, and records audit log entries.
    """
    from src.infrastructure.database.session import async_session_factory
    from src.infrastructure.external.sap_connector import (
        DateRange,
        SAPConfig,
        SAPConnectorService,
    )
    from src.infrastructure.database.models.vlr.ledger_entry_model import LedgerEntryModel
    from src.infrastructure.database.models.vlr.reconciliation_request_model import (
        ReconciliationRequestModel,
    )
    from src.infrastructure.database.models.vlr.reconciliation_case_model import (
        ReconciliationCaseModel,
    )
    from src.infrastructure.database.models.vlr.vendor_model import VendorModel
    from src.infrastructure.database.models.audit_log_model import AuditLogModel

    from sqlalchemy import select, and_

    period = DateRange(
        start=date.fromisoformat(period_start),
        end=date.fromisoformat(period_end),
    )

    extraction_start = datetime.now(timezone.utc)
    total_rows = 0
    vendor_results: list[dict] = []
    overall_status = "completed"
    error_message: str | None = None

    # Load SAP configuration from settings/environment
    from src.config.settings import settings

    sap_config = SAPConfig(
        host=getattr(settings, "SAP_HOST", ""),
        system_number=getattr(settings, "SAP_SYSTEM_NUMBER", "00"),
        client=getattr(settings, "SAP_CLIENT", "100"),
        username=getattr(settings, "SAP_USERNAME", ""),
        password=getattr(settings, "SAP_PASSWORD", ""),
        base_url=getattr(settings, "SAP_BASE_URL", ""),
    )

    sap_connector = SAPConnectorService(config=sap_config)

    async with async_session_factory() as session:
        try:
            # Update request status to in_progress if currently active
            request_stmt = select(ReconciliationRequestModel).where(
                and_(
                    ReconciliationRequestModel.id == request_id,
                    ReconciliationRequestModel.company_code == company_code,
                )
            )
            result = await session.execute(request_stmt)
            request_model = result.scalar_one_or_none()

            if request_model is None:
                raise ValueError(f"Reconciliation request {request_id} not found.")

            if request_model.status == "active":
                request_model.status = "in_progress"
                request_model.modified_by = triggered_by
                request_model.modified_date = datetime.now(timezone.utc)

            # Update task state for progress tracking
            task.update_state(
                state="PROGRESS",
                meta={
                    "current": 0,
                    "total": len(vendor_codes),
                    "status": "Starting SAP extraction...",
                },
            )

            # Process each vendor
            for idx, vendor_code in enumerate(vendor_codes):
                vendor_result = {
                    "vendor_code": vendor_code,
                    "status": "completed",
                    "row_count": 0,
                    "duplicates_skipped": 0,
                    "error": None,
                }

                try:
                    # Pull ledger entries from SAP
                    extraction_result = await sap_connector.pull_ledger_entries(
                        vendor_code=vendor_code,
                        company_code=company_code,
                        period=period,
                    )

                    # Find the case for this vendor within the request
                    vendor_id_subq = (
                        select(VendorModel.id)
                        .where(
                            and_(
                                VendorModel.vendor_code == vendor_code,
                                VendorModel.company_code == company_code,
                            )
                        )
                        .scalar_subquery()
                    )
                    case_stmt = select(ReconciliationCaseModel).where(
                        and_(
                            ReconciliationCaseModel.request_id == request_id,
                            ReconciliationCaseModel.vendor_id == vendor_id_subq,
                            ReconciliationCaseModel.is_deleted == False,  # noqa: E712
                        )
                    )
                    case_result = await session.execute(case_stmt)
                    case_model = case_result.scalar_one_or_none()

                    if case_model is None:
                        vendor_result["status"] = "skipped"
                        vendor_result["error"] = f"No case found for vendor {vendor_code}"
                        vendor_results.append(vendor_result)
                        continue

                    # Store ledger entries in the database
                    for entry in extraction_result.entries:
                        ledger_entry = LedgerEntryModel(
                            id=uuid4(),
                            case_id=case_model.id,
                            side="company",
                            document_number=entry.document_number,
                            document_type=entry.document_type,
                            reference_number=entry.assignment_number,
                            posting_date=entry.posting_date or period.start,
                            clearing_date=entry.clearing_date,
                            clearing_document=entry.clearing_document,
                            amount=float(entry.amount),
                            currency=entry.currency,
                            assignment_number=entry.assignment_number,
                            source="sap",
                            created_by=triggered_by,
                            modified_by=triggered_by,
                        )
                        session.add(ledger_entry)

                    # Update case status to ledger_confirmed
                    if case_model.status == "created":
                        case_model.status = "ledger_confirmed"
                        case_model.modified_by = triggered_by
                        case_model.modified_date = datetime.now(timezone.utc)

                    vendor_result["row_count"] = extraction_result.row_count
                    vendor_result["duplicates_skipped"] = extraction_result.duplicates_skipped
                    total_rows += extraction_result.row_count

                except Exception as exc:
                    vendor_result["status"] = "failed"
                    vendor_result["error"] = str(exc)
                    overall_status = "partial_failure"
                    logger.warning(
                        "SAP pull failed for vendor %s: %s",
                        vendor_code,
                        str(exc),
                    )

                vendor_results.append(vendor_result)

                # Update task progress
                task.update_state(
                    state="PROGRESS",
                    meta={
                        "current": idx + 1,
                        "total": len(vendor_codes),
                        "status": f"Extracted data for {idx + 1}/{len(vendor_codes)} vendors",
                    },
                )

            extraction_end = datetime.now(timezone.utc)
            duration = (extraction_end - extraction_start).total_seconds()

            # Record audit log entry for the extraction
            audit_entry = AuditLogModel(
                id=uuid4(),
                actor_id=None,
                actor_username=triggered_by,
                action="sap_data_pull",
                resource_type="reconciliation_request",
                resource_id=str(request_id),
                old_value=None,
                new_value=json.dumps({
                    "extraction_timestamp": extraction_end.isoformat(),
                    "row_count": total_rows,
                    "status": overall_status,
                    "vendor_count": len(vendor_codes),
                    "duration_seconds": round(duration, 2),
                    "vendor_results": vendor_results,
                }),
                ip_address="",
                user_agent="celery-worker",
                extra_data=json.dumps({
                    "task_id": task.request.id,
                    "company_code": company_code,
                    "period_start": period_start,
                    "period_end": period_end,
                }),
            )
            session.add(audit_entry)

            await session.commit()

            logger.info(
                "SAP pull completed: request_id=%s, total_rows=%d, "
                "vendors=%d, duration=%.2fs, status=%s",
                request_id,
                total_rows,
                len(vendor_codes),
                duration,
                overall_status,
            )

            return {
                "request_id": request_id,
                "status": overall_status,
                "total_rows": total_rows,
                "vendor_count": len(vendor_codes),
                "extraction_timestamp": extraction_end.isoformat(),
                "duration_seconds": round(duration, 2),
                "vendor_results": vendor_results,
            }

        except Exception as exc:
            await session.rollback()
            overall_status = "failed"
            error_message = str(exc)

            logger.error(
                "SAP pull task failed: request_id=%s, error=%s",
                request_id,
                error_message,
            )

            # Record failure in audit log
            try:
                async with async_session_factory() as audit_session:
                    audit_entry = AuditLogModel(
                        id=uuid4(),
                        actor_id=None,
                        actor_username=triggered_by,
                        action="sap_data_pull_failed",
                        resource_type="reconciliation_request",
                        resource_id=str(request_id),
                        old_value=None,
                        new_value=json.dumps({
                            "status": "failed",
                            "error": error_message,
                            "extraction_timestamp": datetime.now(timezone.utc).isoformat(),
                        }),
                        ip_address="",
                        user_agent="celery-worker",
                        extra_data=json.dumps({
                            "task_id": task.request.id,
                            "company_code": company_code,
                        }),
                    )
                    audit_session.add(audit_entry)
                    await audit_session.commit()
            except Exception as audit_exc:
                logger.error(
                    "Failed to record audit log for SAP pull failure: %s",
                    str(audit_exc),
                )

            raise
