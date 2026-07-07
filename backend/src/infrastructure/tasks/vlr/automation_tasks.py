"""
Automation Rule Celery tasks.

Provides Celery beat schedule for recurring automation rule execution
(scheduled reconciliation, auto-matching, auto-escalation) and
a manual trigger task for on-demand execution of due rules.

Requirements: 19.1, 19.5, 19.7
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from celery import Task
from celery.schedules import crontab

from src.infrastructure.background.celery_app import celery_app

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────
# Celery Beat Schedule
# ──────────────────────────────────────────────────────────────────────

# Register periodic tasks with Celery beat.
# The scheduler checks for due automation rules every 15 minutes.
celery_app.conf.beat_schedule = {
    **getattr(celery_app.conf, "beat_schedule", {}),
    "vlr-automation-execute-due-rules": {
        "task": "vlr.automation.execute_due_rules",
        "schedule": crontab(minute="*/15"),  # Every 15 minutes
        "options": {"queue": "automation"},
    },
    "vlr-automation-auto-match": {
        "task": "vlr.automation.execute_auto_match_rules",
        "schedule": crontab(minute=0, hour="*/1"),  # Every hour
        "options": {"queue": "automation"},
    },
    "vlr-automation-auto-escalation": {
        "task": "vlr.automation.execute_auto_escalation_rules",
        "schedule": crontab(minute=0, hour=6),  # Daily at 06:00 UTC
        "options": {"queue": "automation"},
    },
}


# ──────────────────────────────────────────────────────────────────────
# Custom Task Base
# ──────────────────────────────────────────────────────────────────────


class AutomationTask(Task):
    """Custom base task class with error handling for automation rules."""

    max_retries = 2
    default_retry_delay = 60  # 1 minute between retries

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """Log automation task failure."""
        logger.error(
            "Automation task failed: task_id=%s, error=%s",
            task_id,
            str(exc),
        )

    def on_success(self, retval, task_id, args, kwargs):
        """Log automation task success."""
        logger.info(
            "Automation task completed: task_id=%s, result=%s",
            task_id,
            retval,
        )


# ──────────────────────────────────────────────────────────────────────
# Tasks
# ──────────────────────────────────────────────────────────────────────


@celery_app.task(
    base=AutomationTask,
    bind=True,
    name="vlr.automation.execute_due_rules",
    acks_late=True,
    time_limit=300,  # 5 minute hard limit
    soft_time_limit=240,  # 4 minute soft limit
)
def execute_due_rules_task(self: AutomationTask) -> dict:
    """
    Celery task: Find and execute all automation rules whose
    next_execution time has passed.

    Requirement 19.7: Automated execution of due rules via Celery beat.
    This is the primary scheduler entry point — runs every 15 minutes and
    dispatches all overdue rules (scheduled reconciliation, auto-match,
    auto-escalation).
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        result = loop.run_until_complete(_execute_due_rules())
        return result
    finally:
        loop.close()


@celery_app.task(
    base=AutomationTask,
    bind=True,
    name="vlr.automation.execute_auto_match_rules",
    acks_late=True,
    time_limit=300,
    soft_time_limit=240,
)
def execute_auto_match_rules_task(self: AutomationTask) -> dict:
    """
    Celery task: Execute all active auto-match rules.

    Requirement 19.2: Auto-accept matches meeting confidence thresholds.
    Runs hourly via Celery beat to process unconfirmed matches.
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        result = loop.run_until_complete(_execute_rules_by_type("auto_match"))
        return result
    finally:
        loop.close()


@celery_app.task(
    base=AutomationTask,
    bind=True,
    name="vlr.automation.execute_auto_escalation_rules",
    acks_late=True,
    time_limit=300,
    soft_time_limit=240,
)
def execute_auto_escalation_rules_task(self: AutomationTask) -> dict:
    """
    Celery task: Execute all active auto-escalation rules.

    Requirement 19.3: Escalate cases without progress beyond
    configured threshold. Runs daily at 06:00 UTC.
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        result = loop.run_until_complete(_execute_rules_by_type("auto_escalation"))
        return result
    finally:
        loop.close()


@celery_app.task(
    base=AutomationTask,
    bind=True,
    name="vlr.automation.trigger_due_rules",
    acks_late=True,
    time_limit=300,
    soft_time_limit=240,
)
def trigger_due_rules_task(self: AutomationTask, triggered_by: str = "system") -> dict:
    """
    Celery task: Manually trigger execution of all due rules.

    Used by the API endpoint to allow admin-initiated execution
    outside the regular Celery beat schedule.
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        result = loop.run_until_complete(_execute_due_rules(triggered_by=triggered_by))
        return result
    finally:
        loop.close()


# ──────────────────────────────────────────────────────────────────────
# Async Implementations
# ──────────────────────────────────────────────────────────────────────


async def _execute_due_rules(triggered_by: str = "celery_beat") -> dict:
    """Execute all due automation rules using the AutomationRuleService."""
    from src.infrastructure.database.session import async_session_factory
    from src.infrastructure.database.repositories.vlr.automation_rule_repository_impl import (
        AutomationRuleRepositoryImpl,
    )
    from src.infrastructure.database.repositories.vlr.case_repository_impl import (
        CaseRepositoryImpl,
    )
    from src.infrastructure.database.repositories.vlr.match_result_repository_impl import (
        MatchResultRepositoryImpl,
    )
    from src.infrastructure.database.repositories.vlr.setting_repository_impl import (
        SettingRepositoryImpl,
    )
    from src.domain.services.vlr.automation_rule_service import AutomationRuleService

    execution_start = datetime.now(timezone.utc)

    async with async_session_factory() as session:
        try:
            rule_repo = AutomationRuleRepositoryImpl(session)
            case_repo = CaseRepositoryImpl(session)
            match_repo = MatchResultRepositoryImpl(session)
            setting_repo = SettingRepositoryImpl(session)

            service = AutomationRuleService(
                automation_rule_repository=rule_repo,
                case_repository=case_repo,
                match_result_repository=match_repo,
                setting_repository=setting_repo,
            )

            execution_records = await service.execute_due_rules()

            await session.commit()

            execution_end = datetime.now(timezone.utc)
            duration = (execution_end - execution_start).total_seconds()

            result = {
                "status": "completed",
                "triggered_by": triggered_by,
                "rules_executed": len(execution_records),
                "duration_seconds": round(duration, 2),
                "executions": [
                    {
                        "rule_id": str(record.rule_id),
                        "outcome": record.outcome,
                        "cases_affected": record.cases_affected,
                        "matches_auto_accepted": record.matches_auto_accepted,
                        "escalations_triggered": record.escalations_triggered,
                    }
                    for record in execution_records
                ],
            }

            logger.info(
                "Due rules execution completed: rules_executed=%d, duration=%.2fs, triggered_by=%s",
                len(execution_records),
                duration,
                triggered_by,
            )

            return result

        except Exception as exc:
            await session.rollback()
            logger.error("Due rules execution failed: error=%s", str(exc))
            raise


async def _execute_rules_by_type(rule_type: str) -> dict:
    """Execute all active rules of a specific type."""
    from src.infrastructure.database.session import async_session_factory
    from src.infrastructure.database.repositories.vlr.automation_rule_repository_impl import (
        AutomationRuleRepositoryImpl,
    )
    from src.infrastructure.database.repositories.vlr.case_repository_impl import (
        CaseRepositoryImpl,
    )
    from src.infrastructure.database.repositories.vlr.match_result_repository_impl import (
        MatchResultRepositoryImpl,
    )
    from src.infrastructure.database.repositories.vlr.setting_repository_impl import (
        SettingRepositoryImpl,
    )
    from src.domain.services.vlr.automation_rule_service import (
        AutomationRuleService,
        ExecutionOutcome,
        RuleType,
    )

    execution_start = datetime.now(timezone.utc)

    async with async_session_factory() as session:
        try:
            rule_repo = AutomationRuleRepositoryImpl(session)
            case_repo = CaseRepositoryImpl(session)
            match_repo = MatchResultRepositoryImpl(session)
            setting_repo = SettingRepositoryImpl(session)

            service = AutomationRuleService(
                automation_rule_repository=rule_repo,
                case_repository=case_repo,
                match_result_repository=match_repo,
                setting_repository=setting_repo,
            )

            # Get all active rules — filter by type
            now = datetime.now(timezone.utc)
            due_rules = await rule_repo.get_due_rules(before=now)
            typed_rules = [
                r for r in due_rules
                if getattr(r, "rule_type", "") == rule_type
            ]

            total_executed = 0
            results = []

            for rule in typed_rules:
                rule_id = getattr(rule, "id", None)
                if rule_id is None:
                    continue

                trigger_time = now
                try:
                    if rule_type == RuleType.AUTO_MATCH.value:
                        exec_result = await service.execute_auto_match(rule)
                        outcome = ExecutionOutcome.SUCCESS
                        if exec_result.errors:
                            outcome = ExecutionOutcome.PARTIAL
                        await service.record_execution(
                            rule_id=rule_id,
                            trigger_time=trigger_time,
                            outcome=outcome,
                            details="; ".join(exec_result.errors) if exec_result.errors else None,
                            matches_auto_accepted=exec_result.matches_accepted,
                            cases_affected=exec_result.cases_processed,
                        )
                        results.append({
                            "rule_id": str(rule_id),
                            "outcome": outcome.value,
                            "matches_accepted": exec_result.matches_accepted,
                        })

                    elif rule_type == RuleType.AUTO_ESCALATION.value:
                        exec_result = await service.execute_auto_escalation(rule)
                        outcome = ExecutionOutcome.SUCCESS
                        if exec_result.errors:
                            outcome = ExecutionOutcome.PARTIAL
                        await service.record_execution(
                            rule_id=rule_id,
                            trigger_time=trigger_time,
                            outcome=outcome,
                            details="; ".join(exec_result.errors) if exec_result.errors else None,
                            escalations_triggered=exec_result.cases_escalated,
                            cases_affected=exec_result.cases_checked,
                        )
                        results.append({
                            "rule_id": str(rule_id),
                            "outcome": outcome.value,
                            "cases_escalated": exec_result.cases_escalated,
                        })

                    total_executed += 1

                except Exception as exc:
                    logger.error(
                        "Failed to execute %s rule %s: %s",
                        rule_type, rule_id, str(exc),
                    )
                    await service.record_execution(
                        rule_id=rule_id,
                        trigger_time=trigger_time,
                        outcome=ExecutionOutcome.FAILURE,
                        details=str(exc),
                    )

            await session.commit()

            execution_end = datetime.now(timezone.utc)
            duration = (execution_end - execution_start).total_seconds()

            return {
                "status": "completed",
                "rule_type": rule_type,
                "rules_executed": total_executed,
                "duration_seconds": round(duration, 2),
                "results": results,
            }

        except Exception as exc:
            await session.rollback()
            logger.error(
                "Rules by type execution failed: rule_type=%s, error=%s",
                rule_type, str(exc),
            )
            raise
