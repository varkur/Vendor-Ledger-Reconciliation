"""
Global exception handler middleware.
Catches unhandled exceptions, logs them with correlation ID and stack trace,
and returns a standardized error response.
"""

import traceback

from fastapi import Request, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

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
        except Exception as e:
            return self._handle_unexpected_error(request, e)

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
        """Handle unexpected/unhandled exceptions."""
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
                "success": False,
                "message": "Internal Server Error",
                "correlation_id": correlation_id,
            },
        )
