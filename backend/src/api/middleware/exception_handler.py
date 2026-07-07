"""
Global exception handler middleware.
Catches unhandled exceptions, logs them with correlation ID and stack trace,
and returns a standardized error response.

VLR domain exceptions are mapped to structured error responses with:
- error_code: machine-readable error identifier
- message: human-readable description
- field_path: optional field path for validation errors
- correlation_id: request correlation ID for traceability
- details: additional context (e.g., validation errors list)
"""

import traceback
from typing import Any

from fastapi import Request, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from src.domain.exceptions.vlr import FileValidationException, VLRDomainException
from src.infrastructure.security.auth_manager import (
    AuthenticationError,
    InvalidCredentialsError,
    UserBlockedError,
    UserInactiveError,
)
from src.observability.correlation import get_correlation_id
from src.observability.structured_logger import get_logger

logger = get_logger("exception_handler")


class ExceptionHandlerMiddleware(BaseHTTPMiddleware):
    """Catches and handles all unhandled exceptions globally."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        try:
            return await call_next(request)
        except AuthenticationError as e:
            return self._handle_auth_error(request, e)
        except VLRDomainException as e:
            return self._handle_vlr_domain_error(request, e)
        except Exception as e:
            return self._handle_unexpected_error(request, e)

    def _handle_vlr_domain_error(
        self, request: Request, error: VLRDomainException
    ) -> JSONResponse:
        """Handle VLR domain exceptions with structured error responses."""
        correlation_id = get_correlation_id()

        # Build details dict for exceptions that carry extra context
        details: dict[str, Any] = {}
        field_path: str | None = None

        if isinstance(error, FileValidationException) and error.errors:
            details["validation_errors"] = error.errors
            field_path = "file"

        logger.warning(
            "VLR domain error",
            correlation_id=correlation_id,
            error_code=error.error_code,
            error_type=type(error).__name__,
            message=error.message,
            status_code=error.status_code,
            path=request.url.path,
            method=request.method,
        )

        return JSONResponse(
            status_code=error.status_code,
            content={
                "error_code": error.error_code,
                "message": error.message,
                "field_path": field_path,
                "correlation_id": correlation_id,
                "details": details,
            },
        )

    def _handle_auth_error(
        self, request: Request, error: AuthenticationError
    ) -> JSONResponse:
        """Handle known authentication/authorization errors."""
        correlation_id = get_correlation_id()

        logger.warning(
            "Authentication error",
            correlation_id=correlation_id,
            error_type=type(error).__name__,
            message=error.message,
            path=request.url.path,
            method=request.method,
        )

        return JSONResponse(
            status_code=error.status_code,
            content={
                "success": False,
                "message": error.message,
                "correlation_id": correlation_id,
            },
        )

    def _handle_unexpected_error(
        self, request: Request, error: Exception
    ) -> JSONResponse:
        """Handle unexpected/unhandled exceptions.

        Returns only the correlation ID to the client - no internal details exposed.
        Full stack trace is logged server-side for debugging.
        """
        correlation_id = get_correlation_id()
        stack_trace = traceback.format_exc()

        logger.error(
            "Unhandled exception",
            correlation_id=correlation_id,
            error_type=type(error).__name__,
            error_message=str(error),
            stack_trace=stack_trace,
            request_path=request.url.path,
            request_method=request.method,
        )

        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error_code": "VLR_INTERNAL_ERROR",
                "message": "An unexpected error occurred. Please try again or contact support.",
                "field_path": None,
                "correlation_id": correlation_id,
                "details": {},
            },
        )
