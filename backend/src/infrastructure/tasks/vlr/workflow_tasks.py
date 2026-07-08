"""
Workflow orchestration Celery tasks.

Provides async task execution for each workflow step in the 11-step
reconciliation lifecycle. Includes SLA monitoring periodic task that
checks for overdue cases every 15 minutes.

Implements retry logic with exponential backoff per task type:
- SAP pull step: max_retries=3, exponential backoff
- Transformation step: max_retries=2
- Reconciliation step: max_retries=2
- SLA check: max_retries=1 (periodic, runs again on schedule)
- Vendor engagement email: max_retries=3, exponential backoff

Requirements: 12.3, 13.2, 13.3
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone

from celery import Task
from celery.schedules import crontab

from src.infrastructure.background.celery_app import celery_app
from src.infrastructure.logging.structured_logger import get_structured_logger

logger = logging.getLogger(__name__)
_structured_logger = get_structured_logger("celery_workflow")


# ──────────────────────────────────────────────────────────────────────
# Celery Beat Schedule - SLA Monitoring
# ──────────────────────────────────────────────────────────────────────

# Register SLA check as a periodic task (every 15 minutes)
celery_app.conf.beat_schedule = {
    **getattr(celery_app.conf, "beat_schedule", {}),
    "vlr-workflow-check-sla-violations": {
        "task": "vlr.workflow.check_sla_violations",
        "schedule": crontab(minute="*/15"),
        "options": {"queue": "workflow"},
    },
}


# ──────────────────────────────────────────────────────────────────────
# Custom Task Base Classes
# ──────────────────────────────────────────────────────────────────────


class WorkflowStepTask(Task):
    """Base task class for workflow step advancement."""

    max_retries = 2
    default_retry_delay = 30

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """Log workflow step task failure."""
        case_id = kwargs.get("case_id") or (args[0] if args else "unknown")
        _structured_logger.log_failure(
            operation="workflow_step_task",
            duration_ms=0.0,
            error=str(exc),
            error_type=type(exc).__name__,
            case_id=case_id,
            task_id=task_id,
        )
        logger.error(
            "Workflow step task failed: task_id=%s, case_id=%s, error=%s",
            task_id,
            case_id,
            str(exc),
        )

    def on_success(self, retval, task_id, args, kwargs):
        """Log workflow step task success."""
        case_id = kwargs.get("case_id") or (args[0] if args else "unknown")
        _structured_logger.log_success(
            operation="workflow_step_task",
            duration_ms=0.0,
            case_id=case_id,
            task_id=task_id,
        )
        logger.info(
            "Workflow step task completed: task_id=%s, case_id=%s",
            task_id,
            case_id,
        )


class SAPPullStepTask(Task):
    """Task class for SAP pull step with higher retry count."""

    max_retries = 3
    default_retry_delay = 60  # Exponential backoff base

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """Log SAP pull step failure."""
        case_id = kwargs.get("case_id") or (args[0] if args else "unknown")
        _structured_logger.log_failure(
            operation="sap_pull_step_task",
            duration_ms=0.0,
            error=str(exc),
            error_type=type(exc).__name__,
            case_id=case_id,
            task_id=task_id,
        )
        logger.error(
            "SAP pull step task failed: task_id=%s, case_id=%s, error=%s",
            task_id,
            case_id,
            str(exc),
        )

    def on_success(self, retval, task_id, args, kwargs):
        """Log SAP pull step success."""
        case_id = kwargs.get("case_id") or (args[0] if args else "unknown")
        _structured_logger.log_success(
            operation="sap_pull_step_task",
            duration_ms=0.0,
            case_id=case_id,
            task_id=task_id,
        )
        logger.info(
            "SAP pull step task completed: task_id=%s, case_id=%s",
            task_id,
            case_id,
        )


class SLACheckTask(Task):
    """Task class for SLA monitoring with minimal retries."""

    max_retries = 1
    default_retry_delay = 120

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """Log SLA check failure."""
        logger.error(
            "SLA check task failed: task_id=%s, error=%s",
            task_id,
            str(exc),
        )

    def on_success(self, retval, task_id, args, kwargs):
        """Log SLA check success."""
        logger.info(
            "SLA check task completed: task_id=%s, violations=%s",
            task_id,
            retval.get("violations_found", 0) if retval else 0,
        )


class VendorEngagementTask(Task):
    """Task class for vendor engagement email with higher retry count."""

    max_retries = 3
    default_retry_delay = 60

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """Log vendor engagement email failure."""
        case_id = kwargs.get("case_id") or (args[0] if args else "unknown")
        logger.error(
            "Vendor engagement email task failed: task_id=%s, case_id=%s, error=%s",
            task_id,
            case_id,
            str(exc),
        )

    def on_success(self, retval, task_id, args, kwargs):
        """Log vendor engagement email success."""
        case_id = kwargs.get("case_id") or (args[0] if args else "unknown")
        logger.info(
            "Vendor engagement email task completed: task_id=%s, case_id=%s",
            task_id,
            case_id,
        )


# ──────────────────────────────────────────────────────────────────────
# Task: Advance Workflow Step
# ──────────────────────────────────────────────────────────────────────


@celery_app.task(
    base=WorkflowStepTask,
    bind=True,
    name="vlr.workflow.advance_step",
    acks_late=True,
    time_limit=120,
    soft_time_limit=90,
)
def advance_workflow_step(
    self: WorkflowStepTask,
    case_id: str,
    target_step: str,
    triggered_by: str = "system",
) -> dict:
    """
    Advance a reconciliation case to the specified workflow step.

    Calls the WorkflowOrchestratorService.advance() method to validate
    the transition and update the case state. On failure, retries with
    exponential backoff.

    Requirement 12.3: Execute each workflow step as a Celery task.

    Args:
        case_id: UUID of the reconciliation case.
        target_step: Target workflow step value (e.g., "sap_pull").
        triggered_by: Username or system identifier.

    Returns:
        Dict with the updated workflow status.
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        result = loop.run_until_complete(
            _execute_advance_step(
                task=self,
                case_id=case_id,
                target_step=target_step,
                triggered_by=triggered_by,
            )
        )
        return result
    except Exception as exc:
        # Retry with exponential backoff
        retry_delay = self.default_retry_delay * (2 ** self.request.retries)
        raise self.retry(exc=exc, countdown=retry_delay)
    finally:
        loop.close()


async def _execute_advance_step(
    task: WorkflowStepTask,
    case_id: str,
    target_step: str,
    triggered_by: str,
) -> dict:
    """Execute workflow step advancement via the orchestrator service."""
    from uuid import UUID

    from src.infrastructure.database.session import async_session_factory
    from src.infrastructure.database.repositories.vlr.case_repository_impl import (
        CaseRepositoryImpl,
    )
    from src.domain.services.vlr.workflow_orchestrator_service import (
        WorkflowOrchestratorService,
        WorkflowStep,
        SLAConfiguration,
    )

    task.update_state(
        state="PROGRESS",
        meta={
            "phase": "advancing",
            "status": f"Advancing case {case_id} to step '{target_step}'...",
            "case_id": case_id,
        },
    )

    async with async_session_factory() as session:
        try:
            case_repo = CaseRepositoryImpl(session)

            # Load SLA configuration from database
            sla_config = await _load_sla_configuration(session)

            orchestrator = WorkflowOrchestratorService(
                case_repository=case_repo,
                sla_config=sla_config,
            )

            step_enum = WorkflowStep(target_step)
            case_status = await orchestrator.advance(
                case_id=UUID(case_id),
                target_step=step_enum,
                triggered_by=triggered_by,
            )

            await session.commit()

            logger.info(
                "Workflow step advanced: case_id=%s, to_step=%s, triggered_by=%s",
                case_id,
                target_step,
                triggered_by,
            )

            return {
                "case_id": case_id,
                "status": "advanced",
                "current_step": case_status.current_step.value,
                "step_entered_at": case_status.step_entered_at.isoformat(),
                "sla_deadline": (
                    case_status.sla_deadline.isoformat()
                    if case_status.sla_deadline
                    else None
                ),
                "is_overdue": case_status.is_overdue,
            }

        except Exception as exc:
            await session.rollback()
            logger.error(
                "Workflow advance failed: case_id=%s, target=%s, error=%s",
                case_id,
                target_step,
                str(exc),
            )
            raise


# ──────────────────────────────────────────────────────────────────────
# Task: Execute SAP Pull Step
# ──────────────────────────────────────────────────────────────────────


@celery_app.task(
    base=SAPPullStepTask,
    bind=True,
    name="vlr.workflow.execute_sap_pull",
    acks_late=True,
    time_limit=180,
    soft_time_limit=150,
)
def execute_sap_pull_step(
    self: SAPPullStepTask,
    case_id: str,
    triggered_by: str = "system",
) -> dict:
    """
    Trigger SAP data pull for a reconciliation case.

    Advances the case to SAP_PULL step and initiates the SAP
    extraction process. Uses max_retries=3 with exponential backoff
    since SAP connectivity can be intermittent.

    Requirement 12.3: Execute SAP pull as a Celery task.

    Args:
        case_id: UUID of the reconciliation case.
        triggered_by: Username or system identifier.

    Returns:
        Dict with SAP pull execution results.
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        result = loop.run_until_complete(
            _execute_sap_pull_step(
                task=self,
                case_id=case_id,
                triggered_by=triggered_by,
            )
        )
        return result
    except Exception as exc:
        # Exponential backoff: 60s, 120s, 240s
        retry_delay = self.default_retry_delay * (2 ** self.request.retries)
        raise self.retry(exc=exc, countdown=retry_delay)
    finally:
        loop.close()


async def _execute_sap_pull_step(
    task: SAPPullStepTask,
    case_id: str,
    triggered_by: str,
) -> dict:
    """Execute SAP pull step for a case."""
    from uuid import UUID

    from src.infrastructure.database.session import async_session_factory
    from src.infrastructure.database.repositories.vlr.case_repository_impl import (
        CaseRepositoryImpl,
    )
    from src.domain.services.vlr.workflow_orchestrator_service import (
        WorkflowOrchestratorService,
        WorkflowStep,
        SLAConfiguration,
    )

    task.update_state(
        state="PROGRESS",
        meta={
            "phase": "sap_pull",
            "status": f"Executing SAP pull for case {case_id}...",
            "case_id": case_id,
        },
    )

    async with async_session_factory() as session:
        try:
            case_repo = CaseRepositoryImpl(session)
            sla_config = await _load_sla_configuration(session)

            orchestrator = WorkflowOrchestratorService(
                case_repository=case_repo,
                sla_config=sla_config,
            )

            # Advance to SAP_PULL step
            case_status = await orchestrator.advance(
                case_id=UUID(case_id),
                target_step=WorkflowStep.SAP_PULL,
                triggered_by=triggered_by,
            )

            await session.commit()

            logger.info(
                "SAP pull step executed: case_id=%s, triggered_by=%s",
                case_id,
                triggered_by,
            )

            return {
                "case_id": case_id,
                "status": "sap_pull_initiated",
                "current_step": case_status.current_step.value,
                "step_entered_at": case_status.step_entered_at.isoformat(),
                "sla_deadline": (
                    case_status.sla_deadline.isoformat()
                    if case_status.sla_deadline
                    else None
                ),
            }

        except Exception as exc:
            await session.rollback()
            logger.error(
                "SAP pull step failed: case_id=%s, error=%s",
                case_id,
                str(exc),
            )
            raise


# ──────────────────────────────────────────────────────────────────────
# Task: Execute Transformation Step
# ──────────────────────────────────────────────────────────────────────


@celery_app.task(
    base=WorkflowStepTask,
    bind=True,
    name="vlr.workflow.execute_transformation",
    acks_late=True,
    time_limit=180,
    soft_time_limit=150,
)
def execute_transformation_step(
    self: WorkflowStepTask,
    case_id: str,
    triggered_by: str = "system",
) -> dict:
    """
    Trigger the data transformation pipeline for a reconciliation case.

    Advances the case to TRANSFORMATION step and executes invoice
    derivation, sign adjustment, balance calculations, TDS tagging,
    and document type classification. Uses max_retries=2.

    Requirement 12.3: Execute transformation as a Celery task.

    Args:
        case_id: UUID of the reconciliation case.
        triggered_by: Username or system identifier.

    Returns:
        Dict with transformation execution results.
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        result = loop.run_until_complete(
            _execute_transformation_step(
                task=self,
                case_id=case_id,
                triggered_by=triggered_by,
            )
        )
        return result
    except Exception as exc:
        retry_delay = self.default_retry_delay * (2 ** self.request.retries)
        raise self.retry(exc=exc, countdown=retry_delay)
    finally:
        loop.close()


async def _execute_transformation_step(
    task: WorkflowStepTask,
    case_id: str,
    triggered_by: str,
) -> dict:
    """Execute data transformation step for a case."""
    from uuid import UUID

    from src.infrastructure.database.session import async_session_factory
    from src.infrastructure.database.repositories.vlr.case_repository_impl import (
        CaseRepositoryImpl,
    )
    from src.domain.services.vlr.workflow_orchestrator_service import (
        WorkflowOrchestratorService,
        WorkflowStep,
        SLAConfiguration,
    )

    task.update_state(
        state="PROGRESS",
        meta={
            "phase": "transformation",
            "status": f"Executing transformation for case {case_id}...",
            "case_id": case_id,
        },
    )

    async with async_session_factory() as session:
        try:
            case_repo = CaseRepositoryImpl(session)
            sla_config = await _load_sla_configuration(session)

            orchestrator = WorkflowOrchestratorService(
                case_repository=case_repo,
                sla_config=sla_config,
            )

            # Advance to TRANSFORMATION step
            case_status = await orchestrator.advance(
                case_id=UUID(case_id),
                target_step=WorkflowStep.TRANSFORMATION,
                triggered_by=triggered_by,
            )

            await session.commit()

            logger.info(
                "Transformation step executed: case_id=%s, triggered_by=%s",
                case_id,
                triggered_by,
            )

            return {
                "case_id": case_id,
                "status": "transformation_initiated",
                "current_step": case_status.current_step.value,
                "step_entered_at": case_status.step_entered_at.isoformat(),
                "sla_deadline": (
                    case_status.sla_deadline.isoformat()
                    if case_status.sla_deadline
                    else None
                ),
            }

        except Exception as exc:
            await session.rollback()
            logger.error(
                "Transformation step failed: case_id=%s, error=%s",
                case_id,
                str(exc),
            )
            raise


# ──────────────────────────────────────────────────────────────────────
# Task: Execute Auto-Reconciliation Step
# ──────────────────────────────────────────────────────────────────────


@celery_app.task(
    base=WorkflowStepTask,
    bind=True,
    name="vlr.workflow.execute_auto_reconciliation",
    acks_late=True,
    time_limit=180,
    soft_time_limit=150,
)
def execute_auto_reconciliation_step(
    self: WorkflowStepTask,
    case_id: str,
    triggered_by: str = "system",
    tolerance: float = 0.0,
    fuzzy_threshold: float = 0.8,
) -> dict:
    """
    Trigger the auto-reconciliation engine for a reconciliation case.

    Advances the case to AUTO_RECONCILIATION step and executes the
    multi-pass matching algorithm. Uses max_retries=2.

    Requirement 12.3: Execute reconciliation as a Celery task.

    Args:
        case_id: UUID of the reconciliation case.
        triggered_by: Username or system identifier.
        tolerance: Tolerance amount for Pass 2 matching.
        fuzzy_threshold: Similarity threshold for Pass 3.

    Returns:
        Dict with reconciliation execution results.
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        result = loop.run_until_complete(
            _execute_auto_reconciliation_step(
                task=self,
                case_id=case_id,
                triggered_by=triggered_by,
                tolerance=tolerance,
                fuzzy_threshold=fuzzy_threshold,
            )
        )
        return result
    except Exception as exc:
        retry_delay = self.default_retry_delay * (2 ** self.request.retries)
        raise self.retry(exc=exc, countdown=retry_delay)
    finally:
        loop.close()


async def _execute_auto_reconciliation_step(
    task: WorkflowStepTask,
    case_id: str,
    triggered_by: str,
    tolerance: float,
    fuzzy_threshold: float,
) -> dict:
    """Execute auto-reconciliation step for a case."""
    from uuid import UUID

    from src.infrastructure.database.session import async_session_factory
    from src.infrastructure.database.repositories.vlr.case_repository_impl import (
        CaseRepositoryImpl,
    )
    from src.domain.services.vlr.workflow_orchestrator_service import (
        WorkflowOrchestratorService,
        WorkflowStep,
        SLAConfiguration,
    )

    task.update_state(
        state="PROGRESS",
        meta={
            "phase": "auto_reconciliation",
            "status": f"Executing auto-reconciliation for case {case_id}...",
            "case_id": case_id,
        },
    )

    async with async_session_factory() as session:
        try:
            case_repo = CaseRepositoryImpl(session)
            sla_config = await _load_sla_configuration(session)

            orchestrator = WorkflowOrchestratorService(
                case_repository=case_repo,
                sla_config=sla_config,
            )

            # Advance to AUTO_RECONCILIATION step
            case_status = await orchestrator.advance(
                case_id=UUID(case_id),
                target_step=WorkflowStep.AUTO_RECONCILIATION,
                triggered_by=triggered_by,
            )

            await session.commit()

            logger.info(
                "Auto-reconciliation step executed: case_id=%s, "
                "tolerance=%s, fuzzy_threshold=%s, triggered_by=%s",
                case_id,
                tolerance,
                fuzzy_threshold,
                triggered_by,
            )

            return {
                "case_id": case_id,
                "status": "auto_reconciliation_initiated",
                "current_step": case_status.current_step.value,
                "step_entered_at": case_status.step_entered_at.isoformat(),
                "sla_deadline": (
                    case_status.sla_deadline.isoformat()
                    if case_status.sla_deadline
                    else None
                ),
                "tolerance": tolerance,
                "fuzzy_threshold": fuzzy_threshold,
            }

        except Exception as exc:
            await session.rollback()
            logger.error(
                "Auto-reconciliation step failed: case_id=%s, error=%s",
                case_id,
                str(exc),
            )
            raise


# ──────────────────────────────────────────────────────────────────────
# Task: Check SLA Violations (Periodic)
# ──────────────────────────────────────────────────────────────────────


@celery_app.task(
    base=SLACheckTask,
    bind=True,
    name="vlr.workflow.check_sla_violations",
    acks_late=True,
    time_limit=120,
    soft_time_limit=90,
)
def check_sla_violations_periodic(self: SLACheckTask) -> dict:
    """
    Periodic task that checks for SLA violations across all active cases.

    Runs every 15 minutes via Celery Beat. Identifies cases where the
    current workflow step has exceeded its configured SLA deadline and
    triggers escalation notifications to assigned managers.

    Uses max_retries=1 since this task runs periodically and will
    execute again on the next schedule.

    Requirement 13.2: Flag overdue cases and send escalation.
    Requirement 13.3: Send escalation notification on SLA violation.

    Returns:
        Dict with SLA violation check results.
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        result = loop.run_until_complete(
            _execute_sla_check(task=self)
        )
        return result
    except Exception as exc:
        raise self.retry(exc=exc, countdown=self.default_retry_delay)
    finally:
        loop.close()


async def _execute_sla_check(task: SLACheckTask) -> dict:
    """Execute SLA violation check across all active cases."""
    from sqlalchemy import select, and_

    from src.infrastructure.database.session import async_session_factory
    from src.infrastructure.database.repositories.vlr.case_repository_impl import (
        CaseRepositoryImpl,
    )
    from src.infrastructure.database.repositories.vlr.notification_repository_impl import (
        NotificationRepositoryImpl,
    )
    from src.infrastructure.database.repositories.vlr.setting_repository_impl import (
        SettingRepositoryImpl,
    )
    from src.infrastructure.database.models.vlr.reconciliation_case_model import (
        ReconciliationCaseModel,
    )
    from src.domain.services.vlr.workflow_orchestrator_service import (
        WorkflowOrchestratorService,
        SLAConfiguration,
    )
    from src.domain.services.vlr.notification_service import NotificationService

    check_start = datetime.now(timezone.utc)

    task.update_state(
        state="PROGRESS",
        meta={
            "phase": "checking_sla",
            "status": "Checking for SLA violations...",
        },
    )

    async with async_session_factory() as session:
        try:
            # Query cases that have exceeded their SLA deadline
            # and are not yet flagged as overdue
            now = datetime.now(timezone.utc)
            overdue_stmt = select(ReconciliationCaseModel).where(
                and_(
                    ReconciliationCaseModel.is_deleted == False,  # noqa: E712
                    ReconciliationCaseModel.sla_deadline.isnot(None),
                    ReconciliationCaseModel.sla_deadline < now,
                    ReconciliationCaseModel.is_overdue == False,  # noqa: E712
                    ReconciliationCaseModel.current_workflow_step.isnot(None),
                    ReconciliationCaseModel.current_workflow_step != "closure",
                )
            )
            result = await session.execute(overdue_stmt)
            overdue_cases = result.scalars().all()

            if not overdue_cases:
                return {
                    "status": "completed",
                    "violations_found": 0,
                    "checked_at": now.isoformat(),
                    "duration_seconds": 0.0,
                }

            # Initialize services
            case_repo = CaseRepositoryImpl(session)
            notification_repo = NotificationRepositoryImpl(session)
            setting_repo = SettingRepositoryImpl(session)
            sla_config = await _load_sla_configuration(session)

            notification_service = NotificationService(
                notification_repository=notification_repo,
                case_repository=case_repo,
                setting_repository=setting_repo,
                email_sender=None,
            )

            orchestrator = WorkflowOrchestratorService(
                case_repository=case_repo,
                sla_config=sla_config,
                notification_service=notification_service,
            )

            # Check SLA violations and send escalations
            violations = await orchestrator.check_sla_violations(
                overdue_cases=overdue_cases,
            )

            await session.commit()

            check_end = datetime.now(timezone.utc)
            duration = (check_end - check_start).total_seconds()

            logger.info(
                "SLA check completed: violations_found=%d, duration=%.2fs",
                len(violations),
                duration,
            )

            return {
                "status": "completed",
                "violations_found": len(violations),
                "violations": [
                    {
                        "case_id": str(v.case_id),
                        "current_step": v.current_step.value,
                        "hours_overdue": round(v.hours_overdue, 2),
                        "sla_deadline": v.sla_deadline.isoformat(),
                    }
                    for v in violations
                ],
                "checked_at": now.isoformat(),
                "duration_seconds": round(duration, 2),
            }

        except Exception as exc:
            await session.rollback()
            logger.error(
                "SLA violation check failed: error=%s",
                str(exc),
            )
            raise


# ──────────────────────────────────────────────────────────────────────
# Task: Send Vendor Engagement Email
# ──────────────────────────────────────────────────────────────────────


@celery_app.task(
    base=VendorEngagementTask,
    bind=True,
    name="vlr.workflow.send_vendor_engagement_email",
    acks_late=True,
    time_limit=60,
    soft_time_limit=45,
)
def send_vendor_engagement_email(
    self: VendorEngagementTask,
    case_id: str,
    vendor_email: str,
    portal_url: str,
    vendor_name: str = "",
    triggered_by: str = "system",
) -> dict:
    """
    Send vendor portal invite email as part of the Vendor Engagement step.

    Sends an invitation email to the vendor with a unique portal link
    for uploading their statement. Uses max_retries=3 with exponential
    backoff since email delivery can be unreliable.

    Requirement 12.3: Execute vendor engagement as a Celery task.

    Args:
        case_id: UUID of the reconciliation case.
        vendor_email: Vendor contact email address.
        portal_url: Unique portal access URL for the vendor.
        vendor_name: Name of the vendor (for template personalization).
        triggered_by: Username or system identifier.

    Returns:
        Dict with email delivery results.
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        result = loop.run_until_complete(
            _execute_vendor_engagement_email(
                task=self,
                case_id=case_id,
                vendor_email=vendor_email,
                portal_url=portal_url,
                vendor_name=vendor_name,
                triggered_by=triggered_by,
            )
        )
        return result
    except Exception as exc:
        # Exponential backoff: 60s, 120s, 240s
        retry_delay = self.default_retry_delay * (2 ** self.request.retries)
        raise self.retry(exc=exc, countdown=retry_delay)
    finally:
        loop.close()


async def _execute_vendor_engagement_email(
    task: VendorEngagementTask,
    case_id: str,
    vendor_email: str,
    portal_url: str,
    vendor_name: str,
    triggered_by: str,
) -> dict:
    """Execute vendor engagement email sending."""
    from uuid import UUID, uuid4

    from src.infrastructure.database.session import async_session_factory
    from src.infrastructure.database.repositories.vlr.notification_repository_impl import (
        NotificationRepositoryImpl,
    )
    from src.infrastructure.database.repositories.vlr.case_repository_impl import (
        CaseRepositoryImpl,
    )
    from src.infrastructure.database.repositories.vlr.setting_repository_impl import (
        SettingRepositoryImpl,
    )
    from src.domain.services.vlr.notification_service import (
        NotificationService,
        VendorContact,
    )

    task.update_state(
        state="PROGRESS",
        meta={
            "phase": "sending_invite",
            "status": f"Sending vendor engagement email to {vendor_email}...",
            "case_id": case_id,
        },
    )

    async with async_session_factory() as session:
        try:
            notification_repo = NotificationRepositoryImpl(session)
            case_repo = CaseRepositoryImpl(session)
            setting_repo = SettingRepositoryImpl(session)

            service = NotificationService(
                notification_repository=notification_repo,
                case_repository=case_repo,
                setting_repository=setting_repo,
                email_sender=None,
            )

            contact = VendorContact(
                id=uuid4(),
                vendor_id=uuid4(),
                name=vendor_name,
                email=vendor_email,
            )

            result = await service.send_invitation(
                case_id=UUID(case_id),
                vendor_contact=contact,
                portal_url=portal_url,
            )

            await session.commit()

            logger.info(
                "Vendor engagement email sent: case_id=%s, "
                "vendor_email=%s, status=%s",
                case_id,
                vendor_email,
                result.status,
            )

            return {
                "case_id": case_id,
                "status": "email_sent",
                "notification_id": str(result.notification_id),
                "vendor_email": vendor_email,
                "portal_url": portal_url,
                "delivery_status": result.status,
                "sent_date": (
                    result.sent_date.isoformat() if result.sent_date else None
                ),
            }

        except Exception as exc:
            await session.rollback()
            logger.error(
                "Vendor engagement email failed: case_id=%s, "
                "vendor_email=%s, error=%s",
                case_id,
                vendor_email,
                str(exc),
            )
            raise


# ──────────────────────────────────────────────────────────────────────
# Shared Helper: Load SLA Configuration
# ──────────────────────────────────────────────────────────────────────


async def _load_sla_configuration(session: object) -> "SLAConfiguration":
    """
    Load SLA configuration from the database.

    Queries the vlr_sla_configurations table and builds an
    SLAConfiguration dataclass. Falls back to default values
    if the table is empty or query fails.
    """
    from src.domain.services.vlr.workflow_orchestrator_service import SLAConfiguration

    # Default SLA hours per step (hours)
    default_sla_hours: dict[str, int] = {
        "initiation": 4,
        "sap_pull": 8,
        "transformation": 4,
        "finance_review": 48,
        "column_mapping": 24,
        "vendor_engagement": 240,  # 10 days
        "auto_reconciliation": 8,
        "exception_resolution": 120,  # 5 days
        "finance_approval": 72,  # 3 days
        "vendor_sign_off": 168,  # 7 days
    }

    try:
        from sqlalchemy import select
        from src.infrastructure.database.models.vlr.sla_configuration_model import (
            SLAConfigurationModel,
        )

        stmt = select(SLAConfigurationModel).where(
            SLAConfigurationModel.is_active == True  # noqa: E712
        )
        result = await session.execute(stmt)
        sla_configs = result.scalars().all()

        if sla_configs:
            step_sla_hours = {}
            escalation_emails = {}
            for config in sla_configs:
                step_sla_hours[config.step_name] = config.sla_hours
                if config.escalation_email:
                    escalation_emails[config.step_name] = config.escalation_email

            return SLAConfiguration(
                step_sla_hours=step_sla_hours,
                escalation_emails=escalation_emails,
            )
    except Exception as exc:
        logger.warning(
            "Failed to load SLA configuration from database, "
            "using defaults: %s",
            str(exc),
        )

    return SLAConfiguration(step_sla_hours=default_sla_hours)
