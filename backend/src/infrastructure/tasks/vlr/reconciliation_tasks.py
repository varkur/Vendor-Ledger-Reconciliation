"""
Reconciliation engine Celery tasks.

Provides async task execution for the multi-pass reconciliation engine,
preventing API request blocking for large matching operations
(up to 5,000 entries per side within 120 seconds).

Implements idempotency key logic to prevent duplicate engine executions
from rapid user clicks. Progress status updates are provided via
Celery task state for polling-based progress tracking.

Requirements: 16.1, 16.6, 16.9, 17.10
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from uuid import UUID, uuid4

from celery import Task

from src.infrastructure.background.celery_app import celery_app
from src.infrastructure.logging.structured_logger import get_structured_logger

logger = logging.getLogger(__name__)
_structured_logger = get_structured_logger("celery_reconciliation")

# Redis key prefix for reconciliation idempotency
IDEMPOTENCY_KEY_PREFIX = "vlr:reconciliation:idempotency:"
# Idempotency key TTL in seconds (5 minutes - covers timeout + buffer)
IDEMPOTENCY_KEY_TTL = 300


class ReconciliationTask(Task):
    """Custom base task class with error handling for reconciliation engine."""

    name = "vlr.reconciliation"
    max_retries = 0  # No retries - reconciliation is idempotent via re-trigger
    default_retry_delay = 0

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """Log task failure and clear idempotency key so task can be re-triggered."""
        case_id = kwargs.get("case_id") or (args[0] if args else "unknown")
        idempotency_key = kwargs.get("idempotency_key") or (
            args[1] if len(args) > 1 else None
        )
        _structured_logger.log_failure(
            operation="reconciliation_task",
            duration_ms=0.0,
            error=str(exc),
            error_type=type(exc).__name__,
            case_id=case_id,
            task_id=task_id,
        )
        logger.error(
            "Reconciliation task failed: task_id=%s, case_id=%s, error=%s",
            task_id,
            case_id,
            str(exc),
        )
        # Clear the idempotency key on failure so the task can be re-triggered
        if idempotency_key:
            _clear_idempotency_key(idempotency_key)

    def on_success(self, retval, task_id, args, kwargs):
        """Log task success."""
        case_id = kwargs.get("case_id") or (args[0] if args else "unknown")
        _structured_logger.log_success(
            operation="reconciliation_task",
            duration_ms=retval.get("duration_seconds", 0) * 1000 if isinstance(retval, dict) else 0.0,
            case_id=case_id,
            task_id=task_id,
        )
        logger.info(
            "Reconciliation task completed: task_id=%s, case_id=%s",
            task_id,
            case_id,
        )


def _get_redis_client():
    """Get a Redis client using the configured broker URL."""
    import redis

    from src.config.settings import settings

    return redis.from_url(settings.REDIS_URL, decode_responses=True)


def _check_idempotency_key(idempotency_key: str) -> bool:
    """
    Check if the idempotency key already exists in Redis.

    Returns True if the key exists (duplicate execution), False otherwise.
    """
    try:
        client = _get_redis_client()
        return client.exists(f"{IDEMPOTENCY_KEY_PREFIX}{idempotency_key}") > 0
    except Exception as exc:
        logger.warning(
            "Failed to check idempotency key (proceeding with execution): %s",
            str(exc),
        )
        return False


def _set_idempotency_key(idempotency_key: str, task_id: str) -> bool:
    """
    Set the idempotency key in Redis with TTL.

    Uses SET NX (set if not exists) to prevent race conditions.
    Returns True if the key was set successfully, False if it already exists.
    """
    try:
        client = _get_redis_client()
        value = json.dumps({
            "task_id": task_id,
            "started_at": datetime.now(timezone.utc).isoformat(),
        })
        # SET NX - only sets if key does not exist (atomic check-and-set)
        was_set = client.set(
            f"{IDEMPOTENCY_KEY_PREFIX}{idempotency_key}",
            value,
            nx=True,
            ex=IDEMPOTENCY_KEY_TTL,
        )
        return bool(was_set)
    except Exception as exc:
        logger.warning(
            "Failed to set idempotency key (proceeding with execution): %s",
            str(exc),
        )
        return True  # Proceed on Redis failure (graceful degradation)


def _clear_idempotency_key(idempotency_key: str) -> None:
    """Clear the idempotency key from Redis (called on task failure)."""
    try:
        client = _get_redis_client()
        client.delete(f"{IDEMPOTENCY_KEY_PREFIX}{idempotency_key}")
    except Exception as exc:
        logger.warning(
            "Failed to clear idempotency key: %s",
            str(exc),
        )


@celery_app.task(
    base=ReconciliationTask,
    bind=True,
    name="vlr.reconciliation",
    acks_late=True,
    time_limit=150,  # Hard limit: 2.5 minutes (allows cleanup after soft limit)
    soft_time_limit=120,  # Soft limit: 120 seconds (Requirement 16.1)
)
def reconciliation_task(
    self: ReconciliationTask,
    case_id: str,
    idempotency_key: str,
    triggered_by: str,
    tolerance: float = 0.0,
    fuzzy_threshold: float = 0.8,
) -> dict:
    """
    Async Celery task for executing the multi-pass reconciliation engine.

    Implements idempotency key check to prevent duplicate engine executions
    from rapid user clicks (Requirement 17.10). Provides progress status
    updates during execution (Requirement 16.9). Enforces 120-second
    timeout for 5,000-entry matching (Requirement 16.1).

    Args:
        case_id: UUID of the reconciliation case to reconcile.
        idempotency_key: Unique key to prevent duplicate executions.
        triggered_by: Username of the user who triggered reconciliation.
        tolerance: Tolerance amount for Pass 2 matching.
        fuzzy_threshold: Similarity threshold for Pass 3 fuzzy matching.

    Returns:
        Dict with reconciliation results including match statistics.

    Raises:
        IdempotencyConflictException: If a duplicate execution is detected.
    """
    # ─── Idempotency Check ────────────────────────────────────────────────
    # Check if this exact request has already been submitted
    if _check_idempotency_key(idempotency_key):
        logger.warning(
            "Duplicate reconciliation request detected: "
            "case_id=%s, idempotency_key=%s",
            case_id,
            idempotency_key,
        )
        return {
            "case_id": case_id,
            "status": "duplicate",
            "message": "A reconciliation with this idempotency key is already in progress.",
            "idempotency_key": idempotency_key,
        }

    # Atomically set the idempotency key (prevents race condition)
    if not _set_idempotency_key(idempotency_key, self.request.id):
        logger.warning(
            "Concurrent reconciliation request detected (race condition): "
            "case_id=%s, idempotency_key=%s",
            case_id,
            idempotency_key,
        )
        return {
            "case_id": case_id,
            "status": "duplicate",
            "message": "A reconciliation with this idempotency key is already in progress.",
            "idempotency_key": idempotency_key,
        }

    # ─── Execute Reconciliation ───────────────────────────────────────────
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        result = loop.run_until_complete(
            _execute_reconciliation(
                task=self,
                case_id=case_id,
                idempotency_key=idempotency_key,
                triggered_by=triggered_by,
                tolerance=tolerance,
                fuzzy_threshold=fuzzy_threshold,
            )
        )
        return result
    except Exception:
        # Clear idempotency key on failure so task can be re-triggered
        _clear_idempotency_key(idempotency_key)
        raise
    finally:
        loop.close()


async def _execute_reconciliation(
    task: ReconciliationTask,
    case_id: str,
    idempotency_key: str,
    triggered_by: str,
    tolerance: float,
    fuzzy_threshold: float,
) -> dict:
    """
    Execute the multi-pass reconciliation engine for a case.

    Connects to the database, runs the reconciliation engine service,
    updates case status, and records results. Provides progress updates
    throughout execution.
    """
    from decimal import Decimal

    from sqlalchemy import select, and_

    from src.infrastructure.database.session import async_session_factory
    from src.infrastructure.database.models.vlr.reconciliation_case_model import (
        ReconciliationCaseModel,
    )
    from src.infrastructure.database.models.audit_log_model import AuditLogModel
    from src.infrastructure.database.repositories.vlr.ledger_entry_repository_impl import (
        LedgerEntryRepositoryImpl,
    )
    from src.infrastructure.database.repositories.vlr.match_result_repository_impl import (
        MatchResultRepositoryImpl,
    )
    from src.infrastructure.database.repositories.vlr.case_repository_impl import (
        CaseRepositoryImpl,
    )
    from src.infrastructure.database.repositories.vlr.exception_repository_impl import (
        ExceptionRepositoryImpl,
    )
    from src.domain.services.vlr.reconciliation_engine_service import (
        ReconciliationEngineService,
    )

    execution_start = datetime.now(timezone.utc)

    # Update task state: initializing
    task.update_state(
        state="PROGRESS",
        meta={
            "phase": "initializing",
            "progress": 0,
            "status": "Initializing reconciliation engine...",
            "case_id": case_id,
        },
    )

    async with async_session_factory() as session:
        try:
            # Load the reconciliation case
            case_stmt = select(ReconciliationCaseModel).where(
                and_(
                    ReconciliationCaseModel.id == case_id,
                    ReconciliationCaseModel.is_deleted == False,  # noqa: E712
                )
            )
            result = await session.execute(case_stmt)
            case_model = result.scalar_one_or_none()

            if case_model is None:
                raise ValueError(
                    f"Reconciliation case {case_id} not found or has been deleted."
                )

            # Transition case status to 'matching'
            case_model.status = "matching"
            case_model.modified_by = triggered_by
            case_model.modified_date = datetime.now(timezone.utc)
            await session.flush()

            # Update task state: loading entries
            task.update_state(
                state="PROGRESS",
                meta={
                    "phase": "loading_entries",
                    "progress": 10,
                    "status": "Loading ledger entries...",
                    "case_id": case_id,
                },
            )

            # Initialize repositories and engine service
            ledger_repo = LedgerEntryRepositoryImpl(session)
            match_repo = MatchResultRepositoryImpl(session)
            case_repo = CaseRepositoryImpl(session)
            exception_repo = ExceptionRepositoryImpl(session)

            engine = ReconciliationEngineService(
                ledger_entry_repository=ledger_repo,
                match_result_repository=match_repo,
                case_repository=case_repo,
                exception_repository=exception_repo,
            )

            # Update task state: executing matching passes
            task.update_state(
                state="PROGRESS",
                meta={
                    "phase": "matching",
                    "progress": 20,
                    "status": "Executing multi-pass matching algorithm...",
                    "case_id": case_id,
                },
            )

            # Execute the reconciliation engine
            reco_result = await engine.execute(
                case_id=UUID(case_id),
                tolerance=Decimal(str(tolerance)),
                fuzzy_threshold=fuzzy_threshold,
            )

            # Update task state: persisting results
            task.update_state(
                state="PROGRESS",
                meta={
                    "phase": "persisting",
                    "progress": 80,
                    "status": "Persisting match results...",
                    "case_id": case_id,
                },
            )

            # Transition case status to 'matched'
            case_model.status = "matched"
            case_model.modified_by = triggered_by
            case_model.modified_date = datetime.now(timezone.utc)

            # Store match statistics on the case
            stats = reco_result.statistics
            case_model.match_statistics = {
                "total_company_entries": stats.total_company_entries,
                "total_vendor_entries": stats.total_vendor_entries,
                "total_matched_company": stats.total_matched_company,
                "total_matched_vendor": stats.total_matched_vendor,
                "pass_statistics": [
                    {
                        "pass_number": ps.pass_number,
                        "match_count": ps.match_count,
                        "matched_amount": float(ps.matched_amount),
                        "percentage": ps.percentage,
                    }
                    for ps in stats.pass_statistics
                ],
            }

            execution_end = datetime.now(timezone.utc)
            duration = (execution_end - execution_start).total_seconds()

            # Record audit log entry
            audit_entry = AuditLogModel(
                id=uuid4(),
                actor_id=None,
                actor_username=triggered_by,
                action="reconciliation_executed",
                resource_type="reconciliation_case",
                resource_id=str(case_id),
                old_value=None,
                new_value=json.dumps({
                    "execution_timestamp": execution_end.isoformat(),
                    "duration_seconds": round(duration, 2),
                    "total_company_entries": stats.total_company_entries,
                    "total_vendor_entries": stats.total_vendor_entries,
                    "total_matched_company": stats.total_matched_company,
                    "total_matched_vendor": stats.total_matched_vendor,
                    "match_pairs_count": len(reco_result.match_pairs),
                    "match_groups_count": len(reco_result.match_groups),
                    "unmatched_company_count": len(reco_result.unmatched_company_ids),
                    "unmatched_vendor_count": len(reco_result.unmatched_vendor_ids),
                    "needs_confirmation": reco_result.needs_confirmation,
                    "idempotency_key": idempotency_key,
                }),
                ip_address="",
                user_agent="celery-worker",
                extra_data=json.dumps({
                    "task_id": task.request.id,
                    "tolerance": tolerance,
                    "fuzzy_threshold": fuzzy_threshold,
                }),
            )
            session.add(audit_entry)

            await session.commit()

            # Update task state: completed
            task.update_state(
                state="PROGRESS",
                meta={
                    "phase": "completed",
                    "progress": 100,
                    "status": "Reconciliation complete.",
                    "case_id": case_id,
                },
            )

            logger.info(
                "Reconciliation completed: case_id=%s, matched_company=%d/%d, "
                "matched_vendor=%d/%d, duration=%.2fs",
                case_id,
                stats.total_matched_company,
                stats.total_company_entries,
                stats.total_matched_vendor,
                stats.total_vendor_entries,
                duration,
            )

            return {
                "case_id": case_id,
                "status": "completed",
                "duration_seconds": round(duration, 2),
                "total_company_entries": stats.total_company_entries,
                "total_vendor_entries": stats.total_vendor_entries,
                "total_matched_company": stats.total_matched_company,
                "total_matched_vendor": stats.total_matched_vendor,
                "match_pairs_count": len(reco_result.match_pairs),
                "match_groups_count": len(reco_result.match_groups),
                "unmatched_company_count": len(reco_result.unmatched_company_ids),
                "unmatched_vendor_count": len(reco_result.unmatched_vendor_ids),
                "needs_confirmation": reco_result.needs_confirmation,
                "idempotency_key": idempotency_key,
            }

        except Exception as exc:
            await session.rollback()

            # Attempt to revert case status on failure
            try:
                async with async_session_factory() as revert_session:
                    revert_stmt = select(ReconciliationCaseModel).where(
                        ReconciliationCaseModel.id == case_id
                    )
                    revert_result = await revert_session.execute(revert_stmt)
                    revert_case = revert_result.scalar_one_or_none()
                    if revert_case and revert_case.status == "matching":
                        revert_case.status = "data_received"
                        revert_case.modified_by = triggered_by
                        revert_case.modified_date = datetime.now(timezone.utc)

                    # Record failure audit log
                    audit_entry = AuditLogModel(
                        id=uuid4(),
                        actor_id=None,
                        actor_username=triggered_by,
                        action="reconciliation_failed",
                        resource_type="reconciliation_case",
                        resource_id=str(case_id),
                        old_value=None,
                        new_value=json.dumps({
                            "status": "failed",
                            "error": str(exc),
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                            "idempotency_key": idempotency_key,
                        }),
                        ip_address="",
                        user_agent="celery-worker",
                        extra_data=json.dumps({
                            "task_id": task.request.id,
                        }),
                    )
                    revert_session.add(audit_entry)
                    await revert_session.commit()
            except Exception as revert_exc:
                logger.error(
                    "Failed to revert case status after reconciliation failure: %s",
                    str(revert_exc),
                )

            logger.error(
                "Reconciliation task failed: case_id=%s, error=%s",
                case_id,
                str(exc),
            )
            raise
