"""
Unit tests for WorkflowOrchestratorService.

Tests valid transitions, invalid transitions, rollback, and SLA violations.

Requirements: 12.1, 12.2, 12.3, 12.4, 13.1, 13.2
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from src.domain.services.vlr.workflow_orchestrator_service import (
    CaseNotFoundError,
    CaseStatus,
    SLAConfiguration,
    SLAViolation,
    STEP_ORDER,
    VALID_TRANSITIONS,
    WorkflowOrchestratorService,
    WorkflowRollbackError,
    WorkflowStep,
    WorkflowTransitionError,
)


# ──────────────────────────────────────────────────────────────────────────────
# Test Helpers
# ──────────────────────────────────────────────────────────────────────────────


@dataclass
class MockCase:
    """Simulates a reconciliation case object."""

    id: UUID
    current_workflow_step: str | None = None
    step_entered_at: datetime | None = None
    sla_deadline: datetime | None = None
    is_overdue: bool = False


# ──────────────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def case_id() -> UUID:
    return uuid4()


@pytest.fixture
def mock_case_repo():
    repo = MagicMock()
    repo.get_by_id = AsyncMock()
    repo.update = AsyncMock()
    return repo


@pytest.fixture
def mock_history_repo():
    repo = MagicMock()
    repo.record_transition = AsyncMock()
    repo.get_history = AsyncMock(return_value=[])
    return repo


@pytest.fixture
def mock_notification_service():
    service = MagicMock()
    service.send_escalation = AsyncMock()
    return service


@pytest.fixture
def sla_config() -> SLAConfiguration:
    return SLAConfiguration(
        step_sla_hours={
            "initiation": 4,
            "sap_pull": 8,
            "transformation": 4,
            "finance_review": 24,
            "column_mapping": 8,
            "vendor_engagement": 72,
            "auto_reconciliation": 4,
            "exception_resolution": 48,
            "finance_approval": 24,
            "vendor_sign_off": 72,
        },
        escalation_emails={
            "finance_review": "manager@example.com",
            "vendor_engagement": "manager@example.com",
            "finance_approval": "manager@example.com",
        },
    )


@pytest.fixture
def service(mock_case_repo, sla_config, mock_notification_service, mock_history_repo):
    return WorkflowOrchestratorService(
        case_repository=mock_case_repo,
        sla_config=sla_config,
        notification_service=mock_notification_service,
        history_repository=mock_history_repo,
    )


# ──────────────────────────────────────────────────────────────────────────────
# Tests: WorkflowStep Enum
# ──────────────────────────────────────────────────────────────────────────────


class TestWorkflowStepEnum:
    """Tests for the WorkflowStep enum definition."""

    def test_has_all_11_steps(self):
        """WorkflowStep enum should have exactly 11 members."""
        assert len(WorkflowStep) == 11

    def test_step_values(self):
        """WorkflowStep values should be lowercase snake_case strings."""
        expected = [
            "initiation",
            "sap_pull",
            "transformation",
            "finance_review",
            "column_mapping",
            "vendor_engagement",
            "auto_reconciliation",
            "exception_resolution",
            "finance_approval",
            "vendor_sign_off",
            "closure",
        ]
        assert [s.value for s in WorkflowStep] == expected

    def test_step_is_string_enum(self):
        """WorkflowStep should be a string enum (usable as string)."""
        assert WorkflowStep.INITIATION == "initiation"
        assert isinstance(WorkflowStep.CLOSURE, str)


# ──────────────────────────────────────────────────────────────────────────────
# Tests: VALID_TRANSITIONS
# ──────────────────────────────────────────────────────────────────────────────


class TestValidTransitions:
    """Tests for the VALID_TRANSITIONS configuration."""

    def test_all_steps_have_transitions_defined(self):
        """Every step in the enum should have a transition entry."""
        for step in WorkflowStep:
            assert step in VALID_TRANSITIONS

    def test_closure_has_no_transitions(self):
        """Closure is a terminal state with no valid transitions."""
        assert VALID_TRANSITIONS[WorkflowStep.CLOSURE] == []

    def test_initiation_only_advances_to_sap_pull(self):
        """Initiation can only advance to SAP Pull."""
        assert VALID_TRANSITIONS[WorkflowStep.INITIATION] == [WorkflowStep.SAP_PULL]

    def test_each_non_terminal_step_has_forward_transition(self):
        """Each non-terminal step should have at least one forward transition."""
        for step in WorkflowStep:
            if step != WorkflowStep.CLOSURE:
                assert len(VALID_TRANSITIONS[step]) >= 1

    def test_intermediate_steps_have_rollback_target(self):
        """Steps after INITIATION (except CLOSURE) should have a rollback target."""
        for step in WorkflowStep:
            if step not in (WorkflowStep.INITIATION, WorkflowStep.CLOSURE):
                # Should have at least 2 targets: forward + rollback
                assert len(VALID_TRANSITIONS[step]) >= 2


# ──────────────────────────────────────────────────────────────────────────────
# Tests: advance()
# ──────────────────────────────────────────────────────────────────────────────


class TestAdvance:
    """Tests for the advance() method."""

    async def test_advance_from_initiation_to_sap_pull(
        self, service, mock_case_repo, mock_history_repo, case_id
    ):
        """Should advance from INITIATION to SAP_PULL successfully."""
        mock_case_repo.get_by_id.return_value = MockCase(
            id=case_id, current_workflow_step="initiation"
        )

        result = await service.advance(case_id, WorkflowStep.SAP_PULL, "user@test.com")

        assert result.case_id == case_id
        assert result.current_step == WorkflowStep.SAP_PULL
        assert result.is_overdue is False
        assert result.sla_deadline is not None

        mock_case_repo.update.assert_called_once()
        mock_history_repo.record_transition.assert_called_once()

    async def test_advance_full_happy_path(self, service, mock_case_repo, case_id):
        """Should advance through each step in the workflow sequence."""
        # Walk through all forward transitions
        for i in range(len(STEP_ORDER) - 1):
            current = STEP_ORDER[i]
            next_step = STEP_ORDER[i + 1]

            mock_case_repo.get_by_id.return_value = MockCase(
                id=case_id, current_workflow_step=current.value
            )

            result = await service.advance(case_id, next_step)
            assert result.current_step == next_step

    async def test_advance_invalid_transition_raises_error(
        self, service, mock_case_repo, case_id
    ):
        """Should raise WorkflowTransitionError for invalid transitions."""
        mock_case_repo.get_by_id.return_value = MockCase(
            id=case_id, current_workflow_step="initiation"
        )

        with pytest.raises(WorkflowTransitionError) as exc_info:
            await service.advance(case_id, WorkflowStep.CLOSURE)

        assert exc_info.value.current_step == WorkflowStep.INITIATION
        assert exc_info.value.target_step == WorkflowStep.CLOSURE

    async def test_advance_from_closure_raises_error(
        self, service, mock_case_repo, case_id
    ):
        """Should raise WorkflowTransitionError when trying to advance from CLOSURE."""
        mock_case_repo.get_by_id.return_value = MockCase(
            id=case_id, current_workflow_step="closure"
        )

        with pytest.raises(WorkflowTransitionError):
            await service.advance(case_id, WorkflowStep.INITIATION)

    async def test_advance_case_not_found(self, service, mock_case_repo, case_id):
        """Should raise CaseNotFoundError if case doesn't exist."""
        mock_case_repo.get_by_id.return_value = None

        with pytest.raises(CaseNotFoundError):
            await service.advance(case_id, WorkflowStep.SAP_PULL)

    async def test_advance_calculates_sla_deadline(
        self, service, mock_case_repo, case_id
    ):
        """Should set sla_deadline based on SLA config for the target step."""
        mock_case_repo.get_by_id.return_value = MockCase(
            id=case_id, current_workflow_step="initiation"
        )

        result = await service.advance(case_id, WorkflowStep.SAP_PULL)

        # sap_pull has 8 hours SLA configured
        assert result.sla_deadline is not None
        expected_min = datetime.now(timezone.utc) + timedelta(hours=7, minutes=59)
        expected_max = datetime.now(timezone.utc) + timedelta(hours=8, minutes=1)
        assert expected_min <= result.sla_deadline <= expected_max

    async def test_advance_records_history(
        self, service, mock_case_repo, mock_history_repo, case_id
    ):
        """Should record the transition in workflow step history."""
        mock_case_repo.get_by_id.return_value = MockCase(
            id=case_id, current_workflow_step="initiation"
        )

        await service.advance(case_id, WorkflowStep.SAP_PULL, "user@test.com")

        mock_history_repo.record_transition.assert_called_once()
        call_kwargs = mock_history_repo.record_transition.call_args[1]
        assert call_kwargs["case_id"] == case_id
        assert call_kwargs["from_step"] == "initiation"
        assert call_kwargs["to_step"] == "sap_pull"
        assert call_kwargs["triggered_by"] == "user@test.com"
        assert call_kwargs["is_rollback"] is False

    async def test_advance_with_none_workflow_step_defaults_to_initiation(
        self, service, mock_case_repo, case_id
    ):
        """Should treat a case with no workflow step as INITIATION."""
        mock_case_repo.get_by_id.return_value = MockCase(
            id=case_id, current_workflow_step=None
        )

        result = await service.advance(case_id, WorkflowStep.SAP_PULL)
        assert result.current_step == WorkflowStep.SAP_PULL


# ──────────────────────────────────────────────────────────────────────────────
# Tests: rollback()
# ──────────────────────────────────────────────────────────────────────────────


class TestRollback:
    """Tests for the rollback() method."""

    async def test_rollback_from_sap_pull_to_initiation(
        self, service, mock_case_repo, mock_history_repo, case_id
    ):
        """Should rollback from SAP_PULL to INITIATION."""
        mock_case_repo.get_by_id.return_value = MockCase(
            id=case_id, current_workflow_step="sap_pull"
        )

        result = await service.rollback(case_id, WorkflowStep.INITIATION, "admin@test.com")

        assert result.case_id == case_id
        assert result.current_step == WorkflowStep.INITIATION
        assert result.is_overdue is False

        mock_history_repo.record_transition.assert_called_once()
        call_kwargs = mock_history_repo.record_transition.call_args[1]
        assert call_kwargs["is_rollback"] is True

    async def test_rollback_from_transformation_to_sap_pull(
        self, service, mock_case_repo, case_id
    ):
        """Should rollback from TRANSFORMATION to SAP_PULL."""
        mock_case_repo.get_by_id.return_value = MockCase(
            id=case_id, current_workflow_step="transformation"
        )

        result = await service.rollback(case_id, WorkflowStep.SAP_PULL)
        assert result.current_step == WorkflowStep.SAP_PULL

    async def test_rollback_from_initiation_raises_error(
        self, service, mock_case_repo, case_id
    ):
        """Should raise WorkflowRollbackError when rolling back from INITIATION."""
        mock_case_repo.get_by_id.return_value = MockCase(
            id=case_id, current_workflow_step="initiation"
        )

        with pytest.raises(WorkflowRollbackError) as exc_info:
            await service.rollback(case_id, WorkflowStep.INITIATION)

        assert "Cannot rollback from the initial step" in str(exc_info.value)

    async def test_rollback_from_closure_raises_error(
        self, service, mock_case_repo, case_id
    ):
        """Should raise WorkflowRollbackError when rolling back from CLOSURE."""
        mock_case_repo.get_by_id.return_value = MockCase(
            id=case_id, current_workflow_step="closure"
        )

        with pytest.raises(WorkflowRollbackError) as exc_info:
            await service.rollback(case_id, WorkflowStep.VENDOR_SIGN_OFF)

        assert "Cannot rollback from a closed case" in str(exc_info.value)

    async def test_rollback_to_forward_step_raises_error(
        self, service, mock_case_repo, case_id
    ):
        """Should raise WorkflowRollbackError when target is not a previous step."""
        mock_case_repo.get_by_id.return_value = MockCase(
            id=case_id, current_workflow_step="sap_pull"
        )

        with pytest.raises(WorkflowRollbackError) as exc_info:
            await service.rollback(case_id, WorkflowStep.TRANSFORMATION)

        assert "previous step" in str(exc_info.value)

    async def test_rollback_to_non_adjacent_step_raises_error(
        self, service, mock_case_repo, case_id
    ):
        """Should raise WorkflowRollbackError when target is not in valid transitions."""
        mock_case_repo.get_by_id.return_value = MockCase(
            id=case_id, current_workflow_step="finance_review"
        )

        # finance_review can only rollback to transformation (not initiation)
        with pytest.raises(WorkflowRollbackError) as exc_info:
            await service.rollback(case_id, WorkflowStep.INITIATION)

        assert "not a valid rollback target" in str(exc_info.value)

    async def test_rollback_case_not_found(self, service, mock_case_repo, case_id):
        """Should raise CaseNotFoundError if case doesn't exist."""
        mock_case_repo.get_by_id.return_value = None

        with pytest.raises(CaseNotFoundError):
            await service.rollback(case_id, WorkflowStep.INITIATION)

    async def test_rollback_resets_overdue_flag(
        self, service, mock_case_repo, case_id
    ):
        """Should reset is_overdue to False after rollback."""
        mock_case_repo.get_by_id.return_value = MockCase(
            id=case_id, current_workflow_step="transformation", is_overdue=True
        )

        result = await service.rollback(case_id, WorkflowStep.SAP_PULL)
        assert result.is_overdue is False

        update_data = mock_case_repo.update.call_args[0][1]
        assert update_data["is_overdue"] is False


# ──────────────────────────────────────────────────────────────────────────────
# Tests: check_sla_violations()
# ──────────────────────────────────────────────────────────────────────────────


class TestCheckSLAViolations:
    """Tests for the check_sla_violations() method."""

    async def test_detects_overdue_case(
        self, service, mock_case_repo, mock_notification_service
    ):
        """Should detect a case that has exceeded its SLA deadline."""
        case_id = uuid4()
        overdue_deadline = datetime.now(timezone.utc) - timedelta(hours=2)

        overdue_case = MockCase(
            id=case_id,
            current_workflow_step="finance_review",
            step_entered_at=datetime.now(timezone.utc) - timedelta(hours=26),
            sla_deadline=overdue_deadline,
            is_overdue=False,
        )

        violations = await service.check_sla_violations(overdue_cases=[overdue_case])

        assert len(violations) == 1
        assert violations[0].case_id == case_id
        assert violations[0].current_step == WorkflowStep.FINANCE_REVIEW
        assert violations[0].hours_overdue > 0

        # Should update case as overdue
        mock_case_repo.update.assert_called_once_with(case_id, {"is_overdue": True})

    async def test_sends_escalation_notification(
        self, service, mock_case_repo, mock_notification_service
    ):
        """Should send escalation email when SLA is violated for step with escalation config."""
        case_id = uuid4()
        overdue_deadline = datetime.now(timezone.utc) - timedelta(hours=1)

        overdue_case = MockCase(
            id=case_id,
            current_workflow_step="finance_review",
            step_entered_at=datetime.now(timezone.utc) - timedelta(hours=25),
            sla_deadline=overdue_deadline,
            is_overdue=False,
        )

        await service.check_sla_violations(overdue_cases=[overdue_case])

        mock_notification_service.send_escalation.assert_called_once_with(
            case_id=case_id,
            manager_email="manager@example.com",
        )

    async def test_no_escalation_when_no_email_configured(
        self, service, mock_case_repo, mock_notification_service
    ):
        """Should not send escalation when no email is configured for the step."""
        case_id = uuid4()
        overdue_deadline = datetime.now(timezone.utc) - timedelta(hours=1)

        # sap_pull has no escalation_email configured
        overdue_case = MockCase(
            id=case_id,
            current_workflow_step="sap_pull",
            step_entered_at=datetime.now(timezone.utc) - timedelta(hours=9),
            sla_deadline=overdue_deadline,
            is_overdue=False,
        )

        await service.check_sla_violations(overdue_cases=[overdue_case])

        mock_notification_service.send_escalation.assert_not_called()

    async def test_returns_empty_list_when_no_overdue_cases(self, service):
        """Should return empty list when no overdue cases are provided."""
        violations = await service.check_sla_violations(overdue_cases=[])
        assert violations == []

    async def test_returns_empty_list_when_none_provided(self, service):
        """Should return empty list when overdue_cases is None."""
        violations = await service.check_sla_violations(overdue_cases=None)
        assert violations == []

    async def test_handles_multiple_overdue_cases(
        self, service, mock_case_repo, mock_notification_service
    ):
        """Should handle multiple overdue cases in a single check."""
        cases = []
        for i in range(3):
            case_id = uuid4()
            cases.append(
                MockCase(
                    id=case_id,
                    current_workflow_step="vendor_engagement",
                    step_entered_at=datetime.now(timezone.utc) - timedelta(hours=80),
                    sla_deadline=datetime.now(timezone.utc) - timedelta(hours=8),
                    is_overdue=False,
                )
            )

        violations = await service.check_sla_violations(overdue_cases=cases)

        assert len(violations) == 3
        assert mock_case_repo.update.call_count == 3

    async def test_skips_case_with_no_workflow_step(self, service, mock_case_repo):
        """Should skip cases without a workflow step."""
        case = MockCase(
            id=uuid4(),
            current_workflow_step=None,
            sla_deadline=datetime.now(timezone.utc) - timedelta(hours=1),
        )

        violations = await service.check_sla_violations(overdue_cases=[case])
        assert violations == []

    async def test_skips_case_with_no_sla_deadline(self, service, mock_case_repo):
        """Should skip cases without an SLA deadline."""
        case = MockCase(
            id=uuid4(),
            current_workflow_step="finance_review",
            sla_deadline=None,
        )

        violations = await service.check_sla_violations(overdue_cases=[case])
        assert violations == []


# ──────────────────────────────────────────────────────────────────────────────
# Tests: get_status()
# ──────────────────────────────────────────────────────────────────────────────


class TestGetStatus:
    """Tests for the get_status() method."""

    async def test_returns_current_status(self, service, mock_case_repo, case_id):
        """Should return the current workflow status of a case."""
        now = datetime.now(timezone.utc)
        mock_case_repo.get_by_id.return_value = MockCase(
            id=case_id,
            current_workflow_step="finance_review",
            step_entered_at=now,
            sla_deadline=now + timedelta(hours=24),
            is_overdue=False,
        )

        result = await service.get_status(case_id)

        assert result.case_id == case_id
        assert result.current_step == WorkflowStep.FINANCE_REVIEW
        assert result.step_entered_at == now
        assert result.is_overdue is False

    async def test_case_not_found_raises_error(self, service, mock_case_repo, case_id):
        """Should raise CaseNotFoundError if case doesn't exist."""
        mock_case_repo.get_by_id.return_value = None

        with pytest.raises(CaseNotFoundError):
            await service.get_status(case_id)


# ──────────────────────────────────────────────────────────────────────────────
# Tests: SLAConfiguration
# ──────────────────────────────────────────────────────────────────────────────


class TestSLAConfiguration:
    """Tests for SLAConfiguration dataclass."""

    def test_get_sla_hours_configured_step(self, sla_config):
        """Should return configured SLA hours for a step."""
        assert sla_config.get_sla_hours(WorkflowStep.FINANCE_REVIEW) == 24
        assert sla_config.get_sla_hours(WorkflowStep.SAP_PULL) == 8

    def test_get_sla_hours_unconfigured_step(self, sla_config):
        """Should return None for steps without SLA configuration."""
        assert sla_config.get_sla_hours(WorkflowStep.CLOSURE) is None

    def test_get_escalation_email(self, sla_config):
        """Should return escalation email for configured steps."""
        assert sla_config.get_escalation_email(WorkflowStep.FINANCE_REVIEW) == "manager@example.com"

    def test_get_escalation_email_unconfigured(self, sla_config):
        """Should return None for steps without escalation email."""
        assert sla_config.get_escalation_email(WorkflowStep.SAP_PULL) is None
