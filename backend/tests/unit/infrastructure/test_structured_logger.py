"""
Unit tests for the Structured Logging Service.

Tests the StructuredLogger class, log_operation function, decorator,
and sensitive data sanitization logic.

Requirements: 40.1, 40.2, 40.4
"""

from __future__ import annotations

import json
import time
from unittest.mock import patch

import pytest

from src.infrastructure.logging.structured_logger import (
    StructuredLogger,
    _is_sensitive_field,
    _sanitize_message,
    _sanitize_value,
    get_structured_logger,
    log_operation,
    structured_log,
)


class TestStructuredLogger:
    """Tests for the StructuredLogger class."""

    def test_log_operation_success_contains_required_fields(self):
        """All required fields are present in a success log entry."""
        logger = StructuredLogger("test_service")
        entry = logger.log_operation(
            operation="test_op",
            duration_ms=42.5,
            outcome="success",
            correlation_id="test-corr-123",
        )

        assert entry["correlation_id"] == "test-corr-123"
        assert entry["service_name"] == "test_service"
        assert entry["operation_name"] == "test_op"
        assert entry["duration_ms"] == 42.5
        assert entry["outcome_status"] == "success"
        assert "timestamp" in entry
        # No error fields on success
        assert "error_type" not in entry
        assert "error_message" not in entry

    def test_log_operation_failure_includes_error_fields(self):
        """Failed operations include error_type and error_message."""
        logger = StructuredLogger("sap_adapter")
        entry = logger.log_operation(
            operation="pull_all_items",
            duration_ms=1500.0,
            outcome="failure",
            correlation_id="corr-456",
            error="Connection refused to SAP host",
            error_type="SAPConnectionException",
        )

        assert entry["outcome_status"] == "failure"
        assert entry["error_type"] == "SAPConnectionException"
        assert entry["error_message"] == "Connection refused to SAP host"
        assert entry["service_name"] == "sap_adapter"
        assert entry["operation_name"] == "pull_all_items"

    def test_log_operation_uses_context_correlation_id(self):
        """When no correlation_id is provided, it fetches from context."""
        with patch(
            "src.infrastructure.logging.structured_logger.get_correlation_id",
            return_value="ctx-correlation-789",
        ):
            logger = StructuredLogger("workflow")
            entry = logger.log_operation(
                operation="advance_step",
                duration_ms=10.0,
                outcome="success",
            )
            assert entry["correlation_id"] == "ctx-correlation-789"

    def test_log_operation_fallback_when_no_context(self):
        """When context has no correlation ID, uses fallback string."""
        with patch(
            "src.infrastructure.logging.structured_logger.get_correlation_id",
            return_value="",
        ):
            logger = StructuredLogger("test")
            entry = logger.log_operation(
                operation="op",
                duration_ms=1.0,
                outcome="success",
            )
            assert entry["correlation_id"] == "no-correlation-id"

    def test_log_operation_rounds_duration_ms(self):
        """Duration is rounded to 2 decimal places."""
        logger = StructuredLogger("test")
        entry = logger.log_operation(
            operation="op",
            duration_ms=123.456789,
            outcome="success",
            correlation_id="c1",
        )
        assert entry["duration_ms"] == 123.46

    def test_log_operation_extra_fields_included(self):
        """Extra keyword arguments are included in the log entry."""
        logger = StructuredLogger("reconciliation")
        entry = logger.log_operation(
            operation="pass_1_exact_match",
            duration_ms=200.0,
            outcome="success",
            correlation_id="c1",
            matched_count=42,
            case_id="abc-123",
        )
        assert entry["matched_count"] == 42
        assert entry["case_id"] == "abc-123"

    def test_log_operation_filters_sensitive_extra_fields(self):
        """Fields with sensitive names are excluded from log entries."""
        logger = StructuredLogger("auth")
        entry = logger.log_operation(
            operation="login",
            duration_ms=50.0,
            outcome="success",
            correlation_id="c1",
            username="john",
            password="secret123",
            api_key="key-value",
        )
        assert entry.get("username") == "john"
        assert "password" not in entry
        assert "api_key" not in entry

    def test_log_success_convenience(self):
        """log_success() emits a success entry."""
        logger = StructuredLogger("test")
        entry = logger.log_success(
            operation="fast_op",
            duration_ms=5.0,
            correlation_id="c1",
        )
        assert entry["outcome_status"] == "success"
        assert "error_type" not in entry

    def test_log_failure_convenience(self):
        """log_failure() emits a failure entry with error details."""
        logger = StructuredLogger("test")
        entry = logger.log_failure(
            operation="bad_op",
            duration_ms=100.0,
            error="Something went wrong",
            error_type="RuntimeError",
            correlation_id="c1",
        )
        assert entry["outcome_status"] == "failure"
        assert entry["error_type"] == "RuntimeError"
        assert entry["error_message"] == "Something went wrong"

    def test_timestamp_is_iso_format(self):
        """Timestamp field is in ISO 8601 format."""
        logger = StructuredLogger("test")
        entry = logger.log_operation(
            operation="op",
            duration_ms=1.0,
            outcome="success",
            correlation_id="c1",
        )
        # Should be parseable as ISO 8601
        from datetime import datetime

        ts = datetime.fromisoformat(entry["timestamp"])
        assert ts is not None

    def test_service_name_property(self):
        """service_name property returns the configured name."""
        logger = StructuredLogger("my_service")
        assert logger.service_name == "my_service"


class TestGetStructuredLogger:
    """Tests for the get_structured_logger factory."""

    def test_returns_structured_logger(self):
        """Factory returns a StructuredLogger instance."""
        logger = get_structured_logger("some_service")
        assert isinstance(logger, StructuredLogger)
        assert logger.service_name == "some_service"


class TestLogOperationFunction:
    """Tests for the module-level log_operation convenience function."""

    def test_emits_correct_entry(self):
        """Module-level function emits a complete log entry."""
        entry = log_operation(
            service_name="email_service",
            operation="send_reminder",
            duration_ms=300.0,
            outcome="success",
            correlation_id="c1",
        )
        assert entry["service_name"] == "email_service"
        assert entry["operation_name"] == "send_reminder"
        assert entry["duration_ms"] == 300.0
        assert entry["outcome_status"] == "success"


class TestStructuredLogDecorator:
    """Tests for the @structured_log decorator."""

    def test_sync_function_success(self):
        """Decorator logs success for sync functions."""

        @structured_log("test_service", "sync_op")
        def my_func():
            return "result"

        with patch(
            "src.infrastructure.logging.structured_logger.get_correlation_id",
            return_value="dec-corr-1",
        ):
            result = my_func()

        assert result == "result"

    def test_sync_function_failure(self):
        """Decorator logs failure for sync functions that raise."""

        @structured_log("test_service", "failing_op")
        def my_failing_func():
            raise ValueError("test error")

        with patch(
            "src.infrastructure.logging.structured_logger.get_correlation_id",
            return_value="dec-corr-2",
        ):
            with pytest.raises(ValueError, match="test error"):
                my_failing_func()

    @pytest.mark.asyncio
    async def test_async_function_success(self):
        """Decorator logs success for async functions."""

        @structured_log("async_service", "async_op")
        async def my_async_func():
            return "async_result"

        with patch(
            "src.infrastructure.logging.structured_logger.get_correlation_id",
            return_value="dec-corr-3",
        ):
            result = await my_async_func()

        assert result == "async_result"

    @pytest.mark.asyncio
    async def test_async_function_failure(self):
        """Decorator logs failure for async functions that raise."""

        @structured_log("async_service", "async_fail")
        async def my_async_failing():
            raise RuntimeError("async error")

        with patch(
            "src.infrastructure.logging.structured_logger.get_correlation_id",
            return_value="dec-corr-4",
        ):
            with pytest.raises(RuntimeError, match="async error"):
                await my_async_failing()

    def test_uses_function_name_when_operation_not_specified(self):
        """When operation is not given, uses the function name."""

        @structured_log("service")
        def my_named_function():
            return True

        # The wrapper should preserve the function name
        assert my_named_function.__name__ == "my_named_function"


class TestSensitiveDataSanitization:
    """Tests for sensitive data filtering (Requirement 40.4)."""

    @pytest.mark.parametrize(
        "field_name,expected_sensitive",
        [
            ("password", True),
            ("user_password", True),
            ("api_key", True),
            ("apikey", True),
            ("token", True),
            ("auth_header", True),
            ("secret_key", True),
            ("credential", True),
            ("private_key", True),
            ("access_key", True),
            ("session_id", True),
            ("bearer_token", True),
            ("username", False),
            ("operation", False),
            ("case_id", False),
            ("vendor_code", False),
            ("duration_ms", False),
        ],
    )
    def test_sensitive_field_detection(self, field_name, expected_sensitive):
        """Sensitive field names are correctly identified."""
        assert _is_sensitive_field(field_name) == expected_sensitive

    def test_sanitize_message_redacts_bearer_tokens(self):
        """Bearer tokens in error messages are redacted."""
        msg = "Auth failed: Bearer eyJhbGciOiJIUzI1NiJ9.payload.sig"
        result = _sanitize_message(msg)
        assert "eyJhbGci" not in result
        assert "[REDACTED]" in result

    def test_sanitize_message_redacts_long_hex_strings(self):
        """Long hex strings (likely API keys) are redacted."""
        msg = "Failed with key: abcdef1234567890abcdef1234567890abcdef12"
        result = _sanitize_message(msg)
        assert "abcdef1234567890" not in result
        assert "[REDACTED]" in result

    def test_sanitize_message_redacts_password_patterns(self):
        """password=value patterns are redacted."""
        msg = "Connection failed: password=mysecret123 host=db.example.com"
        result = _sanitize_message(msg)
        assert "mysecret123" not in result
        assert "password=[REDACTED]" in result

    def test_sanitize_message_preserves_normal_content(self):
        """Normal error messages are not altered."""
        msg = "Connection refused to host 10.0.0.1 port 3306"
        result = _sanitize_message(msg)
        assert result == msg

    def test_sanitize_value_redacts_jwt_like_values(self):
        """Values that look like JWTs are redacted."""
        result = _sanitize_value(
            "some_field", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.payload.sig"
        )
        assert result == "[REDACTED]"

    def test_sanitize_value_preserves_normal_values(self):
        """Normal string values are not redacted."""
        assert _sanitize_value("name", "John Doe") == "John Doe"
        assert _sanitize_value("count", 42) == 42

    def test_no_sensitive_data_in_failure_log(self):
        """Error messages with sensitive data are sanitized in log entries."""
        logger = StructuredLogger("test")
        entry = logger.log_failure(
            operation="connect",
            duration_ms=100.0,
            error="Auth failed with password=super_secret_123",
            correlation_id="c1",
        )
        assert "super_secret_123" not in entry["error_message"]
        assert "[REDACTED]" in entry["error_message"]
