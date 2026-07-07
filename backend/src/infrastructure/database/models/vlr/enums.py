"""
VLR domain enumerations used across models and domain services.
"""

from enum import Enum


class RequestStatus(str, Enum):
    """Status lifecycle for ReconciliationRequest."""

    DRAFT = "draft"
    ACTIVE = "active"
    IN_PROGRESS = "in_progress"
    REVIEW = "review"
    SIGN_OFF = "sign_off"
    CLOSED = "closed"


class CaseStatus(str, Enum):
    """Status lifecycle for ReconciliationCase."""

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


class MatchPassType(int, Enum):
    """Types of matching passes executed by the reconciliation engine."""

    EXACT = 1
    TOLERANCE = 2
    FUZZY_REFERENCE = 3
    ONE_TO_MANY = 4
    MANY_TO_ONE = 5
    UNMATCHED = 6


class ExceptionSeverity(str, Enum):
    """Severity classification for reconciliation exceptions."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class ResolutionAction(str, Enum):
    """Actions available for resolving reconciliation exceptions."""

    ACM = "accept_company_match"
    RDV = "request_document_vendor"
    MTD = "mark_tds_difference"
    MAA = "mark_agreed_adjustment"
    WOF = "write_off"
    ESC = "escalate"


class LedgerSide(str, Enum):
    """Identifies which side a ledger entry belongs to."""

    COMPANY = "company"
    VENDOR = "vendor"


class CaseType(str, Enum):
    """Type of reconciliation case."""

    BATCH = "batch"
    DIRECT = "direct"


class NotificationType(str, Enum):
    """Types of notifications sent by the system."""

    INVITATION = "invitation"
    REMINDER = "reminder"
    ESCALATION = "escalation"
    APPROVAL_REQUEST = "approval_request"
    REJECTION = "rejection"
    SIGN_OFF_REQUEST = "sign_off_request"
    SIGN_OFF_COMPLETE = "sign_off_complete"
