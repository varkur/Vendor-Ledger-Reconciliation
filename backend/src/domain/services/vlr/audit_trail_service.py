"""
Audit Trail Domain Service.

Immutable event logging with search, pagination, and export.
No UPDATE/DELETE operations are exposed — this is append-only by design.

Captures event types:
- login, logout
- case_created, status_changed
- match_override
- approval, rejection
- vendor_interaction

Requirements: 38.1, 38.2, 38.3, 39.1, 39.2
"""

import csv
import io
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from uuid import UUID

from src.domain.repositories.vlr.audit_trail_repository import (
    AuditSearchFilters,
    IAuditTrailRepository,
)
from src.domain.repositories.vlr.vendor_repository import PaginatedResult, PaginationParams


logger = logging.getLogger(__name__)


# ─── Enumerations ─────────────────────────────────────────────────────────────


class AuditEventType(str, Enum):
    """All supported audit event types."""

    LOGIN = "login"
    LOGOUT = "logout"
    CASE_CREATED = "case_created"
    STATUS_CHANGED = "status_changed"
    MATCH_OVERRIDE = "match_override"
    APPROVAL = "approval"
    REJECTION = "rejection"
    VENDOR_INTERACTION = "vendor_interaction"


class ExportFormat(str, Enum):
    """Supported export formats for audit trail data."""

    CSV = "csv"
    EXCEL = "excel"


# ─── Data Classes ─────────────────────────────────────────────────────────────


@dataclass
class AuditEvent:
    """Data required to log an audit event."""

    actor_username: str
    event_type: AuditEventType
    event_details: dict
    actor_id: UUID | None = None
    case_id: UUID | None = None
    ip_address: str | None = None
    timestamp: datetime | None = None


# ─── Service Implementation ───────────────────────────────────────────────────


class AuditTrailService:
    """
    Immutable audit event logging (append-only).

    Provides log_event(), search(), and export() operations.
    No update or delete operations are exposed.

    Requirements: 38.1, 38.2, 38.3, 39.1, 39.2
    """

    def __init__(self, audit_repository: IAuditTrailRepository) -> None:
        self._repo = audit_repository

    async def log_event(self, event: AuditEvent) -> None:
        """
        Append an audit event to the immutable log.

        The event is persisted with the current UTC timestamp if not provided.
        No update/delete is exposed — events are permanent once logged.

        Requirements: 38.1, 38.2
        """
        event_data = {
            "actor_id": str(event.actor_id) if event.actor_id else None,
            "actor_username": event.actor_username,
            "event_type": event.event_type.value if isinstance(event.event_type, AuditEventType) else event.event_type,
            "case_id": str(event.case_id) if event.case_id else None,
            "event_details": event.event_details,
            "timestamp": event.timestamp or datetime.now(timezone.utc),
            "ip_address": event.ip_address,
        }

        await self._repo.append(event_data)

        logger.info(
            "Audit event logged: type=%s, actor=%s, case_id=%s",
            event.event_type,
            event.actor_username,
            event.case_id,
        )

    async def search(
        self,
        filters: AuditSearchFilters | None = None,
        pagination: PaginationParams | None = None,
    ) -> PaginatedResult:
        """
        Search audit events with filters and pagination.

        Supports filtering by:
        - actor_username: partial match (case-insensitive)
        - event_type: exact match
        - case_id: exact match
        - date_from / date_to: timestamp range

        Requirements: 38.3, 39.1
        """
        return await self._repo.search(filters=filters, pagination=pagination)

    async def export(
        self,
        filters: AuditSearchFilters | None = None,
        export_format: ExportFormat = ExportFormat.CSV,
    ) -> bytes:
        """
        Export filtered audit events as Excel or CSV.

        Fetches all matching events (up to 10,000 limit) and formats
        them into the requested output format.

        Requirements: 39.2
        """
        # Fetch all matching events with a large page size for export
        export_pagination = PaginationParams(page=1, page_size=10000)
        result = await self._repo.search(filters=filters, pagination=export_pagination)

        if export_format == ExportFormat.EXCEL:
            return self._export_excel(result.items)
        else:
            return self._export_csv(result.items)

    def _export_csv(self, events: list) -> bytes:
        """Export audit events as CSV bytes."""
        output = io.StringIO()
        writer = csv.writer(output)

        # Header row
        writer.writerow([
            "Timestamp",
            "Event Type",
            "Actor Username",
            "Actor ID",
            "Case ID",
            "IP Address",
            "Event Details",
        ])

        # Data rows
        for event in events:
            writer.writerow([
                getattr(event, "timestamp", "").isoformat() if getattr(event, "timestamp", None) else "",
                getattr(event, "event_type", ""),
                getattr(event, "actor_username", ""),
                str(getattr(event, "actor_id", "")) if getattr(event, "actor_id", None) else "",
                str(getattr(event, "case_id", "")) if getattr(event, "case_id", None) else "",
                getattr(event, "ip_address", "") or "",
                str(getattr(event, "event_details", {})),
            ])

        return output.getvalue().encode("utf-8")

    def _export_excel(self, events: list) -> bytes:
        """
        Export audit events as Excel (XLSX) bytes.

        Uses openpyxl if available, falls back to CSV with .xlsx-compatible
        tab-separated format if openpyxl is not installed.
        """
        try:
            from openpyxl import Workbook

            wb = Workbook()
            ws = wb.active
            ws.title = "Audit Events"

            # Header row
            headers = [
                "Timestamp",
                "Event Type",
                "Actor Username",
                "Actor ID",
                "Case ID",
                "IP Address",
                "Event Details",
            ]
            ws.append(headers)

            # Data rows
            for event in events:
                ws.append([
                    getattr(event, "timestamp", "").isoformat() if getattr(event, "timestamp", None) else "",
                    getattr(event, "event_type", ""),
                    getattr(event, "actor_username", ""),
                    str(getattr(event, "actor_id", "")) if getattr(event, "actor_id", None) else "",
                    str(getattr(event, "case_id", "")) if getattr(event, "case_id", None) else "",
                    getattr(event, "ip_address", "") or "",
                    str(getattr(event, "event_details", {})),
                ])

            # Write to bytes
            output = io.BytesIO()
            wb.save(output)
            return output.getvalue()

        except ImportError:
            # Fallback: return CSV if openpyxl is not available
            logger.warning("openpyxl not available, falling back to CSV for Excel export")
            return self._export_csv(events)
