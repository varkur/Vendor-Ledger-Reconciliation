"""
VLR Domain Exception Hierarchy.

All domain-level exceptions for the Vendor Ledger Reconciliation module.
Each exception carries an error_code (machine-readable) and message (human-readable),
and maps to a specific HTTP status code for the API layer.
"""


class VLRDomainException(Exception):
    """Base exception for all VLR domain errors."""

    error_code: str = "VLR_DOMAIN_ERROR"
    status_code: int = 400

    def __init__(self, message: str | None = None) -> None:
        self.message = message or self._default_message()
        super().__init__(self.message)

    def _default_message(self) -> str:
        return "A domain error occurred in the VLR module."


class VendorNotFoundException(VLRDomainException):
    """Raised when a vendor record cannot be found."""

    error_code = "VLR_VENDOR_NOT_FOUND"
    status_code = 404

    def _default_message(self) -> str:
        return "The requested vendor was not found."


class VendorInactiveException(VLRDomainException):
    """Raised when an operation is attempted on an inactive vendor."""

    error_code = "VLR_VENDOR_INACTIVE"
    status_code = 409

    def _default_message(self) -> str:
        return "The vendor is inactive and cannot be used for this operation."


class VendorHasActiveCaseException(VLRDomainException):
    """Raised when vendor deletion is blocked by an active reconciliation case."""

    error_code = "VLR_VENDOR_HAS_ACTIVE_CASE"
    status_code = 409

    def _default_message(self) -> str:
        return "The vendor cannot be deleted because it has an active reconciliation case."


class OverlappingPeriodException(VLRDomainException):
    """Raised when a reconciliation request overlaps an existing period for the same vendor."""

    error_code = "VLR_OVERLAPPING_PERIOD"
    status_code = 409

    def _default_message(self) -> str:
        return "A reconciliation request already exists for this vendor in the specified period."


class InvalidStatusTransitionException(VLRDomainException):
    """Raised when an invalid status transition is attempted."""

    error_code = "VLR_INVALID_STATUS_TRANSITION"
    status_code = 409

    def __init__(
        self,
        current_status: str | None = None,
        target_status: str | None = None,
        message: str | None = None,
    ) -> None:
        if message is None and current_status and target_status:
            message = (
                f"Cannot transition from '{current_status}' to '{target_status}'."
            )
        super().__init__(message)

    def _default_message(self) -> str:
        return "The requested status transition is not allowed."


class CaseClosedException(VLRDomainException):
    """Raised when an edit is attempted on a closed reconciliation case."""

    error_code = "VLR_CASE_CLOSED"
    status_code = 409

    def _default_message(self) -> str:
        return "This reconciliation case is closed and cannot be modified."


class UploadLimitExceededException(VLRDomainException):
    """Raised when the vendor file upload limit (5) is exceeded."""

    error_code = "VLR_UPLOAD_LIMIT_EXCEEDED"
    status_code = 409

    def _default_message(self) -> str:
        return (
            "The maximum number of file uploads (5) has been reached for this case. "
            "Please contact the reconciliation team."
        )


class EditLimitExceededException(VLRDomainException):
    """Raised when the manual edit limit (10) per case is exceeded."""

    error_code = "VLR_EDIT_LIMIT_EXCEEDED"
    status_code = 409

    def _default_message(self) -> str:
        return "The maximum number of manual edits (10) has been reached for this case."


class Row10NonZeroException(VLRDomainException):
    """Raised when approval is submitted but Row 10 balance is not zero."""

    error_code = "VLR_ROW10_NON_ZERO"
    status_code = 409

    def __init__(self, difference_amount: str | None = None, message: str | None = None) -> None:
        if message is None and difference_amount is not None:
            message = (
                f"Cannot submit for approval: Row 10 balance is {difference_amount}, "
                "but must be zero."
            )
        super().__init__(message)

    def _default_message(self) -> str:
        return "Cannot submit for approval: Row 10 balance must be zero."


class WriteOffThresholdExceededException(VLRDomainException):
    """Raised when a write-off amount exceeds the configured threshold without approval."""

    error_code = "VLR_WRITE_OFF_THRESHOLD_EXCEEDED"
    status_code = 409

    def _default_message(self) -> str:
        return (
            "The write-off amount exceeds the configured threshold. "
            "Manager approval is required."
        )


class TokenExpiredException(VLRDomainException):
    """Raised when a vendor portal token has expired."""

    error_code = "VLR_TOKEN_EXPIRED"
    status_code = 400

    def _default_message(self) -> str:
        return (
            "The portal access token has expired. "
            "Please contact the reconciliation team to request a new invitation."
        )


class DuplicateVendorCodeException(VLRDomainException):
    """Raised when a vendor code already exists within the same company code."""

    error_code = "VLR_DUPLICATE_VENDOR_CODE"
    status_code = 409

    def __init__(self, vendor_code: str | None = None, message: str | None = None) -> None:
        if message is None and vendor_code is not None:
            message = (
                f"A vendor with code '{vendor_code}' already exists in this company."
            )
        super().__init__(message)

    def _default_message(self) -> str:
        return "A vendor with this code already exists in the company."


class CompanyLedgerNotConfirmedException(VLRDomainException):
    """Raised when an operation requires company ledger confirmation that hasn't occurred."""

    error_code = "VLR_COMPANY_LEDGER_NOT_CONFIRMED"
    status_code = 409

    def _default_message(self) -> str:
        return (
            "The company ledger must be confirmed before this operation can proceed."
        )


class IdempotencyConflictException(VLRDomainException):
    """Raised when a duplicate request is detected via idempotency key."""

    error_code = "VLR_IDEMPOTENCY_CONFLICT"
    status_code = 409

    def _default_message(self) -> str:
        return "A request with this idempotency key has already been processed."


class ConcurrentModificationException(VLRDomainException):
    """Raised when a resource has been modified by another user concurrently."""

    error_code = "VLR_CONCURRENT_MODIFICATION"
    status_code = 409

    def _default_message(self) -> str:
        return "The resource has been modified by another user. Please refresh and try again."


class SAPConnectionException(VLRDomainException):
    """Raised when the SAP system is unavailable or connection fails."""

    error_code = "VLR_SAP_CONNECTION_ERROR"
    status_code = 503

    def _default_message(self) -> str:
        return (
            "Unable to connect to the SAP system. "
            "The operation has been queued for retry."
        )


class FileValidationException(VLRDomainException):
    """Raised when an uploaded file fails validation (type, size, or structure)."""

    error_code = "VLR_FILE_VALIDATION_ERROR"
    status_code = 400

    def __init__(
        self,
        errors: list[str] | None = None,
        message: str | None = None,
    ) -> None:
        self.errors = errors or []
        if message is None and self.errors:
            message = f"File validation failed: {'; '.join(self.errors)}"
        super().__init__(message)

    def _default_message(self) -> str:
        return "The uploaded file failed validation."
