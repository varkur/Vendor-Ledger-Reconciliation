"""
Exception Management Domain Service.

Implements exception categorization by severity, resolution actions,
Row_10 calculation, manual edit limit enforcement, write-off threshold
checks, and bulk resolution for same-category exceptions.

Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7, 6.8, 6.9, 6.10
"""

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal
from enum import Enum
from uuid import UUID, uuid4

from src.domain.exceptions.vlr import (
    CaseClosedException,
    EditLimitExceededException,
    WriteOffThresholdExceededException,
)
from src.domain.repositories.vlr.case_repository import ICaseRepository
from src.domain.repositories.vlr.exception_repository import (
    ExceptionFilters,
    IExceptionRepository,
)
from src.domain.repositories.vlr.ledger_entry_repository import ILedgerEntryRepository
from src.domain.repositories.vlr.setting_repository import ISettingRepository


# ─── Enumerations ─────────────────────────────────────────────────────────────


class ExceptionSeverity(str, Enum):
    """Exception severity levels."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class ResolutionAction(str, Enum):
    """Available resolution actions for exceptions."""

    ACM = "accept_company_match"
    RDV = "request_document_vendor"
    MTD = "mark_tds_difference"
    MAA = "mark_agreed_adjustment"
    WOF = "write_off"
    ESC = "escalate"


class ExceptionStatus(str, Enum):
    """Exception lifecycle status."""

    OPEN = "open"
    RESOLVED = "resolved"
    ESCALATED = "escalated"


# ─── Constants ────────────────────────────────────────────────────────────────

MAX_MANUAL_EDITS_PER_CASE = 10

# Default severity thresholds (can be overridden via settings)
DEFAULT_SEVERITY_THRESHOLDS = {
    # Amount thresholds (in currency units)
    "critical_amount": Decimal("100000"),  # >= 100,000
    "high_amount": Decimal("50000"),  # >= 50,000
    "medium_amount": Decimal("10000"),  # >= 10,000
    # Age thresholds (in days since first flagged)
    "critical_age_days": 90,  # >= 90 days
    "high_age_days": 60,  # >= 60 days
    "medium_age_days": 30,  # >= 30 days
}

# Default write-off threshold requiring manager approval
DEFAULT_WRITE_OFF_THRESHOLD = Decimal("50000")


# ─── Data Transfer Objects ────────────────────────────────────────────────────


@dataclass
class SeverityThresholds:
    """Configurable thresholds for exception severity classification."""

    critical_amount: Decimal = Decimal("100000")
    high_amount: Decimal = Decimal("50000")
    medium_amount: Decimal = Decimal("10000")
    critical_age_days: int = 90
    high_age_days: int = 60
    medium_age_days: int = 30


@dataclass
class ExceptionCategoryResult:
    """Result of categorizing an unmatched entry."""

    ledger_entry_id: UUID
    case_id: UUID
    category: str
    severity: str
    amount: Decimal
    first_flagged_date: date


@dataclass
class ResolutionResult:
    """Result of resolving an exception."""

    exception_id: UUID
    action: str
    status: str
    resolved_by: UUID
    resolved_date: datetime
    comments: str | None = None


@dataclass
class BulkResolutionResult:
    """Result of bulk resolving exceptions."""

    total: int
    resolved: int
    failed: int
    results: list[ResolutionResult] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


@dataclass
class Row10Result:
    """Result of Row 10 calculation."""

    company_total: Decimal
    vendor_total: Decimal
    resolved_adjustments: Decimal
    net_difference: Decimal


# ─── Service ──────────────────────────────────────────────────────────────────


class ExceptionManagerService:
    """
    Domain service for exception management.

    Handles categorization, resolution, Row_10 calculation,
    edit limit enforcement, write-off thresholds, and bulk resolution.
    """

    def __init__(
        self,
        exception_repository: IExceptionRepository,
        case_repository: ICaseRepository,
        ledger_entry_repository: ILedgerEntryRepository,
        setting_repository: ISettingRepository,
    ) -> None:
        self._exception_repo = exception_repository
        self._case_repo = case_repository
        self._ledger_repo = ledger_entry_repository
        self._setting_repo = setting_repository

    # ──────────────────────────────────────────────────────────────────────
    # Exception Categorization
    # ──────────────────────────────────────────────────────────────────────

    async def categorize_exceptions(
        self,
        case_id: UUID,
        unmatched_entry_ids: list[UUID],
        company_code: str | None = None,
    ) -> list[ExceptionCategoryResult]:
        """
        Categorize unmatched ledger entries by severity based on amount
        and age thresholds.

        Requirement 6.1: Categorize by severity (Critical, High, Medium, Low)
                         based on amount and age.
        Requirement 6.4: Track exception ageing from first flagged date.
        """
        if not unmatched_entry_ids:
            return []

        # Load severity thresholds from settings (or use defaults)
        thresholds = await self._load_severity_thresholds(company_code)
        today = date.today()

        results: list[ExceptionCategoryResult] = []

        for entry_id in unmatched_entry_ids:
            entry = await self._ledger_repo.get_by_id(entry_id)
            if entry is None:
                continue

            amount = Decimal(str(getattr(entry, "amount", 0)))
            abs_amount = abs(amount)

            # Determine severity based on amount and age
            first_flagged = today  # New exceptions are flagged today
            severity = self._classify_severity(abs_amount, 0, thresholds)

            category_result = ExceptionCategoryResult(
                ledger_entry_id=entry_id,
                case_id=case_id,
                category="unmatched",
                severity=severity,
                amount=amount,
                first_flagged_date=first_flagged,
            )
            results.append(category_result)

            # Persist the exception with proper severity
            await self._exception_repo.create({
                "case_id": str(case_id),
                "ledger_entry_id": str(entry_id),
                "category": "unmatched",
                "severity": severity,
                "amount": float(amount),
                "first_flagged_date": first_flagged,
                "status": ExceptionStatus.OPEN.value,
            })

        return results

    def _classify_severity(
        self,
        amount: Decimal,
        age_days: int,
        thresholds: SeverityThresholds,
    ) -> str:
        """
        Determine severity based on amount and age thresholds.

        An entry is classified at the highest severity level that
        either its amount or age qualifies for.

        Requirement 6.1: Classification based on amount and age.
        """
        # Check Critical thresholds
        if amount >= thresholds.critical_amount or age_days >= thresholds.critical_age_days:
            return ExceptionSeverity.CRITICAL.value

        # Check High thresholds
        if amount >= thresholds.high_amount or age_days >= thresholds.high_age_days:
            return ExceptionSeverity.HIGH.value

        # Check Medium thresholds
        if amount >= thresholds.medium_amount or age_days >= thresholds.medium_age_days:
            return ExceptionSeverity.MEDIUM.value

        # Default to Low
        return ExceptionSeverity.LOW.value

    async def recategorize_exception(
        self,
        exception_id: UUID,
        company_code: str | None = None,
    ) -> str:
        """
        Recategorize an exception based on current age.

        Requirement 6.4: Track exception ageing from first flagged date.
        """
        exception = await self._exception_repo.get_by_id(exception_id)
        if exception is None:
            return ExceptionSeverity.LOW.value

        thresholds = await self._load_severity_thresholds(company_code)
        first_flagged = getattr(exception, "first_flagged_date", date.today())
        age_days = (date.today() - first_flagged).days
        amount = Decimal(str(abs(getattr(exception, "amount", 0))))

        new_severity = self._classify_severity(amount, age_days, thresholds)

        # Update if severity changed
        current_severity = getattr(exception, "severity", "")
        if new_severity != current_severity:
            await self._exception_repo.update(exception_id, {"severity": new_severity})

        return new_severity

    # ──────────────────────────────────────────────────────────────────────
    # Resolution Actions
    # ──────────────────────────────────────────────────────────────────────

    async def resolve_exception(
        self,
        exception_id: UUID,
        action: ResolutionAction,
        resolved_by: UUID,
        comment: str | None = None,
        company_code: str | None = None,
    ) -> ResolutionResult:
        """
        Resolve an exception with a specified action.

        Requirement 6.2: Support resolution actions ACM, RDV, MTD, MAA, WOF, ESC.
        Requirement 6.3: Record action, actor, timestamp, and comments.
        Requirement 6.5: Update reconciliation statement totals and Row_10.
        Requirement 6.7: Enforce maximum 10 manual edits per case.
        Requirement 6.10: Write-off threshold requires manager approval.
        """
        # Get the exception
        exception = await self._exception_repo.get_by_id(exception_id)
        if exception is None:
            raise ValueError(f"Exception '{exception_id}' not found.")

        case_id = UUID(str(getattr(exception, "case_id")))

        # Check case is not closed (Requirement 6.6 implicit)
        await self._validate_case_not_closed(case_id)

        # Enforce manual edit limit (Requirement 6.7, 6.8)
        await self._enforce_edit_limit(case_id)

        # Check write-off threshold (Requirement 6.10)
        if action == ResolutionAction.WOF:
            amount = Decimal(str(abs(getattr(exception, "amount", 0))))
            await self._check_write_off_threshold(amount, company_code)

        # Record the resolution
        resolved_date = datetime.now(timezone.utc)
        new_status = (
            ExceptionStatus.ESCALATED.value
            if action == ResolutionAction.ESC
            else ExceptionStatus.RESOLVED.value
        )

        # Update exception status
        await self._exception_repo.update(exception_id, {"status": new_status})

        # Increment edit count on the case
        await self._case_repo.increment_edit_count(case_id)

        return ResolutionResult(
            exception_id=exception_id,
            action=action.value,
            status=new_status,
            resolved_by=resolved_by,
            resolved_date=resolved_date,
            comments=comment,
        )

    async def bulk_resolve(
        self,
        exception_ids: list[UUID],
        action: ResolutionAction,
        resolved_by: UUID,
        comment: str | None = None,
        company_code: str | None = None,
    ) -> BulkResolutionResult:
        """
        Bulk resolve multiple exceptions of the same category.

        Requirement 6.9: Support bulk resolution for same-category exceptions.
        Requirement 6.7: Enforce edit limit across the bulk operation.
        """
        if not exception_ids:
            return BulkResolutionResult(total=0, resolved=0, failed=0)

        # Validate all exceptions are same category
        categories: set[str] = set()
        case_ids: set[UUID] = set()
        for eid in exception_ids:
            exc = await self._exception_repo.get_by_id(eid)
            if exc is not None:
                categories.add(getattr(exc, "category", ""))
                case_ids.add(UUID(str(getattr(exc, "case_id"))))

        if len(categories) > 1:
            return BulkResolutionResult(
                total=len(exception_ids),
                resolved=0,
                failed=len(exception_ids),
                errors=["Bulk resolution requires all exceptions to be of the same category."],
            )

        results: list[ResolutionResult] = []
        errors: list[str] = []

        for eid in exception_ids:
            try:
                result = await self.resolve_exception(
                    exception_id=eid,
                    action=action,
                    resolved_by=resolved_by,
                    comment=comment,
                    company_code=company_code,
                )
                results.append(result)
            except EditLimitExceededException:
                errors.append(
                    f"Edit limit reached. Could not resolve exception '{eid}'."
                )
                break  # Stop processing further
            except WriteOffThresholdExceededException:
                errors.append(
                    f"Write-off threshold exceeded for exception '{eid}'. "
                    "Manager approval required."
                )
            except Exception as e:
                errors.append(f"Failed to resolve exception '{eid}': {str(e)}")

        return BulkResolutionResult(
            total=len(exception_ids),
            resolved=len(results),
            failed=len(exception_ids) - len(results),
            results=results,
            errors=errors,
        )

    # ──────────────────────────────────────────────────────────────────────
    # Row 10 Calculation
    # ──────────────────────────────────────────────────────────────────────

    async def calculate_row_10(self, case_id: UUID) -> Row10Result:
        """
        Calculate Row_10 balance for a reconciliation case.

        Requirement 6.5: Row_10 = sum company entries - sum vendor entries
                         - sum resolved adjustments.

        The net_difference should equal zero before the case can be
        submitted for approval.
        """
        # Sum all company-side ledger entries
        company_total = Decimal(
            str(await self._ledger_repo.sum_amount_by_case(case_id, "company"))
        )

        # Sum all vendor-side ledger entries
        vendor_total = Decimal(
            str(await self._ledger_repo.sum_amount_by_case(case_id, "vendor"))
        )

        # Sum resolved adjustments (amounts from resolved exceptions)
        resolved_adjustments = await self._sum_resolved_adjustments(case_id)

        # Row_10 = company - vendor - resolved adjustments
        net_difference = company_total - vendor_total - resolved_adjustments

        return Row10Result(
            company_total=company_total,
            vendor_total=vendor_total,
            resolved_adjustments=resolved_adjustments,
            net_difference=net_difference,
        )

    async def _sum_resolved_adjustments(self, case_id: UUID) -> Decimal:
        """
        Sum the amounts of all resolved exceptions for a case.

        These represent accepted differences that have been accounted for.
        """
        # Get all exceptions for this case that are resolved
        filters = ExceptionFilters(case_id=case_id, status=ExceptionStatus.RESOLVED.value)
        result = await self._exception_repo.list_by_case(case_id, filters=filters)

        total = Decimal("0")
        for exc in result.items:
            amount = Decimal(str(getattr(exc, "amount", 0)))
            total += amount

        return total

    # ──────────────────────────────────────────────────────────────────────
    # Edit Limit Enforcement
    # ──────────────────────────────────────────────────────────────────────

    async def get_edit_count(self, case_id: UUID) -> int:
        """
        Get current manual edit count for a case.

        Requirement 6.7: Maximum 10 manual edits per reconciliation case.
        """
        case = await self._case_repo.get_by_id(case_id)
        if case is None:
            return 0
        return int(getattr(case, "edit_count", 0))

    async def get_remaining_edits(self, case_id: UUID) -> int:
        """Get remaining allowed edits for a case."""
        current = await self.get_edit_count(case_id)
        return max(0, MAX_MANUAL_EDITS_PER_CASE - current)

    async def _enforce_edit_limit(self, case_id: UUID) -> None:
        """
        Check and enforce the manual edit limit.

        Requirement 6.7, 6.8: Reject edits when limit is reached.
        """
        current_count = await self.get_edit_count(case_id)
        if current_count >= MAX_MANUAL_EDITS_PER_CASE:
            raise EditLimitExceededException()

    # ──────────────────────────────────────────────────────────────────────
    # Write-Off Threshold
    # ──────────────────────────────────────────────────────────────────────

    async def _check_write_off_threshold(
        self,
        amount: Decimal,
        company_code: str | None = None,
    ) -> None:
        """
        Check if a write-off amount exceeds the configured threshold.

        Requirement 6.10: Write-off exceeding threshold requires manager approval.
        """
        threshold = await self._load_write_off_threshold(company_code)
        if amount > threshold:
            raise WriteOffThresholdExceededException()

    async def check_write_off_requires_approval(
        self,
        exception_id: UUID,
        company_code: str | None = None,
    ) -> bool:
        """
        Check if a write-off for this exception would require manager approval.

        Returns True if the amount exceeds the configured threshold.
        """
        exception = await self._exception_repo.get_by_id(exception_id)
        if exception is None:
            return False

        amount = Decimal(str(abs(getattr(exception, "amount", 0))))
        threshold = await self._load_write_off_threshold(company_code)
        return amount > threshold

    # ──────────────────────────────────────────────────────────────────────
    # Case Validation
    # ──────────────────────────────────────────────────────────────────────

    async def _validate_case_not_closed(self, case_id: UUID) -> None:
        """
        Validate the case is not in closed status.

        Requirement 6.6 (implicit): Cannot resolve exceptions on closed cases.
        """
        case = await self._case_repo.get_by_id(case_id)
        if case is not None:
            status = getattr(case, "status", "")
            if status == "closed":
                raise CaseClosedException()

    async def has_unresolved_critical(self, case_id: UUID) -> bool:
        """
        Check if a case has unresolved critical exceptions.

        Requirement 6.6: Reject closure with unresolved Critical exceptions.
        """
        critical_exceptions = await self._exception_repo.get_critical_open_by_case(
            case_id
        )
        return len(critical_exceptions) > 0

    async def get_unresolved_critical(self, case_id: UUID) -> list[object]:
        """
        Get all unresolved critical exceptions for a case.

        Requirement 6.6: List outstanding Critical items.
        """
        return await self._exception_repo.get_critical_open_by_case(case_id)

    # ──────────────────────────────────────────────────────────────────────
    # Configuration Loading
    # ──────────────────────────────────────────────────────────────────────

    async def _load_severity_thresholds(
        self, company_code: str | None = None
    ) -> SeverityThresholds:
        """Load severity thresholds from settings or return defaults."""
        if company_code is None:
            return SeverityThresholds()

        thresholds = SeverityThresholds()

        # Try to load from settings
        try:
            setting = await self._setting_repo.get_by_key(
                company_code, "exception_critical_amount"
            )
            if setting:
                thresholds.critical_amount = Decimal(
                    str(getattr(setting, "value", thresholds.critical_amount))
                )

            setting = await self._setting_repo.get_by_key(
                company_code, "exception_high_amount"
            )
            if setting:
                thresholds.high_amount = Decimal(
                    str(getattr(setting, "value", thresholds.high_amount))
                )

            setting = await self._setting_repo.get_by_key(
                company_code, "exception_medium_amount"
            )
            if setting:
                thresholds.medium_amount = Decimal(
                    str(getattr(setting, "value", thresholds.medium_amount))
                )

            setting = await self._setting_repo.get_by_key(
                company_code, "exception_critical_age_days"
            )
            if setting:
                thresholds.critical_age_days = int(
                    getattr(setting, "value", thresholds.critical_age_days)
                )

            setting = await self._setting_repo.get_by_key(
                company_code, "exception_high_age_days"
            )
            if setting:
                thresholds.high_age_days = int(
                    getattr(setting, "value", thresholds.high_age_days)
                )

            setting = await self._setting_repo.get_by_key(
                company_code, "exception_medium_age_days"
            )
            if setting:
                thresholds.medium_age_days = int(
                    getattr(setting, "value", thresholds.medium_age_days)
                )
        except Exception:
            # If settings lookup fails, use defaults
            pass

        return thresholds

    async def _load_write_off_threshold(
        self, company_code: str | None = None
    ) -> Decimal:
        """Load write-off threshold from settings or return default."""
        if company_code is None:
            return DEFAULT_WRITE_OFF_THRESHOLD

        try:
            setting = await self._setting_repo.get_by_key(
                company_code, "write_off_threshold"
            )
            if setting:
                return Decimal(str(getattr(setting, "value", DEFAULT_WRITE_OFF_THRESHOLD)))
        except Exception:
            pass

        return DEFAULT_WRITE_OFF_THRESHOLD
