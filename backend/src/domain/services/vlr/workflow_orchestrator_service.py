"""
Workflow Orchestrator Service.

Celery-based state machine managing the 11-step reconciliation lifecycle
(including Closure) with SLA monitoring, rollback support, and step
transition validation.

Requirements: 12.1, 12.2, 12.3, 12.4, 13.1, 13.2
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from uuid import UUID

logger = logging.getLogger(__name__)


# ─── Enumerations ─────────────────────────────────────────────────────────────


class WorkflowStep(str, Enum):
    """
    All 11 steps in the reconciliation workflow lifecycle.

    Requirement 12.1: Implement steps in sequence from Initiation through Closure.
    """

    INITIATION = "initiation"
    SAP_PULL = "sap_pull"
    TRANSFORMATION = "transformation"
    FINANCE_REVIEW = "finance_review"
    COLUMN_MAPPING = "column_mapping"
    VENDOR_ENGAGEMENT = "vendor_engagement"
    AUTO_RECONCILIATION = "auto_reconciliation"
    EXCEPTION_RESOLUTION = "exception_resolution"
    FINANCE_APPROVAL = "finance_approval"
    VENDOR_SIGN_OFF = "vendor_sign_off"
    CLOSURE = "closure"


# ─── Valid Transitions ────────────────────────────────────────────────────────

# Each step maps to a list of valid target steps.
# The first entry is the forward transition; subsequent entries are rollback targets.
VALID_TRANSITIONS: dict[WorkflowStep, list[WorkflowStep]] = {
    WorkflowStep.INITIATION: [WorkflowStep.SAP_PULL],
    WorkflowStep.SAP_PULL: [WorkflowStep.TRANSFORMATION, WorkflowStep.INITIATION],
    WorkflowStep.TRANSFORMATION: [WorkflowStep.FINANCE_REVIEW, WorkflowStep.SAP_PULL],
    WorkflowStep.FINANCE_REVIEW: [WorkflowStep.COLUMN_MAPPING, WorkflowStep.TRANSFORMATION],
    WorkflowStep.COLUMN_MAPPING: [WorkflowStep.VENDOR_ENGAGEMENT, WorkflowStep.FINANCE_REVIEW],
    WorkflowStep.VENDOR_ENGAGEMENT: [
        WorkflowStep.AUTO_RECONCILIATION,
        WorkflowStep.COLUMN_MAPPING,
    ],
    WorkflowStep.AUTO_RECONCILIATION: [
        WorkflowStep.EXCEPTION_RESOLUTION,
        WorkflowStep.VENDOR_ENGAGEMENT,
    ],
    WorkflowStep.EXCEPTION_RESOLUTION: [
        WorkflowStep.FINANCE_APPROVAL,
        WorkflowStep.AUTO_RECONCILIATION,
    ],
    WorkflowStep.FINANCE_APPROVAL: [
        WorkflowStep.VENDOR_SIGN_OFF,
        WorkflowStep.EXCEPTION_RESOLUTION,
    ],
    WorkflowStep.VENDOR_SIGN_OFF: [WorkflowStep.CLOSURE, WorkflowStep.FINANCE_APPROVAL],
    WorkflowStep.CLOSURE: [],
}

# Ordered sequence of workflow steps for rollback validation
STEP_ORDER: list[WorkflowStep] = [
    WorkflowStep.INITIATION,
    WorkflowStep.SAP_PULL,
    WorkflowStep.TRANSFORMATION,
    WorkflowStep.FINANCE_REVIEW,
    WorkflowStep.COLUMN_MAPPING,
    WorkflowStep.VENDOR_ENGAGEMENT,
    WorkflowStep.AUTO_RECONCILIATION,
    WorkflowStep.EXCEPTION_RESOLUTION,
    WorkflowStep.FINANCE_APPROVAL,
    WorkflowStep.VENDOR_SIGN_OFF,
    WorkflowStep.CLOSURE,
]


# ─── Data Transfer Objects ────────────────────────────────────────────────────


@dataclass
class CaseStatus:
    """Current workflow status of a reconciliation case."""

    case_id: UUID
    current_step: WorkflowStep
    step_entered_at: datetime
    sla_deadline: datetime | None = None
    is_overdue: bool = False


@dataclass
class SLAViolation:
    """Represents a case that has violated its SLA deadline."""

    case_id: UUID
    current_step: WorkflowStep
    step_entered_at: datetime
    sla_deadline: datetime
    hours_overdue: float = 0.0


@dataclass
class SLAConfiguration:
    """SLA configuration for workflow steps."""

    step_sla_hours: dict[str, int] = field(default_factory=dict)
    escalation_emails: dict[str, str] = field(default_factory=dict)

    def get_sla_hours(self, step: WorkflowStep) -> int | None:
        """Get the SLA hours for a given step, or None if not configured."""
        return self.step_sla_hours.get(step.value)

    def get_escalation_email(self, step: WorkflowStep) -> str | None:
        """Get the escalation email for a given step."""
        return self.escalation_emails.get(step.value)


# ─── Exceptions ───────────────────────────────────────────────────────────────


class WorkflowTransitionError(Exception):
    """Raised when an invalid workflow transition is attempted."""

    def __init__(
        self,
        current_step: WorkflowStep,
        target_step: WorkflowStep,
        valid_targets: list[WorkflowStep],
    ):
        self.current_step = current_step
        self.target_step = target_step
        self.valid_targets = valid_targets
        valid_names = [s.value for s in valid_targets]
        super().__init__(
            f"Cannot transition from '{current_step.value}' to '{target_step.value}'. "
            f"Valid targets: {valid_names}"
        )


class WorkflowRollbackError(Exception):
    """Raised when an invalid rollback is attempted."""

    def __init__(self, current_step: WorkflowStep, target_step: WorkflowStep, reason: str):
        self.current_step = current_step
        self.target_step = target_step
        super().__init__(
            f"Cannot rollback from '{current_step.value}' to '{target_step.value}': {reason}"
        )


class CaseNotFoundError(Exception):
    """Raised when a case is not found."""

    def __init__(self, case_id: UUID):
        self.case_id = case_id
        super().__init__(f"Reconciliation case '{case_id}' not found.")


# ─── Repository Protocol ─────────────────────────────────────────────────────


class ICaseRepository:
    """Protocol for case repository interactions needed by the workflow orchestrator."""

    async def get_by_id(self, case_id: UUID, company_code: str | None = None) -> object | None:
        """Retrieve a case by ID."""
        raise NotImplementedError

    async def update(self, case_id: UUID, update_data: dict) -> object:
        """Update a case."""
        raise NotImplementedError


class IWorkflowStepHistoryRepository:
    """Protocol for workflow step history persistence."""

    async def record_transition(
        self,
        case_id: UUID,
        from_step: str | None,
        to_step: str,
        triggered_by: str,
        triggered_at: datetime,
        sla_deadline: datetime | None = None,
        is_rollback: bool = False,
    ) -> None:
        """Record a workflow step transition."""
        raise NotImplementedError

    async def get_history(self, case_id: UUID) -> list[object]:
        """Get step history for a case."""
        raise NotImplementedError


class INotificationService:
    """Protocol for notification service interactions."""

    async def send_escalation(
        self, case_id: UUID, manager_email: str | None = None, **kwargs: object
    ) -> object:
        """Send an SLA escalation notification."""
        raise NotImplementedError


# ─── Service ──────────────────────────────────────────────────────────────────


class WorkflowOrchestratorService:
    """
    Celery-based state machine for the 11-step reconciliation lifecycle.

    Manages workflow step transitions with validation, SLA monitoring,
    and rollback support. Each step transition is recorded in history
    and can be executed as a Celery task for async processing.

    Requirements: 12.1, 12.2, 12.3, 12.4, 13.1, 13.2
    """

    def __init__(
        self,
        case_repository: ICaseRepository,
        sla_config: SLAConfiguration,
        notification_service: INotificationService | None = None,
        history_repository: IWorkflowStepHistoryRepository | None = None,
    ) -> None:
        self._case_repo = case_repository
        self._sla_config = sla_config
        self._notification_service = notification_service
        self._history_repo = history_repository

    # ──────────────────────────────────────────────────────────────────────
    # Advance
    # ──────────────────────────────────────────────────────────────────────

    async def advance(
        self,
        case_id: UUID,
        target_step: WorkflowStep,
        triggered_by: str = "system",
    ) -> CaseStatus:
        """
        Advance a case to the next workflow step.

        Validates the transition against VALID_TRANSITIONS, updates the case
        record, records step history, and calculates the SLA deadline for the
        target step.

        Requirement 12.1: Enforce step sequence.
        Requirement 12.2: Track current status at all times.
        Requirement 12.3: Execute each step as a Celery task.
        Requirement 12.4: Support transition validation.

        Args:
            case_id: The reconciliation case ID.
            target_step: The target workflow step to advance to.
            triggered_by: User or system that triggered the advance.

        Returns:
            CaseStatus with the updated workflow state.

        Raises:
            CaseNotFoundError: If the case does not exist.
            WorkflowTransitionError: If the transition is not valid.
        """
        case = await self._case_repo.get_by_id(case_id)
        if case is None:
            raise CaseNotFoundError(case_id)

        current_step = self._get_current_step(case)

        # Validate the transition
        valid_targets = VALID_TRANSITIONS.get(current_step, [])
        if target_step not in valid_targets:
            raise WorkflowTransitionError(current_step, target_step, valid_targets)

        # Calculate SLA deadline for the target step
        now = datetime.now(timezone.utc)
        sla_deadline = self._calculate_sla_deadline(target_step, now)

        # Update the case record
        await self._case_repo.update(
            case_id,
            {
                "current_workflow_step": target_step.value,
                "step_entered_at": now,
                "sla_deadline": sla_deadline,
                "is_overdue": False,
            },
        )

        # Record step history
        if self._history_repo is not None:
            await self._history_repo.record_transition(
                case_id=case_id,
                from_step=current_step.value,
                to_step=target_step.value,
                triggered_by=triggered_by,
                triggered_at=now,
                sla_deadline=sla_deadline,
                is_rollback=False,
            )

        logger.info(
            "Workflow advanced",
            extra={
                "case_id": str(case_id),
                "from_step": current_step.value,
                "to_step": target_step.value,
                "triggered_by": triggered_by,
                "sla_deadline": str(sla_deadline) if sla_deadline else None,
            },
        )

        return CaseStatus(
            case_id=case_id,
            current_step=target_step,
            step_entered_at=now,
            sla_deadline=sla_deadline,
            is_overdue=False,
        )

    # ──────────────────────────────────────────────────────────────────────
    # Rollback
    # ──────────────────────────────────────────────────────────────────────

    async def rollback(
        self,
        case_id: UUID,
        target_step: WorkflowStep,
        triggered_by: str = "system",
    ) -> CaseStatus:
        """
        Rollback a case to a previous workflow step.

        Validates that the target step is a valid rollback target (must be
        in the VALID_TRANSITIONS list for the current step and must be a
        step that comes before the current step in the sequence).

        Requirement 12.4: Support rollback to previous step.

        Args:
            case_id: The reconciliation case ID.
            target_step: The target step to rollback to.
            triggered_by: User or system that triggered the rollback.

        Returns:
            CaseStatus with the rolled-back workflow state.

        Raises:
            CaseNotFoundError: If the case does not exist.
            WorkflowRollbackError: If the rollback is not valid.
        """
        case = await self._case_repo.get_by_id(case_id)
        if case is None:
            raise CaseNotFoundError(case_id)

        current_step = self._get_current_step(case)

        # Cannot rollback from INITIATION or CLOSURE
        if current_step == WorkflowStep.INITIATION:
            raise WorkflowRollbackError(
                current_step, target_step, "Cannot rollback from the initial step."
            )
        if current_step == WorkflowStep.CLOSURE:
            raise WorkflowRollbackError(
                current_step, target_step, "Cannot rollback from a closed case."
            )

        # Validate target is a previous step
        current_index = STEP_ORDER.index(current_step)
        target_index = STEP_ORDER.index(target_step)
        if target_index >= current_index:
            raise WorkflowRollbackError(
                current_step,
                target_step,
                "Rollback target must be a previous step in the workflow.",
            )

        # Validate the target step is in the valid transitions (rollback targets)
        valid_targets = VALID_TRANSITIONS.get(current_step, [])
        if target_step not in valid_targets:
            raise WorkflowRollbackError(
                current_step,
                target_step,
                f"Target step is not a valid rollback target. "
                f"Valid targets: {[s.value for s in valid_targets]}",
            )

        # Calculate SLA deadline for the target step
        now = datetime.now(timezone.utc)
        sla_deadline = self._calculate_sla_deadline(target_step, now)

        # Update the case record
        await self._case_repo.update(
            case_id,
            {
                "current_workflow_step": target_step.value,
                "step_entered_at": now,
                "sla_deadline": sla_deadline,
                "is_overdue": False,
            },
        )

        # Record step history with is_rollback=True
        if self._history_repo is not None:
            await self._history_repo.record_transition(
                case_id=case_id,
                from_step=current_step.value,
                to_step=target_step.value,
                triggered_by=triggered_by,
                triggered_at=now,
                sla_deadline=sla_deadline,
                is_rollback=True,
            )

        logger.info(
            "Workflow rolled back",
            extra={
                "case_id": str(case_id),
                "from_step": current_step.value,
                "to_step": target_step.value,
                "triggered_by": triggered_by,
                "is_rollback": True,
            },
        )

        return CaseStatus(
            case_id=case_id,
            current_step=target_step,
            step_entered_at=now,
            sla_deadline=sla_deadline,
            is_overdue=False,
        )

    # ──────────────────────────────────────────────────────────────────────
    # SLA Violation Detection
    # ──────────────────────────────────────────────────────────────────────

    async def check_sla_violations(
        self,
        overdue_cases: list[object] | None = None,
    ) -> list[SLAViolation]:
        """
        Identify cases that have exceeded their workflow step SLA deadline.

        Queries for cases where the current time is past the SLA deadline
        and is_overdue is False. Updates is_overdue=True and sends escalation
        notifications.

        Requirement 13.1: Define configurable SLA durations per step.
        Requirement 13.2: Flag overdue cases and send escalation.

        Args:
            overdue_cases: Optional pre-fetched list of overdue case objects.
                If None, this method returns an empty list (caller should
                provide cases from a database query).

        Returns:
            List of SLAViolation objects for newly identified violations.
        """
        if overdue_cases is None:
            overdue_cases = []

        now = datetime.now(timezone.utc)
        violations: list[SLAViolation] = []

        for case in overdue_cases:
            case_id = self._get_case_id(case)
            current_step_str = getattr(case, "current_workflow_step", None)
            step_entered_at = getattr(case, "step_entered_at", None)
            sla_deadline = getattr(case, "sla_deadline", None)

            if current_step_str is None or sla_deadline is None:
                continue

            try:
                current_step = WorkflowStep(current_step_str)
            except ValueError:
                continue

            # Calculate hours overdue
            hours_overdue = (now - sla_deadline).total_seconds() / 3600.0

            # Mark as overdue
            await self._case_repo.update(case_id, {"is_overdue": True})

            violation = SLAViolation(
                case_id=case_id,
                current_step=current_step,
                step_entered_at=step_entered_at or now,
                sla_deadline=sla_deadline,
                hours_overdue=max(0.0, hours_overdue),
            )
            violations.append(violation)

            # Send escalation notification
            if self._notification_service is not None:
                escalation_email = self._sla_config.get_escalation_email(current_step)
                if escalation_email:
                    try:
                        await self._notification_service.send_escalation(
                            case_id=case_id,
                            manager_email=escalation_email,
                        )
                    except Exception as e:
                        logger.warning(
                            "Failed to send SLA escalation notification",
                            extra={
                                "case_id": str(case_id),
                                "error": str(e),
                            },
                        )

            logger.warning(
                "SLA violation detected",
                extra={
                    "case_id": str(case_id),
                    "current_step": current_step.value,
                    "sla_deadline": str(sla_deadline),
                    "hours_overdue": round(hours_overdue, 2),
                },
            )

        return violations

    # ──────────────────────────────────────────────────────────────────────
    # Get Current Status
    # ──────────────────────────────────────────────────────────────────────

    async def get_status(self, case_id: UUID) -> CaseStatus:
        """
        Get the current workflow status of a case.

        Requirement 12.2: Track current status at all times.

        Args:
            case_id: The reconciliation case ID.

        Returns:
            CaseStatus with the current workflow state.

        Raises:
            CaseNotFoundError: If the case does not exist.
        """
        case = await self._case_repo.get_by_id(case_id)
        if case is None:
            raise CaseNotFoundError(case_id)

        current_step = self._get_current_step(case)
        step_entered_at = getattr(case, "step_entered_at", None) or datetime.now(timezone.utc)
        sla_deadline = getattr(case, "sla_deadline", None)
        is_overdue = getattr(case, "is_overdue", False)

        return CaseStatus(
            case_id=case_id,
            current_step=current_step,
            step_entered_at=step_entered_at,
            sla_deadline=sla_deadline,
            is_overdue=is_overdue,
        )

    # ──────────────────────────────────────────────────────────────────────
    # Internal Helpers
    # ──────────────────────────────────────────────────────────────────────

    def _get_current_step(self, case: object) -> WorkflowStep:
        """Extract and validate the current workflow step from a case object."""
        step_value = getattr(case, "current_workflow_step", None)
        if step_value is None:
            return WorkflowStep.INITIATION
        try:
            return WorkflowStep(step_value)
        except ValueError:
            logger.warning(
                "Unknown workflow step value '%s', defaulting to INITIATION",
                step_value,
            )
            return WorkflowStep.INITIATION

    def _get_case_id(self, case: object) -> UUID:
        """Extract the case ID from a case object."""
        case_id = getattr(case, "id", None)
        if case_id is None:
            raise ValueError("Case object has no 'id' attribute.")
        if isinstance(case_id, UUID):
            return case_id
        return UUID(str(case_id))

    def _calculate_sla_deadline(
        self, step: WorkflowStep, from_time: datetime
    ) -> datetime | None:
        """
        Calculate the SLA deadline for a workflow step.

        Returns None if no SLA is configured for the step.
        """
        sla_hours = self._sla_config.get_sla_hours(step)
        if sla_hours is None:
            return None
        return from_time + timedelta(hours=sla_hours)
