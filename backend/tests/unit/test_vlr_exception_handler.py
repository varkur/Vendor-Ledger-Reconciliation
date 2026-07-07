"""
Unit tests for VLR error handler and structured error responses.

Tests that VLR domain exceptions are correctly mapped to HTTP status codes
and that all error responses include the required structured fields:
error_code, message, field_path, correlation_id, and details.
"""

import pytest
from httpx import ASGITransport, AsyncClient
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from src.api.middleware.correlation_id import CorrelationIdMiddleware
from src.api.middleware.exception_handler import ExceptionHandlerMiddleware
from src.domain.exceptions.vlr import (
    CaseClosedException,
    CompanyLedgerNotConfirmedException,
    ConcurrentModificationException,
    DuplicateVendorCodeException,
    EditLimitExceededException,
    FileValidationException,
    IdempotencyConflictException,
    InvalidStatusTransitionException,
    OverlappingPeriodException,
    Row10NonZeroException,
    SAPConnectionException,
    TokenExpiredException,
    UploadLimitExceededException,
    VendorHasActiveCaseException,
    VendorInactiveException,
    VendorNotFoundException,
    VLRDomainException,
    WriteOffThresholdExceededException,
)


def create_test_app(exception_to_raise: Exception) -> FastAPI:
    """Create a minimal FastAPI app that raises the given exception."""
    app = FastAPI()

    app.add_middleware(ExceptionHandlerMiddleware)
    app.add_middleware(CorrelationIdMiddleware)

    @app.get("/test")
    async def test_endpoint():
        raise exception_to_raise

    return app


class TestVLRStructuredErrorResponse:
    """Test that all VLR error responses follow the structured format."""

    @pytest.mark.asyncio
    async def test_error_response_has_required_fields(self):
        """Every VLR error response must include error_code, message, field_path, correlation_id, details."""
        app = create_test_app(VendorNotFoundException())
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/test")

        data = response.json()
        assert "error_code" in data
        assert "message" in data
        assert "field_path" in data
        assert "correlation_id" in data
        assert "details" in data

    @pytest.mark.asyncio
    async def test_correlation_id_present_in_error_response(self):
        """Error responses must include the correlation ID from the request context."""
        app = create_test_app(VendorNotFoundException())
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                "/test", headers={"X-Correlation-ID": "test-corr-123"}
            )

        data = response.json()
        assert data["correlation_id"] == "test-corr-123"

    @pytest.mark.asyncio
    async def test_correlation_id_generated_when_not_provided(self):
        """Error responses must have a correlation ID even when not provided in request."""
        app = create_test_app(VendorNotFoundException())
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/test")

        data = response.json()
        assert data["correlation_id"]  # non-empty
        assert len(data["correlation_id"]) == 36  # UUID format


class TestVLRNotFoundExceptions:
    """Test 404 error mapping for not-found exceptions."""

    @pytest.mark.asyncio
    async def test_vendor_not_found_returns_404(self):
        """VendorNotFoundException should map to HTTP 404."""
        app = create_test_app(VendorNotFoundException())
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/test")

        assert response.status_code == 404
        data = response.json()
        assert data["error_code"] == "VLR_VENDOR_NOT_FOUND"
        assert data["field_path"] is None
        assert data["details"] == {}

    @pytest.mark.asyncio
    async def test_vendor_not_found_custom_message(self):
        """VendorNotFoundException with custom message."""
        app = create_test_app(
            VendorNotFoundException("Vendor with ID 'abc-123' not found")
        )
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/test")

        data = response.json()
        assert data["message"] == "Vendor with ID 'abc-123' not found"


class TestVLRBusinessRuleExceptions:
    """Test 409 error mapping for business rule violations."""

    @pytest.mark.asyncio
    async def test_vendor_inactive_returns_409(self):
        """VendorInactiveException should map to HTTP 409."""
        app = create_test_app(VendorInactiveException())
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/test")

        assert response.status_code == 409
        data = response.json()
        assert data["error_code"] == "VLR_VENDOR_INACTIVE"

    @pytest.mark.asyncio
    async def test_vendor_has_active_case_returns_409(self):
        """VendorHasActiveCaseException should map to HTTP 409."""
        app = create_test_app(VendorHasActiveCaseException())
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/test")

        assert response.status_code == 409
        data = response.json()
        assert data["error_code"] == "VLR_VENDOR_HAS_ACTIVE_CASE"

    @pytest.mark.asyncio
    async def test_overlapping_period_returns_409(self):
        """OverlappingPeriodException should map to HTTP 409."""
        app = create_test_app(OverlappingPeriodException())
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/test")

        assert response.status_code == 409
        data = response.json()
        assert data["error_code"] == "VLR_OVERLAPPING_PERIOD"

    @pytest.mark.asyncio
    async def test_invalid_status_transition_returns_409(self):
        """InvalidStatusTransitionException should map to HTTP 409 with transition info."""
        app = create_test_app(
            InvalidStatusTransitionException(
                current_status="draft", target_status="closed"
            )
        )
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/test")

        assert response.status_code == 409
        data = response.json()
        assert data["error_code"] == "VLR_INVALID_STATUS_TRANSITION"
        assert "draft" in data["message"]
        assert "closed" in data["message"]

    @pytest.mark.asyncio
    async def test_case_closed_returns_409(self):
        """CaseClosedException should map to HTTP 409."""
        app = create_test_app(CaseClosedException())
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/test")

        assert response.status_code == 409
        data = response.json()
        assert data["error_code"] == "VLR_CASE_CLOSED"

    @pytest.mark.asyncio
    async def test_upload_limit_exceeded_returns_409(self):
        """UploadLimitExceededException should map to HTTP 409."""
        app = create_test_app(UploadLimitExceededException())
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/test")

        assert response.status_code == 409
        data = response.json()
        assert data["error_code"] == "VLR_UPLOAD_LIMIT_EXCEEDED"

    @pytest.mark.asyncio
    async def test_edit_limit_exceeded_returns_409(self):
        """EditLimitExceededException should map to HTTP 409."""
        app = create_test_app(EditLimitExceededException())
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/test")

        assert response.status_code == 409
        data = response.json()
        assert data["error_code"] == "VLR_EDIT_LIMIT_EXCEEDED"

    @pytest.mark.asyncio
    async def test_row10_non_zero_returns_409(self):
        """Row10NonZeroException should map to HTTP 409 with difference amount."""
        app = create_test_app(Row10NonZeroException(difference_amount="1234.56"))
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/test")

        assert response.status_code == 409
        data = response.json()
        assert data["error_code"] == "VLR_ROW10_NON_ZERO"
        assert "1234.56" in data["message"]

    @pytest.mark.asyncio
    async def test_write_off_threshold_exceeded_returns_409(self):
        """WriteOffThresholdExceededException should map to HTTP 409."""
        app = create_test_app(WriteOffThresholdExceededException())
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/test")

        assert response.status_code == 409
        data = response.json()
        assert data["error_code"] == "VLR_WRITE_OFF_THRESHOLD_EXCEEDED"

    @pytest.mark.asyncio
    async def test_duplicate_vendor_code_returns_409(self):
        """DuplicateVendorCodeException should map to HTTP 409 with vendor code."""
        app = create_test_app(DuplicateVendorCodeException(vendor_code="V001"))
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/test")

        assert response.status_code == 409
        data = response.json()
        assert data["error_code"] == "VLR_DUPLICATE_VENDOR_CODE"
        assert "V001" in data["message"]

    @pytest.mark.asyncio
    async def test_company_ledger_not_confirmed_returns_409(self):
        """CompanyLedgerNotConfirmedException should map to HTTP 409."""
        app = create_test_app(CompanyLedgerNotConfirmedException())
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/test")

        assert response.status_code == 409
        data = response.json()
        assert data["error_code"] == "VLR_COMPANY_LEDGER_NOT_CONFIRMED"

    @pytest.mark.asyncio
    async def test_idempotency_conflict_returns_409(self):
        """IdempotencyConflictException should map to HTTP 409."""
        app = create_test_app(IdempotencyConflictException())
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/test")

        assert response.status_code == 409
        data = response.json()
        assert data["error_code"] == "VLR_IDEMPOTENCY_CONFLICT"

    @pytest.mark.asyncio
    async def test_concurrent_modification_returns_409(self):
        """ConcurrentModificationException should map to HTTP 409."""
        app = create_test_app(ConcurrentModificationException())
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/test")

        assert response.status_code == 409
        data = response.json()
        assert data["error_code"] == "VLR_CONCURRENT_MODIFICATION"


class TestVLRValidationExceptions:
    """Test error mapping for validation-related exceptions."""

    @pytest.mark.asyncio
    async def test_file_validation_returns_400_with_details(self):
        """FileValidationException should return 400 with validation errors in details."""
        errors = ["Missing column: amount", "Missing column: posting_date"]
        app = create_test_app(FileValidationException(errors=errors))
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/test")

        assert response.status_code == 400
        data = response.json()
        assert data["error_code"] == "VLR_FILE_VALIDATION_ERROR"
        assert data["field_path"] == "file"
        assert data["details"]["validation_errors"] == errors

    @pytest.mark.asyncio
    async def test_token_expired_returns_400(self):
        """TokenExpiredException should map to HTTP 400."""
        app = create_test_app(TokenExpiredException())
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/test")

        assert response.status_code == 400
        data = response.json()
        assert data["error_code"] == "VLR_TOKEN_EXPIRED"


class TestVLRServiceUnavailableExceptions:
    """Test error mapping for service unavailability."""

    @pytest.mark.asyncio
    async def test_sap_connection_returns_503(self):
        """SAPConnectionException should map to HTTP 503."""
        app = create_test_app(SAPConnectionException())
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/test")

        assert response.status_code == 503
        data = response.json()
        assert data["error_code"] == "VLR_SAP_CONNECTION_ERROR"
        assert data["field_path"] is None
        assert data["correlation_id"]


class TestUnexpectedErrorResponse:
    """Test that unexpected exceptions return structured 500 responses without internal details."""

    @pytest.mark.asyncio
    async def test_unexpected_error_returns_500_with_structured_format(self):
        """Unexpected errors should return 500 with structured format."""
        app = create_test_app(RuntimeError("something broke internally"))
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/test")

        assert response.status_code == 500
        data = response.json()
        assert data["error_code"] == "VLR_INTERNAL_ERROR"
        assert data["field_path"] is None
        assert data["correlation_id"]
        assert data["details"] == {}

    @pytest.mark.asyncio
    async def test_unexpected_error_does_not_expose_internal_details(self):
        """Unexpected errors must not expose stack traces or internal error messages."""
        app = create_test_app(RuntimeError("secret database password leaked"))
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/test")

        data = response.json()
        assert "secret" not in data["message"]
        assert "database" not in data["message"]
        assert "password" not in data["message"]
        assert "leaked" not in data["message"]

    @pytest.mark.asyncio
    async def test_unexpected_error_includes_correlation_id(self):
        """Unexpected 500 errors must include correlation_id for support traceability."""
        app = create_test_app(ValueError("unexpected"))
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                "/test", headers={"X-Correlation-ID": "support-ticket-456"}
            )

        data = response.json()
        assert data["correlation_id"] == "support-ticket-456"
