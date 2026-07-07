"""
Unit tests for ApprovalEngineService domain logic.

Tests Row_10 zero validation, approve/reject/request-changes decisions,
write-off threshold checks, delegation of approval authority,
and request closure logic.
"""

import pytest
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

from src.domain.exceptions.vlr import (
    CaseClosedException,
    InvalidStatusTransitionException,
    Row10NonZeroException,
)
from src.domain.repositories.vlr.vendor_repository import PaginatedResult
from src.domain.services.vlr.approval_engine_service import (
    ApprovalDecision,
    ApprovalEngineService,
    ApprovalLevel,
    DEFAULT_DELEGATION_MAX_DAYS,
    DEFAULT_WRITE_OFF_THRESHOLD,
    DelegationRecord,
)
from src.domain.services.vlr.exception_manager_service import Row10Result


# ─── Test Helpers ─────────────────────────────────────────────────────────────


@dataclass
class FakeCase:
    """Fake case object for testing."""

    id: UUID = field(default_factory=uuid4)
    request_id: UUID = field(default_factory=uuid4)
    status: str = "review"
    edit_count: int = 0


@dataclass
class FakeRequest:
    """Fake request object for testing."""

    id: UUID = field(default_factory=uuid4)
    assigned_manager: UUID = field(default_factory=uuid4)
    status: str = "review"
    company_code: str = "1000"


@dataclass
class FakeSetting:
    """Fake setting object for testing."""

    id: UUID = field(default_factory=uuid4)
    key: str = "write_off_threshold"
    value: str = "50000"


@dataclass
class FakeApprovalRecord:
    """Fake approval record for testing."""

    id: UUID = field(default_factory=uuid4)
    case_id: UUID = field(default_factory=uuid4)
    decision: str = "submitted"
    comments: str | None = None
    approver_id: UUID = field(default_factory=uuid4)
    approval_level: str = "manager"
    decision_date: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


# ─── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_approval_repo() -> AsyncMock:
    """Create a mock approval repository."""
    repo = AsyncMock()
    repo.get_by_id = AsyncMock(return_value=None)
    repo.create = AsyncMock()
    repo.list_by_case = AsyncMock(
        return_value=PaginatedResult(items=[], total=0, page=1, page_size=50)
    )
    repo.get_pending_approvals = AsyncMock(
        return_value=PaginatedResult(items=[], total=0, page=1, page_size=50)
    )
    repo.get_latest_by_case = AsyncMock(return_value=None)
    repo.count_pending = AsyncMock(return_value=0)
    return repo


@pytest.fixture
def mock_case_repo() -> AsyncMock:
    """Create a mock case repository."""
    repo = AsyncMock()
    repo.get_by_id = AsyncMock(return_value=FakeCase())
    repo.update = AsyncMock()
    repo.count_by_status = AsyncMock(return_value={})
    return repo


@pytest.fixture
def mock_request_repo() -> AsyncMock:
    """Create a mock request repository."""
    repo = AsyncMock()
    repo.get_by_id = AsyncMock(return_value=FakeRequest())
    repo.update = AsyncMock()
    return repo


@pytest.fixture
def mock_setting_repo() -> AsyncMock:
    """Create a mock setting repository."""
    repo = AsyncMock()
    repo.get_by_key = AsyncMock(return_value=None)
    return repo


@pytest.fixture
def mock_exception_manager() -> AsyncMock:
    """Create a mock exception manager service."""
    svc = AsyncMock()
    svc.calculate_row_10 = AsyncMock(
        return_value=Row10Result(
            company_total=Decimal("100000"),
            vendor_total=Decimal("100000"),
            resolved_adjustments=Decimal("0"),
            net_difference=Decimal("0"),
        )
    )
    svc._exception_repo = AsyncMock()
    svc._exception_repo.list_by_case = AsyncMock(
        return_value=PaginatedResult(items=[], total=0, page=1, page_size=50)
    )
    return svc


@pytest.fixture
def approval_service(
    mock_approval_repo: AsyncMock,
    mock_case_repo: AsyncMock,
    mock_request_repo: AsyncMock,
    mock_setting_repo: AsyncMock,
    mock_exception_manager: AsyncMock,
) -> ApprovalEngineService:
    """Create ApprovalEngineService with mocked dependencies."""
    return ApprovalEngineService(
        approval_repository=mock_approval_repo,
        case_repository=mock_case_repo,
        request_repository=mock_request_repo,
        setting_repository=mock_setting_repo,
        exception_manager_service=mock_exception_manager,
    )


# ─── Submission Tests ─────────────────────────────────────────────────────────


class TestSubmitForApproval:
    """Tests for submit_for_approval method."""

    async def test_submit_success_with_zero_row_10(
        self,
        approval_service: ApprovalEngineService,
        mock_case_repo: AsyncMock,
        mock_approval_repo: AsyncMock,
        mock_exception_manager: AsyncMock,
    ):
        """Should submit case when Row_10 is zero."""
        case_id = uuid4()
        submitter = uuid4()
        mock_case_repo.get_by_id.return_value = FakeCase(
            id=case_id, status="review"
        )
        mock_exception_manager.calculate_row_10.return_value = Row10Result(
            company_total=Decimal("100000"),
            vendor_total=Decimal("100000"),
            resolved_adjustments=Decimal("0"),
            net_difference=Decimal("0"),
        )

        result = await approval_service.submit_for_approval(
            case_id=case_id, submitted_by=submitter
        )

        assert result.decision == ApprovalDecision.SUBMITTED.value
        assert result.case_id == case_id
        assert result.approver_id == submitter
        mock_case_repo.update.assert_called_once_with(
            case_id, {"status": "pending_approval"}
        )
        mock_approval_repo.create.assert_called_once()

    async def test_submit_rejected_when_row_10_non_zero(
        self,
        approval_service: ApprovalEngineService,
        mock_case_repo: AsyncMock,
        mock_exception_manager: AsyncMock,
    ):
        """Should reject submission when Row_10 is not zero (Req 7.1, 7.2)."""
        case_id = uuid4()
        mock_case_repo.get_by_id.return_value = FakeCase(
            id=case_id, status="review"
        )
        mock_exception_manager.calculate_row_10.return_value = Row10Result(
            company_total=Decimal("150000"),
            vendor_total=Decimal("100000"),
            resolved_adjustments=Decimal("0"),
            net_difference=Decimal("50000"),
        )

        with pytest.raises(Row10NonZeroException):
            await approval_service.submit_for_approval(
                case_id=case_id, submitted_by=uuid4()
            )

    async def test_submit_rejected_when_case_not_in_review(
        self,
        approval_service: ApprovalEngineService,
        mock_case_repo: AsyncMock,
    ):
        """Should reject submission when case is not in review status."""
        case_id = uuid4()
        mock_case_repo.get_by_id.return_value = FakeCase(
            id=case_id, status="matched"
        )

        with pytest.raises(InvalidStatusTransitionException):
            await approval_service.submit_for_approval(
                case_id=case_id, submitted_by=uuid4()
            )

    async def test_submit_rejected_when_case_closed(
        self,
        approval_service: ApprovalEngineService,
        mock_case_repo: AsyncMock,
    ):
        """Should reject submission when case is closed."""
        case_id = uuid4()
        mock_case_repo.get_by_id.return_value = FakeCase(
            id=case_id, status="closed"
        )

        with pytest.raises(CaseClosedException):
            await approval_service.submit_for_approval(
                case_id=case_id, submitted_by=uuid4()
            )

    async def test_submit_case_not_found_raises(
        self,
        approval_service: ApprovalEngineService,
        mock_case_repo: AsyncMock,
    ):
        """Should raise ValueError when case does not exist."""
        mock_case_repo.get_by_id.return_value = None

        with pytest.raises(ValueError, match="not found"):
            await approval_service.submit_for_approval(
                case_id=uuid4(), submitted_by=uuid4()
            )


# ─── Approve Tests ────────────────────────────────────────────────────────────


class TestApprove:
    """Tests for approve method."""

    async def test_approve_success(
        self,
        approval_service: ApprovalEngineService,
        mock_case_repo: AsyncMock,
        mock_approval_repo: AsyncMock,
    ):
        """Should approve case and transition to approved status (Req 7.4, 7.6)."""
        case_id = uuid4()
        approver = uuid4()
        request_id = uuid4()
        mock_case_repo.get_by_id.return_value = FakeCase(
            id=case_id, status="pending_approval", request_id=request_id
        )
        mock_case_repo.count_by_status.return_value = {
            "pending_approval": 1, "review": 2
        }

        result = await approval_service.approve(
            case_id=case_id,
            approver_id=approver,
            comments="Looks good",
        )

        assert result.decision == ApprovalDecision.APPROVED.value
        assert result.comments == "Looks good"
        assert result.approver_id == approver
        mock_case_repo.update.assert_called_once_with(
            case_id, {"status": "approved"}
        )
        mock_approval_repo.create.assert_called_once()

    async def test_approve_rejected_when_not_pending(
        self,
        approval_service: ApprovalEngineService,
        mock_case_repo: AsyncMock,
    ):
        """Should reject approval when case is not pending_approval."""
        case_id = uuid4()
        mock_case_repo.get_by_id.return_value = FakeCase(
            id=case_id, status="review"
        )

        with pytest.raises(InvalidStatusTransitionException):
            await approval_service.approve(
                case_id=case_id,
                approver_id=uuid4(),
                comments="Approved",
            )

    async def test_approve_without_comments_allowed(
        self,
        approval_service: ApprovalEngineService,
        mock_case_repo: AsyncMock,
        mock_approval_repo: AsyncMock,
    ):
        """Should allow approval without comments."""
        case_id = uuid4()
        mock_case_repo.get_by_id.return_value = FakeCase(
            id=case_id, status="pending_approval"
        )
        mock_case_repo.count_by_status.return_value = {"review": 1}

        result = await approval_service.approve(
            case_id=case_id,
            approver_id=uuid4(),
        )

        assert result.decision == ApprovalDecision.APPROVED.value
        assert result.comments is None


# ─── Reject Tests ─────────────────────────────────────────────────────────────


class TestReject:
    """Tests for reject method."""

    async def test_reject_success(
        self,
        approval_service: ApprovalEngineService,
        mock_case_repo: AsyncMock,
        mock_approval_repo: AsyncMock,
    ):
        """Should reject case and transition back to review (Req 7.4, 7.5)."""
        case_id = uuid4()
        approver = uuid4()
        mock_case_repo.get_by_id.return_value = FakeCase(
            id=case_id, status="pending_approval"
        )

        result = await approval_service.reject(
            case_id=case_id,
            approver_id=approver,
            comments="Needs rework on exception A",
        )

        assert result.decision == ApprovalDecision.REJECTED.value
        assert result.comments == "Needs rework on exception A"
        mock_case_repo.update.assert_called_once_with(
            case_id, {"status": "review"}
        )

    async def test_reject_requires_comments(
        self,
        approval_service: ApprovalEngineService,
        mock_case_repo: AsyncMock,
    ):
        """Should raise ValueError when rejecting without comments."""
        case_id = uuid4()
        mock_case_repo.get_by_id.return_value = FakeCase(
            id=case_id, status="pending_approval"
        )

        with pytest.raises(ValueError, match="Comments are required"):
            await approval_service.reject(
                case_id=case_id,
                approver_id=uuid4(),
                comments="",
            )

    async def test_reject_rejected_when_not_pending(
        self,
        approval_service: ApprovalEngineService,
        mock_case_repo: AsyncMock,
    ):
        """Should reject when case is not in pending_approval status."""
        case_id = uuid4()
        mock_case_repo.get_by_id.return_value = FakeCase(
            id=case_id, status="approved"
        )

        with pytest.raises(InvalidStatusTransitionException):
            await approval_service.reject(
                case_id=case_id,
                approver_id=uuid4(),
                comments="Rejected",
            )


# ─── Request Changes Tests ────────────────────────────────────────────────────


class TestRequestChanges:
    """Tests for request_changes method."""

    async def test_request_changes_success(
        self,
        approval_service: ApprovalEngineService,
        mock_case_repo: AsyncMock,
        mock_approval_repo: AsyncMock,
    ):
        """Should request changes and transition back to review (Req 7.4, 7.5)."""
        case_id = uuid4()
        mock_case_repo.get_by_id.return_value = FakeCase(
            id=case_id, status="pending_approval"
        )

        result = await approval_service.request_changes(
            case_id=case_id,
            approver_id=uuid4(),
            comments="Please clarify write-off rationale",
        )

        assert result.decision == ApprovalDecision.CHANGES_REQUESTED.value
        assert result.comments == "Please clarify write-off rationale"
        mock_case_repo.update.assert_called_once_with(
            case_id, {"status": "review"}
        )

    async def test_request_changes_requires_comments(
        self,
        approval_service: ApprovalEngineService,
        mock_case_repo: AsyncMock,
    ):
        """Should raise ValueError when requesting changes without comments."""
        case_id = uuid4()
        mock_case_repo.get_by_id.return_value = FakeCase(
            id=case_id, status="pending_approval"
        )

        with pytest.raises(ValueError, match="Comments are required"):
            await approval_service.request_changes(
                case_id=case_id,
                approver_id=uuid4(),
                comments="",
            )

    async def test_request_changes_rejected_when_not_pending(
        self,
        approval_service: ApprovalEngineService,
        mock_case_repo: AsyncMock,
    ):
        """Should reject when case is not in pending_approval status."""
        case_id = uuid4()
        mock_case_repo.get_by_id.return_value = FakeCase(
            id=case_id, status="review"
        )

        with pytest.raises(InvalidStatusTransitionException):
            await approval_service.request_changes(
                case_id=case_id,
                approver_id=uuid4(),
                comments="Need changes",
            )


# ─── Write-Off Threshold Tests ────────────────────────────────────────────────


class TestWriteOffThreshold:
    """Tests for write-off threshold check."""

    async def test_threshold_exceeded_returns_true(
        self,
        approval_service: ApprovalEngineService,
        mock_exception_manager: AsyncMock,
    ):
        """Should return True when write-off exceeds threshold (Req 7.7)."""
        case_id = uuid4()
        # Mock exception repo to return resolved exceptions with large amounts
        @dataclass
        class FakeExc:
            amount: Decimal = Decimal("60000")
            status: str = "resolved"

        mock_exception_manager._exception_repo.list_by_case.return_value = (
            PaginatedResult(
                items=[FakeExc()], total=1, page=1, page_size=50
            )
        )

        result = await approval_service.check_write_off_threshold(case_id)
        assert result is True

    async def test_threshold_not_exceeded_returns_false(
        self,
        approval_service: ApprovalEngineService,
        mock_exception_manager: AsyncMock,
    ):
        """Should return False when write-off is within threshold."""
        case_id = uuid4()
        mock_exception_manager._exception_repo.list_by_case.return_value = (
            PaginatedResult(items=[], total=0, page=1, page_size=50)
        )

        result = await approval_service.check_write_off_threshold(case_id)
        assert result is False

    async def test_threshold_uses_custom_setting(
        self,
        approval_service: ApprovalEngineService,
        mock_setting_repo: AsyncMock,
        mock_exception_manager: AsyncMock,
    ):
        """Should use custom threshold from settings."""
        case_id = uuid4()
        # Set custom threshold to 10,000
        mock_setting_repo.get_by_key.return_value = FakeSetting(
            key="write_off_threshold", value="10000"
        )

        @dataclass
        class FakeExc:
            amount: Decimal = Decimal("15000")
            status: str = "resolved"

        mock_exception_manager._exception_repo.list_by_case.return_value = (
            PaginatedResult(
                items=[FakeExc()], total=1, page=1, page_size=50
            )
        )

        result = await approval_service.check_write_off_threshold(
            case_id, company_code="1000"
        )
        assert result is True


# ─── Delegation Tests ─────────────────────────────────────────────────────────


class TestDelegation:
    """Tests for delegation of approval authority."""

    async def test_delegate_authority_success(
        self,
        approval_service: ApprovalEngineService,
    ):
        """Should create a delegation record (Req 7.9)."""
        from_user = uuid4()
        to_user = uuid4()

        result = await approval_service.delegate_authority(
            from_user_id=from_user,
            to_user_id=to_user,
            duration=timedelta(days=7),
        )

        assert result.from_user_id == from_user
        assert result.to_user_id == to_user
        assert result.is_active is True
        assert result.end_date > result.start_date

    async def test_delegate_to_self_raises(
        self,
        approval_service: ApprovalEngineService,
    ):
        """Should reject delegation to self."""
        user_id = uuid4()

        with pytest.raises(ValueError, match="Cannot delegate"):
            await approval_service.delegate_authority(
                from_user_id=user_id,
                to_user_id=user_id,
            )

    async def test_delegation_enforces_max_duration(
        self,
        approval_service: ApprovalEngineService,
    ):
        """Should cap delegation at maximum duration (30 days)."""
        result = await approval_service.delegate_authority(
            from_user_id=uuid4(),
            to_user_id=uuid4(),
            duration=timedelta(days=90),
        )

        max_days = DEFAULT_DELEGATION_MAX_DAYS
        actual_duration = (result.end_date - result.start_date).days
        assert actual_duration <= max_days

    async def test_delegation_defaults_to_max_days(
        self,
        approval_service: ApprovalEngineService,
    ):
        """Should use default max days when no duration specified."""
        result = await approval_service.delegate_authority(
            from_user_id=uuid4(),
            to_user_id=uuid4(),
        )

        duration_days = (result.end_date - result.start_date).days
        assert duration_days == DEFAULT_DELEGATION_MAX_DAYS

    async def test_new_delegation_deactivates_existing(
        self,
        approval_service: ApprovalEngineService,
    ):
        """Should deactivate previous delegation from same user."""
        from_user = uuid4()
        to_user_1 = uuid4()
        to_user_2 = uuid4()

        first = await approval_service.delegate_authority(
            from_user_id=from_user,
            to_user_id=to_user_1,
        )

        second = await approval_service.delegate_authority(
            from_user_id=from_user,
            to_user_id=to_user_2,
        )

        # First delegation should be deactivated
        active = await approval_service.get_active_delegation(from_user)
        assert active is not None
        assert active.to_user_id == to_user_2

    async def test_revoke_delegation(
        self,
        approval_service: ApprovalEngineService,
    ):
        """Should revoke active delegation."""
        from_user = uuid4()
        to_user = uuid4()

        await approval_service.delegate_authority(
            from_user_id=from_user,
            to_user_id=to_user,
        )

        revoked = await approval_service.revoke_delegation(from_user)
        assert revoked is True

        active = await approval_service.get_active_delegation(from_user)
        assert active is None

    async def test_revoke_nonexistent_delegation(
        self,
        approval_service: ApprovalEngineService,
    ):
        """Should return False when no delegation exists to revoke."""
        revoked = await approval_service.revoke_delegation(uuid4())
        assert revoked is False

    async def test_get_delegations_to_user(
        self,
        approval_service: ApprovalEngineService,
    ):
        """Should return delegations where user is the delegate."""
        delegate_user = uuid4()
        from_user_1 = uuid4()
        from_user_2 = uuid4()

        await approval_service.delegate_authority(
            from_user_id=from_user_1,
            to_user_id=delegate_user,
        )
        await approval_service.delegate_authority(
            from_user_id=from_user_2,
            to_user_id=delegate_user,
        )

        delegations = await approval_service.get_delegations_to_user(
            delegate_user
        )
        assert len(delegations) == 2


# ─── Request Closure Tests ────────────────────────────────────────────────────


class TestRequestClosure:
    """Tests for request closure logic."""

    async def test_request_closes_when_all_cases_signed_off(
        self,
        approval_service: ApprovalEngineService,
        mock_case_repo: AsyncMock,
        mock_request_repo: AsyncMock,
    ):
        """Should close request when all cases are signed off (Req 7.10)."""
        request_id = uuid4()
        mock_case_repo.count_by_status.return_value = {
            "signed_off": 3, "closed": 2
        }

        result = await approval_service._check_and_close_request(
            request_id, company_code="1000"
        )

        assert result is True
        mock_request_repo.update.assert_called_once_with(
            request_id, "1000", {"status": "closed"}
        )

    async def test_request_not_closed_when_cases_pending(
        self,
        approval_service: ApprovalEngineService,
        mock_case_repo: AsyncMock,
        mock_request_repo: AsyncMock,
    ):
        """Should not close request when some cases are still pending."""
        request_id = uuid4()
        mock_case_repo.count_by_status.return_value = {
            "signed_off": 2, "pending_approval": 1
        }

        result = await approval_service._check_and_close_request(
            request_id, company_code="1000"
        )

        assert result is False
        mock_request_repo.update.assert_not_called()

    async def test_request_not_closed_when_no_cases(
        self,
        approval_service: ApprovalEngineService,
        mock_case_repo: AsyncMock,
    ):
        """Should not close request when no cases exist."""
        request_id = uuid4()
        mock_case_repo.count_by_status.return_value = {}

        result = await approval_service._check_and_close_request(
            request_id, company_code="1000"
        )

        assert result is False

    async def test_check_request_closure_eligible(
        self,
        approval_service: ApprovalEngineService,
        mock_case_repo: AsyncMock,
    ):
        """Should correctly determine closure eligibility."""
        request_id = uuid4()
        mock_case_repo.count_by_status.return_value = {
            "signed_off": 5
        }

        eligible = await approval_service.check_request_closure_eligible(
            request_id
        )
        assert eligible is True

    async def test_check_request_closure_not_eligible(
        self,
        approval_service: ApprovalEngineService,
        mock_case_repo: AsyncMock,
    ):
        """Should return False when not all cases are complete."""
        request_id = uuid4()
        mock_case_repo.count_by_status.return_value = {
            "signed_off": 3, "review": 2
        }

        eligible = await approval_service.check_request_closure_eligible(
            request_id
        )
        assert eligible is False


# ─── Authorization Tests ──────────────────────────────────────────────────────


class TestAuthorization:
    """Tests for approver authorization checks."""

    async def test_assigned_manager_is_authorized(
        self,
        approval_service: ApprovalEngineService,
        mock_case_repo: AsyncMock,
        mock_request_repo: AsyncMock,
    ):
        """Should authorize the assigned manager."""
        manager_id = uuid4()
        case_id = uuid4()
        request_id = uuid4()

        mock_case_repo.get_by_id.return_value = FakeCase(
            id=case_id, request_id=request_id
        )
        mock_request_repo.get_by_id.return_value = FakeRequest(
            id=request_id, assigned_manager=manager_id
        )

        is_auth = await approval_service.is_authorized_approver(
            manager_id, case_id
        )
        assert is_auth is True

    async def test_delegate_is_authorized(
        self,
        approval_service: ApprovalEngineService,
        mock_case_repo: AsyncMock,
        mock_request_repo: AsyncMock,
    ):
        """Should authorize a delegate of the assigned manager."""
        manager_id = uuid4()
        delegate_id = uuid4()
        case_id = uuid4()
        request_id = uuid4()

        mock_case_repo.get_by_id.return_value = FakeCase(
            id=case_id, request_id=request_id
        )
        mock_request_repo.get_by_id.return_value = FakeRequest(
            id=request_id, assigned_manager=manager_id
        )

        # Create delegation from manager to delegate
        await approval_service.delegate_authority(
            from_user_id=manager_id,
            to_user_id=delegate_id,
            duration=timedelta(days=7),
        )

        is_auth = await approval_service.is_authorized_approver(
            delegate_id, case_id
        )
        assert is_auth is True

    async def test_unauthorized_user_not_authorized(
        self,
        approval_service: ApprovalEngineService,
        mock_case_repo: AsyncMock,
        mock_request_repo: AsyncMock,
    ):
        """Should not authorize an unrelated user."""
        manager_id = uuid4()
        random_user = uuid4()
        case_id = uuid4()
        request_id = uuid4()

        mock_case_repo.get_by_id.return_value = FakeCase(
            id=case_id, request_id=request_id
        )
        mock_request_repo.get_by_id.return_value = FakeRequest(
            id=request_id, assigned_manager=manager_id
        )

        is_auth = await approval_service.is_authorized_approver(
            random_user, case_id
        )
        assert is_auth is False


# ─── Approval History Tests ───────────────────────────────────────────────────


class TestApprovalHistory:
    """Tests for approval history retrieval."""

    async def test_get_approval_history(
        self,
        approval_service: ApprovalEngineService,
        mock_approval_repo: AsyncMock,
    ):
        """Should return approval history for a case (Req 7.8)."""
        case_id = uuid4()
        records = [
            FakeApprovalRecord(case_id=case_id, decision="submitted"),
            FakeApprovalRecord(case_id=case_id, decision="approved"),
        ]
        mock_approval_repo.list_by_case.return_value = PaginatedResult(
            items=records, total=2, page=1, page_size=50
        )

        history = await approval_service.get_approval_history(case_id)
        assert len(history) == 2

    async def test_get_approval_history_empty(
        self,
        approval_service: ApprovalEngineService,
        mock_approval_repo: AsyncMock,
    ):
        """Should return empty list when no history exists."""
        mock_approval_repo.list_by_case.return_value = PaginatedResult(
            items=[], total=0, page=1, page_size=50
        )

        history = await approval_service.get_approval_history(uuid4())
        assert history == []
