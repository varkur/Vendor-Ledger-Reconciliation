"""
Unit tests for BusinessRulesService.

Tests the 5 centralized business rules:
- One-sided reconciliation closure (Requirements 32.1, 32.2, 32.3)
- Portal link expiry enforcement (Requirements 33.1, 33.2, 33.3)
- Period overlap prevention (Requirements 34.1, 34.2)
- Active vendor validation (Requirements 35.1, 35.2)
- Case closure net-zero condition (Requirements 37.1, 37.2, 37.3)
"""

import pytest
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

from src.domain.services.vlr.business_rules_service import (
    BusinessRulesService,
    CaseClosureNetZeroException,
    NetZeroValidationResult,
    OneSidedClosureMissingJustificationException,
    OneSidedClosureNotApprovedException,
    OneSidedClosureRequest,
    OneSidedClosureResult,
    PeriodOverlapCheckResult,
    PeriodOverlapException,
    PortalLinkExpiredException,
    PortalLinkValidationResult,
    PORTAL_LINK_VALIDITY_DAYS,
    VendorNotActiveException,
    VendorValidationResult,
)


# ─── Test Helpers ─────────────────────────────────────────────────────────────


@dataclass
class FakeCase:
    """Fake case object for testing."""

    id: UUID = field(default_factory=uuid4)
    status: str = "matched"
    net_difference: Decimal | None = Decimal("0")
    closure_type: str | None = None
    closure_justification: str | None = None
    closure_approved_by: str | None = None


@dataclass
class FakeVendor:
    """Fake vendor object for testing."""

    id: UUID = field(default_factory=uuid4)
    vendor_code: str = "V001"
    status: str = "active"
    name: str = "Test Vendor"


@pytest.fixture
def mock_case_repo() -> AsyncMock:
    """Create a mock case repository."""
    repo = AsyncMock()
    repo.get_by_id = AsyncMock(return_value=None)
    repo.update = AsyncMock()
    return repo


@pytest.fixture
def mock_request_repo() -> AsyncMock:
    """Create a mock request repository."""
    repo = AsyncMock()
    repo.has_overlapping_period = AsyncMock(return_value=False)
    return repo


@pytest.fixture
def mock_vendor_repo() -> AsyncMock:
    """Create a mock vendor repository."""
    repo = AsyncMock()
    repo.get_by_id = AsyncMock(return_value=None)
    return repo


@pytest.fixture
def service(
    mock_case_repo: AsyncMock,
    mock_request_repo: AsyncMock,
    mock_vendor_repo: AsyncMock,
) -> BusinessRulesService:
    """Create BusinessRulesService with mocked repositories."""
    return BusinessRulesService(
        case_repository=mock_case_repo,
        request_repository=mock_request_repo,
        vendor_repository=mock_vendor_repo,
    )


@pytest.fixture
def service_no_repos() -> BusinessRulesService:
    """Create BusinessRulesService without repositories (for pure validation tests)."""
    return BusinessRulesService()


# ═══════════════════════════════════════════════════════════════════════════════
# Rule 1: One-Sided Reconciliation Closure
# Requirements: 32.1, 32.2, 32.3
# ═══════════════════════════════════════════════════════════════════════════════


class TestOneSidedClosure:
    """Tests for one-sided reconciliation closure validation."""

    def test_valid_one_sided_closure_approved_by_recon_manager(
        self, service_no_repos: BusinessRulesService
    ):
        """Should approve one-sided closure when Recon_Manager approves with justification."""
        request = OneSidedClosureRequest(
            case_id=uuid4(),
            approver_id="manager@company.com",
            approver_role="Recon_Manager",
            justification="Vendor non-responsive after 3 reminder cycles.",
        )

        result = service_no_repos.validate_one_sided_closure(request)

        assert isinstance(result, OneSidedClosureResult)
        assert result.approved is True
        assert result.case_id == request.case_id
        assert result.approver_id == "manager@company.com"
        assert result.justification == request.justification
        assert result.closure_type == "one_sided"

    def test_one_sided_closure_rejected_without_recon_manager_role(
        self, service_no_repos: BusinessRulesService
    ):
        """Should reject one-sided closure when approver is not Recon_Manager (Req 32.2)."""
        request = OneSidedClosureRequest(
            case_id=uuid4(),
            approver_id="user@company.com",
            approver_role="Finance_User",
            justification="Vendor non-responsive.",
        )

        with pytest.raises(OneSidedClosureNotApprovedException):
            service_no_repos.validate_one_sided_closure(request)

    def test_one_sided_closure_rejected_with_empty_justification(
        self, service_no_repos: BusinessRulesService
    ):
        """Should reject one-sided closure without justification (Req 32.3)."""
        request = OneSidedClosureRequest(
            case_id=uuid4(),
            approver_id="manager@company.com",
            approver_role="Recon_Manager",
            justification="",
        )

        with pytest.raises(OneSidedClosureMissingJustificationException):
            service_no_repos.validate_one_sided_closure(request)

    def test_one_sided_closure_rejected_with_whitespace_justification(
        self, service_no_repos: BusinessRulesService
    ):
        """Should reject one-sided closure with whitespace-only justification."""
        request = OneSidedClosureRequest(
            case_id=uuid4(),
            approver_id="manager@company.com",
            approver_role="Recon_Manager",
            justification="   \t  \n  ",
        )

        with pytest.raises(OneSidedClosureMissingJustificationException):
            service_no_repos.validate_one_sided_closure(request)

    async def test_execute_one_sided_closure_updates_case(
        self, service: BusinessRulesService, mock_case_repo: AsyncMock
    ):
        """Should update case with closure details on execution (Req 32.3)."""
        case_id = uuid4()
        request = OneSidedClosureRequest(
            case_id=case_id,
            approver_id="manager@company.com",
            approver_role="Recon_Manager",
            justification="Vendor non-responsive after all reminders.",
        )

        result = await service.execute_one_sided_closure(request)

        assert result.approved is True
        mock_case_repo.update.assert_called_once_with(
            case_id,
            {
                "closure_type": "one_sided",
                "closure_justification": "Vendor non-responsive after all reminders.",
                "closure_approved_by": "manager@company.com",
                "status": "closed",
            },
        )

    def test_one_sided_closure_various_invalid_roles(
        self, service_no_repos: BusinessRulesService
    ):
        """Should reject one-sided closure for all non-Recon_Manager roles."""
        invalid_roles = ["Finance_User", "Admin", "Viewer", "Vendor", ""]

        for role in invalid_roles:
            request = OneSidedClosureRequest(
                case_id=uuid4(),
                approver_id="user@company.com",
                approver_role=role,
                justification="Valid justification.",
            )

            with pytest.raises(OneSidedClosureNotApprovedException):
                service_no_repos.validate_one_sided_closure(request)


# ═══════════════════════════════════════════════════════════════════════════════
# Rule 2: Portal Link Expiry Enforcement
# Requirements: 33.1, 33.2, 33.3
# ═══════════════════════════════════════════════════════════════════════════════


class TestPortalLinkExpiry:
    """Tests for portal link 90-day expiry enforcement."""

    def test_valid_link_within_90_days(
        self, service_no_repos: BusinessRulesService
    ):
        """Should validate a link created less than 90 days ago (Req 33.1)."""
        created_at = datetime.now(timezone.utc) - timedelta(days=45)

        result = service_no_repos.validate_portal_link_expiry(created_at)

        assert isinstance(result, PortalLinkValidationResult)
        assert result.is_valid is True
        assert result.days_remaining is not None
        assert result.days_remaining >= 44  # approximately 45 days remaining

    def test_expired_link_after_90_days(
        self, service_no_repos: BusinessRulesService
    ):
        """Should reject a link created more than 90 days ago (Req 33.1, 33.2)."""
        created_at = datetime.now(timezone.utc) - timedelta(days=91)

        with pytest.raises(PortalLinkExpiredException) as exc_info:
            service_no_repos.validate_portal_link_expiry(created_at)

        assert "expired" in str(exc_info.value).lower()
        assert "90 days" in str(exc_info.value)

    def test_link_expired_exactly_at_90_days(
        self, service_no_repos: BusinessRulesService
    ):
        """Should reject a link that is exactly at the 90-day boundary."""
        created_at = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        current_time = datetime(2024, 4, 1, 12, 0, 0, tzinfo=timezone.utc)
        # 91 days later → expired

        with pytest.raises(PortalLinkExpiredException):
            service_no_repos.validate_portal_link_expiry(created_at, current_time)

    def test_link_valid_at_day_89(
        self, service_no_repos: BusinessRulesService
    ):
        """Should validate a link at day 89."""
        created_at = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        current_time = created_at + timedelta(days=89)

        result = service_no_repos.validate_portal_link_expiry(created_at, current_time)

        assert result.is_valid is True
        assert result.days_remaining == 1

    def test_link_created_today_is_valid(
        self, service_no_repos: BusinessRulesService
    ):
        """Should validate a link created today."""
        created_at = datetime.now(timezone.utc)

        result = service_no_repos.validate_portal_link_expiry(created_at)

        assert result.is_valid is True
        assert result.days_remaining is not None
        assert result.days_remaining >= 89

    def test_link_with_naive_datetime_treated_as_utc(
        self, service_no_repos: BusinessRulesService
    ):
        """Should handle naive datetime by treating it as UTC."""
        created_at = datetime(2024, 1, 1, 12, 0, 0)  # No timezone
        current_time = datetime(2024, 2, 1, 12, 0, 0, tzinfo=timezone.utc)

        result = service_no_repos.validate_portal_link_expiry(created_at, current_time)

        assert result.is_valid is True

    def test_recon_manager_can_regenerate_link(
        self, service_no_repos: BusinessRulesService
    ):
        """Should allow Recon_Manager to regenerate portal link (Req 33.3)."""
        assert service_no_repos.can_regenerate_portal_link("Recon_Manager") is True

    def test_non_recon_manager_cannot_regenerate_link(
        self, service_no_repos: BusinessRulesService
    ):
        """Should deny non-Recon_Manager from regenerating portal link (Req 33.3)."""
        assert service_no_repos.can_regenerate_portal_link("Finance_User") is False
        assert service_no_repos.can_regenerate_portal_link("Admin") is False
        assert service_no_repos.can_regenerate_portal_link("") is False


# ═══════════════════════════════════════════════════════════════════════════════
# Rule 3: Period Overlap Prevention
# Requirements: 34.1, 34.2
# ═══════════════════════════════════════════════════════════════════════════════


class TestPeriodOverlapPrevention:
    """Tests for reconciliation period overlap prevention."""

    def test_no_overlap_with_empty_existing_periods(
        self, service_no_repos: BusinessRulesService
    ):
        """Should allow creation when no existing periods."""
        result = service_no_repos.check_period_overlap(
            new_period_start=date(2024, 1, 1),
            new_period_end=date(2024, 3, 31),
            existing_periods=[],
        )

        assert isinstance(result, PeriodOverlapCheckResult)
        assert result.has_overlap is False

    def test_no_overlap_with_non_overlapping_period(
        self, service_no_repos: BusinessRulesService
    ):
        """Should allow creation when periods don't overlap."""
        existing = [
            {
                "period_start": date(2024, 4, 1),
                "period_end": date(2024, 6, 30),
                "case_id": uuid4(),
                "case_reference": "CASE-001",
            }
        ]

        result = service_no_repos.check_period_overlap(
            new_period_start=date(2024, 1, 1),
            new_period_end=date(2024, 3, 31),
            existing_periods=existing,
        )

        assert result.has_overlap is False

    def test_overlap_detected_partial(
        self, service_no_repos: BusinessRulesService
    ):
        """Should reject when new period partially overlaps existing (Req 34.1)."""
        case_id = uuid4()
        existing = [
            {
                "period_start": date(2024, 2, 1),
                "period_end": date(2024, 4, 30),
                "case_id": case_id,
                "case_reference": "CASE-001",
            }
        ]

        with pytest.raises(PeriodOverlapException) as exc_info:
            service_no_repos.check_period_overlap(
                new_period_start=date(2024, 1, 1),
                new_period_end=date(2024, 3, 31),
                existing_periods=existing,
            )

        # Requirement 34.2: Return conflicting case reference
        assert exc_info.value.conflicting_case_reference == "CASE-001"
        assert "CASE-001" in str(exc_info.value)

    def test_overlap_detected_contained(
        self, service_no_repos: BusinessRulesService
    ):
        """Should reject when new period is contained within existing."""
        existing = [
            {
                "period_start": date(2024, 1, 1),
                "period_end": date(2024, 12, 31),
                "case_id": uuid4(),
                "case_reference": "CASE-FULL-YEAR",
            }
        ]

        with pytest.raises(PeriodOverlapException) as exc_info:
            service_no_repos.check_period_overlap(
                new_period_start=date(2024, 3, 1),
                new_period_end=date(2024, 5, 31),
                existing_periods=existing,
            )

        assert exc_info.value.conflicting_case_reference == "CASE-FULL-YEAR"

    def test_overlap_detected_identical_period(
        self, service_no_repos: BusinessRulesService
    ):
        """Should reject when new period is identical to existing."""
        existing = [
            {
                "period_start": date(2024, 1, 1),
                "period_end": date(2024, 3, 31),
                "case_id": uuid4(),
                "case_reference": "CASE-DUPLICATE",
            }
        ]

        with pytest.raises(PeriodOverlapException):
            service_no_repos.check_period_overlap(
                new_period_start=date(2024, 1, 1),
                new_period_end=date(2024, 3, 31),
                existing_periods=existing,
            )

    def test_overlap_on_same_end_start_date(
        self, service_no_repos: BusinessRulesService
    ):
        """Should detect overlap when new period starts on existing period's end date."""
        existing = [
            {
                "period_start": date(2024, 1, 1),
                "period_end": date(2024, 3, 31),
                "case_id": uuid4(),
                "case_reference": "CASE-ADJ",
            }
        ]

        with pytest.raises(PeriodOverlapException):
            service_no_repos.check_period_overlap(
                new_period_start=date(2024, 3, 31),
                new_period_end=date(2024, 6, 30),
                existing_periods=existing,
            )

    async def test_validate_period_no_overlap_uses_repository(
        self, service: BusinessRulesService, mock_request_repo: AsyncMock
    ):
        """Should delegate to repository for database-level overlap check."""
        mock_request_repo.has_overlapping_period.return_value = False
        vendor_id = uuid4()

        result = await service.validate_period_no_overlap(
            vendor_id=vendor_id,
            company_code="CC01",
            period_start=date(2024, 1, 1),
            period_end=date(2024, 3, 31),
        )

        assert result.has_overlap is False
        mock_request_repo.has_overlapping_period.assert_called_once()

    async def test_validate_period_overlap_from_repository(
        self, service: BusinessRulesService, mock_request_repo: AsyncMock
    ):
        """Should raise PeriodOverlapException when repository detects overlap."""
        mock_request_repo.has_overlapping_period.return_value = True

        with pytest.raises(PeriodOverlapException):
            await service.validate_period_no_overlap(
                vendor_id=uuid4(),
                company_code="CC01",
                period_start=date(2024, 1, 1),
                period_end=date(2024, 3, 31),
            )


# ═══════════════════════════════════════════════════════════════════════════════
# Rule 4: Active Vendor Validation
# Requirements: 35.1, 35.2
# ═══════════════════════════════════════════════════════════════════════════════


class TestActiveVendorValidation:
    """Tests for active vendor validation on request creation."""

    def test_active_vendor_passes_validation(
        self, service_no_repos: BusinessRulesService
    ):
        """Should allow reconciliation for active vendors (Req 35.1)."""
        result = service_no_repos.validate_vendor_active("active", "V001")

        assert isinstance(result, VendorValidationResult)
        assert result.is_active is True
        assert result.vendor_code == "V001"

    def test_inactive_vendor_rejected(
        self, service_no_repos: BusinessRulesService
    ):
        """Should reject reconciliation for inactive vendors (Req 35.1, 35.2)."""
        with pytest.raises(VendorNotActiveException) as exc_info:
            service_no_repos.validate_vendor_active("inactive", "V002")

        assert "V002" in str(exc_info.value)
        assert "inactive" in str(exc_info.value).lower()

    def test_suspended_vendor_rejected(
        self, service_no_repos: BusinessRulesService
    ):
        """Should reject reconciliation for suspended vendors."""
        with pytest.raises(VendorNotActiveException):
            service_no_repos.validate_vendor_active("suspended", "V003")

    def test_blocked_vendor_rejected(
        self, service_no_repos: BusinessRulesService
    ):
        """Should reject reconciliation for blocked vendors."""
        with pytest.raises(VendorNotActiveException):
            service_no_repos.validate_vendor_active("blocked", "V004")

    def test_case_insensitive_active_check(
        self, service_no_repos: BusinessRulesService
    ):
        """Should accept 'Active', 'ACTIVE', 'active' as valid status."""
        # The service converts to lower() for comparison
        result = service_no_repos.validate_vendor_active("Active", "V001")
        assert result.is_active is True

        result = service_no_repos.validate_vendor_active("ACTIVE", "V001")
        assert result.is_active is True

    def test_vendor_code_included_in_error_message(
        self, service_no_repos: BusinessRulesService
    ):
        """Should include vendor code in the rejection message (Req 35.2)."""
        with pytest.raises(VendorNotActiveException) as exc_info:
            service_no_repos.validate_vendor_active("inactive", "VENDOR-XYZ")

        assert "VENDOR-XYZ" in str(exc_info.value)

    async def test_validate_vendor_active_by_id_success(
        self, service: BusinessRulesService, mock_vendor_repo: AsyncMock
    ):
        """Should validate active vendor by repository lookup."""
        vendor = FakeVendor(status="active", vendor_code="V001")
        mock_vendor_repo.get_by_id.return_value = vendor

        result = await service.validate_vendor_active_by_id(vendor.id, "CC01")

        assert result.is_active is True
        mock_vendor_repo.get_by_id.assert_called_once_with(vendor.id, "CC01")

    async def test_validate_vendor_active_by_id_inactive_raises(
        self, service: BusinessRulesService, mock_vendor_repo: AsyncMock
    ):
        """Should raise VendorNotActiveException for inactive vendor from repository."""
        vendor = FakeVendor(status="inactive", vendor_code="V-INACTIVE")
        mock_vendor_repo.get_by_id.return_value = vendor

        with pytest.raises(VendorNotActiveException):
            await service.validate_vendor_active_by_id(vendor.id, "CC01")

    async def test_validate_vendor_not_found_raises_value_error(
        self, service: BusinessRulesService, mock_vendor_repo: AsyncMock
    ):
        """Should raise ValueError when vendor is not found."""
        mock_vendor_repo.get_by_id.return_value = None

        with pytest.raises(ValueError, match="not found"):
            await service.validate_vendor_active_by_id(uuid4(), "CC01")


# ═══════════════════════════════════════════════════════════════════════════════
# Rule 5: Case Closure Net-Zero Condition
# Requirements: 37.1, 37.2, 37.3
# ═══════════════════════════════════════════════════════════════════════════════


class TestCaseClosureNetZero:
    """Tests for case closure net-zero condition validation."""

    def test_net_zero_allows_closure(
        self, service_no_repos: BusinessRulesService
    ):
        """Should allow closure when net difference is exactly zero (Req 37.1)."""
        result = service_no_repos.validate_closure_net_zero(Decimal("0"))

        assert isinstance(result, NetZeroValidationResult)
        assert result.can_close is True
        assert result.net_difference == Decimal("0")
        assert result.is_one_sided_approved is False

    def test_positive_net_difference_rejects_closure(
        self, service_no_repos: BusinessRulesService
    ):
        """Should reject closure when net difference is positive (Req 37.2)."""
        with pytest.raises(CaseClosureNetZeroException) as exc_info:
            service_no_repos.validate_closure_net_zero(Decimal("1500.50"))

        assert exc_info.value.net_difference == Decimal("1500.50")
        assert "1500.50" in str(exc_info.value)

    def test_negative_net_difference_rejects_closure(
        self, service_no_repos: BusinessRulesService
    ):
        """Should reject closure when net difference is negative (Req 37.2)."""
        with pytest.raises(CaseClosureNetZeroException) as exc_info:
            service_no_repos.validate_closure_net_zero(Decimal("-250.00"))

        assert exc_info.value.net_difference == Decimal("-250.00")

    def test_one_sided_closure_bypasses_net_zero(
        self, service_no_repos: BusinessRulesService
    ):
        """Should allow closure with non-zero difference when one-sided approved (Req 37.3)."""
        result = service_no_repos.validate_closure_net_zero(
            Decimal("5000.00"),
            is_one_sided_closure_approved=True,
        )

        assert result.can_close is True
        assert result.net_difference == Decimal("5000.00")
        assert result.is_one_sided_approved is True

    def test_one_sided_closure_with_zero_difference(
        self, service_no_repos: BusinessRulesService
    ):
        """Should allow closure with zero difference even with one-sided approval."""
        result = service_no_repos.validate_closure_net_zero(
            Decimal("0"),
            is_one_sided_closure_approved=True,
        )

        assert result.can_close is True
        assert result.is_one_sided_approved is True

    def test_small_non_zero_difference_rejects(
        self, service_no_repos: BusinessRulesService
    ):
        """Should reject even very small non-zero differences."""
        with pytest.raises(CaseClosureNetZeroException):
            service_no_repos.validate_closure_net_zero(Decimal("0.01"))

    def test_decimal_zero_variants(
        self, service_no_repos: BusinessRulesService
    ):
        """Should accept various representations of zero."""
        # Decimal("0.00") should compare equal to Decimal("0")
        result = service_no_repos.validate_closure_net_zero(Decimal("0.00"))
        assert result.can_close is True

    async def test_validate_case_closure_from_repository(
        self, service: BusinessRulesService, mock_case_repo: AsyncMock
    ):
        """Should fetch case and validate net difference from repository."""
        case = FakeCase(net_difference=Decimal("0"), closure_type=None)
        mock_case_repo.get_by_id.return_value = case

        result = await service.validate_case_closure(case.id)

        assert result.can_close is True
        mock_case_repo.get_by_id.assert_called_once_with(case.id)

    async def test_validate_case_closure_non_zero_from_repository(
        self, service: BusinessRulesService, mock_case_repo: AsyncMock
    ):
        """Should reject closure when case has non-zero net difference."""
        case = FakeCase(net_difference=Decimal("1000.00"), closure_type=None)
        mock_case_repo.get_by_id.return_value = case

        with pytest.raises(CaseClosureNetZeroException) as exc_info:
            await service.validate_case_closure(case.id)

        assert exc_info.value.net_difference == Decimal("1000.00")

    async def test_validate_case_closure_one_sided_already_approved(
        self, service: BusinessRulesService, mock_case_repo: AsyncMock
    ):
        """Should allow closure when case already has one-sided closure type."""
        case = FakeCase(
            net_difference=Decimal("2500.00"),
            closure_type="one_sided",
        )
        mock_case_repo.get_by_id.return_value = case

        result = await service.validate_case_closure(case.id)

        assert result.can_close is True
        assert result.is_one_sided_approved is True

    async def test_validate_case_closure_case_not_found(
        self, service: BusinessRulesService, mock_case_repo: AsyncMock
    ):
        """Should raise ValueError when case not found."""
        mock_case_repo.get_by_id.return_value = None

        with pytest.raises(ValueError, match="not found"):
            await service.validate_case_closure(uuid4())

    async def test_validate_case_closure_null_net_difference_treated_as_zero(
        self, service: BusinessRulesService, mock_case_repo: AsyncMock
    ):
        """Should treat null net_difference as zero (case not yet calculated)."""
        case = FakeCase(net_difference=None, closure_type=None)
        mock_case_repo.get_by_id.return_value = case

        result = await service.validate_case_closure(case.id)

        assert result.can_close is True
        assert result.net_difference == Decimal("0")
