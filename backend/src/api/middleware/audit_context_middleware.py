"""
Middleware to populate the audit context from the current request.

Sets actor identity (user ID, username, IP, user-agent) into the
request-scoped context variable so the audit listener can attribute
database changes to the correct user automatically.
"""

import logging
from uuid import UUID

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from src.infrastructure.database.audit_context import clear_audit_context, set_audit_context

logger = logging.getLogger(__name__)


class AuditContextMiddleware(BaseHTTPMiddleware):
    """
    Extracts authenticated user info from request state and sets the audit context.

    Expects that an auth middleware has already run and placed user info
    on request.state (e.g., request.state.user_id, request.state.username).

    If no user info is available, the audit context defaults to 'system'.
    """

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        # Extract user identity from request state (set by auth middleware)
        actor_id = getattr(request.state, "user_id", None)
        actor_username = getattr(request.state, "username", "anonymous")
        tenant_id = getattr(request.state, "tenant_id", None)

        # Parse UUID if string
        if actor_id and isinstance(actor_id, str):
            try:
                actor_id = UUID(actor_id)
            except ValueError:
                actor_id = None

        if tenant_id and isinstance(tenant_id, str):
            try:
                tenant_id = UUID(tenant_id)
            except ValueError:
                tenant_id = None

        # Get client info
        ip_address = ""
        if request.client:
            ip_address = request.client.host
        # Check for forwarded header (behind proxy)
        forwarded_for = request.headers.get("x-forwarded-for", "")
        if forwarded_for:
            ip_address = forwarded_for.split(",")[0].strip()

        user_agent = request.headers.get("user-agent", "")

        # Set the audit context for this request
        set_audit_context(
            actor_id=actor_id,
            actor_username=actor_username,
            ip_address=ip_address,
            user_agent=user_agent,
            tenant_id=tenant_id,
        )

        try:
            response = await call_next(request)
            return response
        finally:
            # Clear context at the end of the request
            clear_audit_context()
