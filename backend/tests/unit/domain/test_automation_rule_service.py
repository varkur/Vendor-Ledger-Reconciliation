"""
Unit tests for AutomationRuleService domain logic.

Tests scheduling for recurring reconciliation, auto-matching rules,
auto-escalation rules, execution history recording, and enable/disable
without deletion.

Requirements: 19.1, 19.2, 19.3, 19.4, 19.5, 19.6, 19.7
"""

import pytest
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

from src.domain.services.vlr.automation_rule_service import (
    AutoEscalationConfig,
    AutoEscalationResult,
    AutoMatchConfig,
    AutoMatchResult,
    AutomationRuleService,
    DEFAULT_CONFIDENCE_THRESHOLD,
    DEFAULT_ESCALATION_DAYS,
    EscalationTarget,
    ExecutionOutcome,
    ExecutionRecord,
    MAX_CONFIDENCE_THRESHOLD,
    MIN_CONFIDENCE_THRESHOLD,
    RuleCreateDTO,
    RuleType,
    RuleUpdateDTO,
    ScheduleConfig,
    ScheduleFrequency,
    ScheduledReconciliationResult,
)


# ─── Test Helpers ─────────────────────────────────────────────────────────────


@dataclass
class FakeRule:
    """Fake automation rule object for testing."""

    id: UUID = field(default_factory=uuid4)
    company_code: str = "CC01"
    rule_type: str = "scheduled_reconciliation"
    name: str = "Monthly Reconciliation"
    description: str | None = None
    is_active: bool = True
    config: dict = field(default_factory=dict)
    next_execution: datetime | None = None
    last_executed_at: datetime | None = None
    created_by: str | None = None


@dataclass
class FakeCase:
    """Fake case object for testing."""

    id: UUID = field(default_factory=uuid4)
    vendor_id: UUID = field(default_factory=uuid4)
    company_code: str = "CC01"
    status: str = "in_progress"
    created_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc) - timedelta(days=10)
    )
    updated_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc) - timedelta(days=10)
    )


@dataclass
class FakeMatch:
    """Fake match result for testing."""

    id: UUID = field(default_factory=uuid4)
    case_id: UUID = field(default_factory=uuid4)
    confidence_score: float = 0.98
    matched_amount: Decimal = Decimal("1000.00")
    is_confirmed: bool = False


@dataclass
class FakePaginatedResult:
    """Fake paginated result."""

    items: list = field(default_factory=list)
    total: int = 0


# ─── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_rule_repo() -> AsyncMock:
    """Create a mock automation rule repository."""
    repo = AsyncMock()
    repo.get_by_id = AsyncMock(return_value=None)
    repo.create = AsyncMock()
    repo.update = AsyncMock()
    repo.list_by_company = AsyncMock(
        return_value=FakePaginatedResult(items=[], total=0)
    )
    repo.get_active_rules = AsyncMock(return_value=[])
    repo.get_due_rules = AsyncMock(return_value=[])
    repo.record_execution = AsyncMock()
    repo.get_execution_history = AsyncMock(
        return_value=FakePaginatedResult(items=[], total=0)
    )
    repo.deactivate = AsyncMock()
    repo.activate = AsyncMock()
    return repo


@pytest.fixture
def mock_case_repo() -> AsyncMock:
    """Create a mock case repository."""
    repo = AsyncMock()
    repo.get_by_id = AsyncMock(return_value=None)
    repo.create = AsyncMock()
    repo.update = AsyncMock()
    repo.list_cases = AsyncMock(
        return_value=FakePaginatedResult(items=[], total=0)
    )
    return repo


@pytest.fixture
def mock_match_repo() -> AsyncMock:
    """Create a mock match result repository."""
    repo = AsyncMock()
    repo.get_unconfirmed_by_case = AsyncMock(return_value=[])
    repo.confirm_match = AsyncMock()
    return repo


@pytest.fixture
def mock_setting_repo() -> AsyncMock:
    """Create a mock setting repository."""
    repo = AsyncMock()
    repo.get_by_key = AsyncMock(return_value=None)
    return repo


@pytest.fixture
def service(
    mock_rule_repo: AsyncMock,
    mock_case_repo: AsyncMock,
    mock_match_repo: AsyncMock,
    mock_setting_repo: AsyncMock,
) -> AutomationRuleService:
    """Create AutomationRuleService with mocked repositories."""
    return AutomationRuleService(
        automation_rule_repository=mock_rule_repo,
        case_repository=mock_case_repo,
        match_result_repository=mock_match_repo,
        setting_repository=mock_setting_repo,
    )


# ─── Rule Creation Tests ─────────────────────────────────────────────────────


class TestCreateRule:
    """Tests for rule creation with configuration validation."""

    @pytest.mark.asyncio
    async def test_create_scheduled_reconciliation_monthly(
        self, service: AutomationRuleService, mock_rule_repo: AsyncMock
    ):
        """Requirement 19.1: Create monthly scheduled reconciliation rule."""
        dto = RuleCreateDTO(
            company_code="CC01",
            rule_type=RuleType.SCHEDULED_RECONCILIATION.value,
            name="Monthly Recon",
            schedule_config=ScheduleConfig(
                frequency=ScheduleFrequency.MONTHLY.value,
                day_of_month=15,
                time_of_day="03:00",
            ),
        )
        mock_rule_repo.create.return_value = FakeRule(name="Monthly Recon")

        result = await service.create_rule(dto)

        mock_rule_repo.create.assert_called_once()
        call_data = mock_rule_repo.create.call_args[0][0]
        assert call_data["rule_type"] == "scheduled_reconciliation"
        assert call_data["is_active"] is True
        assert call_data["config"]["schedule"]["frequency"] == "monthly"
        assert call_data["config"]["schedule"]["day_of_month"] == 15

    @pytest.mark.asyncio
    async def test_create_scheduled_reconciliation_quarterly(
        self, service: AutomationRuleService, mock_rule_repo: AsyncMock
    ):
        """Requirement 19.1: Create quarterly scheduled reconciliation rule."""
        dto = RuleCreateDTO(
            company_code="CC01",
            rule_type=RuleType.SCHEDULED_RECONCILIATION.value,
            name="Quarterly Recon",
            schedule_config=ScheduleConfig(
                frequency=ScheduleFrequency.QUARTERLY.value,
                quarter_months=[1, 4, 7, 10],
                day_of_month=1,
                time_of_day="02:00",
            ),
        )
        mock_rule_repo.create.return_value = FakeRule(name="Quarterly Recon")

        result = await service.create_rule(dto)

        mock_rule_repo.create.assert_called_once()
        call_data = mock_rule_repo.create.call_args[0][0]
        assert call_data["config"]["schedule"]["frequency"] == "quarterly"
        assert call_data["config"]["schedule"]["quarter_months"] == [1, 4, 7, 10]

    @pytest.mark.asyncio
    async def test_create_auto_match_rule(
        self, service: AutomationRuleService, mock_rule_repo: AsyncMock
    ):
        """Requirement 19.2: Create auto-match rule with confidence threshold."""
        dto = RuleCreateDTO(
            company_code="CC01",
            rule_type=RuleType.AUTO_MATCH.value,
            name="Auto-Match 95%",
            auto_match_config=AutoMatchConfig(
                confidence_threshold=0.95,
                max_amount=Decimal("50000"),
            ),
        )
        mock_rule_repo.create.return_value = FakeRule(
            rule_type="auto_match", name="Auto-Match 95%"
        )

        result = await service.create_rule(dto)

        mock_rule_repo.create.assert_called_once()
        call_data = mock_rule_repo.create.call_args[0][0]
        assert call_data["config"]["auto_match"]["confidence_threshold"] == 0.95
        assert call_data["config"]["auto_match"]["max_amount"] == 50000.0

    @pytest.mark.asyncio
    async def test_create_auto_escalation_rule(
        self, service: AutomationRuleService, mock_rule_repo: AsyncMock
    ):
        """Requirement 19.3: Create auto-escalation rule."""
        dto = RuleCreateDTO(
            company_code="CC01",
            rule_type=RuleType.AUTO_ESCALATION.value,
            name="Escalate after 7 days",
            auto_escalation_config=AutoEscalationConfig(
                days_without_progress=7,
                target=EscalationTarget.MANAGER.value,
            ),
        )
        mock_rule_repo.create.return_value = FakeRule(
            rule_type="auto_escalation", name="Escalate after 7 days"
        )

        result = await service.create_rule(dto)

        mock_rule_repo.create.assert_called_once()
        call_data = mock_rule_repo.create.call_args[0][0]
        assert call_data["config"]["auto_escalation"]["days_without_progress"] == 7
        assert call_data["config"]["auto_escalation"]["target"] == "manager"

    @pytest.mark.asyncio
    async def test_create_rule_invalid_type_raises(
        self, service: AutomationRuleService
    ):
        """Requirement 19.6: Invalid rule type raises ValueError."""
        dto = RuleCreateDTO(
            company_code="CC01",
            rule_type="invalid_type",
            name="Bad Rule",
        )

        with pytest.raises(ValueError, match="Invalid rule type"):
            await service.create_rule(dto)

    @pytest.mark.asyncio
    async def test_create_scheduled_rule_without_config_raises(
        self, service: AutomationRuleService
    ):
        """Requirement 19.6: Missing config for scheduled rule raises ValueError."""
        dto = RuleCreateDTO(
            company_code="CC01",
            rule_type=RuleType.SCHEDULED_RECONCILIATION.value,
            name="No Config",
        )

        with pytest.raises(ValueError, match="Schedule configuration is required"):
            await service.create_rule(dto)


# ─── Validation Tests ─────────────────────────────────────────────────────────


class TestValidation:
    """Tests for rule configuration validation."""

    @pytest.mark.asyncio
    async def test_monthly_schedule_invalid_day(
        self, service: AutomationRuleService
    ):
        """Requirement 19.6: day_of_month must be 1-28."""
        dto = RuleCreateDTO(
            company_code="CC01",
            rule_type=RuleType.SCHEDULED_RECONCILIATION.value,
            name="Bad Day",
            schedule_config=ScheduleConfig(
                frequency=ScheduleFrequency.MONTHLY.value,
                day_of_month=31,
            ),
        )

        with pytest.raises(ValueError, match="day_of_month must be between 1 and 28"):
            await service.create_rule(dto)

    @pytest.mark.asyncio
    async def test_monthly_schedule_missing_day(
        self, service: AutomationRuleService
    ):
        """Requirement 19.6: day_of_month required for monthly."""
        dto = RuleCreateDTO(
            company_code="CC01",
            rule_type=RuleType.SCHEDULED_RECONCILIATION.value,
            name="No Day",
            schedule_config=ScheduleConfig(
                frequency=ScheduleFrequency.MONTHLY.value,
            ),
        )

        with pytest.raises(ValueError, match="day_of_month is required"):
            await service.create_rule(dto)

    @pytest.mark.asyncio
    async def test_weekly_schedule_invalid_day_of_week(
        self, service: AutomationRuleService
    ):
        """Requirement 19.6: day_of_week must be 0-6."""
        dto = RuleCreateDTO(
            company_code="CC01",
            rule_type=RuleType.SCHEDULED_RECONCILIATION.value,
            name="Bad Day of Week",
            schedule_config=ScheduleConfig(
                frequency=ScheduleFrequency.WEEKLY.value,
                day_of_week=7,
            ),
        )

        with pytest.raises(ValueError, match="day_of_week must be between 0"):
            await service.create_rule(dto)

    @pytest.mark.asyncio
    async def test_auto_match_confidence_below_minimum(
        self, service: AutomationRuleService
    ):
        """Requirement 19.6: Confidence threshold must be >= MIN."""
        dto = RuleCreateDTO(
            company_code="CC01",
            rule_type=RuleType.AUTO_MATCH.value,
            name="Low Confidence",
            auto_match_config=AutoMatchConfig(
                confidence_threshold=0.50,
            ),
        )

        with pytest.raises(ValueError, match="Confidence threshold must be at least"):
            await service.create_rule(dto)

    @pytest.mark.asyncio
    async def test_auto_match_confidence_above_maximum(
        self, service: AutomationRuleService
    ):
        """Requirement 19.6: Confidence threshold must be <= MAX."""
        dto = RuleCreateDTO(
            company_code="CC01",
            rule_type=RuleType.AUTO_MATCH.value,
            name="Too High",
            auto_match_config=AutoMatchConfig(
                confidence_threshold=1.5,
            ),
        )

        with pytest.raises(ValueError, match="Confidence threshold cannot exceed"):
            await service.create_rule(dto)

    @pytest.mark.asyncio
    async def test_auto_match_negative_max_amount(
        self, service: AutomationRuleService
    ):
        """Requirement 19.6: max_amount must be positive."""
        dto = RuleCreateDTO(
            company_code="CC01",
            rule_type=RuleType.AUTO_MATCH.value,
            name="Negative Amount",
            auto_match_config=AutoMatchConfig(
                confidence_threshold=0.95,
                max_amount=Decimal("-100"),
            ),
        )

        with pytest.raises(ValueError, match="max_amount must be positive"):
            await service.create_rule(dto)

    @pytest.mark.asyncio
    async def test_auto_escalation_zero_days(
        self, service: AutomationRuleService
    ):
        """Requirement 19.6: days_without_progress must be >= 1."""
        dto = RuleCreateDTO(
            company_code="CC01",
            rule_type=RuleType.AUTO_ESCALATION.value,
            name="Zero Days",
            auto_escalation_config=AutoEscalationConfig(
                days_without_progress=0,
            ),
        )

        with pytest.raises(ValueError, match="days_without_progress must be at least 1"):
            await service.create_rule(dto)

    @pytest.mark.asyncio
    async def test_auto_escalation_invalid_target(
        self, service: AutomationRuleService
    ):
        """Requirement 19.6: Invalid escalation target raises ValueError."""
        dto = RuleCreateDTO(
            company_code="CC01",
            rule_type=RuleType.AUTO_ESCALATION.value,
            name="Bad Target",
            auto_escalation_config=AutoEscalationConfig(
                days_without_progress=5,
                target="intern",
            ),
        )

        with pytest.raises(ValueError, match="Invalid escalation target"):
            await service.create_rule(dto)


# ─── Enable/Disable Tests ─────────────────────────────────────────────────────


class TestEnableDisable:
    """Tests for enabling/disabling rules without deletion."""

    @pytest.mark.asyncio
    async def test_enable_rule(
        self, service: AutomationRuleService, mock_rule_repo: AsyncMock
    ):
        """Requirement 19.5: Enable a disabled rule."""
        rule = FakeRule(is_active=False)
        mock_rule_repo.get_by_id.return_value = rule
        mock_rule_repo.activate.return_value = FakeRule(is_active=True)

        result = await service.enable_rule(rule.id)

        mock_rule_repo.activate.assert_called_once_with(rule.id)

    @pytest.mark.asyncio
    async def test_disable_rule(
        self, service: AutomationRuleService, mock_rule_repo: AsyncMock
    ):
        """Requirement 19.5: Disable an active rule."""
        rule = FakeRule(is_active=True)
        mock_rule_repo.get_by_id.return_value = rule
        mock_rule_repo.deactivate.return_value = FakeRule(is_active=False)

        result = await service.disable_rule(rule.id)

        mock_rule_repo.deactivate.assert_called_once_with(rule.id)

    @pytest.mark.asyncio
    async def test_enable_nonexistent_rule_raises(
        self, service: AutomationRuleService, mock_rule_repo: AsyncMock
    ):
        """Requirement 19.5: Enabling non-existent rule raises ValueError."""
        mock_rule_repo.get_by_id.return_value = None

        with pytest.raises(ValueError, match="not found"):
            await service.enable_rule(uuid4())

    @pytest.mark.asyncio
    async def test_disable_nonexistent_rule_raises(
        self, service: AutomationRuleService, mock_rule_repo: AsyncMock
    ):
        """Requirement 19.5: Disabling non-existent rule raises ValueError."""
        mock_rule_repo.get_by_id.return_value = None

        with pytest.raises(ValueError, match="not found"):
            await service.disable_rule(uuid4())


# ─── Auto-Match Execution Tests ───────────────────────────────────────────────


class TestAutoMatchExecution:
    """Tests for auto-match rule execution."""

    @pytest.mark.asyncio
    async def test_auto_accept_above_threshold(
        self,
        service: AutomationRuleService,
        mock_case_repo: AsyncMock,
        mock_match_repo: AsyncMock,
    ):
        """Requirement 19.2: Auto-accept matches above confidence threshold."""
        case = FakeCase()
        match1 = FakeMatch(case_id=case.id, confidence_score=0.98)
        match2 = FakeMatch(case_id=case.id, confidence_score=0.96)

        mock_case_repo.list_cases.return_value = FakePaginatedResult(
            items=[case], total=1
        )
        mock_match_repo.get_unconfirmed_by_case.return_value = [match1, match2]

        rule = FakeRule(
            rule_type=RuleType.AUTO_MATCH.value,
            config={"auto_match": {"confidence_threshold": 0.95, "max_amount": None, "exclude_vendor_ids": []}},
        )

        result = await service.execute_auto_match(rule)

        assert result.matches_accepted == 2
        assert result.matches_skipped == 0
        assert result.cases_processed == 1
        assert mock_match_repo.confirm_match.call_count == 2

    @pytest.mark.asyncio
    async def test_skip_below_threshold(
        self,
        service: AutomationRuleService,
        mock_case_repo: AsyncMock,
        mock_match_repo: AsyncMock,
    ):
        """Requirement 19.2: Skip matches below confidence threshold."""
        case = FakeCase()
        low_match = FakeMatch(case_id=case.id, confidence_score=0.80)

        mock_case_repo.list_cases.return_value = FakePaginatedResult(
            items=[case], total=1
        )
        mock_match_repo.get_unconfirmed_by_case.return_value = [low_match]

        rule = FakeRule(
            rule_type=RuleType.AUTO_MATCH.value,
            config={"auto_match": {"confidence_threshold": 0.95, "max_amount": None, "exclude_vendor_ids": []}},
        )

        result = await service.execute_auto_match(rule)

        assert result.matches_accepted == 0
        assert result.matches_skipped == 1
        mock_match_repo.confirm_match.assert_not_called()

    @pytest.mark.asyncio
    async def test_skip_above_max_amount(
        self,
        service: AutomationRuleService,
        mock_case_repo: AsyncMock,
        mock_match_repo: AsyncMock,
    ):
        """Requirement 19.2: Skip matches exceeding max amount."""
        case = FakeCase()
        big_match = FakeMatch(
            case_id=case.id, confidence_score=0.99, matched_amount=Decimal("100000")
        )

        mock_case_repo.list_cases.return_value = FakePaginatedResult(
            items=[case], total=1
        )
        mock_match_repo.get_unconfirmed_by_case.return_value = [big_match]

        rule = FakeRule(
            rule_type=RuleType.AUTO_MATCH.value,
            config={"auto_match": {"confidence_threshold": 0.95, "max_amount": 50000.0, "exclude_vendor_ids": []}},
        )

        result = await service.execute_auto_match(rule)

        assert result.matches_accepted == 0
        assert result.matches_skipped == 1

    @pytest.mark.asyncio
    async def test_exclude_vendor_ids(
        self,
        service: AutomationRuleService,
        mock_case_repo: AsyncMock,
        mock_match_repo: AsyncMock,
    ):
        """Requirement 19.2: Exclude specific vendors from auto-matching."""
        excluded_vendor_id = uuid4()
        case = FakeCase(vendor_id=excluded_vendor_id)

        mock_case_repo.list_cases.return_value = FakePaginatedResult(
            items=[case], total=1
        )

        rule = FakeRule(
            rule_type=RuleType.AUTO_MATCH.value,
            config={
                "auto_match": {
                    "confidence_threshold": 0.95,
                    "max_amount": None,
                    "exclude_vendor_ids": [str(excluded_vendor_id)],
                }
            },
        )

        result = await service.execute_auto_match(rule)

        assert result.cases_processed == 0
        mock_match_repo.get_unconfirmed_by_case.assert_not_called()


# ─── Auto-Escalation Execution Tests ──────────────────────────────────────────


class TestAutoEscalationExecution:
    """Tests for auto-escalation rule execution."""

    @pytest.mark.asyncio
    async def test_escalate_stale_case(
        self,
        service: AutomationRuleService,
        mock_case_repo: AsyncMock,
    ):
        """Requirement 19.3: Escalate cases without progress beyond threshold."""
        stale_case = FakeCase(
            status="in_progress",
            updated_at=datetime.now(timezone.utc) - timedelta(days=10),
        )
        mock_case_repo.list_cases.return_value = FakePaginatedResult(
            items=[stale_case], total=1
        )

        rule = FakeRule(
            rule_type=RuleType.AUTO_ESCALATION.value,
            config={
                "auto_escalation": {
                    "days_without_progress": 7,
                    "target": "manager",
                    "notify_assignee": True,
                    "include_case_statuses": ["in_progress", "pending_vendor"],
                }
            },
        )

        result = await service.execute_auto_escalation(rule)

        assert result.cases_escalated == 1
        assert result.notifications_sent == 1
        assert result.cases_checked == 1
        mock_case_repo.update.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_escalation_for_fresh_case(
        self,
        service: AutomationRuleService,
        mock_case_repo: AsyncMock,
    ):
        """Requirement 19.3: Don't escalate cases with recent progress."""
        fresh_case = FakeCase(
            status="in_progress",
            updated_at=datetime.now(timezone.utc) - timedelta(days=2),
        )
        mock_case_repo.list_cases.return_value = FakePaginatedResult(
            items=[fresh_case], total=1
        )

        rule = FakeRule(
            rule_type=RuleType.AUTO_ESCALATION.value,
            config={
                "auto_escalation": {
                    "days_without_progress": 7,
                    "target": "manager",
                    "notify_assignee": True,
                    "include_case_statuses": ["in_progress", "pending_vendor"],
                }
            },
        )

        result = await service.execute_auto_escalation(rule)

        assert result.cases_escalated == 0
        assert result.cases_checked == 1
        mock_case_repo.update.assert_not_called()

    @pytest.mark.asyncio
    async def test_skip_excluded_status(
        self,
        service: AutomationRuleService,
        mock_case_repo: AsyncMock,
    ):
        """Requirement 19.3: Only escalate cases with included statuses."""
        closed_case = FakeCase(
            status="closed",
            updated_at=datetime.now(timezone.utc) - timedelta(days=30),
        )
        mock_case_repo.list_cases.return_value = FakePaginatedResult(
            items=[closed_case], total=1
        )

        rule = FakeRule(
            rule_type=RuleType.AUTO_ESCALATION.value,
            config={
                "auto_escalation": {
                    "days_without_progress": 7,
                    "target": "manager",
                    "notify_assignee": True,
                    "include_case_statuses": ["in_progress", "pending_vendor"],
                }
            },
        )

        result = await service.execute_auto_escalation(rule)

        assert result.cases_escalated == 0
        assert result.cases_checked == 0

    @pytest.mark.asyncio
    async def test_no_notification_when_disabled(
        self,
        service: AutomationRuleService,
        mock_case_repo: AsyncMock,
    ):
        """Requirement 19.3: Don't send notification when notify_assignee is False."""
        stale_case = FakeCase(
            status="in_progress",
            updated_at=datetime.now(timezone.utc) - timedelta(days=10),
        )
        mock_case_repo.list_cases.return_value = FakePaginatedResult(
            items=[stale_case], total=1
        )

        rule = FakeRule(
            rule_type=RuleType.AUTO_ESCALATION.value,
            config={
                "auto_escalation": {
                    "days_without_progress": 7,
                    "target": "senior_manager",
                    "notify_assignee": False,
                    "include_case_statuses": ["in_progress"],
                }
            },
        )

        result = await service.execute_auto_escalation(rule)

        assert result.cases_escalated == 1
        assert result.notifications_sent == 0


# ─── Execution History Tests ──────────────────────────────────────────────────


class TestExecutionHistory:
    """Tests for execution history recording."""

    @pytest.mark.asyncio
    async def test_record_execution_success(
        self, service: AutomationRuleService, mock_rule_repo: AsyncMock
    ):
        """Requirement 19.4: Record execution with trigger time, rule ID, outcome."""
        rule_id = uuid4()
        trigger_time = datetime.now(timezone.utc)

        record = await service.record_execution(
            rule_id=rule_id,
            trigger_time=trigger_time,
            outcome=ExecutionOutcome.SUCCESS,
            details="Processed 5 cases",
            cases_affected=5,
            matches_auto_accepted=3,
        )

        assert record.rule_id == rule_id
        assert record.trigger_time == trigger_time
        assert record.outcome == ExecutionOutcome.SUCCESS.value
        assert record.cases_affected == 5
        assert record.matches_auto_accepted == 3
        assert record.completed_at is not None
        mock_rule_repo.record_execution.assert_called_once()

    @pytest.mark.asyncio
    async def test_record_execution_failure(
        self, service: AutomationRuleService, mock_rule_repo: AsyncMock
    ):
        """Requirement 19.4: Record failed executions."""
        rule_id = uuid4()
        trigger_time = datetime.now(timezone.utc)

        record = await service.record_execution(
            rule_id=rule_id,
            trigger_time=trigger_time,
            outcome=ExecutionOutcome.FAILURE,
            details="Database connection failed",
        )

        assert record.outcome == ExecutionOutcome.FAILURE.value
        assert record.details == "Database connection failed"
        mock_rule_repo.record_execution.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_execution_history(
        self, service: AutomationRuleService, mock_rule_repo: AsyncMock
    ):
        """Requirement 19.4: Retrieve execution history for a rule."""
        rule_id = uuid4()
        mock_rule_repo.get_execution_history.return_value = FakePaginatedResult(
            items=[], total=0
        )

        result = await service.get_execution_history(rule_id)

        mock_rule_repo.get_execution_history.assert_called_once_with(rule_id, None)


# ─── Due Rule Execution Tests ─────────────────────────────────────────────────


class TestDueRuleExecution:
    """Tests for executing due rules."""

    @pytest.mark.asyncio
    async def test_execute_due_auto_match_rule(
        self,
        service: AutomationRuleService,
        mock_rule_repo: AsyncMock,
        mock_case_repo: AsyncMock,
        mock_match_repo: AsyncMock,
    ):
        """Requirement 19.7: Execute due auto-match rules."""
        case = FakeCase()
        match = FakeMatch(case_id=case.id, confidence_score=0.99)
        rule = FakeRule(
            rule_type=RuleType.AUTO_MATCH.value,
            is_active=True,
            config={"auto_match": {"confidence_threshold": 0.95, "max_amount": None, "exclude_vendor_ids": []}},
        )

        mock_rule_repo.get_due_rules.return_value = [rule]
        mock_case_repo.list_cases.return_value = FakePaginatedResult(
            items=[case], total=1
        )
        mock_match_repo.get_unconfirmed_by_case.return_value = [match]

        records = await service.execute_due_rules()

        assert len(records) == 1
        assert records[0].outcome == ExecutionOutcome.SUCCESS.value
        assert records[0].matches_auto_accepted == 1
        mock_rule_repo.record_execution.assert_called_once()
        mock_rule_repo.update.assert_called_once()

    @pytest.mark.asyncio
    async def test_skip_inactive_due_rules(
        self,
        service: AutomationRuleService,
        mock_rule_repo: AsyncMock,
    ):
        """Requirement 19.7: Inactive rules are not executed."""
        inactive_rule = FakeRule(
            rule_type=RuleType.AUTO_MATCH.value,
            is_active=False,
        )
        mock_rule_repo.get_due_rules.return_value = [inactive_rule]

        records = await service.execute_due_rules()

        assert len(records) == 0
        mock_rule_repo.record_execution.assert_not_called()

    @pytest.mark.asyncio
    async def test_execute_due_escalation_rule(
        self,
        service: AutomationRuleService,
        mock_rule_repo: AsyncMock,
        mock_case_repo: AsyncMock,
    ):
        """Requirement 19.7: Execute due auto-escalation rules."""
        stale_case = FakeCase(
            status="in_progress",
            updated_at=datetime.now(timezone.utc) - timedelta(days=14),
        )
        rule = FakeRule(
            rule_type=RuleType.AUTO_ESCALATION.value,
            is_active=True,
            config={
                "auto_escalation": {
                    "days_without_progress": 7,
                    "target": "manager",
                    "notify_assignee": True,
                    "include_case_statuses": ["in_progress"],
                }
            },
        )

        mock_rule_repo.get_due_rules.return_value = [rule]
        mock_case_repo.list_cases.return_value = FakePaginatedResult(
            items=[stale_case], total=1
        )

        records = await service.execute_due_rules()

        assert len(records) == 1
        assert records[0].outcome == ExecutionOutcome.SUCCESS.value
        assert records[0].escalations_triggered == 1

    @pytest.mark.asyncio
    async def test_execute_due_rule_handles_exception(
        self,
        service: AutomationRuleService,
        mock_rule_repo: AsyncMock,
        mock_case_repo: AsyncMock,
    ):
        """Requirement 19.7: Execution exceptions are recorded as failures."""
        rule = FakeRule(
            rule_type=RuleType.AUTO_MATCH.value,
            is_active=True,
            config={"auto_match": {"confidence_threshold": 0.95, "max_amount": None, "exclude_vendor_ids": []}},
        )
        mock_rule_repo.get_due_rules.return_value = [rule]
        mock_case_repo.list_cases.side_effect = RuntimeError("DB connection lost")

        records = await service.execute_due_rules()

        assert len(records) == 1
        assert records[0].outcome == ExecutionOutcome.FAILURE.value
        assert "DB connection lost" in records[0].details


# ─── Update Rule Tests ────────────────────────────────────────────────────────


class TestUpdateRule:
    """Tests for rule update operations."""

    @pytest.mark.asyncio
    async def test_update_rule_name(
        self, service: AutomationRuleService, mock_rule_repo: AsyncMock
    ):
        """Update a rule's name."""
        rule = FakeRule(rule_type=RuleType.AUTO_MATCH.value)
        mock_rule_repo.get_by_id.return_value = rule
        mock_rule_repo.update.return_value = FakeRule(name="Updated Name")

        dto = RuleUpdateDTO(name="Updated Name")
        result = await service.update_rule(rule.id, dto)

        mock_rule_repo.update.assert_called_once()
        call_data = mock_rule_repo.update.call_args[0][1]
        assert call_data["name"] == "Updated Name"

    @pytest.mark.asyncio
    async def test_update_nonexistent_rule_raises(
        self, service: AutomationRuleService, mock_rule_repo: AsyncMock
    ):
        """Update non-existent rule raises ValueError."""
        mock_rule_repo.get_by_id.return_value = None

        dto = RuleUpdateDTO(name="New Name")
        with pytest.raises(ValueError, match="not found"):
            await service.update_rule(uuid4(), dto)

    @pytest.mark.asyncio
    async def test_update_rule_with_new_config(
        self, service: AutomationRuleService, mock_rule_repo: AsyncMock
    ):
        """Update rule configuration triggers validation."""
        rule = FakeRule(rule_type=RuleType.AUTO_MATCH.value, company_code="CC01")
        mock_rule_repo.get_by_id.return_value = rule
        mock_rule_repo.update.return_value = rule

        dto = RuleUpdateDTO(
            auto_match_config=AutoMatchConfig(
                confidence_threshold=0.90,
            ),
        )
        result = await service.update_rule(rule.id, dto)

        mock_rule_repo.update.assert_called_once()
        call_data = mock_rule_repo.update.call_args[0][1]
        assert "config" in call_data
        assert call_data["config"]["auto_match"]["confidence_threshold"] == 0.90


# ─── Scheduling Tests ─────────────────────────────────────────────────────────


class TestScheduling:
    """Tests for schedule calculation logic."""

    @pytest.mark.asyncio
    async def test_scheduled_reconciliation_creates_cases(
        self,
        service: AutomationRuleService,
        mock_case_repo: AsyncMock,
    ):
        """Requirement 19.1: Scheduled reconciliation creates cases for vendors."""
        vendor_id = uuid4()
        rule = FakeRule(
            rule_type=RuleType.SCHEDULED_RECONCILIATION.value,
            config={
                "schedule": {
                    "frequency": "monthly",
                    "day_of_month": 15,
                    "vendor_ids": [str(vendor_id)],
                    "time_of_day": "03:00",
                }
            },
        )

        result = await service.execute_scheduled_reconciliation(rule)

        assert result.cases_created == 1
        assert result.vendors_processed == 1
        mock_case_repo.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_scheduled_reconciliation_handles_errors(
        self,
        service: AutomationRuleService,
        mock_case_repo: AsyncMock,
    ):
        """Requirement 19.1: Errors during case creation are captured."""
        vendor_id = uuid4()
        rule = FakeRule(
            rule_type=RuleType.SCHEDULED_RECONCILIATION.value,
            config={
                "schedule": {
                    "frequency": "monthly",
                    "day_of_month": 1,
                    "vendor_ids": [str(vendor_id)],
                    "time_of_day": "02:00",
                }
            },
        )
        mock_case_repo.create.side_effect = RuntimeError("DB error")

        result = await service.execute_scheduled_reconciliation(rule)

        assert result.cases_created == 0
        assert len(result.errors) == 1
        assert "DB error" in result.errors[0]
