"""
Recovery follow-up Celery tasks.

Provides a periodic task that checks for overdue recovery items and
auto-triggers follow-up reminders based on configurable schedule.

Each follow-up action is logged with a timestamp in the recovery
follow-up log for audit trail purposes.

Requirements: 31.1, 31.2
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from celery import Task
from celery.schedules import crontab

from src.infrastructure.background.celery_app import celery_app

logger = logging.getLogger(__name__)

# Default interval for recovery follow-up check (every 6 hours)
DEFAULT_RECOVERY_CHECK_INTERVAL_HOURS: int = 6


# ──────────────────────────────────────────────────────────────────────
# Celery Beat Schedule - Recovery Follow-Up Checking
# ──────────────────────────────────────────────────────────────────────

# Register recovery follow-up check as a periodic task (every 6 hours)
celery_app.conf.beat_schedule = {
    **getattr(celery_app.conf, "beat_schedule", {}),
    "vlr-check-recovery-follow-ups": {
        "task": "vlr.check_recovery_follow_ups",
        "schedule": crontab(minute=0, hour=f"*/{DEFAULT_RECOVERY_CHECK_INTERVAL_HOURS}"),
        "options": {"queue": "recovery"},
    },
}


# ──────────────────────────────────────────────────────────────────────
# Task Base Class
# ──────────────────────────────────────────────────────────────────────


class RecoveryFollowUpCheckTask(Task):
    """Custom base task class for periodic recovery follow-up checking."""

    name = "vlr.check_recovery_follow_ups"
    max_retries = 1
    default_retry_delay = 300  # 5 minutes

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """Log task failure."""
        logger.error(
            "Recovery follow-up check task failed: task_id=%s, error=%s",
            task_id,
            str(exc),
        )

    def on_success(self, retval, task_id, args, kwargs):
        """Log task success."""
        logger.info(
            "Recovery follow-up check task completed: task_id=%s, "
            "reminders_triggered=%s",
            task_id,
            retval.get("reminders_triggered", 0) if retval else 0,
        )


# ──────────────────────────────────────────────────────────────────────
# Periodic Task: Check Recovery Follow-Ups
# ──────────────────────────────────────────────────────────────────────


@celery_app.task(
    base=RecoveryFollowUpCheckTask,
    bind=True,
    name="vlr.check_recovery_follow_ups",
    acks_late=True,
    time_limit=300,  # Hard limit: 5 minutes
    soft_time_limit=240,  # Soft limit: 4 minutes
)
def check_recovery_follow_ups_periodic(self: RecoveryFollowUpCheckTask) -> dict:
    """
    Periodic task that checks for overdue recovery items and auto-triggers
    follow-up reminders.

    Runs every 6 hours via Celery Beat. For each overdue recovery item:
    1. Records a follow-up action in the log with timestamp
    2. Advances the next_follow_up_date by the item's configured interval
    3. Transitions status from 'open' to 'in_progress' if still open

    Uses max_retries=1 since this task runs periodically and will
    execute again on the next schedule.

    Requirements: 31.1, 31.2

    Returns:
        Dict with follow-up check results including count of
        reminders triggered and items processed.
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        result = loop.run_until_complete(
            _execute_check_recovery_follow_ups(task=self)
        )
        return result
    except Exception as exc:
        raise self.retry(exc=exc, countdown=self.default_retry_delay)
    finally:
        loop.close()


async def _execute_check_recovery_follow_ups(task: RecoveryFollowUpCheckTask) -> dict:
    """
    Execute recovery follow-up check via the RecoveryService.

    Connects to the database, initializes the service, and delegates
    to trigger_follow_up_reminders() which handles:
    - Identifying overdue items (next_follow_up_date <= today, status in open/in_progress)
    - Logging each follow-up action with timestamp
    - Advancing next_follow_up_date by the configured interval
    - Transitioning open items to in_progress
    """
    from src.infrastructure.database.session import async_session_factory
    from src.infrastructure.database.repositories.vlr.recovery_repository_impl import (
        RecoveryRepositoryImpl,
    )
    from src.domain.services.vlr.recovery_service import RecoveryService

    check_start = datetime.now(timezone.utc)

    task.update_state(
        state="PROGRESS",
        meta={
            "phase": "checking_recovery_follow_ups",
            "status": "Checking for overdue recovery items...",
            "started_at": check_start.isoformat(),
        },
    )

    async with async_session_factory() as session:
        try:
            recovery_repo = RecoveryRepositoryImpl(session)
            service = RecoveryService(recovery_repository=recovery_repo)

            # Trigger follow-up reminders for all overdue items
            reminders_triggered = await service.trigger_follow_up_reminders(
                action_by="system:periodic_task"
            )

            await session.commit()

            check_end = datetime.now(timezone.utc)
            duration = (check_end - check_start).total_seconds()

            logger.info(
                "Recovery follow-up check complete: "
                "reminders_triggered=%d, duration=%.2fs",
                reminders_triggered,
                duration,
            )

            return {
                "status": "completed",
                "reminders_triggered": reminders_triggered,
                "checked_at": check_start.isoformat(),
                "duration_seconds": round(duration, 2),
            }

        except Exception as exc:
            await session.rollback()
            logger.error(
                "Recovery follow-up check failed: error=%s",
                str(exc),
            )
            raise
