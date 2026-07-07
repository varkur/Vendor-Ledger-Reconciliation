"""
Unit tests for RequestManagerService domain logic.

Tests request creation, cloning, status transitions, period overlap
validation, case creation, company ledger confirmation, vendor invitation,
and closed-case edit blocking.

Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9, 3.10
"""

import pytest
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

from src.domain.exceptions.vlr import (
    CaseClosedException,
    CompanyLedgerNotConfirmedException,
    InvalidStatusTransitionException,
    OverlappingPeriodException,
    VendorInactiveException,
)
from src.domain.repositories.vlr.vendor_repository import PaginatedResult
from src.domain.services.vlr.request_manager_service import (
    CaseStatus,
    DateRange,
    MatchingPreferences,
    RequestCreateDTO,
    RequestManagerService,
    RequestStatus,
    VALID_CASE_TRANSITIONS,
    VALID_REQUEST_TRANSITIONS,
)


# ─── Test Helpers ─────────────────────────────────────────────────────────────


@dataclass
class FakeVendor:
    """Fake vendor object for testing."""

    id: UUID = field(default_factory=uuid4)
    vendor_code: str = "V001"
    company_code: str = "CC01"
    name: str = "Test Vendor"
    status: str = "active"


@dataclass
class FakeRequest:
    """Fake request object for testing."""

    id: UUID = field(default_factory=uuid4)
    company_code: str = "CC01"
    fiscal_year: str = "2024"
    period_start: date = field(default_factory=lambda: date(2024, 1, 1))
    period_end: date = field(default_factory=lambda: date(2024, 3, 31))
    status: str = "draft"
    tolerance_amount: Decimal = Decimal("100")
    tds_percentage: Decimal = Decimal("2")
    gst_percentage: Decimal = Decimal("18")
    matching_preferences: dict | None = None
    assigned_manager: UUID | None = None
    created_by: UUID | None = None


@dataclass
class FakeCase:
    """Fake case object for testing."""

    id: UUID = field(default_factory=uuid4)
    request_id: UUID = field(default_factory=uuid4)
    vendor_id: UUID = field(default_factory=uuid4)
    case_type: str = "batch"
    status: str = "created"
    upload_count: int = 0
    edit_count: int = 0
    portal_token: str = "token-123"


@pytest.fixture
def mock_request_repo() -> AsyncMock:
    """Create a mock request repository."""
    repo = AsyncMock()
    repo.get_by_id = AsyncMock(return_value=None)
    repo.create = AsyncMock()
    repo.update = AsyncMock()
    repo.has_overlapping_period = AsyncMock(return_value=False)
    repo.list_requests = AsyncMock()
    repo.get_statistics = AsyncMock(return_value={})
    repo.count = AsyncMock(return_value=0)
    return repo


@pytest.fixture
def mock_case_repo() -> AsyncMock:
    """Create a mock case repository."""
    repo = AsyncMock()
    repo.get_by_id = AsyncMock(return_value=None)
    repo.create = AsyncMock()
    repo.bulk_create = AsyncMock(return_value=[])
    repo.update = AsyncMock()
    repo.list_by_request = AsyncMock()
    repo.get_active_cases_for_vendor = AsyncMock(return_value=[])
    repo.count_by_request = AsyncMock(return_value=0)
    repo.count_by_status = AsyncMock(return_value={})
    return repo


@pytest.fixture
def mock_vendor_repo() -> AsyncMock:
    """Create a mock vendor repository."""
    repo = AsyncMock()
    repo.get_by_id = AsyncMock(return_value=None)
    repo.get_by_vendor_code = AsyncMock(return_value=None)
    repo.exists_by_vendor_code = AsyncMock(return_value=False)
    repo.has_active_cases = AsyncMock(return_value=False)
    return repo


@pytest.fixture
def service(
    mock_request_repo: AsyncMock,
    mock_case_repo: AsyncMock,
    mock_vendor_repo: AsyncMock,
) -> RequestManagerService:
    """Create RequestManagerService with mocked repositories."""
    return RequestManagerService(
        request_repository=mock_request_repo,
        case_repository=mock_case_repo,
        vendor_repository=mock_vendor_repo,
    )


# ─── Create Request Tests ─────────────────────────────────────────────────────


class TestCreateRequest:
    """Tests for reconciliation request creation."""

    async def test_create_request_success(
        self, service: RequestManagerService, mock_request_repo: AsyncMock,
        mock_case_repo: AsyncMock, mock_vendor_repo: AsyncMock
    ):
        """Should create a request and N cases for N vendors."""
        v1 = FakeVendor(vendor_code="V001")
        v2 = FakeVendor(vendor_code="V002")
        mock_vendor_repo.get_by_id.side_effect = [v1, v2, v1, v2]
        mock_request_repo.has_overlapping_period.return_value = False
        fake_request = FakeRequest()
        mock_request_repo.create.return_value = fake_request
        mock_case_repo.bulk_create.return_value = [FakeCase(), FakeCase()]

        dto = RequestCreateDTO(
            company_code="CC01",
            fiscal_year="2024",
            period_start=date(2024, 1, 1),
            period_end=date(2024, 3, 31),
            vendor_ids=[v1.id, v2.id],
            tolerance_amount=Decimal("100"),
            tds_percentage=Decimal("2"),
            gst_percentage=Decimal("18"),
        )

        result = await service.create_request(dto)

        assert result == fake_request
        mock_request_repo.create.assert_called_once()
        mock_case_repo.bulk_create.assert_called_once()
        # Exactly 2 cases should be created for 2 vendors
        cases_data = mock_case_repo.bulk_create.call_args[0][0]
        assert len(cases_data) == 2

    async def test_create_request_no_vendors_raises(
        self, service: RequestManagerService, mock_request_repo: AsyncMock
    ):
        """Should raise ValueError when no vendors selected."""
        dto = RequestCreateDTO(
            company_code="CC01",
            fiscal_year="2024",
            period_start=date(2024, 1, 1),
            period_end=date(2024, 3, 31),
            vendor_ids=[],
        )

        with pytest.raises(ValueError, match="At least one vendor"):
            await service.create_request(dto)

        mock_request_repo.create.assert_not_called()

    async def test_create_request_inactive_vendor_raises(
        self, service: RequestManagerService, mock_request_repo: AsyncMock,
        mock_vendor_repo: AsyncMock
    ):
        """Should raise VendorInactiveException for inactive vendors."""
        v1 = FakeVendor(status="active", vendor_code="V001")
        v2 = FakeVendor(status="inactive", vendor_code="V002")
        mock_vendor_repo.get_by_id.side_effect = [v1, v2]

        dto = RequestCreateDTO(
            company_code="CC01",
            fiscal_year="2024",
            period_start=date(2024, 1, 1),
            period_end=date(2024, 3, 31),
            vendor_ids=[v1.id, v2.id],
        )

        with pytest.raises(VendorInactiveException) as exc_info:
            await service.create_request(dto)
        assert "V002" in str(exc_info.value)
        mock_request_repo.create.assert_not_called()

    async def test_create_request_overlapping_period_raises(
        self, service: RequestManagerService, mock_request_repo: AsyncMock,
        mock_vendor_repo: AsyncMock
    ):
        """Should raise OverlappingPeriodException for overlapping periods."""
        v1 = FakeVendor(status="active")
        mock_vendor_repo.get_by_id.side_effect = [v1]
        mock_request_repo.has_overlapping_period.return_value = True

        dto = RequestCreateDTO(
            company_code="CC01",
            fiscal_year="2024",
            period_start=date(2024, 1, 1),
            period_end=date(2024, 3, 31),
            vendor_ids=[v1.id],
        )

        with pytest.raises(OverlappingPeriodException):
            await service.create_request(dto)
        mock_request_repo.create.assert_not_called()

    async def test_create_request_with_matching_preferences(
        self, service: RequestManagerService, mock_request_repo: AsyncMock,
        mock_case_repo: AsyncMock, mock_vendor_repo: AsyncMock
    ):
        """Should include matching preferences in request data."""
        v1 = FakeVendor(status="active")
        mock_vendor_repo.get_by_id.side_effect = [v1, v1]
        mock_request_repo.has_overlapping_period.return_value = False
        fake_request = FakeRequest()
        mock_request_repo.create.return_value = fake_request

        prefs = MatchingPreferences(
            exact_match_enabled=True,
            tolerance_match_enabled=False,
            fuzzy_reference_enabled=True,
            one_to_many_enabled=False,
            many_to_one_enabled=False,
        )
        dto = RequestCreateDTO(
            company_code="CC01",
            fiscal_year="2024",
            period_start=date(2024, 4, 1),
            period_end=date(2024, 6, 30),
            vendor_ids=[v1.id],
            matching_preferences=prefs,
        )

        await service.create_request(dto)

        call_data = mock_request_repo.create.call_args[0][0]
        assert call_data["matching_preferences"]["exact_match_enabled"] is True
        assert call_data["matching_preferences"]["tolerance_match_enabled"] is False

    async def test_create_request_creates_exactly_n_cases(
        self, service: RequestManagerService, mock_request_repo: AsyncMock,
        mock_case_repo: AsyncMock, mock_vendor_repo: AsyncMock
    ):
        """Should create exactly N cases for N vendors (Requirement 3.6)."""
        vendors = [FakeVendor(vendor_code=f"V{i:03d}") for i in range(5)]
        mock_vendor_repo.get_by_id.side_effect = vendors + vendors
        mock_request_repo.has_overlapping_period.return_value = False
        fake_request = FakeRequest()
        mock_request_repo.create.return_value = fake_request

        dto = RequestCreateDTO(
            company_code="CC01",
            fiscal_year="2024",
            period_start=date(2024, 1, 1),
            period_end=date(2024, 3, 31),
            vendor_ids=[v.id for v in vendors],
        )

        await service.create_request(dto)

        cases_data = mock_case_repo.bulk_create.call_args[0][0]
        assert len(cases_data) == 5
        # Each case should reference a different vendor
        case_vendor_ids = [c["vendor_id"] for c in cases_data]
        assert len(set(case_vendor_ids)) == 5


# ─── Clone Request Tests ───────────────────────────────────────────────────────


class TestCloneRequest:
    """Tests for cloning an existing request for a new period."""

    async def test_clone_request_success(
        self, service: RequestManagerService, mock_request_repo: AsyncMock,
        mock_case_repo: AsyncMock, mock_vendor_repo: AsyncMock
    ):
        """Should clone request configuration to a new period."""
        source_request = FakeRequest(
            tolerance_amount=Decimal("200"),
            tds_percentage=Decimal("5"),
            gst_percentage=Decimal("18"),
            matching_preferences={
                "exact_match_enabled": True,
                "tolerance_match_enabled": True,
                "fuzzy_reference_enabled": False,
                "one_to_many_enabled": True,
                "many_to_one_enabled": True,
            },
        )
        mock_request_repo.get_by_id.return_value = source_request

        v1 = FakeVendor(vendor_code="V001")
        v2 = FakeVendor(vendor_code="V002")
        case1 = FakeCase(vendor_id=v1.id)
        case2 = FakeCase(vendor_id=v2.id)
        mock_case_repo.list_by_request.return_value = PaginatedResult(
            items=[case1, case2], total=2, page=1, page_size=50
        )

        # For create_request validation: get_by_id called for each vendor
        mock_vendor_repo.get_by_id.side_effect = [v1, v2, v1, v2]
        mock_request_repo.has_overlapping_period.return_value = False

        new_request = FakeRequest()
        mock_request_repo.create.return_value = new_request

        new_period = DateRange(start=date(2024, 4, 1), end=date(2024, 6, 30))
        result = await service.clone_request(
            source_request.id, "CC01", new_period
        )

        assert result == new_request
        create_data = mock_request_repo.create.call_args[0][0]
        assert create_data["period_start"] == date(2024, 4, 1)
        assert create_data["period_end"] == date(2024, 6, 30)
        assert create_data["tolerance_amount"] == Decimal("200")

    async def test_clone_request_not_found_raises(
        self, service: RequestManagerService, mock_request_repo: AsyncMock
    ):
        """Should raise ValueError when source request not found."""
        mock_request_repo.get_by_id.return_value = None

        new_period = DateRange(start=date(2024, 4, 1), end=date(2024, 6, 30))
        with pytest.raises(ValueError, match="not found"):
            await service.clone_request(uuid4(), "CC01", new_period)

    async def test_clone_request_no_cases_raises(
        self, service: RequestManagerService, mock_request_repo: AsyncMock,
        mock_case_repo: AsyncMock
    ):
        """Should raise ValueError when source request has no cases."""
        source_request = FakeRequest()
        mock_request_repo.get_by_id.return_value = source_request
        mock_case_repo.list_by_request.return_value = PaginatedResult(
            items=[], total=0, page=1, page_size=50
        )

        new_period = DateRange(start=date(2024, 4, 1), end=date(2024, 6, 30))
        with pytest.raises(ValueError, match="no cases"):
            await service.clone_request(source_request.id, "CC01", new_period)


# ─── Company Ledger Confirmation Tests ────────────────────────────────────────


class TestConfirmCompanyLedger:
    """Tests for company ledger confirmation."""

    async def test_confirm_ledger_success(
        self, service: RequestManagerService, mock_case_repo: AsyncMock
    ):
        """Should transition case from Created to LedgerConfirmed."""
        case = FakeCase(status="created")
        mock_case_repo.get_by_id.return_value = case
        updated_case = FakeCase(status="ledger_confirmed")
        mock_case_repo.update.return_value = updated_case

        result = await service.confirm_company_ledger(case.id, "CC01")

        assert result == updated_case
        mock_case_repo.update.assert_called_once_with(
            case.id, {"status": "ledger_confirmed"}
        )

    async def test_confirm_ledger_on_closed_case_raises(
        self, service: RequestManagerService, mock_case_repo: AsyncMock
    ):
        """Should raise CaseClosedException for closed case."""
        case = FakeCase(status="closed")
        mock_case_repo.get_by_id.return_value = case

        with pytest.raises(CaseClosedException):
            await service.confirm_company_ledger(case.id, "CC01")

        mock_case_repo.update.assert_not_called()

    async def test_confirm_ledger_invalid_status_raises(
        self, service: RequestManagerService, mock_case_repo: AsyncMock
    ):
        """Should raise InvalidStatusTransitionException for wrong source status."""
        case = FakeCase(status="invited")
        mock_case_repo.get_by_id.return_value = case

        with pytest.raises(InvalidStatusTransitionException):
            await service.confirm_company_ledger(case.id, "CC01")

    async def test_confirm_ledger_case_not_found_raises(
        self, service: RequestManagerService, mock_case_repo: AsyncMock
    ):
        """Should raise ValueError when case not found."""
        mock_case_repo.get_by_id.return_value = None

        with pytest.raises(ValueError, match="not found"):
            await service.confirm_company_ledger(uuid4(), "CC01")


# ─── Invite Vendor Tests ──────────────────────────────────────────────────────


class TestInviteVendor:
    """Tests for vendor invitation with ledger confirmation enforcement."""

    async def test_invite_vendor_success(
        self, service: RequestManagerService, mock_case_repo: AsyncMock
    ):
        """Should transition case from LedgerConfirmed to Invited."""
        case = FakeCase(status="ledger_confirmed")
        mock_case_repo.get_by_id.return_value = case
        updated_case = FakeCase(status="invited")
        mock_case_repo.update.return_value = updated_case

        result = await service.invite_vendor(case.id, "CC01")

        assert result == updated_case
        mock_case_repo.update.assert_called_once_with(
            case.id, {"status": "invited"}
        )

    async def test_invite_vendor_without_ledger_confirmation_raises(
        self, service: RequestManagerService, mock_case_repo: AsyncMock
    ):
        """Should raise CompanyLedgerNotConfirmedException when ledger not confirmed."""
        case = FakeCase(status="created")
        mock_case_repo.get_by_id.return_value = case

        with pytest.raises(CompanyLedgerNotConfirmedException):
            await service.invite_vendor(case.id, "CC01")

        mock_case_repo.update.assert_not_called()

    async def test_invite_vendor_on_closed_case_raises(
        self, service: RequestManagerService, mock_case_repo: AsyncMock
    ):
        """Should raise CaseClosedException for closed case."""
        case = FakeCase(status="closed")
        mock_case_repo.get_by_id.return_value = case

        with pytest.raises(CaseClosedException):
            await service.invite_vendor(case.id, "CC01")

        mock_case_repo.update.assert_not_called()

    async def test_invite_vendor_case_not_found_raises(
        self, service: RequestManagerService, mock_case_repo: AsyncMock
    ):
        """Should raise ValueError when case not found."""
        mock_case_repo.get_by_id.return_value = None

        with pytest.raises(ValueError, match="not found"):
            await service.invite_vendor(uuid4(), "CC01")


# ─── Request Status Transition Tests ──────────────────────────────────────────


class TestTransitionRequestStatus:
    """Tests for request status transition state machine enforcement."""

    async def test_valid_request_transitions(
        self, service: RequestManagerService, mock_request_repo: AsyncMock
    ):
        """Should allow all valid request transitions."""
        valid_transitions = [
            (RequestStatus.DRAFT, RequestStatus.ACTIVE),
            (RequestStatus.ACTIVE, RequestStatus.IN_PROGRESS),
            (RequestStatus.IN_PROGRESS, RequestStatus.REVIEW),
            (RequestStatus.REVIEW, RequestStatus.SIGN_OFF),
            (RequestStatus.REVIEW, RequestStatus.IN_PROGRESS),
            (RequestStatus.SIGN_OFF, RequestStatus.CLOSED),
        ]

        for current, target in valid_transitions:
            request = FakeRequest(status=current.value)
            mock_request_repo.get_by_id.return_value = request
            updated = FakeRequest(status=target.value)
            mock_request_repo.update.return_value = updated

            result = await service.transition_request_status(
                request.id, "CC01", target
            )
            assert result.status == target.value

    async def test_invalid_request_transitions_raise(
        self, service: RequestManagerService, mock_request_repo: AsyncMock
    ):
        """Should reject invalid request status transitions."""
        invalid_transitions = [
            (RequestStatus.DRAFT, RequestStatus.CLOSED),
            (RequestStatus.DRAFT, RequestStatus.IN_PROGRESS),
            (RequestStatus.ACTIVE, RequestStatus.DRAFT),
            (RequestStatus.ACTIVE, RequestStatus.REVIEW),
            (RequestStatus.IN_PROGRESS, RequestStatus.CLOSED),
            (RequestStatus.CLOSED, RequestStatus.DRAFT),
            (RequestStatus.CLOSED, RequestStatus.ACTIVE),
            (RequestStatus.SIGN_OFF, RequestStatus.REVIEW),
        ]

        for current, target in invalid_transitions:
            request = FakeRequest(status=current.value)
            mock_request_repo.get_by_id.return_value = request

            with pytest.raises(InvalidStatusTransitionException):
                await service.transition_request_status(
                    request.id, "CC01", target
                )

    async def test_transition_request_not_found_raises(
        self, service: RequestManagerService, mock_request_repo: AsyncMock
    ):
        """Should raise ValueError when request not found."""
        mock_request_repo.get_by_id.return_value = None

        with pytest.raises(ValueError, match="not found"):
            await service.transition_request_status(
                uuid4(), "CC01", RequestStatus.ACTIVE
            )


# ─── Case Status Transition Tests ─────────────────────────────────────────────


class TestTransitionCaseStatus:
    """Tests for case status transition state machine enforcement."""

    async def test_valid_case_transitions(
        self, service: RequestManagerService, mock_case_repo: AsyncMock
    ):
        """Should allow all valid case transitions."""
        valid_transitions = [
            (CaseStatus.CREATED, CaseStatus.LEDGER_CONFIRMED),
            (CaseStatus.LEDGER_CONFIRMED, CaseStatus.INVITED),
            (CaseStatus.INVITED, CaseStatus.DATA_RECEIVED),
            (CaseStatus.DATA_RECEIVED, CaseStatus.MATCHING),
            (CaseStatus.MATCHING, CaseStatus.MATCHED),
            (CaseStatus.MATCHED, CaseStatus.REVIEW),
            (CaseStatus.REVIEW, CaseStatus.PENDING_APPROVAL),
            (CaseStatus.PENDING_APPROVAL, CaseStatus.APPROVED),
            (CaseStatus.PENDING_APPROVAL, CaseStatus.REVIEW),
            (CaseStatus.APPROVED, CaseStatus.SIGNED_OFF),
            (CaseStatus.SIGNED_OFF, CaseStatus.CLOSED),
        ]

        for current, target in valid_transitions:
            case = FakeCase(status=current.value)
            mock_case_repo.get_by_id.return_value = case
            updated = FakeCase(status=target.value)
            mock_case_repo.update.return_value = updated

            result = await service.transition_case_status(
                case.id, "CC01", target
            )
            assert result.status == target.value

    async def test_invalid_case_transitions_raise(
        self, service: RequestManagerService, mock_case_repo: AsyncMock
    ):
        """Should reject invalid case status transitions."""
        invalid_transitions = [
            (CaseStatus.CREATED, CaseStatus.INVITED),
            (CaseStatus.CREATED, CaseStatus.CLOSED),
            (CaseStatus.LEDGER_CONFIRMED, CaseStatus.CREATED),
            (CaseStatus.INVITED, CaseStatus.MATCHED),
            (CaseStatus.MATCHING, CaseStatus.REVIEW),
            (CaseStatus.APPROVED, CaseStatus.CREATED),
        ]

        for current, target in invalid_transitions:
            case = FakeCase(status=current.value)
            mock_case_repo.get_by_id.return_value = case

            with pytest.raises(InvalidStatusTransitionException):
                await service.transition_case_status(
                    case.id, "CC01", target
                )

    async def test_transition_closed_case_raises(
        self, service: RequestManagerService, mock_case_repo: AsyncMock
    ):
        """Should raise CaseClosedException for any transition on closed case."""
        case = FakeCase(status="closed")
        mock_case_repo.get_by_id.return_value = case

        with pytest.raises(CaseClosedException):
            await service.transition_case_status(
                case.id, "CC01", CaseStatus.CREATED
            )


# ─── Period Overlap Validation Tests ──────────────────────────────────────────


class TestValidateNoOverlap:
    """Tests for period overlap validation."""

    async def test_no_overlap_returns_true(
        self, service: RequestManagerService, mock_request_repo: AsyncMock
    ):
        """Should return True when no overlap exists."""
        mock_request_repo.has_overlapping_period.return_value = False

        result = await service.validate_no_overlap(
            vendor_id=uuid4(),
            company_code="CC01",
            period=DateRange(start=date(2024, 1, 1), end=date(2024, 3, 31)),
        )

        assert result is True

    async def test_overlap_raises_exception(
        self, service: RequestManagerService, mock_request_repo: AsyncMock
    ):
        """Should raise OverlappingPeriodException when overlap exists."""
        mock_request_repo.has_overlapping_period.return_value = True

        with pytest.raises(OverlappingPeriodException):
            await service.validate_no_overlap(
                vendor_id=uuid4(),
                company_code="CC01",
                period=DateRange(
                    start=date(2024, 1, 1), end=date(2024, 3, 31)
                ),
            )

    async def test_overlap_with_exclusion(
        self, service: RequestManagerService, mock_request_repo: AsyncMock
    ):
        """Should pass exclude_request_id to the repository."""
        mock_request_repo.has_overlapping_period.return_value = False
        exclude_id = uuid4()

        await service.validate_no_overlap(
            vendor_id=uuid4(),
            company_code="CC01",
            period=DateRange(start=date(2024, 1, 1), end=date(2024, 3, 31)),
            exclude_request_id=exclude_id,
        )

        call_kwargs = mock_request_repo.has_overlapping_period.call_args[1]
        assert call_kwargs["exclude_request_id"] == exclude_id


# ─── DateRange Overlap Logic Tests ────────────────────────────────────────────


class TestDateRangeOverlap:
    """Tests for DateRange.overlaps() logic."""

    def test_overlapping_ranges(self):
        """Should detect overlapping date ranges."""
        r1 = DateRange(start=date(2024, 1, 1), end=date(2024, 3, 31))
        r2 = DateRange(start=date(2024, 3, 1), end=date(2024, 5, 31))
        assert r1.overlaps(r2) is True
        assert r2.overlaps(r1) is True

    def test_non_overlapping_ranges(self):
        """Should not detect overlap for non-overlapping ranges."""
        r1 = DateRange(start=date(2024, 1, 1), end=date(2024, 3, 31))
        r2 = DateRange(start=date(2024, 4, 1), end=date(2024, 6, 30))
        assert r1.overlaps(r2) is False
        assert r2.overlaps(r1) is False

    def test_adjacent_ranges_no_overlap(self):
        """Ranges ending and starting on same day do overlap."""
        r1 = DateRange(start=date(2024, 1, 1), end=date(2024, 3, 31))
        r2 = DateRange(start=date(2024, 3, 31), end=date(2024, 6, 30))
        # start1 <= end2 AND start2 <= end1 → 2024-01-01 <= 2024-06-30 AND 2024-03-31 <= 2024-03-31
        assert r1.overlaps(r2) is True

    def test_contained_range(self):
        """Should detect overlap when one range is contained in another."""
        outer = DateRange(start=date(2024, 1, 1), end=date(2024, 12, 31))
        inner = DateRange(start=date(2024, 3, 1), end=date(2024, 5, 31))
        assert outer.overlaps(inner) is True
        assert inner.overlaps(outer) is True

    def test_identical_ranges(self):
        """Should detect overlap for identical ranges."""
        r1 = DateRange(start=date(2024, 1, 1), end=date(2024, 3, 31))
        r2 = DateRange(start=date(2024, 1, 1), end=date(2024, 3, 31))
        assert r1.overlaps(r2) is True


# ─── Closed Case Edit Blocking Tests ─────────────────────────────────────────


class TestClosedCaseBlocking:
    """Tests that closed cases reject all modifications."""

    async def test_closed_case_blocks_confirm_ledger(
        self, service: RequestManagerService, mock_case_repo: AsyncMock
    ):
        """Confirm ledger should be blocked on closed case."""
        case = FakeCase(status="closed")
        mock_case_repo.get_by_id.return_value = case

        with pytest.raises(CaseClosedException):
            await service.confirm_company_ledger(case.id, "CC01")

    async def test_closed_case_blocks_invite_vendor(
        self, service: RequestManagerService, mock_case_repo: AsyncMock
    ):
        """Invite vendor should be blocked on closed case."""
        case = FakeCase(status="closed")
        mock_case_repo.get_by_id.return_value = case

        with pytest.raises(CaseClosedException):
            await service.invite_vendor(case.id, "CC01")

    async def test_closed_case_blocks_status_transition(
        self, service: RequestManagerService, mock_case_repo: AsyncMock
    ):
        """Status transition should be blocked on closed case."""
        case = FakeCase(status="closed")
        mock_case_repo.get_by_id.return_value = case

        with pytest.raises(CaseClosedException):
            await service.transition_case_status(
                case.id, "CC01", CaseStatus.REVIEW
            )


# ─── State Machine Completeness Tests ────────────────────────────────────────


class TestStateMachineCompleteness:
    """Tests ensuring the state machine definitions are complete."""

    def test_all_request_statuses_have_transition_entry(self):
        """Every RequestStatus should have an entry in the transition map."""
        for status in RequestStatus:
            assert status in VALID_REQUEST_TRANSITIONS

    def test_all_case_statuses_have_transition_entry(self):
        """Every CaseStatus should have an entry in the transition map."""
        for status in CaseStatus:
            assert status in VALID_CASE_TRANSITIONS

    def test_closed_request_has_no_transitions(self):
        """Closed request should have no outgoing transitions."""
        assert VALID_REQUEST_TRANSITIONS[RequestStatus.CLOSED] == set()

    def test_closed_case_has_no_transitions(self):
        """Closed case should have no outgoing transitions."""
        assert VALID_CASE_TRANSITIONS[CaseStatus.CLOSED] == set()
