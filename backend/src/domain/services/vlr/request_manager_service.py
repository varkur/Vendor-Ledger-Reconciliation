"""
Reconciliation Request Lifecycle Domain Service.

Implements request creation, cloning, status transitions, period overlap
validation, case creation, company ledger confirmation, vendor invitation,
and closed-case edit blocking.

Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9, 3.10
"""

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from uuid import UUID, uuid4

from src.domain.exceptions.vlr import (
    CaseClosedException,
    CompanyLedgerNotConfirmedException,
    InvalidStatusTransitionException,
    OverlappingPeriodException,
    VendorInactiveException,
)
from src.domain.repositories.vlr.case_repository import ICaseRepository
from src.domain.repositories.vlr.request_repository import IRequestRepository
from src.domain.repositories.vlr.vendor_repository import IVendorRepository


class RequestStatus(str, Enum):
    """Reconciliation request status values."""

    DRAFT = "draft"
    ACTIVE = "active"
    IN_PROGRESS = "in_progress"
    REVIEW = "review"
    SIGN_OFF = "sign_off"
    CLOSED = "closed"


class CaseStatus(str, Enum):
    """Reconciliation case status values."""

    CREATED = "created"
    LEDGER_CONFIRMED = "ledger_confirmed"
    INVITED = "invited"
    DATA_RECEIVED = "data_received"
    MATCHING = "matching"
    MATCHED = "matched"
    REVIEW = "review"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    SIGNED_OFF = "signed_off"
    CLOSED = "closed"


# ─── Valid Status Transitions (State Machine) ─────────────────────────────────

# Request status transitions: Draft→Active→InProgress→Review→SignOff→Closed
# Also allows Review→InProgress (changes requested)
VALID_REQUEST_TRANSITIONS: dict[RequestStatus, set[RequestStatus]] = {
    RequestStatus.DRAFT: {RequestStatus.ACTIVE},
    RequestStatus.ACTIVE: {RequestStatus.IN_PROGRESS},
    RequestStatus.IN_PROGRESS: {RequestStatus.REVIEW},
    RequestStatus.REVIEW: {RequestStatus.SIGN_OFF, RequestStatus.IN_PROGRESS},
    RequestStatus.SIGN_OFF: {RequestStatus.CLOSED},
    RequestStatus.CLOSED: set(),
}

# Case status transitions
VALID_CASE_TRANSITIONS: dict[CaseStatus, set[CaseStatus]] = {
    CaseStatus.CREATED: {CaseStatus.LEDGER_CONFIRMED},
    CaseStatus.LEDGER_CONFIRMED: {CaseStatus.INVITED},
    CaseStatus.INVITED: {CaseStatus.DATA_RECEIVED},
    CaseStatus.DATA_RECEIVED: {CaseStatus.MATCHING},
    CaseStatus.MATCHING: {CaseStatus.MATCHED},
    CaseStatus.MATCHED: {CaseStatus.REVIEW},
    CaseStatus.REVIEW: {CaseStatus.PENDING_APPROVAL},
    CaseStatus.PENDING_APPROVAL: {CaseStatus.APPROVED, CaseStatus.REVIEW},
    CaseStatus.APPROVED: {CaseStatus.SIGNED_OFF},
    CaseStatus.SIGNED_OFF: {CaseStatus.CLOSED},
    CaseStatus.CLOSED: set(),
}


# ─── Data Transfer Objects ────────────────────────────────────────────────────


@dataclass
class DateRange:
    """Represents a date range (period_start to period_end)."""

    start: date
    end: date

    def overlaps(self, other: "DateRange") -> bool:
        """Check if this range overlaps with another range."""
        return self.start <= other.end and other.start <= self.end


@dataclass
class MatchingPreferences:
    """Configuration for matching passes."""

    exact_match_enabled: bool = True
    tolerance_match_enabled: bool = True
    fuzzy_reference_enabled: bool = True
    one_to_many_enabled: bool = True
    many_to_one_enabled: bool = True


@dataclass
class RequestCreateDTO:
    """Data transfer object for reconciliation request creation."""

    company_code: str
    fiscal_year: str
    period_start: date
    period_end: date
    vendor_ids: list[UUID]
    tolerance_amount: Decimal = Decimal("0")
    tds_percentage: Decimal = Decimal("0")
    gst_percentage: Decimal = Decimal("0")
    matching_preferences: MatchingPreferences | None = None
    assigned_manager_id: UUID | None = None
    created_by: UUID | None = None


@dataclass
class RequestCloneDTO:
    """Data transfer object for cloning a request with a new period."""

    period_start: date
    period_end: date
    created_by: UUID | None = None


class RequestManagerService:
    """
    Domain service for Reconciliation Request lifecycle management.

    Encapsulates business rules for request creation, cloning, status
    transitions, period overlap validation, case creation, company ledger
    confirmation, vendor invitation enforcement, and closed-case blocking.
    """

    def __init__(
        self,
        request_repository: IRequestRepository,
        case_repository: ICaseRepository,
        vendor_repository: IVendorRepository,
    ) -> None:
        self._request_repo = request_repository
        self._case_repo = case_repository
        self._vendor_repo = vendor_repository

    # ──────────────────────────────────────────────────────────────────────
    # Request Creation
    # ──────────────────────────────────────────────────────────────────────

    async def create_request(self, data: RequestCreateDTO) -> object:
        """
        Create a reconciliation request with cases for each selected vendor.

        Requirement 3.1: Require company code, fiscal year, date range, and at least one vendor.
        Requirement 3.2: Allow configuration of tolerance, TDS%, GST%, matching preferences.
        Requirement 3.3: Validate no overlapping period for any selected vendor.
        Requirement 3.6: Create exactly N cases for N selected active vendors.
        Requirement 3.9: Reject if any vendor is inactive.
        """
        # Validate at least one vendor selected
        if not data.vendor_ids:
            raise ValueError("At least one vendor must be selected for the request.")

        # Validate all vendors are active (Requirement 3.9)
        inactive_vendors: list[str] = []
        for vendor_id in data.vendor_ids:
            vendor = await self._vendor_repo.get_by_id(vendor_id, data.company_code)
            if vendor is None:
                raise ValueError(f"Vendor with id '{vendor_id}' not found.")
            if getattr(vendor, "status", None) == "inactive":
                inactive_vendors.append(
                    getattr(vendor, "vendor_code", str(vendor_id))
                )

        if inactive_vendors:
            raise VendorInactiveException(
                f"The following vendors are inactive and cannot be included: "
                f"{', '.join(inactive_vendors)}"
            )

        # Validate no overlapping periods for any vendor (Requirement 3.3)
        period = DateRange(start=data.period_start, end=data.period_end)
        for vendor_id in data.vendor_ids:
            await self.validate_no_overlap(
                vendor_id=vendor_id,
                company_code=data.company_code,
                period=period,
            )

        # Build matching preferences as JSON-serializable dict
        matching_prefs = None
        if data.matching_preferences:
            matching_prefs = {
                "exact_match_enabled": data.matching_preferences.exact_match_enabled,
                "tolerance_match_enabled": data.matching_preferences.tolerance_match_enabled,
                "fuzzy_reference_enabled": data.matching_preferences.fuzzy_reference_enabled,
                "one_to_many_enabled": data.matching_preferences.one_to_many_enabled,
                "many_to_one_enabled": data.matching_preferences.many_to_one_enabled,
            }

        # Create the request in Draft status
        request_data = {
            "company_code": data.company_code,
            "fiscal_year": data.fiscal_year,
            "period_start": data.period_start,
            "period_end": data.period_end,
            "status": RequestStatus.DRAFT.value,
            "tolerance_amount": data.tolerance_amount,
            "tds_percentage": data.tds_percentage,
            "gst_percentage": data.gst_percentage,
            "matching_preferences": matching_prefs,
            "assigned_manager": data.assigned_manager_id,
            "created_by": data.created_by,
        }

        request = await self._request_repo.create(request_data)
        request_id = getattr(request, "id")

        # Create exactly N cases for N vendors (Requirement 3.6)
        cases_data = []
        for vendor_id in data.vendor_ids:
            cases_data.append({
                "request_id": request_id,
                "vendor_id": vendor_id,
                "case_type": "batch",
                "status": CaseStatus.CREATED.value,
                "upload_count": 0,
                "edit_count": 0,
                "portal_token": str(uuid4()),
            })

        await self._case_repo.bulk_create(cases_data)

        return request

    # ──────────────────────────────────────────────────────────────────────
    # Clone Request
    # ──────────────────────────────────────────────────────────────────────

    async def clone_request(
        self,
        request_id: UUID,
        company_code: str,
        new_period: DateRange,
        created_by: UUID | None = None,
    ) -> object:
        """
        Clone an existing request configuration for a new period.

        Requirement 3.10: Support cloning an existing request for a new period.
        Copies configuration (tolerance, TDS%, GST%, matching preferences,
        assigned manager) and vendor selections to a new request.
        """
        # Get the source request
        source_request = await self._request_repo.get_by_id(request_id, company_code)
        if source_request is None:
            raise ValueError(
                f"Request with id '{request_id}' not found in company '{company_code}'."
            )

        # Get cases for the source request to extract vendor IDs
        cases_result = await self._case_repo.list_by_request(request_id)
        vendor_ids = [
            getattr(case, "vendor_id") for case in cases_result.items
        ]

        if not vendor_ids:
            raise ValueError("Source request has no cases to clone.")

        # Build creation DTO from source + new period
        create_dto = RequestCreateDTO(
            company_code=company_code,
            fiscal_year=getattr(source_request, "fiscal_year", ""),
            period_start=new_period.start,
            period_end=new_period.end,
            vendor_ids=vendor_ids,
            tolerance_amount=getattr(
                source_request, "tolerance_amount", Decimal("0")
            ),
            tds_percentage=getattr(
                source_request, "tds_percentage", Decimal("0")
            ),
            gst_percentage=getattr(
                source_request, "gst_percentage", Decimal("0")
            ),
            matching_preferences=self._extract_matching_preferences(source_request),
            assigned_manager_id=getattr(source_request, "assigned_manager", None),
            created_by=created_by,
        )

        return await self.create_request(create_dto)

    def _extract_matching_preferences(self, request: object) -> MatchingPreferences | None:
        """Extract matching preferences from a request object."""
        prefs = getattr(request, "matching_preferences", None)
        if prefs is None:
            return None
        if isinstance(prefs, dict):
            return MatchingPreferences(
                exact_match_enabled=prefs.get("exact_match_enabled", True),
                tolerance_match_enabled=prefs.get("tolerance_match_enabled", True),
                fuzzy_reference_enabled=prefs.get("fuzzy_reference_enabled", True),
                one_to_many_enabled=prefs.get("one_to_many_enabled", True),
                many_to_one_enabled=prefs.get("many_to_one_enabled", True),
            )
        return None

    # ──────────────────────────────────────────────────────────────────────
    # Company Ledger Confirmation
    # ──────────────────────────────────────────────────────────────────────

    async def confirm_company_ledger(self, case_id: UUID, company_code: str) -> object:
        """
        Confirm the company ledger for a case, transitioning to LedgerConfirmed.

        Requirement 3.4: Transition case to Invited status and trigger notification
        after ledger is confirmed.
        Requirement 3.8: Block edits on closed cases.
        """
        case = await self._get_case_or_raise(case_id, company_code)

        # Block edits on closed cases
        self._assert_case_not_closed(case)

        # Validate current status allows this transition
        current_status = CaseStatus(getattr(case, "status"))
        self._validate_case_transition(current_status, CaseStatus.LEDGER_CONFIRMED)

        # Update case status
        updated_case = await self._case_repo.update(
            case_id, {"status": CaseStatus.LEDGER_CONFIRMED.value}
        )

        return updated_case

    # ──────────────────────────────────────────────────────────────────────
    # Vendor Invitation
    # ──────────────────────────────────────────────────────────────────────

    async def invite_vendor(self, case_id: UUID, company_code: str) -> object:
        """
        Invite a vendor for reconciliation (transition case to Invited).

        Requirement 3.5: Company ledger must be confirmed before invitation.
        Requirement 3.8: Block edits on closed cases.
        """
        case = await self._get_case_or_raise(case_id, company_code)

        # Block edits on closed cases
        self._assert_case_not_closed(case)

        # Enforce company ledger confirmation before invitation (Requirement 3.5)
        current_status = CaseStatus(getattr(case, "status"))
        if current_status != CaseStatus.LEDGER_CONFIRMED:
            raise CompanyLedgerNotConfirmedException()

        # Validate the transition
        self._validate_case_transition(current_status, CaseStatus.INVITED)

        # Update case status to Invited
        updated_case = await self._case_repo.update(
            case_id, {"status": CaseStatus.INVITED.value}
        )

        return updated_case

    # ──────────────────────────────────────────────────────────────────────
    # Status Transitions
    # ──────────────────────────────────────────────────────────────────────

    async def transition_request_status(
        self,
        request_id: UUID,
        company_code: str,
        new_status: RequestStatus,
    ) -> object:
        """
        Transition a reconciliation request to a new status.

        Requirement 3.7: Track status through Draft, Active, In Progress,
        Review, Sign Off, and Closed stages.
        Enforces the state machine — only valid transitions are allowed.
        """
        request = await self._request_repo.get_by_id(request_id, company_code)
        if request is None:
            raise ValueError(
                f"Request with id '{request_id}' not found in company '{company_code}'."
            )

        current_status = RequestStatus(getattr(request, "status"))
        self._validate_request_transition(current_status, new_status)

        updated_request = await self._request_repo.update(
            request_id, company_code, {"status": new_status.value}
        )

        return updated_request

    async def transition_case_status(
        self,
        case_id: UUID,
        company_code: str,
        new_status: CaseStatus,
    ) -> object:
        """
        Transition a reconciliation case to a new status.

        Requirement 3.7: Enforce state machine.
        Requirement 3.8: Block edits on closed cases.
        """
        case = await self._get_case_or_raise(case_id, company_code)

        # Block edits on closed cases
        self._assert_case_not_closed(case)

        current_status = CaseStatus(getattr(case, "status"))
        self._validate_case_transition(current_status, new_status)

        updated_case = await self._case_repo.update(
            case_id, {"status": new_status.value}
        )

        return updated_case

    # ──────────────────────────────────────────────────────────────────────
    # Period Overlap Validation
    # ──────────────────────────────────────────────────────────────────────

    async def validate_no_overlap(
        self,
        vendor_id: UUID,
        company_code: str,
        period: DateRange,
        exclude_request_id: UUID | None = None,
    ) -> bool:
        """
        Validate that no overlapping reconciliation period exists for a vendor.

        Requirement 3.3: Validate no overlapping period for any selected vendor
        within the same company code.

        Returns True if no overlap exists.
        Raises OverlappingPeriodException if overlap is detected.
        """
        has_overlap = await self._request_repo.has_overlapping_period(
            vendor_id=vendor_id,
            company_code=company_code,
            period_start=period.start,
            period_end=period.end,
            exclude_request_id=exclude_request_id,
        )

        if has_overlap:
            raise OverlappingPeriodException()

        return True

    # ──────────────────────────────────────────────────────────────────────
    # State Machine Validation Helpers
    # ──────────────────────────────────────────────────────────────────────

    def _validate_request_transition(
        self, current: RequestStatus, target: RequestStatus
    ) -> None:
        """Validate that a request status transition is allowed."""
        allowed = VALID_REQUEST_TRANSITIONS.get(current, set())
        if target not in allowed:
            raise InvalidStatusTransitionException(
                current_status=current.value,
                target_status=target.value,
            )

    def _validate_case_transition(
        self, current: CaseStatus, target: CaseStatus
    ) -> None:
        """Validate that a case status transition is allowed."""
        allowed = VALID_CASE_TRANSITIONS.get(current, set())
        if target not in allowed:
            raise InvalidStatusTransitionException(
                current_status=current.value,
                target_status=target.value,
            )

    # ──────────────────────────────────────────────────────────────────────
    # Private Helpers
    # ──────────────────────────────────────────────────────────────────────

    async def _get_case_or_raise(self, case_id: UUID, company_code: str) -> object:
        """Get a case by ID or raise ValueError if not found."""
        case = await self._case_repo.get_by_id(case_id, company_code)
        if case is None:
            raise ValueError(
                f"Reconciliation case with id '{case_id}' not found."
            )
        return case

    def _assert_case_not_closed(self, case: object) -> None:
        """Raise CaseClosedException if the case is in Closed status."""
        status = getattr(case, "status", None)
        if status == CaseStatus.CLOSED.value:
            raise CaseClosedException()
