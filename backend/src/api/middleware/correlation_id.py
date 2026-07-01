"""
Correlation ID middleware.
Extracts or generates X-Correlation-ID for every incoming request
and attaches it to the response headers.
"""

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from src.observability.correlation import (
    generate_correlation_id,
    get_correlation_id,
    set_correlation_id,
)

CORRELATION_ID_HEADER = "X-Correlation-ID"


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """
    Middleware that ensures every request has a correlation ID.

    If the incoming request contains X-Correlation-ID, it is reused.
    Otherwise, a new UUID is generated.
    The correlation ID is stored in contextvars for global access
    and included in the response headers.
    """

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        # Extract or generate correlation ID
        correlation_id = request.headers.get(CORRELATION_ID_HEADER)
        if not correlation_id:
            correlation_id = generate_correlation_id()

        # Store in context for use throughout the request lifecycle
        set_correlation_id(correlation_id)

        # Process request
        response = await call_next(request)

        # Attach correlation ID to response
        response.headers[CORRELATION_ID_HEADER] = get_correlation_id()

        return response
