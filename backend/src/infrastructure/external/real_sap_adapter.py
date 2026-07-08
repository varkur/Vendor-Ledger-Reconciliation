"""
Real SAP Adapter wrapping existing SAPConnectorService.

This adapter implements SAPAdapterInterface by delegating to the existing
SAPConnectorService and translating its response format into the standardized
SAPLedgerEntry dataclass used by the domain layer.

The adapter is a thin wrapper — no business logic, just translation between
the existing connector API and the new interface contract.

Requirements: 8.4
"""

from __future__ import annotations

import logging
import time
from datetime import date

from src.domain.exceptions.vlr import SAPConnectionException
from src.domain.interfaces.sap_adapter_interface import (
    SAPAdapterInterface,
    SAPLedgerEntry,
)
from src.infrastructure.external.sap_connector import (
    DateRange,
    SAPConnectorService,
    SAPLedgerEntry as ConnectorLedgerEntry,
)
from src.infrastructure.logging.structured_logger import get_structured_logger

logger = logging.getLogger(__name__)
_structured_logger = get_structured_logger("sap_adapter")


class RealSAPAdapter(SAPAdapterInterface):
    """
    Production adapter wrapping existing SAPConnectorService.

    Translates between the SAPConnectorService API (which uses DateRange
    and returns ExtractionResult) and the SAPAdapterInterface contract
    (which uses explicit date parameters and returns list[SAPLedgerEntry]).

    This ensures zero changes are required to business logic services that
    consume the SAPAdapterInterface — they remain decoupled from the
    underlying SAP connectivity implementation.
    """

    def __init__(self, connector: SAPConnectorService) -> None:
        """
        Initialize with an existing SAPConnectorService instance.

        Args:
            connector: The configured SAPConnectorService to delegate calls to.
        """
        self._connector = connector

    async def pull_all_items(
        self,
        vendor_code: str,
        company_code: str,
        date_from: date,
        date_to: date,
        doc_type_filters: list[str] | None = None,
    ) -> list[SAPLedgerEntry]:
        """
        Pull all items (cleared and open) from SAP for a vendor.

        Delegates to SAPConnectorService.pull_ledger_entries() and converts
        the result into standardized SAPLedgerEntry objects.

        Args:
            vendor_code: SAP vendor number (LIFNR).
            company_code: SAP company code (BUKRS).
            date_from: Start of posting date range (BUDAT from).
            date_to: End of posting date range (BUDAT to).
            doc_type_filters: Optional list of document types to filter (BLART).

        Returns:
            List of SAPLedgerEntry objects (both cleared and uncleared).

        Raises:
            SAPConnectionException: If SAP connection fails after retries.
        """
        start = time.perf_counter()
        logger.info(
            "RealSAPAdapter.pull_all_items: vendor_code=%s, company_code=%s, "
            "date_from=%s, date_to=%s, doc_type_filters=%s",
            vendor_code,
            company_code,
            date_from.isoformat(),
            date_to.isoformat(),
            doc_type_filters,
        )

        try:
            period = DateRange(start=date_from, end=date_to)
            extraction_result = await self._connector.pull_ledger_entries(
                vendor_code=vendor_code,
                company_code=company_code,
                period=period,
            )

            entries = [
                self._convert_entry(entry)
                for entry in extraction_result.entries
            ]

            # Apply document type filters if specified
            if doc_type_filters:
                entries = [
                    e for e in entries
                    if e.blart in doc_type_filters
                ]

            duration_ms = (time.perf_counter() - start) * 1000
            _structured_logger.log_success(
                operation="pull_all_items",
                duration_ms=duration_ms,
                vendor_code=vendor_code,
                company_code=company_code,
                entries_returned=len(entries),
            )
            logger.info(
                "RealSAPAdapter.pull_all_items complete: "
                "vendor_code=%s, entries_returned=%d",
                vendor_code,
                len(entries),
            )
            return entries

        except SAPConnectionException:
            duration_ms = (time.perf_counter() - start) * 1000
            _structured_logger.log_failure(
                operation="pull_all_items",
                duration_ms=duration_ms,
                error="SAP connection failed",
                error_type="SAPConnectionException",
                vendor_code=vendor_code,
                company_code=company_code,
            )
            raise
        except Exception as exc:
            duration_ms = (time.perf_counter() - start) * 1000
            _structured_logger.log_failure(
                operation="pull_all_items",
                duration_ms=duration_ms,
                error=str(exc),
                error_type=type(exc).__name__,
                vendor_code=vendor_code,
                company_code=company_code,
            )
            logger.error(
                "RealSAPAdapter.pull_all_items unexpected error: "
                "vendor_code=%s, company_code=%s, error=%s",
                vendor_code,
                company_code,
                str(exc),
            )
            raise SAPConnectionException(
                f"Failed to pull all items from SAP: {exc}"
            ) from exc

    async def pull_open_items(
        self,
        vendor_code: str,
        company_code: str,
        key_date: date,
        doc_type_filters: list[str] | None = None,
    ) -> list[SAPLedgerEntry]:
        """
        Pull only uncleared (open) items from SAP as of a key date.

        Delegates to SAPConnectorService.pull_ledger_entries() and filters
        for entries that are not cleared as of the key_date.

        An item is considered open if:
        - It has no clearing document (augbl is empty), OR
        - Its clearing date is after the key_date

        Args:
            vendor_code: SAP vendor number (LIFNR).
            company_code: SAP company code (BUKRS).
            key_date: The reference date for determining open item status.
            doc_type_filters: Optional list of document types to filter (BLART).

        Returns:
            List of SAPLedgerEntry objects representing uncleared items.

        Raises:
            SAPConnectionException: If SAP connection fails after retries.
        """
        start = time.perf_counter()
        logger.info(
            "RealSAPAdapter.pull_open_items: vendor_code=%s, company_code=%s, "
            "key_date=%s, doc_type_filters=%s",
            vendor_code,
            company_code,
            key_date.isoformat(),
            doc_type_filters,
        )

        try:
            # Pull all items up to the key_date, then filter for open items
            period = DateRange(start=date(2000, 1, 1), end=key_date)
            extraction_result = await self._connector.pull_ledger_entries(
                vendor_code=vendor_code,
                company_code=company_code,
                period=period,
            )

            entries = [
                self._convert_entry(entry)
                for entry in extraction_result.entries
            ]

            # Filter for open items: no clearing document, or cleared after key_date
            open_entries = [
                e for e in entries
                if self._is_open_item(e, key_date)
            ]

            # Apply document type filters if specified
            if doc_type_filters:
                open_entries = [
                    e for e in open_entries
                    if e.blart in doc_type_filters
                ]

            duration_ms = (time.perf_counter() - start) * 1000
            _structured_logger.log_success(
                operation="pull_open_items",
                duration_ms=duration_ms,
                vendor_code=vendor_code,
                company_code=company_code,
                total_pulled=len(entries),
                open_items=len(open_entries),
            )
            logger.info(
                "RealSAPAdapter.pull_open_items complete: "
                "vendor_code=%s, total_pulled=%d, open_items=%d",
                vendor_code,
                len(entries),
                len(open_entries),
            )
            return open_entries

        except SAPConnectionException:
            duration_ms = (time.perf_counter() - start) * 1000
            _structured_logger.log_failure(
                operation="pull_open_items",
                duration_ms=duration_ms,
                error="SAP connection failed",
                error_type="SAPConnectionException",
                vendor_code=vendor_code,
                company_code=company_code,
            )
            raise
        except Exception as exc:
            duration_ms = (time.perf_counter() - start) * 1000
            _structured_logger.log_failure(
                operation="pull_open_items",
                duration_ms=duration_ms,
                error=str(exc),
                error_type=type(exc).__name__,
                vendor_code=vendor_code,
                company_code=company_code,
            )
            logger.error(
                "RealSAPAdapter.pull_open_items unexpected error: "
                "vendor_code=%s, company_code=%s, error=%s",
                vendor_code,
                company_code,
                str(exc),
            )
            raise SAPConnectionException(
                f"Failed to pull open items from SAP: {exc}"
            ) from exc

    # ──────────────────────────────────────────────────────────────────────
    # Private helpers
    # ──────────────────────────────────────────────────────────────────────

    def _convert_entry(self, connector_entry: ConnectorLedgerEntry) -> SAPLedgerEntry:
        """
        Convert a SAPConnectorService entry to the standardized SAPLedgerEntry.

        Maps fields from the connector's flat data model to the richer
        FBL1N-style dataclass used by the domain interface.

        Args:
            connector_entry: Entry from the existing SAPConnectorService.

        Returns:
            Standardized SAPLedgerEntry for the domain layer.
        """
        return SAPLedgerEntry(
            belnr=connector_entry.document_number or "",
            budat=self._date_to_sap_format(connector_entry.posting_date),
            blart=connector_entry.document_type or "",
            dmbtr=connector_entry.amount,
            wrbtr=connector_entry.amount,  # Default: same as local currency
            waers=connector_entry.currency or "INR",
            zuonr=connector_entry.assignment_number or "",
            augbl=connector_entry.clearing_document or "",
            augdt=self._date_to_sap_format(connector_entry.clearing_date),
            lifnr=connector_entry.vendor_code or "",
            bukrs=connector_entry.company_code or "",
        )

    @staticmethod
    def _date_to_sap_format(d: date | None) -> str:
        """
        Convert a Python date to SAP YYYYMMDD string format.

        Args:
            d: A date object, or None.

        Returns:
            Date formatted as 'YYYYMMDD', or empty string if None.
        """
        if d is None:
            return ""
        return d.strftime("%Y%m%d")

    @staticmethod
    def _is_open_item(entry: SAPLedgerEntry, key_date: date) -> bool:
        """
        Determine if a ledger entry is an open (uncleared) item as of key_date.

        An item is open if:
        - It has no clearing document (augbl is empty/falsy), OR
        - Its clearing date is after the key_date

        Args:
            entry: The ledger entry to check.
            key_date: The reference date for open item determination.

        Returns:
            True if the item is open as of key_date, False otherwise.
        """
        # No clearing document means the item is still open
        if not entry.augbl:
            return True

        # If there's a clearing date, check if it's after the key_date
        if entry.augdt:
            try:
                clearing_date_str = entry.augdt
                if len(clearing_date_str) == 8 and clearing_date_str.isdigit():
                    clearing_date = date(
                        int(clearing_date_str[:4]),
                        int(clearing_date_str[4:6]),
                        int(clearing_date_str[6:8]),
                    )
                    return clearing_date > key_date
            except (ValueError, IndexError):
                # If we can't parse the clearing date, treat as open
                return True

        # Has clearing document but no valid clearing date — treat as cleared
        return False
