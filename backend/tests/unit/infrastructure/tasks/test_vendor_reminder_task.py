"""
Unit tests for the check_vendor_reminders_periodic Celery task.

Tests the periodic vendor reminder checking logic that:
- Queries cases in vendor_engagement step
- Determines appropriate action (send_reminder, escalate, none)
- Dispatches D3/D7/D10 reminders based on elapsed time
- Triggers escalation when max reminders exhausted

Requirements: 15.1, 15.2, 15.3, 15.4
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest


class TestCheckVendorRemindersPeriodicTask:
    """Tests for the check_vendor_reminders_periodic task logic."""

    def test_task_is_registered_with_celery(self):
        """Verify the task is registered with the correct name."""
        from src.infrastructure.tasks.vlr.notification_tasks import (
            check_vendor_reminders_periodic,
        )

        assert check_vendor_reminders_periodic.name == "vlr.check_vendor_reminders"

    def test_task_has_correct_max_retries(self):
        """Verify the task has max_retries=1 (periodic, runs again on schedule)."""
        from src.infrastructure.tasks.vlr.notification_tasks import (
            VendorReminderCheckTask,
        )

        task = VendorReminderCheckTask()
        assert task.max_retries == 1

    def test_task_is_in_beat_schedule(self):
        """Verify the task is scheduled in Celery Beat."""
        from src.infrastructure.background.celery_app import celery_app

        beat_schedule = celery_app.conf.beat_schedule
        assert "vlr-check-vendor-reminders" in beat_schedule
        entry = beat_schedule["vlr-check-vendor-reminders"]
        assert entry["task"] == "vlr.check_vendor_reminders"

    def test_task_is_exported_from_init(self):
        """Verify the task is exported from the __init__.py."""
        from src.infrastructure.tasks.vlr import check_vendor_reminders_periodic

        assert check_vendor_reminders_periodic is not None
        assert callable(check_vendor_reminders_periodic)


class TestDetermineReminderActionIntegration:
    """
    Tests that the determine_reminder_action logic works correctly
    for D3/D7/D10 scheduling used by the periodic task.
    """

    def _create_email_service(self):
        """Create an EmailNotificationService with mocked dependencies."""
        from src.domain.services.vlr.notification_service import (
            EmailNotificationService,
        )

        return EmailNotificationService(
            notification_repository=MagicMock(),
            case_repository=MagicMock(),
            setting_repository=MagicMock(),
            email_sender=None,
        )

    def test_d3_reminder_triggered_after_3_days(self):
        """D3 reminder should trigger when 3+ days have elapsed with 0 reminders sent."""
        service = self._create_email_service()
        invite_date = datetime.now(timezone.utc) - timedelta(days=4)

        action = service.determine_reminder_action(
            reminders_sent=0,
            invite_date=invite_date,
        )

        assert action["action"] == "send_reminder"
        assert action["reminder_number"] == 1
        assert action["interval_days"] == 3

    def test_d7_reminder_triggered_after_7_days(self):
        """D7 reminder should trigger when 7+ days have elapsed with 1 reminder sent."""
        service = self._create_email_service()
        invite_date = datetime.now(timezone.utc) - timedelta(days=8)

        action = service.determine_reminder_action(
            reminders_sent=1,
            invite_date=invite_date,
        )

        assert action["action"] == "send_reminder"
        assert action["reminder_number"] == 2
        assert action["interval_days"] == 7

    def test_d10_reminder_triggered_after_10_days(self):
        """D10 reminder should trigger when 10+ days have elapsed with 2 reminders sent."""
        service = self._create_email_service()
        invite_date = datetime.now(timezone.utc) - timedelta(days=11)

        action = service.determine_reminder_action(
            reminders_sent=2,
            invite_date=invite_date,
        )

        assert action["action"] == "send_reminder"
        assert action["reminder_number"] == 3
        assert action["interval_days"] == 10

    def test_escalation_after_all_reminders_exhausted(self):
        """Escalation should trigger when all 3 reminders have been sent."""
        service = self._create_email_service()
        invite_date = datetime.now(timezone.utc) - timedelta(days=15)

        action = service.determine_reminder_action(
            reminders_sent=3,
            invite_date=invite_date,
        )

        assert action["action"] == "escalate"

    def test_no_action_before_d3(self):
        """No action should be taken before 3 days have elapsed."""
        service = self._create_email_service()
        invite_date = datetime.now(timezone.utc) - timedelta(days=1)

        action = service.determine_reminder_action(
            reminders_sent=0,
            invite_date=invite_date,
        )

        assert action["action"] == "none"

    def test_no_action_between_d3_and_d7_with_1_reminder(self):
        """No action between D3 and D7 if D3 reminder already sent."""
        service = self._create_email_service()
        invite_date = datetime.now(timezone.utc) - timedelta(days=5)

        action = service.determine_reminder_action(
            reminders_sent=1,
            invite_date=invite_date,
        )

        assert action["action"] == "none"

    def test_no_action_between_d7_and_d10_with_2_reminders(self):
        """No action between D7 and D10 if D7 reminder already sent."""
        service = self._create_email_service()
        invite_date = datetime.now(timezone.utc) - timedelta(days=8)

        action = service.determine_reminder_action(
            reminders_sent=2,
            invite_date=invite_date,
        )

        assert action["action"] == "none"
