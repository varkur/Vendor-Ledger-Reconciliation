"""
In-process Event Bus.
Publishes domain events to registered handlers asynchronously.
"""
import logging
from collections import defaultdict
from typing import Any, Callable, Coroutine

from src.domain.entities.workflow.events import DomainEvent

logger = logging.getLogger(__name__)

# Type alias for async handler
EventHandler = Callable[[DomainEvent], Coroutine[Any, Any, None]]


class EventBus:
    """Simple in-process async event bus."""

    def __init__(self) -> None:
        self._handlers: dict[str, list[EventHandler]] = defaultdict(list)

    def subscribe(self, event_type: str, handler: EventHandler) -> None:
        """Register a handler for an event type."""
        self._handlers[event_type].append(handler)
        logger.debug("Handler registered for event: %s", event_type)

    async def publish(self, event: DomainEvent) -> None:
        """Publish an event to all registered handlers."""
        handlers = self._handlers.get(event.event_type, [])
        logger.info("Publishing event: %s (handlers=%d)", event.event_type, len(handlers))

        for handler in handlers:
            try:
                await handler(event)
            except Exception as exc:
                logger.error(
                    "Event handler failed: event=%s error=%s",
                    event.event_type, exc, exc_info=True,
                )


# Singleton event bus instance
event_bus = EventBus()
