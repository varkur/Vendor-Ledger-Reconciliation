"""
Request/response logging middleware.
Logs method, URL, headers, query params, status code, and duration with correlation ID.
Uses the structured logging service for JSON-formatted operation entries.
"""

import time

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from src.infrastructure.logging.structured_logger import get_structured_logger
from src.observability.correlation import get_correlation_id
from src.observability.structured_logger import get_logger

logger = get_logger("request_logging")
_structured_logger = get_structured_logger("api_request")


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Logs incoming requests and outgoing responses with timing."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        start_time = time.perf_counter()
        correlation_id = get_correlation_id()

        # Log request
        logger.info(
            "Incoming request",
            correlation_id=correlation_id,
            method=request.method,
            url=str(request.url),
            path=request.url.path,
            query_params=str(request.query_params),
            client_host=request.client.host if request.client else "unknown",
        )

        # Process request
        response = await call_next(request)

        # Calculate duration
        duration_ms = (time.perf_counter() - start_time) * 1000

        # Log response with structlog
        logger.info(
            "Outgoing response",
            correlation_id=correlation_id,
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration_ms=round(duration_ms, 2),
        )

        # Emit structured log operation entry
        outcome = "success" if response.status_code < 400 else "failure"
        _structured_logger.log_operation(
            operation=f"{request.method} {request.url.path}",
            duration_ms=duration_ms,
            outcome=outcome,
            correlation_id=correlation_id,
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
        )

        return response
