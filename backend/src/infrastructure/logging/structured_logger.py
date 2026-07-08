"""
Structured Logging Service.

Emits JSON log entries with correlation_id, timestamp, service_name,
operation_name, duration_ms, and outcome_status. On failure, includes
error_type and error_message while ensuring no sensitive data
(passwords, tokens, secrets) is ever logged.

This module provides:
- StructuredLogger class for per-service logging
- log_operation() convenience function
- A decorator for automatic operation logging with duration tracking

Requirements: 40.1, 40.2, 40.4
"""

from __future__ import annotations

import functools
import inspect
import json
import logging
import re
import time
from datetime import datetime, timezone
from typing import Any, Callable

from src.observability.correlation import get_correlation_id

# Patterns that indicate sensitive data in field names
SENSITIVE_FIELD_PATTERNS = re.compile(
    r"(password|passwd|secret|token|api_key|apikey|auth|credential|"
    r"private_key|access_key|session_id|cookie|bearer)",
    re.IGNORECASE,
)

# Values that look like tokens or secrets (long hex/base64 strings)
SENSITIVE_VALUE_PATTERNS = re.compile(
    r"^(eyJ[A-Za-z0-9_-]+\.)|([A-Fa-f0-9]{32,})|([A-Za-z0-9+/]{40,}={0,2})$"
)

# Standard Python logger for structured output
_logger = logging.getLogger("vlr.structured")


class StructuredLogger:
    """
    Emits JSON log entries with correlation_id, timestamp, service,
    operation, duration, and outcome.

    Each log entry contains:
    - correlation_id: Request-scoped tracking ID
    - timestamp: ISO 8601 UTC timestamp
    - service_name: The service/module emitting the log
    - operation_name: The specific operation being logged
    - duration_ms: How long the operation took
    - outcome_status: "success" or "failure"
    - error_type: (on failure) The exception class name
    - error_message: (on failure) Sanitized error message

    Sensitive data (passwords, tokens, secrets) is never included.
    """

    def __init__(self, service_name: str) -> None:
        """
        Initialize a StructuredLogger for a specific service.

        Args:
            service_name: Identifier for the service/module (e.g., "data_transformation").
        """
        self._service_name = service_name

    @property
    def service_name(self) -> str:
        """The service name this logger is bound to."""
        return self._service_name

    def log_operation(
        self,
        operation: str,
        duration_ms: float,
        outcome: str,
        correlation_id: str | None = None,
        error: str | None = None,
        error_type: str | None = None,
        **extra: Any,
    ) -> dict[str, Any]:
        """
        Emit a structured JSON log entry.

        Args:
            operation: Name of the operation (e.g., "derive_invoice_number").
            duration_ms: Duration of the operation in milliseconds.
            outcome: Outcome status - typically "success" or "failure".
            correlation_id: Optional correlation ID. If not provided,
                fetched from the current context.
            error: Optional error message (sanitized before logging).
            error_type: Optional error type/class name.
            **extra: Additional context fields to include in the log entry.

        Returns:
            The structured log entry dict (useful for testing).
        """
        # Use context correlation ID if not explicitly provided
        if correlation_id is None:
            correlation_id = get_correlation_id() or "no-correlation-id"

        entry: dict[str, Any] = {
            "correlation_id": correlation_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "service_name": self._service_name,
            "operation_name": operation,
            "duration_ms": round(duration_ms, 2),
            "outcome_status": outcome,
        }

        # Include error details on failure (sanitized)
        if outcome == "failure" or error is not None:
            if error_type:
                entry["error_type"] = error_type
            if error:
                entry["error_message"] = _sanitize_message(error)

        # Include sanitized extra fields
        for key, value in extra.items():
            if not _is_sensitive_field(key):
                entry[key] = _sanitize_value(key, value)

        # Emit as JSON log line
        _logger.info(json.dumps(entry, default=str))

        return entry

    def log_success(
        self,
        operation: str,
        duration_ms: float,
        correlation_id: str | None = None,
        **extra: Any,
    ) -> dict[str, Any]:
        """Convenience method to log a successful operation."""
        return self.log_operation(
            operation=operation,
            duration_ms=duration_ms,
            outcome="success",
            correlation_id=correlation_id,
            **extra,
        )

    def log_failure(
        self,
        operation: str,
        duration_ms: float,
        error: str,
        error_type: str | None = None,
        correlation_id: str | None = None,
        **extra: Any,
    ) -> dict[str, Any]:
        """Convenience method to log a failed operation."""
        return self.log_operation(
            operation=operation,
            duration_ms=duration_ms,
            outcome="failure",
            correlation_id=correlation_id,
            error=error,
            error_type=error_type,
            **extra,
        )


def get_structured_logger(service_name: str) -> StructuredLogger:
    """
    Get a StructuredLogger instance for the given service.

    Args:
        service_name: Identifier for the service/module.

    Returns:
        A configured StructuredLogger instance.
    """
    return StructuredLogger(service_name)


def log_operation(
    service_name: str,
    operation: str,
    duration_ms: float,
    outcome: str,
    correlation_id: str | None = None,
    error: str | None = None,
    error_type: str | None = None,
    **extra: Any,
) -> dict[str, Any]:
    """
    Module-level convenience function to emit a structured log entry.

    Args:
        service_name: The service/module name.
        operation: The operation name.
        duration_ms: Duration in milliseconds.
        outcome: "success" or "failure".
        correlation_id: Optional correlation ID (auto-fetched from context if None).
        error: Optional error message.
        error_type: Optional error type/class name.
        **extra: Additional fields.

    Returns:
        The structured log entry dict.
    """
    logger = StructuredLogger(service_name)
    return logger.log_operation(
        operation=operation,
        duration_ms=duration_ms,
        outcome=outcome,
        correlation_id=correlation_id,
        error=error,
        error_type=error_type,
        **extra,
    )


def structured_log(service_name: str, operation: str | None = None) -> Callable:
    """
    Decorator that automatically logs operation duration and outcome.

    Wraps a function to measure execution time and emit a structured log
    entry on completion (success or failure).

    Usage:
        @structured_log("data_transformation", "derive_invoice_number")
        def derive_invoice_number(self, entry):
            ...

        @structured_log("sap_adapter")  # uses function name as operation
        async def pull_all_items(self, ...):
            ...

    Args:
        service_name: The service/module name for the log entry.
        operation: Optional operation name. Defaults to the function name.

    Returns:
        A decorator that wraps the target function with logging.
    """

    def decorator(func: Callable) -> Callable:
        op_name = operation or func.__name__

        @functools.wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            logger = StructuredLogger(service_name)
            start = time.perf_counter()
            try:
                result = await func(*args, **kwargs)
                duration_ms = (time.perf_counter() - start) * 1000
                logger.log_success(operation=op_name, duration_ms=duration_ms)
                return result
            except Exception as exc:
                duration_ms = (time.perf_counter() - start) * 1000
                logger.log_failure(
                    operation=op_name,
                    duration_ms=duration_ms,
                    error=str(exc),
                    error_type=type(exc).__name__,
                )
                raise

        @functools.wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            logger = StructuredLogger(service_name)
            start = time.perf_counter()
            try:
                result = func(*args, **kwargs)
                duration_ms = (time.perf_counter() - start) * 1000
                logger.log_success(operation=op_name, duration_ms=duration_ms)
                return result
            except Exception as exc:
                duration_ms = (time.perf_counter() - start) * 1000
                logger.log_failure(
                    operation=op_name,
                    duration_ms=duration_ms,
                    error=str(exc),
                    error_type=type(exc).__name__,
                )
                raise

        if inspect.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator


# ──────────────────────────────────────────────────────────────────────────────
# Sensitive Data Sanitization Helpers
# ──────────────────────────────────────────────────────────────────────────────


def _is_sensitive_field(field_name: str) -> bool:
    """Check if a field name suggests sensitive content."""
    return bool(SENSITIVE_FIELD_PATTERNS.search(field_name))


def _sanitize_value(field_name: str, value: Any) -> Any:
    """
    Sanitize a value to prevent sensitive data leakage.

    Replaces values that look like tokens/secrets with a redacted placeholder.
    """
    if isinstance(value, str) and SENSITIVE_VALUE_PATTERNS.match(value):
        return "[REDACTED]"
    return value


def _sanitize_message(message: str) -> str:
    """
    Sanitize an error message to remove potential secrets.

    Removes patterns that look like bearer tokens, API keys, or passwords
    from error messages.
    """
    # Redact bearer tokens
    message = re.sub(
        r"Bearer\s+[A-Za-z0-9._~+/=-]+",
        "Bearer [REDACTED]",
        message,
    )
    # Redact long hex strings (likely keys/tokens)
    message = re.sub(
        r"[A-Fa-f0-9]{32,}",
        "[REDACTED]",
        message,
    )
    # Redact password= patterns
    message = re.sub(
        r"(password|passwd|secret|token|api_key)\s*[=:]\s*\S+",
        r"\1=[REDACTED]",
        message,
        flags=re.IGNORECASE,
    )
    return message
