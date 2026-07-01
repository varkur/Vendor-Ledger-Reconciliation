"""
Method entry/exit logging decorator.
Automatically logs START and END of function execution with timing and correlation ID.
"""

import time
from functools import wraps
from typing import Any, Callable

from src.observability.correlation import get_correlation_id
from src.observability.structured_logger import get_logger

logger = get_logger(__name__)


def log_execution(func: Callable) -> Callable:
    """
    Decorator that logs method entry and exit with execution time.

    Output:
        START: method_name (correlation_id=...)
        END: method_name (correlation_id=..., execution_time_ms=...)

    Works with both sync and async functions.
    """

    @wraps(func)
    async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
        correlation_id = get_correlation_id()
        func_name = func.__qualname__

        logger.info(
            f"START: {func_name}",
            correlation_id=correlation_id,
            function=func_name,
        )

        start_time = time.perf_counter()
        try:
            result = await func(*args, **kwargs)
            return result
        finally:
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            logger.info(
                f"END: {func_name}",
                correlation_id=correlation_id,
                function=func_name,
                execution_time_ms=round(elapsed_ms, 2),
            )

    @wraps(func)
    def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
        correlation_id = get_correlation_id()
        func_name = func.__qualname__

        logger.info(
            f"START: {func_name}",
            correlation_id=correlation_id,
            function=func_name,
        )

        start_time = time.perf_counter()
        try:
            result = func(*args, **kwargs)
            return result
        finally:
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            logger.info(
                f"END: {func_name}",
                correlation_id=correlation_id,
                function=func_name,
                execution_time_ms=round(elapsed_ms, 2),
            )

    import asyncio

    if asyncio.iscoroutinefunction(func):
        return async_wrapper
    return sync_wrapper
