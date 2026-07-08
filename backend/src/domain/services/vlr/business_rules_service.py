"""
Business Rules Service for VLR.

Centralizes core business rule validations:
- One-sided reconciliation closure (Requirement 32.1, 32.2, 32.3)
- Portal link expiry enforcement (Requirement 33.1, 33.2, 33.3)
- Period overlap prevention (Requirement 34.1, 34.2)
- Active vendor validation (Requirement 35.1, 35.2)
- Case closure net-zero condition (Requirement 37.1, 37.2, 37.3)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

from src.domain.exceptions.vlr import (
    OverlappingPeriodException,
    VendorInactiveException,
    VLRDomainException,
)

logger = logging.getLogger(__name__)

# ─── Constants ────────────────────────────────────────────────────────────────

PORTAL_LINK_VALIDITY_DAYS = 90


# ─── Custom Exceptions ────────────────────────────────────────────────────────


class OneSidedClosureNotApprovedException(VLRDomainException):
    """Raised when one-sided closure is attempted without Recon_Manager approval."""

    error_code = "VLR_ONE_SIDED_CLOSURE_NOT_APPROVED"
    status_code = 403

    def _default_message(self) -> str:
        return (
            "One-sided reconciliation closure requires explicit approval "
            "from a Reconciliation Manager."
        )


class OneSidedClosureMissingJustificationException(VLRDomainException):
    """Raised when one-sided closure is attempted without justification."""

    error_code = "VLR_ONE_SIDED_CLOSURE_NO_JUSTIFICATION"
    status_code = 400

    def _default_message(self) -> str:
        return "One-sided closure requires a justification to be provided."


class PortalLinkExpiredException(VLRDomainException):
    """Raised when a vendor portal link has expired (90-day validity exceeded)."""

    error_code = "VLR_PORTAL_LINK_EXPIRED"
    status_code = 410

    def _default_message(self) -> str:
        return (
            "This portal link has expired. Portal links are valid for 90 days. "
            "Please contact the reconciliation team to request a new invitation."
        )


class PeriodOverlapException(VLRDomainException):
    """Raised when a reconciliation period overlaps an existing case."""

    error_code = "VLR_PERIOD_OVERLAP"
    status_code = 409

    def __init__(
        self,
        conflicting_case_reference: str | None = None,
        message: str | None = None,
    ) -> None:
        self.conflicting_case_reference = conflicting_case_reference
        if message is None and conflicting_case_reference:
            message = (
                f"A reconciliation case already exists for this vendor in the "
                f"specified period. Conflicting case: {conflicting_case_reference}"
            )
        super().__init__(message)

    def _default_message(self) -> str:
        return (
            "A reconciliation case already exists for this vendor in the "
            "specified period."
        )


class VendorNotActiveException(VLRDomainException):
    """Raised when a reconciliation request targets an inactive vendor."""

    error_code = "VLR_VENDOR_NOT_ACTIVE"
    status_code = 422

    def __init__(
        self,
        vendor_code: str | None = None,
        message: str | None = None,
    ) -> None:
        self.vendor_code = vendor_code
        if message is None and vendor_code:
            message = (
                f"Cannot create reconciliation request for inactive vendor "
                f"'{vendor_code}'. Only active vendors are eligible for reconciliation."
            )
        super().__init__(message)

    def _default_message(self) -> str:
        return (
            "Cannot create reconciliation request for an inactive vendor. "
            "Only active vendors are eligible for reconciliation."
        )


class CaseClosureNetZeroException(VLRDomainException):
    """Raised when case closure is attempted but net difference is not zero."""

    error_code = "VLR_CASE_CLOSURE_NET_NON_ZERO"
    status_code = 409

    def __init__(
        self,
        net_difference: Decimal | None = None,
        message: str | None = None,
    ) -> None:
        self.net_difference = net_difference
        if message is None and net_difference is not None:
            message = (
                f"Cannot close case: net difference is {net_difference}. "
                f"The net difference must be zero for normal closure."
            )
        super().__init__(message)

    def _default_message(self) -> str:
        return (
            "Cannot close case: the net difference between company and vendor "
            "adjusted balances must be zero for normal closure."
        )


# ─── Data Transfer Objects ────────────────────────────────────────────────────


@dataclass
class OneSidedClosureRequest:
    """Data for a one-sided reconciliation closure request."""

    case_id: UUID
    approver_id: str
    approver_role: str
    justification: str


@dataclass
class OneSidedClosureResult:
    """Result of a one-sided closure validation."""

    approved: bool
    case_id: UUID
    approver_id: str
    justification: str
    closure_type: str = "one_sided"


@dataclass
class PortalLinkValidationResult:
    """Result of portal link expiry validation."""

    is_valid: bool
    token: str
    created_at: datetime | None = None
    expires_at: datetime | None = None
    days_remaining: int | None = None
    message: str | None = None


@dataclass
class PeriodOverlapCheckResult:
    """Result of period overlap check."""

    has_overlap: bool
    conflicting_case_id: UUID | None = None
    conflicting_case_reference: str | None = None


@dataclass
class VendorValidationResult:
    """Result of active vendor validation."""

    is_active: bool
    vendor_id: UUID | None = None
    vendor_code: str | None = None
    message: str | None = None


@dataclass
class NetZeroValidationResult:
    """Result of net-zero validation for case closure."""

    can_close: bool
    net_difference: Decimal
    is_one_sided_approved: bool = False
    message: str | None = None


# ─── Service ──────────────────────────────────────────────────────────────────


class BusinessRulesService:
    """
    Centralized business rules validation service for VLR.

    Validates:
    - One-sided closure authorization (Req 32.1, 32.2, 32.3)
    - Portal link expiry (Req 33.1, 33.2, 33.3)
    - Period overlap prevention (Req 34.1, 34.2)
    - Active vendor validation (Req 35.1, 35.2)
    - Case closure net-zero condition (Req 37.1, 37.2, 37.3)
    """

    RECON_MANAGER_ROLE = "Recon_Manager"

    def __init__(
        self,
        case_repository=None,
        request_repository=None,
        vendor_repository=None,
    ) -> None:
        self._case_repo = case_repository
        self._request_repo = request_repository
        self._vendor_repo = vendor_repository

    # ──────────────────────────────────────────────────────────────────────
    # Rule 1: One-Sided Reconciliation Closure
    # Requirements: 32.1, 32.2, 32.3
    # ──────────────────────────────────────────────────────────────────────

    def validate_one_sided_closure(
        self, request: OneSidedClosureRequest
    ) -> OneSidedClosureResult:
        """
        Validate a one-sided reconciliation closure request.

        Requirements:
        - 32.1: Allow Recon_Manager to initiate one-sided closure when vendor
                 is non-responsive after all reminder cycles.
        - 32.2: Require explicit Recon_Manager approval.
        - 32.3: Record justification and approver details.

        Args:
            request: The one-sided closure request with approver details.

        Returns:
            OneSidedClosureResult if validation passes.

        Raises:
            OneSidedClosureNotApprovedException: If approver is not Recon_Manager.
            OneSidedClosureMissingJustificationException: If no justification provided.
        """
        # Requirement 32.2: Require Recon_Manager role
        if request.approver_role != self.RECON_MANAGER_ROLE:
            raise OneSidedClosureNotApprovedException(
                f"One-sided closure requires approval from a {self.RECON_MANAGER_ROLE}. "
                f"Current role: '{request.approver_role}'."
            )

        # Requirement 32.3: Require justification
        if not request.justification or not request.justification.strip():
            raise OneSidedClosureMissingJustificationException()

        logger.info(
            "One-sided closure approved: case_id=%s, approver=%s",
            request.case_id,
            request.approver_id,
        )

        return OneSidedClosureResult(
            approved=True,
            case_id=request.case_id,
            approver_id=request.approver_id,
            justification=request.justification,
        )

    async def execute_one_sided_closure(
        self, request: OneSidedClosureRequest
    ) -> OneSidedClosureResult:
        """
        Execute the full one-sided closure: validate, record justification,
        and update case with closure details.

        Requirement 32.3: Record justification and approver details.
        """
        result = self.validate_one_sided_closure(request)

        # Update the case record with one-sided closure details
        if self._case_repo is not None:
            await self._case_repo.update(
                request.case_id,
                {
                    "closure_type": "one_sided",
                    "closure_justification": request.justification,
                    "closure_approved_by": request.approver_id,
                    "status": "closed",
                },
            )

        return result

    # ──────────────────────────────────────────────────────────────────────
    # Rule 2: Portal Link Expiry Enforcement
    # Requirements: 33.1, 33.2, 33.3
    # ──────────────────────────────────────────────────────────────────────

    def validate_portal_link_expiry(
        self,
        token_created_at: datetime,
        current_time: datetime | None = None,
    ) -> PortalLinkValidationResult:
        """
        Validate whether a portal link is still within its 90-day validity period.

        Requirements:
        - 33.1: Enforce 90-day validity period for portal access links.
        - 33.2: Display expiry message and deny access after 90 days.

        Args:
            token_created_at: When the portal token/link was created.
            current_time: Current UTC time (defaults to now if not provided).

        Returns:
            PortalLinkValidationResult with validity status.

        Raises:
            PortalLinkExpiredException: If the link has expired.
        """
        if current_time is None:
            current_time = datetime.now(timezone.utc)

        # Ensure token_created_at is timezone-aware
        if token_created_at.tzinfo is None:
            token_created_at = token_created_at.replace(tzinfo=timezone.utc)

        expires_at = token_created_at + timedelta(days=PORTAL_LINK_VALIDITY_DAYS)
        is_valid = current_time < expires_at

        if is_valid:
            days_remaining = (expires_at - current_time).days
            return PortalLinkValidationResult(
                is_valid=True,
                token="",  # Token value not stored here for security
                created_at=token_created_at,
                expires_at=expires_at,
                days_remaining=days_remaining,
            )
        else:
            raise PortalLinkExpiredException(
                "This portal link has expired. Portal links are valid for 90 days. "
                "Please contact the reconciliation team to request a new invitation."
            )

    def can_regenerate_portal_link(self, user_role: str) -> bool:
        """
        Check if a user can regenerate an expired portal link.

        Requirement 33.3: Allow Recon_Manager to generate new portal link.

        Args:
            user_role: The role of the user attempting to regenerate.

        Returns:
            True if the user has the required role.
        """
        return user_role == self.RECON_MANAGER_ROLE

    # ──────────────────────────────────────────────────────────────────────
    # Rule 3: Period Overlap Prevention
    # Requirements: 34.1, 34.2
    # ──────────────────────────────────────────────────────────────────────

    def check_period_overlap(
        self,
        new_period_start: date,
        new_period_end: date,
        existing_periods: list[dict],
    ) -> PeriodOverlapCheckResult:
        """
        Check if a new reconciliation period overlaps with any existing cases
        for the same vendor and company code.

        Requirements:
        - 34.1: Validate that the requested period does not overlap with any
                 existing active or closed case for the same vendor and company code.
        - 34.2: Return conflicting case reference on rejection.

        Args:
            new_period_start: Start date of the new reconciliation period.
            new_period_end: End date of the new reconciliation period.
            existing_periods: List of dicts with keys:
                - period_start (date)
                - period_end (date)
                - case_id (UUID)
                - case_reference (str)

        Returns:
            PeriodOverlapCheckResult with overlap status.

        Raises:
            PeriodOverlapException: If an overlapping period is found.
        """
        for existing in existing_periods:
            existing_start = existing["period_start"]
            existing_end = existing["period_end"]

            # Overlap: new_start <= existing_end AND existing_start <= new_end
            if new_period_start <= existing_end and existing_start <= new_period_end:
                case_ref = existing.get("case_reference", str(existing.get("case_id", "")))
                raise PeriodOverlapException(
                    conflicting_case_reference=case_ref,
                    message=(
                        f"A reconciliation case already exists for this vendor in the "
                        f"specified period. Conflicting case: {case_ref}"
                    ),
                )

        return PeriodOverlapCheckResult(has_overlap=False)

    async def validate_period_no_overlap(
        self,
        vendor_id: UUID,
        company_code: str,
        period_start: date,
        period_end: date,
        exclude_case_id: UUID | None = None,
    ) -> PeriodOverlapCheckResult:
        """
        Validate that no overlapping period exists using the repository.

        Wrapper that integrates with the request repository for database-level
        overlap detection.

        Args:
            vendor_id: The vendor ID.
            company_code: The company code.
            period_start: New period start date.
            period_end: New period end date.
            exclude_case_id: Optional case ID to exclude (for updates).

        Returns:
            PeriodOverlapCheckResult if no overlap.

        Raises:
            PeriodOverlapException: If an overlapping period is found.
        """
        if self._request_repo is None:
            return PeriodOverlapCheckResult(has_overlap=False)

        has_overlap = await self._request_repo.has_overlapping_period(
            vendor_id=vendor_id,
            company_code=company_code,
            period_start=period_start,
            period_end=period_end,
            exclude_request_id=exclude_case_id,
        )

        if has_overlap:
            raise PeriodOverlapException(
                message=(
                    "A reconciliation case already exists for this vendor in the "
                    "specified period."
                )
            )

        return PeriodOverlapCheckResult(has_overlap=False)

    # ──────────────────────────────────────────────────────────────────────
    # Rule 4: Active Vendor Validation
    # Requirements: 35.1, 35.2
    # ──────────────────────────────────────────────────────────────────────

    def validate_vendor_active(
        self,
        vendor_status: str,
        vendor_code: str | None = None,
    ) -> VendorValidationResult:
        """
        Validate that a vendor has an active status.

        Requirements:
        - 35.1: Verify vendor has active status in vendor master.
        - 35.2: Reject request and inform user if vendor is inactive.

        Args:
            vendor_status: The current vendor status string.
            vendor_code: Optional vendor code for error messaging.

        Returns:
            VendorValidationResult if vendor is active.

        Raises:
            VendorNotActiveException: If vendor is inactive.
        """
        if vendor_status.lower() != "active":
            raise VendorNotActiveException(
                vendor_code=vendor_code,
                message=(
                    f"Cannot create reconciliation request for inactive vendor"
                    f"{' ' + repr(vendor_code) if vendor_code else ''}. "
                    f"Only active vendors are eligible for reconciliation. "
                    f"Current status: '{vendor_status}'."
                ),
            )

        return VendorValidationResult(
            is_active=True,
            vendor_code=vendor_code,
        )

    async def validate_vendor_active_by_id(
        self,
        vendor_id: UUID,
        company_code: str,
    ) -> VendorValidationResult:
        """
        Validate vendor is active by fetching from the repository.

        Args:
            vendor_id: The vendor ID to check.
            company_code: The company code for scoping.

        Returns:
            VendorValidationResult if vendor is active.

        Raises:
            VendorNotActiveException: If vendor is inactive.
            ValueError: If vendor not found.
        """
        if self._vendor_repo is None:
            return VendorValidationResult(is_active=True)

        vendor = await self._vendor_repo.get_by_id(vendor_id, company_code)
        if vendor is None:
            raise ValueError(f"Vendor with id '{vendor_id}' not found.")

        vendor_status = getattr(vendor, "status", "active")
        vendor_code = getattr(vendor, "vendor_code", str(vendor_id))

        return self.validate_vendor_active(vendor_status, vendor_code)

    # ──────────────────────────────────────────────────────────────────────
    # Rule 5: Case Closure Net-Zero Condition
    # Requirements: 37.1, 37.2, 37.3
    # ──────────────────────────────────────────────────────────────────────

    def validate_closure_net_zero(
        self,
        net_difference: Decimal,
        is_one_sided_closure_approved: bool = False,
    ) -> NetZeroValidationResult:
        """
        Validate that the net difference is zero for case closure.

        Requirements:
        - 37.1: Verify net difference between company and vendor equals zero.
        - 37.2: Reject closure and display remaining difference if not zero.
        - 37.3: Allow closure regardless of net difference if one-sided closure
                 is approved by Recon_Manager.

        Args:
            net_difference: The net difference between company and vendor balances.
            is_one_sided_closure_approved: Whether one-sided closure has been approved.

        Returns:
            NetZeroValidationResult if closure is allowed.

        Raises:
            CaseClosureNetZeroException: If net difference is not zero and
                                          one-sided closure is not approved.
        """
        # Requirement 37.3: Bypass for approved one-sided closures
        if is_one_sided_closure_approved:
            return NetZeroValidationResult(
                can_close=True,
                net_difference=net_difference,
                is_one_sided_approved=True,
                message="Closure approved via one-sided reconciliation.",
            )

        # Requirement 37.1 & 37.2: Net difference must be zero
        if net_difference != Decimal("0"):
            raise CaseClosureNetZeroException(
                net_difference=net_difference,
                message=(
                    f"Cannot close case: net difference is {net_difference}. "
                    f"The net difference must be zero for normal closure."
                ),
            )

        return NetZeroValidationResult(
            can_close=True,
            net_difference=net_difference,
            is_one_sided_approved=False,
            message="Case is fully reconciled. Net difference is zero.",
        )

    async def validate_case_closure(
        self,
        case_id: UUID,
        is_one_sided_closure_approved: bool = False,
    ) -> NetZeroValidationResult:
        """
        Validate case closure by checking net difference from the case record.

        Args:
            case_id: The case ID to validate.
            is_one_sided_closure_approved: Whether one-sided closure is approved.

        Returns:
            NetZeroValidationResult if closure is allowed.

        Raises:
            CaseClosureNetZeroException: If net difference is not zero and
                                          one-sided closure is not approved.
            ValueError: If case not found.
        """
        if self._case_repo is None:
            return NetZeroValidationResult(
                can_close=True,
                net_difference=Decimal("0"),
            )

        case = await self._case_repo.get_by_id(case_id)
        if case is None:
            raise ValueError(f"Reconciliation case with id '{case_id}' not found.")

        net_difference = getattr(case, "net_difference", None) or Decimal("0")
        closure_type = getattr(case, "closure_type", None)

        # Check if one-sided closure was already approved for this case
        if closure_type == "one_sided" or is_one_sided_closure_approved:
            is_one_sided_closure_approved = True

        return self.validate_closure_net_zero(
            net_difference=Decimal(str(net_difference)),
            is_one_sided_closure_approved=is_one_sided_closure_approved,
        )
