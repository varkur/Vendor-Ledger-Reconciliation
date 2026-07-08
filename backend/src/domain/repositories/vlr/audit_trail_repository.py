"""
Audit trail repository interface (Port).
Defines the contract for immutable audit event persistence.

This repository is APPEND-ONLY by design — no update() or delete() methods exist.

Requirements: 38.1, 38.4
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from src.domain.repositories.vlr.vendor_repository import PaginatedResult, PaginationParams


@dataclass
class AuditSearchFilters:
    """Filter criteria for searching audit events."""

    actor_username: str | None = None
    event_type: str | None = None
    case_id: UUID | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None


class IAuditTrailRepository(ABC):
    """
    Append-only audit event persistence.

    NOTE: No update() or delete() methods — immutable by design.
    Only append and search operations are permitted.
    """

    @abstractmethod
    async def append(self, event_data: dict) -> object:
        """
        Persist a new audit event (append-only).

        Args:
            event_data: Dictionary of audit event fields.

        Returns:
            The persisted audit event model instance.
        """
        ...

    @abstractmethod
    async def search(
        self,
        filters: AuditSearchFilters | None = None,
        pagination: PaginationParams | None = None,
    ) -> PaginatedResult:
        """
        Search audit events with filters and pagination.

        Args:
            filters: Optional filter criteria (user, date range, case_id, event_type).
            pagination: Pagination parameters.

        Returns:
            Paginated list of matching audit events.
        """
        ...
