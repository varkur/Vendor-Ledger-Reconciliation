"""
Automation Rule Domain Service.

Implements scheduling for recurring reconciliation (monthly, quarterly),
auto-matching rules (confidence threshold-based auto-accept),
auto-escalation rules (configurable days without progress),
execution history recording, and enable/disable without deletion.

Requirements: 19.1, 19.2, 19.3, 19.4, 19.5, 19.6, 19.7
"""

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from enum import Enum
from uuid import UUID, uuid4

from src.domain.repositories.vlr.automation_rule_repository import (
    IAutomationRuleRepository,
)
from src.domain.repositories.vlr.case_repository import ICaseRepository
from src.domain.repositories.vlr.match_result_repository import IMatchResultRepository
from src.domain.repositories.vlr.setting_repository import ISettingRepository


# ─── Enumerations ─────────────────────────────────────────────────────────────


class RuleType(str, Enum):
    """Automation rule types."""

    SCHEDULED_RECONCILIATION = "scheduled_reconciliation"
    AUTO_MATCH = "auto_match"
    AUTO_ESCALATION = "auto_escalation"


class ScheduleFrequency(str, Enum):
    """Scheduling frequency options."""

    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"


class ExecutionOutcome(str, Enum):
    """Possible outcomes of a rule execution."""

    SUCCESS = "success"
    PARTIAL = "partial"
    FAILURE = "failure"
    SKIPPED = "skipped"


class EscalationTarget(str, Enum):
    """Escalation targets."""

    MANAGER = "manager"
    SENIOR_MANAGER = "senior_manager"
    DIRECTOR = "director"


# ─── Constants ────────────────────────────────────────────────────────────────

DEFAULT_CONFIDENCE_THRESHOLD = 0.95  # 95% confidence for auto-accept
DEFAULT_ESCALATION_DAYS = 7  # Days without progress before escalation
MIN_CONFIDENCE_THRESHOLD = 0.80  # Minimum allowed confidence for auto-accept
MAX_CONFIDENCE_THRESHOLD = 1.0  # Maximum confidence threshold


# ─── Data Transfer Objects ────────────────────────────────────────────────────


@dataclass
class ScheduleConfig:
    """Configuration for scheduled reconciliation rules."""

    frequency: str  # ScheduleFrequency value
    day_of_month: int | None = None  # For monthly (1-28)
    day_of_week: int | None = None  # For weekly (0=Mon, 6=Sun)
    quarter_months: list[int] = field(default_factory=lambda: [1, 4, 7, 10])
    time_of_day: str = "02:00"  # HH:MM in UTC
    vendor_ids: list[UUID] = field(default_factory=list)  # Empty = all vendors


@dataclass
class AutoMatchConfig:
    """Configuration for auto-matching rules."""

    confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD
    max_amount: Decimal | None = None  # Max amount for auto-accept (None = no limit)
    exclude_vendor_ids: list[UUID] = field(default_factory=list)


@dataclass
class AutoEscalationConfig:
    """Configuration for auto-escalation rules."""

    days_without_progress: int = DEFAULT_ESCALATION_DAYS
    target: str = EscalationTarget.MANAGER.value
    notify_assignee: bool = True
    include_case_statuses: list[str] = field(
        default_factory=lambda: ["in_progress", "pending_vendor"]
    )


@dataclass
class RuleCreateDTO:
    """Data transfer object for creating an automation rule."""

    company_code: str
    rule_type: str  # RuleType value
    name: str
    description: str | None = None
    created_by: UUID | None = None
    schedule_config: ScheduleConfig | None = None
    auto_match_config: AutoMatchConfig | None = None
    auto_escalation_config: AutoEscalationConfig | None = None


@dataclass
class RuleUpdateDTO:
    """Data transfer object for updating an automation rule."""

    name: str | None = None
    description: str | None = None
    schedule_config: ScheduleConfig | None = None
    auto_match_config: AutoMatchConfig | None = None
    auto_escalation_config: AutoEscalationConfig | None = None


@dataclass
class ExecutionRecord:
    """Record of a single rule execution."""

    id: UUID
    rule_id: UUID
    trigger_time: datetime
    outcome: str
    details: str | None = None
    cases_affected: int = 0
    matches_auto_accepted: int = 0
    escalations_triggered: int = 0
    completed_at: datetime | None = None


@dataclass
class ScheduledReconciliationResult:
    """Result of executing a scheduled reconciliation."""

    cases_created: int = 0
    vendors_processed: int = 0
    errors: list[str] = field(default_factory=list)


@dataclass
class AutoMatchResult:
    """Result of executing auto-match rules."""

    matches_accepted: int = 0
    matches_skipped: int = 0
    cases_processed: int = 0
    errors: list[str] = field(default_factory=list)


@dataclass
class AutoEscalationResult:
    """Result of executing auto-escalation rules."""

    cases_escalated: int = 0
    notifications_sent: int = 0
    cases_checked: int = 0
    errors: list[str] = field(default_factory=list)


# ─── Service ──────────────────────────────────────────────────────────────────


class AutomationRuleService:
    """
    Domain service for automation rule management.

    Handles scheduling recurring reconciliation, auto-matching based on
    confidence thresholds, auto-escalation of stale cases, execution
    history recording, and rule enable/disable lifecycle.

    Requirements:
        19.1: Scheduling recurring reconciliation (monthly, quarterly).
        19.2: Auto-matching rules with confidence threshold-based auto-accept.
        19.3: Auto-escalation rules (configurable days without progress).
        19.4: Record execution history with trigger time, rule ID, outcome.
        19.5: Support enable/disable without deletion.
        19.6: Rule configuration validation.
        19.7: Execution of due rules.
    """

    def __init__(
        self,
        automation_rule_repository: IAutomationRuleRepository,
        case_repository: ICaseRepository,
        match_result_repository: IMatchResultRepository,
        setting_repository: ISettingRepository,
    ) -> None:
        self._rule_repo = automation_rule_repository
        self._case_repo = case_repository
        self._match_repo = match_result_repository
        self._setting_repo = setting_repository

    # ──────────────────────────────────────────────────────────────────────
    # Rule CRUD Operations
    # ──────────────────────────────────────────────────────────────────────

    async def create_rule(self, dto: RuleCreateDTO) -> object:
        """
        Create a new automation rule.

        Requirement 19.1, 19.2, 19.3: Create rules for scheduling,
        auto-matching, or auto-escalation.
        Requirement 19.6: Validate rule configuration before creation.
        """
        # Validate rule type
        if dto.rule_type not in [rt.value for rt in RuleType]:
            raise ValueError(
                f"Invalid rule type '{dto.rule_type}'. "
                f"Must be one of: {[rt.value for rt in RuleType]}"
            )

        # Validate configuration based on rule type
        self._validate_rule_config(dto)

        # Calculate next execution time
        next_execution = self._calculate_next_execution(dto)

        rule_data = {
            "company_code": dto.company_code,
            "rule_type": dto.rule_type,
            "name": dto.name,
            "description": dto.description,
            "is_active": True,
            "created_by": str(dto.created_by) if dto.created_by else None,
            "next_execution": next_execution,
            "config": self._serialize_config(dto),
        }

        return await self._rule_repo.create(rule_data)

    async def update_rule(self, rule_id: UUID, dto: RuleUpdateDTO) -> object:
        """
        Update an existing automation rule.

        Requirement 19.6: Validate updated configuration.
        """
        rule = await self._rule_repo.get_by_id(rule_id)
        if rule is None:
            raise ValueError(f"Automation rule '{rule_id}' not found.")

        update_data: dict = {}

        if dto.name is not None:
            update_data["name"] = dto.name

        if dto.description is not None:
            update_data["description"] = dto.description

        # Update config if any config DTO is provided
        rule_type = getattr(rule, "rule_type", "")
        if dto.schedule_config is not None or dto.auto_match_config is not None or dto.auto_escalation_config is not None:
            # Build a temporary create DTO for validation
            temp_dto = RuleCreateDTO(
                company_code=getattr(rule, "company_code", ""),
                rule_type=rule_type,
                name=dto.name or getattr(rule, "name", ""),
                schedule_config=dto.schedule_config,
                auto_match_config=dto.auto_match_config,
                auto_escalation_config=dto.auto_escalation_config,
            )
            self._validate_rule_config(temp_dto)
            update_data["config"] = self._serialize_config(temp_dto)

            # Recalculate next execution
            next_execution = self._calculate_next_execution(temp_dto)
            if next_execution:
                update_data["next_execution"] = next_execution

        if not update_data:
            return rule

        return await self._rule_repo.update(rule_id, update_data)

    async def get_rule(self, rule_id: UUID) -> object | None:
        """Get an automation rule by ID."""
        return await self._rule_repo.get_by_id(rule_id)

    async def list_rules(
        self,
        company_code: str,
        pagination=None,
    ):
        """List automation rules for a company."""
        return await self._rule_repo.list_by_company(company_code, pagination)

    # ──────────────────────────────────────────────────────────────────────
    # Enable / Disable (Requirement 19.5)
    # ──────────────────────────────────────────────────────────────────────

    async def enable_rule(self, rule_id: UUID) -> object:
        """
        Enable a previously disabled rule without deletion.

        Requirement 19.5: Support enable/disable without deletion.
        """
        rule = await self._rule_repo.get_by_id(rule_id)
        if rule is None:
            raise ValueError(f"Automation rule '{rule_id}' not found.")

        return await self._rule_repo.activate(rule_id)

    async def disable_rule(self, rule_id: UUID) -> object:
        """
        Disable an active rule without deletion.

        Requirement 19.5: Support enable/disable without deletion.
        """
        rule = await self._rule_repo.get_by_id(rule_id)
        if rule is None:
            raise ValueError(f"Automation rule '{rule_id}' not found.")

        return await self._rule_repo.deactivate(rule_id)

    # ──────────────────────────────────────────────────────────────────────
    # Scheduled Reconciliation (Requirement 19.1)
    # ──────────────────────────────────────────────────────────────────────

    async def execute_scheduled_reconciliation(
        self,
        rule: object,
    ) -> ScheduledReconciliationResult:
        """
        Execute a scheduled reconciliation rule.

        Requirement 19.1: Schedule recurring reconciliation
        (monthly, quarterly) by creating reconciliation cases for
        configured vendors.
        """
        config = getattr(rule, "config", {}) or {}
        schedule_config = config.get("schedule", {})
        vendor_ids = schedule_config.get("vendor_ids", [])
        company_code = getattr(rule, "company_code", "")

        result = ScheduledReconciliationResult()

        # If no specific vendors, reconcile all active vendors for company
        if not vendor_ids:
            active_cases = await self._case_repo.list_cases(
                company_code=company_code,
            )
            result.vendors_processed = getattr(active_cases, "total", 0)
        else:
            result.vendors_processed = len(vendor_ids)

        # Create reconciliation cases for the period
        for vendor_id_str in vendor_ids:
            try:
                vendor_id = UUID(str(vendor_id_str)) if not isinstance(vendor_id_str, UUID) else vendor_id_str
                # Create case for this vendor's scheduled reconciliation
                await self._case_repo.create({
                    "vendor_id": str(vendor_id),
                    "company_code": company_code,
                    "status": "pending",
                    "case_type": "scheduled",
                    "created_by": "automation",
                })
                result.cases_created += 1
            except Exception as e:
                result.errors.append(
                    f"Failed to create case for vendor '{vendor_id_str}': {str(e)}"
                )

        return result

    # ──────────────────────────────────────────────────────────────────────
    # Auto-Matching (Requirement 19.2)
    # ──────────────────────────────────────────────────────────────────────

    async def execute_auto_match(self, rule: object) -> AutoMatchResult:
        """
        Execute auto-matching rules based on confidence thresholds.

        Requirement 19.2: Auto-accept matches that meet or exceed the
        configured confidence threshold. Optionally filter by amount
        and vendor exclusion list.
        """
        config = getattr(rule, "config", {}) or {}
        match_config = config.get("auto_match", {})
        confidence_threshold = match_config.get(
            "confidence_threshold", DEFAULT_CONFIDENCE_THRESHOLD
        )
        max_amount = match_config.get("max_amount")
        exclude_vendor_ids = match_config.get("exclude_vendor_ids", [])
        company_code = getattr(rule, "company_code", "")

        result = AutoMatchResult()

        # Get active cases for the company
        cases_result = await self._case_repo.list_cases(company_code=company_code)
        cases = getattr(cases_result, "items", [])

        for case in cases:
            case_id = getattr(case, "id", None)
            if case_id is None:
                continue

            # Skip excluded vendors
            vendor_id = getattr(case, "vendor_id", None)
            if vendor_id and str(vendor_id) in [str(v) for v in exclude_vendor_ids]:
                continue

            result.cases_processed += 1

            # Get unconfirmed matches for this case
            try:
                unconfirmed = await self._match_repo.get_unconfirmed_by_case(case_id)
            except Exception as e:
                result.errors.append(
                    f"Failed to get matches for case '{case_id}': {str(e)}"
                )
                continue

            for match in unconfirmed:
                score = getattr(match, "confidence_score", 0.0)
                amount = getattr(match, "matched_amount", Decimal("0"))

                # Check confidence threshold
                if score < confidence_threshold:
                    result.matches_skipped += 1
                    continue

                # Check max amount limit
                if max_amount is not None and abs(float(amount)) > float(max_amount):
                    result.matches_skipped += 1
                    continue

                # Auto-accept the match
                try:
                    match_id = getattr(match, "id", None)
                    if match_id:
                        await self._match_repo.confirm_match(match_id)
                        result.matches_accepted += 1
                except Exception as e:
                    result.errors.append(
                        f"Failed to auto-accept match '{getattr(match, 'id', '?')}': {str(e)}"
                    )
                    result.matches_skipped += 1

        return result

    # ──────────────────────────────────────────────────────────────────────
    # Auto-Escalation (Requirement 19.3)
    # ──────────────────────────────────────────────────────────────────────

    async def execute_auto_escalation(self, rule: object) -> AutoEscalationResult:
        """
        Execute auto-escalation rules for cases without progress.

        Requirement 19.3: Escalate cases that have not progressed
        within the configured number of days. Escalation target and
        notification behavior are configurable.
        """
        config = getattr(rule, "config", {}) or {}
        escalation_config = config.get("auto_escalation", {})
        days_without_progress = escalation_config.get(
            "days_without_progress", DEFAULT_ESCALATION_DAYS
        )
        target = escalation_config.get("target", EscalationTarget.MANAGER.value)
        notify_assignee = escalation_config.get("notify_assignee", True)
        include_statuses = escalation_config.get(
            "include_case_statuses", ["in_progress", "pending_vendor"]
        )
        company_code = getattr(rule, "company_code", "")

        result = AutoEscalationResult()
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days_without_progress)

        # Get cases for the company
        cases_result = await self._case_repo.list_cases(company_code=company_code)
        cases = getattr(cases_result, "items", [])

        for case in cases:
            case_id = getattr(case, "id", None)
            if case_id is None:
                continue

            status = getattr(case, "status", "")
            if status not in include_statuses:
                continue

            result.cases_checked += 1

            # Check last updated timestamp
            updated_at = getattr(case, "updated_at", None)
            if updated_at is None:
                updated_at = getattr(case, "created_at", None)

            if updated_at is None:
                continue

            # Ensure timezone-aware comparison
            if updated_at.tzinfo is None:
                updated_at = updated_at.replace(tzinfo=timezone.utc)

            if updated_at <= cutoff_date:
                # Escalate the case
                try:
                    await self._case_repo.update(case_id, {
                        "status": "escalated",
                        "escalation_target": target,
                        "escalated_at": datetime.now(timezone.utc).isoformat(),
                    })
                    result.cases_escalated += 1

                    if notify_assignee:
                        result.notifications_sent += 1
                except Exception as e:
                    result.errors.append(
                        f"Failed to escalate case '{case_id}': {str(e)}"
                    )

        return result

    # ──────────────────────────────────────────────────────────────────────
    # Execution History (Requirement 19.4)
    # ──────────────────────────────────────────────────────────────────────

    async def record_execution(
        self,
        rule_id: UUID,
        trigger_time: datetime,
        outcome: ExecutionOutcome,
        details: str | None = None,
        cases_affected: int = 0,
        matches_auto_accepted: int = 0,
        escalations_triggered: int = 0,
    ) -> ExecutionRecord:
        """
        Record execution history with trigger time, rule ID, and outcome.

        Requirement 19.4: Every rule execution is logged with timing,
        identification, and result data for auditability.
        """
        execution_id = uuid4()
        completed_at = datetime.now(timezone.utc)

        execution_data = {
            "id": str(execution_id),
            "rule_id": str(rule_id),
            "trigger_time": trigger_time.isoformat(),
            "outcome": outcome.value,
            "details": details,
            "cases_affected": cases_affected,
            "matches_auto_accepted": matches_auto_accepted,
            "escalations_triggered": escalations_triggered,
            "completed_at": completed_at.isoformat(),
        }

        await self._rule_repo.record_execution(execution_data)

        return ExecutionRecord(
            id=execution_id,
            rule_id=rule_id,
            trigger_time=trigger_time,
            outcome=outcome.value,
            details=details,
            cases_affected=cases_affected,
            matches_auto_accepted=matches_auto_accepted,
            escalations_triggered=escalations_triggered,
            completed_at=completed_at,
        )

    async def get_execution_history(self, rule_id: UUID, pagination=None):
        """
        Retrieve execution history for a rule.

        Requirement 19.4: Execution history is queryable per rule.
        """
        return await self._rule_repo.get_execution_history(rule_id, pagination)

    # ──────────────────────────────────────────────────────────────────────
    # Due Rule Execution (Requirement 19.7)
    # ──────────────────────────────────────────────────────────────────────

    async def execute_due_rules(self) -> list[ExecutionRecord]:
        """
        Find and execute all rules whose next_execution time has passed.

        Requirement 19.7: Automated execution of due rules. Each rule
        is executed based on its type and the result is recorded.
        """
        now = datetime.now(timezone.utc)
        due_rules = await self._rule_repo.get_due_rules(before=now)

        execution_records: list[ExecutionRecord] = []

        for rule in due_rules:
            rule_id = getattr(rule, "id", None)
            if rule_id is None:
                continue

            # Skip inactive rules
            is_active = getattr(rule, "is_active", False)
            if not is_active:
                continue

            rule_type = getattr(rule, "rule_type", "")
            trigger_time = now

            try:
                outcome = ExecutionOutcome.SUCCESS
                details = None
                cases_affected = 0
                matches_auto_accepted = 0
                escalations_triggered = 0

                if rule_type == RuleType.SCHEDULED_RECONCILIATION.value:
                    exec_result = await self.execute_scheduled_reconciliation(rule)
                    cases_affected = exec_result.cases_created
                    if exec_result.errors:
                        outcome = ExecutionOutcome.PARTIAL
                        details = "; ".join(exec_result.errors)

                elif rule_type == RuleType.AUTO_MATCH.value:
                    exec_result = await self.execute_auto_match(rule)
                    matches_auto_accepted = exec_result.matches_accepted
                    cases_affected = exec_result.cases_processed
                    if exec_result.errors:
                        outcome = ExecutionOutcome.PARTIAL
                        details = "; ".join(exec_result.errors)

                elif rule_type == RuleType.AUTO_ESCALATION.value:
                    exec_result = await self.execute_auto_escalation(rule)
                    escalations_triggered = exec_result.cases_escalated
                    cases_affected = exec_result.cases_checked
                    if exec_result.errors:
                        outcome = ExecutionOutcome.PARTIAL
                        details = "; ".join(exec_result.errors)

                else:
                    outcome = ExecutionOutcome.SKIPPED
                    details = f"Unknown rule type: {rule_type}"

            except Exception as e:
                outcome = ExecutionOutcome.FAILURE
                details = str(e)

            # Record execution
            record = await self.record_execution(
                rule_id=rule_id,
                trigger_time=trigger_time,
                outcome=outcome,
                details=details,
                cases_affected=cases_affected,
                matches_auto_accepted=matches_auto_accepted,
                escalations_triggered=escalations_triggered,
            )
            execution_records.append(record)

            # Update next_execution for the rule
            next_execution = self._calculate_next_execution_from_rule(rule)
            if next_execution:
                await self._rule_repo.update(rule_id, {
                    "next_execution": next_execution,
                    "last_executed_at": now.isoformat(),
                })

        return execution_records

    # ──────────────────────────────────────────────────────────────────────
    # Validation Helpers
    # ──────────────────────────────────────────────────────────────────────

    def _validate_rule_config(self, dto: RuleCreateDTO) -> None:
        """
        Validate rule configuration based on rule type.

        Requirement 19.6: Ensure configuration is valid before persisting.
        """
        if dto.rule_type == RuleType.SCHEDULED_RECONCILIATION.value:
            if dto.schedule_config is None:
                raise ValueError(
                    "Schedule configuration is required for scheduled reconciliation rules."
                )
            self._validate_schedule_config(dto.schedule_config)

        elif dto.rule_type == RuleType.AUTO_MATCH.value:
            if dto.auto_match_config is None:
                raise ValueError(
                    "Auto-match configuration is required for auto-match rules."
                )
            self._validate_auto_match_config(dto.auto_match_config)

        elif dto.rule_type == RuleType.AUTO_ESCALATION.value:
            if dto.auto_escalation_config is None:
                raise ValueError(
                    "Auto-escalation configuration is required for auto-escalation rules."
                )
            self._validate_auto_escalation_config(dto.auto_escalation_config)

    def _validate_schedule_config(self, config: ScheduleConfig) -> None:
        """Validate scheduling configuration."""
        if config.frequency not in [f.value for f in ScheduleFrequency]:
            raise ValueError(
                f"Invalid frequency '{config.frequency}'. "
                f"Must be one of: {[f.value for f in ScheduleFrequency]}"
            )

        if config.frequency == ScheduleFrequency.MONTHLY.value:
            if config.day_of_month is None:
                raise ValueError("day_of_month is required for monthly schedules.")
            if not (1 <= config.day_of_month <= 28):
                raise ValueError("day_of_month must be between 1 and 28.")

        if config.frequency == ScheduleFrequency.WEEKLY.value:
            if config.day_of_week is None:
                raise ValueError("day_of_week is required for weekly schedules.")
            if not (0 <= config.day_of_week <= 6):
                raise ValueError("day_of_week must be between 0 (Monday) and 6 (Sunday).")

    def _validate_auto_match_config(self, config: AutoMatchConfig) -> None:
        """Validate auto-match configuration."""
        if config.confidence_threshold < MIN_CONFIDENCE_THRESHOLD:
            raise ValueError(
                f"Confidence threshold must be at least {MIN_CONFIDENCE_THRESHOLD}."
            )
        if config.confidence_threshold > MAX_CONFIDENCE_THRESHOLD:
            raise ValueError(
                f"Confidence threshold cannot exceed {MAX_CONFIDENCE_THRESHOLD}."
            )
        if config.max_amount is not None and config.max_amount <= Decimal("0"):
            raise ValueError("max_amount must be positive if specified.")

    def _validate_auto_escalation_config(self, config: AutoEscalationConfig) -> None:
        """Validate auto-escalation configuration."""
        if config.days_without_progress < 1:
            raise ValueError("days_without_progress must be at least 1.")
        if config.target not in [t.value for t in EscalationTarget]:
            raise ValueError(
                f"Invalid escalation target '{config.target}'. "
                f"Must be one of: {[t.value for t in EscalationTarget]}"
            )

    # ──────────────────────────────────────────────────────────────────────
    # Scheduling Helpers
    # ──────────────────────────────────────────────────────────────────────

    def _calculate_next_execution(self, dto: RuleCreateDTO) -> datetime | None:
        """Calculate the next execution time based on rule configuration."""
        now = datetime.now(timezone.utc)

        if dto.rule_type == RuleType.SCHEDULED_RECONCILIATION.value and dto.schedule_config:
            return self._next_schedule_time(dto.schedule_config, now)

        if dto.rule_type == RuleType.AUTO_MATCH.value:
            # Auto-match runs daily by default
            return now + timedelta(hours=1)

        if dto.rule_type == RuleType.AUTO_ESCALATION.value:
            # Auto-escalation checks run daily
            return now + timedelta(hours=24)

        return None

    def _calculate_next_execution_from_rule(self, rule: object) -> datetime | None:
        """Calculate next execution from an existing rule object."""
        config = getattr(rule, "config", {}) or {}
        rule_type = getattr(rule, "rule_type", "")
        now = datetime.now(timezone.utc)

        if rule_type == RuleType.SCHEDULED_RECONCILIATION.value:
            schedule_data = config.get("schedule", {})
            schedule_config = ScheduleConfig(
                frequency=schedule_data.get("frequency", ScheduleFrequency.MONTHLY.value),
                day_of_month=schedule_data.get("day_of_month"),
                day_of_week=schedule_data.get("day_of_week"),
                quarter_months=schedule_data.get("quarter_months", [1, 4, 7, 10]),
                time_of_day=schedule_data.get("time_of_day", "02:00"),
            )
            return self._next_schedule_time(schedule_config, now)

        if rule_type == RuleType.AUTO_MATCH.value:
            return now + timedelta(hours=1)

        if rule_type == RuleType.AUTO_ESCALATION.value:
            return now + timedelta(hours=24)

        return None

    def _next_schedule_time(
        self, config: ScheduleConfig, from_time: datetime
    ) -> datetime:
        """Calculate the next scheduled execution time."""
        # Parse time_of_day
        parts = config.time_of_day.split(":")
        hour = int(parts[0]) if len(parts) > 0 else 2
        minute = int(parts[1]) if len(parts) > 1 else 0

        if config.frequency == ScheduleFrequency.DAILY.value:
            next_date = from_time.date() + timedelta(days=1)
            return datetime(
                next_date.year, next_date.month, next_date.day,
                hour, minute, tzinfo=timezone.utc,
            )

        elif config.frequency == ScheduleFrequency.WEEKLY.value:
            day_of_week = config.day_of_week or 0
            current_dow = from_time.weekday()
            days_ahead = day_of_week - current_dow
            if days_ahead <= 0:
                days_ahead += 7
            next_date = from_time.date() + timedelta(days=days_ahead)
            return datetime(
                next_date.year, next_date.month, next_date.day,
                hour, minute, tzinfo=timezone.utc,
            )

        elif config.frequency == ScheduleFrequency.MONTHLY.value:
            day_of_month = config.day_of_month or 1
            # Move to next month
            year = from_time.year
            month = from_time.month + 1
            if month > 12:
                month = 1
                year += 1
            return datetime(
                year, month, day_of_month,
                hour, minute, tzinfo=timezone.utc,
            )

        elif config.frequency == ScheduleFrequency.QUARTERLY.value:
            quarter_months = config.quarter_months or [1, 4, 7, 10]
            current_month = from_time.month
            # Find next quarter month
            next_quarter_month = None
            for qm in sorted(quarter_months):
                if qm > current_month:
                    next_quarter_month = qm
                    break
            year = from_time.year
            if next_quarter_month is None:
                next_quarter_month = sorted(quarter_months)[0]
                year += 1
            day = config.day_of_month or 1
            return datetime(
                year, next_quarter_month, day,
                hour, minute, tzinfo=timezone.utc,
            )

        # Fallback: next day
        next_date = from_time.date() + timedelta(days=1)
        return datetime(
            next_date.year, next_date.month, next_date.day,
            hour, minute, tzinfo=timezone.utc,
        )

    # ──────────────────────────────────────────────────────────────────────
    # Serialization Helpers
    # ──────────────────────────────────────────────────────────────────────

    def _serialize_config(self, dto: RuleCreateDTO) -> dict:
        """Serialize rule configuration to a storable dict."""
        config: dict = {}

        if dto.schedule_config:
            config["schedule"] = {
                "frequency": dto.schedule_config.frequency,
                "day_of_month": dto.schedule_config.day_of_month,
                "day_of_week": dto.schedule_config.day_of_week,
                "quarter_months": dto.schedule_config.quarter_months,
                "time_of_day": dto.schedule_config.time_of_day,
                "vendor_ids": [str(v) for v in dto.schedule_config.vendor_ids],
            }

        if dto.auto_match_config:
            config["auto_match"] = {
                "confidence_threshold": dto.auto_match_config.confidence_threshold,
                "max_amount": (
                    float(dto.auto_match_config.max_amount)
                    if dto.auto_match_config.max_amount is not None
                    else None
                ),
                "exclude_vendor_ids": [
                    str(v) for v in dto.auto_match_config.exclude_vendor_ids
                ],
            }

        if dto.auto_escalation_config:
            config["auto_escalation"] = {
                "days_without_progress": dto.auto_escalation_config.days_without_progress,
                "target": dto.auto_escalation_config.target,
                "notify_assignee": dto.auto_escalation_config.notify_assignee,
                "include_case_statuses": dto.auto_escalation_config.include_case_statuses,
            }

        return config
