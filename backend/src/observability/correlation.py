"""
Correlation ID context management.
Uses contextvars to propagate a unique ID throughout the request lifecycle.
"""

import contextvars
from uuid import uuid4

# Context variable holding the current request's correlation ID
_correlation_id_ctx: contextvars.ContextVar[str] = contextvars.ContextVar(
    "correlation_id", default=""
)


def get_correlation_id() -> str:
    """Retrieve the current correlation ID."""
    return _correlation_id_ctx.get()


def set_correlation_id(correlation_id: str) -> None:
    """Set the correlation ID for the current context."""
    _correlation_id_ctx.set(correlation_id)


def generate_correlation_id() -> str:
    """Generate a new UUID-based correlation ID."""
    return str(uuid4())
