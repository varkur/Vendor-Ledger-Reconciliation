"""
Rate limiting middleware for API endpoints.

Implements a sliding window rate limiter that restricts API requests
to 100 requests per minute per user (identified by JWT sub claim or IP).
Applied to all /api/v1/vlr/* routes.
"""

import time
from collections import defaultdict
from threading import Lock

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

# Rate limit configuration
RATE_LIMIT_REQUESTS = 100  # max requests
RATE_LIMIT_WINDOW_SECONDS = 60  # per time window (1 minute)
RATE_LIMIT_PATH_PREFIX = "/api/v1/vlr"


class SlidingWindowCounter:
    """Thread-safe in-memory sliding window rate limiter."""

    def __init__(self, max_requests: int = RATE_LIMIT_REQUESTS, window_seconds: int = RATE_LIMIT_WINDOW_SECONDS):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._requests: dict[str, list[float]] = defaultdict(list)
        self._lock = Lock()

    def is_allowed(self, key: str) -> tuple[bool, int, int]:
        """
        Check if a request is allowed for the given key.

        Returns:
            tuple of (allowed: bool, remaining: int, retry_after: int)
        """
        now = time.time()
        window_start = now - self.window_seconds

        with self._lock:
            # Remove expired timestamps
            self._requests[key] = [
                ts for ts in self._requests[key] if ts > window_start
            ]

            current_count = len(self._requests[key])

            if current_count >= self.max_requests:
                # Calculate retry-after from the oldest request in the window
                oldest = self._requests[key][0] if self._requests[key] else now
                retry_after = int(oldest + self.window_seconds - now) + 1
                return False, 0, retry_after

            # Record this request
            self._requests[key].append(now)
            remaining = self.max_requests - current_count - 1
            return True, remaining, 0

    def cleanup_expired(self) -> None:
        """Remove all expired entries to free memory."""
        now = time.time()
        window_start = now - self.window_seconds

        with self._lock:
            expired_keys = [
                key for key, timestamps in self._requests.items()
                if not timestamps or timestamps[-1] <= window_start
            ]
            for key in expired_keys:
                del self._requests[key]


# Module-level rate limiter instance (shared across requests)
_rate_limiter = SlidingWindowCounter()


def _get_client_identifier(request: Request) -> str:
    """
    Extract a unique client identifier from the request.

    Prioritizes the JWT subject (username) from the Authorization header.
    Falls back to client IP address for unauthenticated requests.
    """
    # Try to extract user identity from Authorization header
    auth_header = request.headers.get("authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        # Decode JWT payload without verification (just for rate-limit keying)
        # The actual auth middleware handles full verification
        try:
            import base64
            import json

            # Split JWT and decode payload (middle part)
            parts = token.split(".")
            if len(parts) == 3:
                # Add padding if needed
                payload_b64 = parts[1] + "=" * (4 - len(parts[1]) % 4)
                payload = json.loads(base64.urlsafe_b64decode(payload_b64))
                sub = payload.get("sub")
                if sub:
                    return f"user:{sub}"
        except (ValueError, KeyError, json.JSONDecodeError):
            pass

    # Fallback to client IP
    client_host = request.client.host if request.client else "unknown"
    return f"ip:{client_host}"


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Middleware that enforces rate limiting on /api/v1/vlr/* routes.

    Uses a sliding window counter to limit requests to 100/minute/user.
    Returns 429 Too Many Requests when the limit is exceeded.
    """

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        # Only apply rate limiting to VLR API routes
        if not request.url.path.startswith(RATE_LIMIT_PATH_PREFIX):
            return await call_next(request)

        # Identify the client
        client_key = _get_client_identifier(request)

        # Check rate limit
        allowed, remaining, retry_after = _rate_limiter.is_allowed(client_key)

        if not allowed:
            return JSONResponse(
                status_code=429,
                content={
                    "detail": "Rate limit exceeded. Maximum 100 requests per minute.",
                    "retry_after": retry_after,
                },
                headers={
                    "Retry-After": str(retry_after),
                    "X-RateLimit-Limit": str(RATE_LIMIT_REQUESTS),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(int(time.time()) + retry_after),
                },
            )

        # Process request and add rate limit headers to response
        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(RATE_LIMIT_REQUESTS)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Reset"] = str(
            int(time.time()) + RATE_LIMIT_WINDOW_SECONDS
        )

        return response
