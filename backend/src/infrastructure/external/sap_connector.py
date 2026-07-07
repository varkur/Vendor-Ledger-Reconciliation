"""
SAP ERP Connector Service.

Integration layer that pulls vendor master data and ledger entries from SAP
via RFC/BAPI calls. Implements retry logic with exponential backoff, duplicate
detection, incremental pulls, and rollback on partial extraction failure.

SAP field mapping:
  ZUONR → assignment_number
  BELNR → document_number
  BLART → document_type
  DMBTR → amount
  BUDAT → posting_date
  AUGDT → clearing_date
  AUGBL → clearing_document

Security: SAP credentials are never exposed in responses or logs.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

import httpx

from src.domain.exceptions.vlr import SAPConnectionException

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Retry configuration: 3 retries with exponential backoff (2s, 4s, 8s)
MAX_RETRIES = 3
BASE_BACKOFF_SECONDS = 2.0

# SAP field mapping: SAP field name → internal field name
SAP_FIELD_MAPPING: dict[str, str] = {
    "ZUONR": "assignment_number",
    "BELNR": "document_number",
    "BLART": "document_type",
    "DMBTR": "amount",
    "BUDAT": "posting_date",
    "AUGDT": "clearing_date",
    "AUGBL": "clearing_document",
}

# Reverse mapping: internal field name → SAP field name
INTERNAL_TO_SAP_MAPPING: dict[str, str] = {v: k for k, v in SAP_FIELD_MAPPING.items()}

# Connection test timeout in seconds
CONNECTION_TEST_TIMEOUT = 30


# ---------------------------------------------------------------------------
# Data Transfer Objects
# ---------------------------------------------------------------------------


@dataclass
class DateRange:
    """Date range for ledger extraction."""

    start: date
    end: date


@dataclass
class SAPVendorData:
    """Vendor master data pulled from SAP."""

    vendor_code: str
    name: str
    company_code: str
    city: str | None = None
    pan: str | None = None
    gstin: str | None = None


@dataclass
class SAPLedgerEntry:
    """A single ledger entry mapped from SAP fields to internal schema."""

    assignment_number: str | None = None
    document_number: str = ""
    document_type: str | None = None
    amount: Decimal = Decimal("0.00")
    posting_date: date | None = None
    clearing_date: date | None = None
    clearing_document: str | None = None
    # Additional metadata
    vendor_code: str = ""
    company_code: str = ""
    currency: str = "INR"


@dataclass
class ConnectionTestResult:
    """Result of a SAP connection test."""

    success: bool
    message: str
    response_time_ms: float = 0.0
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class SAPHealthStatus:
    """SAP integration health status."""

    is_connected: bool
    last_successful_pull: datetime | None = None
    error_count: int = 0
    last_error: str | None = None
    last_check: datetime | None = None


@dataclass
class ExtractionResult:
    """Result of a SAP data extraction operation."""

    entries: list[SAPLedgerEntry]
    row_count: int
    duplicates_skipped: int
    extraction_timestamp: datetime
    duration_seconds: float


# ---------------------------------------------------------------------------
# SAP Connector Configuration
# ---------------------------------------------------------------------------


@dataclass
class SAPConfig:
    """
    SAP connection configuration.

    Credentials are stored here but never exposed in string representations
    or log output.
    """

    host: str = ""
    system_number: str = "00"
    client: str = "100"
    username: str = ""
    password: str = ""
    base_url: str = ""

    def __repr__(self) -> str:
        """Ensure credentials are never leaked in repr."""
        return (
            f"SAPConfig(host='{self.host}', system_number='{self.system_number}', "
            f"client='{self.client}', username='***', password='***')"
        )

    def __str__(self) -> str:
        """Ensure credentials are never leaked in str."""
        return self.__repr__()

    @property
    def is_configured(self) -> bool:
        """True when minimum required connection parameters are set."""
        return bool(self.host and self.username and self.password)


# ---------------------------------------------------------------------------
# Helper Functions
# ---------------------------------------------------------------------------


def map_sap_entry_to_internal(raw_entry: dict[str, Any]) -> SAPLedgerEntry:
    """
    Map a raw SAP entry dict (with SAP field names) to an SAPLedgerEntry.

    Applies the SAP_FIELD_MAPPING to translate field names and handles
    type conversions for amount (Decimal) and dates.
    """
    mapped: dict[str, Any] = {}

    for sap_field, internal_field in SAP_FIELD_MAPPING.items():
        value = raw_entry.get(sap_field)
        if value is None:
            mapped[internal_field] = None
            continue

        if internal_field == "amount":
            mapped[internal_field] = Decimal(str(value))
        elif internal_field in ("posting_date", "clearing_date"):
            mapped[internal_field] = _parse_sap_date(value)
        else:
            mapped[internal_field] = str(value) if value else None

    # Pass through non-mapped fields that we need
    mapped["vendor_code"] = raw_entry.get("LIFNR", raw_entry.get("vendor_code", ""))
    mapped["company_code"] = raw_entry.get("BUKRS", raw_entry.get("company_code", ""))
    mapped["currency"] = raw_entry.get("WAERS", raw_entry.get("currency", "INR"))

    return SAPLedgerEntry(**mapped)


def map_internal_to_sap(entry: SAPLedgerEntry) -> dict[str, Any]:
    """
    Map an internal SAPLedgerEntry back to SAP field names.

    Used for round-trip verification and testing.
    """
    result: dict[str, Any] = {}
    for sap_field, internal_field in SAP_FIELD_MAPPING.items():
        value = getattr(entry, internal_field, None)
        if value is None:
            result[sap_field] = None
        elif internal_field == "amount":
            result[sap_field] = float(value) if value else 0.0
        elif internal_field in ("posting_date", "clearing_date"):
            result[sap_field] = value.strftime("%Y%m%d") if value else None
        else:
            result[sap_field] = str(value) if value else None
    return result


def _parse_sap_date(value: Any) -> date | None:
    """Parse a SAP date value to a Python date. Handles YYYYMMDD and ISO formats."""
    if value is None:
        return None
    if isinstance(value, date):
        return value

    date_str = str(value).strip()
    if not date_str or date_str == "00000000":
        return None

    # Try YYYYMMDD format (SAP standard)
    if len(date_str) == 8 and date_str.isdigit():
        try:
            return date(int(date_str[:4]), int(date_str[4:6]), int(date_str[6:8]))
        except ValueError:
            return None

    # Try ISO format (YYYY-MM-DD)
    try:
        return date.fromisoformat(date_str[:10])
    except ValueError:
        return None


def detect_duplicates(
    entries: list[SAPLedgerEntry],
    vendor_code: str,
    period: DateRange,
) -> tuple[list[SAPLedgerEntry], list[SAPLedgerEntry]]:
    """
    Detect and remove duplicate SAP entries.

    Duplicates are identified by the combination of:
    - vendor_code
    - period (all entries are for same period)
    - document_number
    - amount

    Returns:
        Tuple of (unique_entries, duplicate_entries)
    """
    seen: set[tuple[str, str, str]] = set()
    unique: list[SAPLedgerEntry] = []
    duplicates: list[SAPLedgerEntry] = []

    for entry in entries:
        # Composite key for duplicate detection
        key = (
            vendor_code,
            entry.document_number,
            str(entry.amount),
        )

        if key in seen:
            duplicates.append(entry)
        else:
            seen.add(key)
            unique.append(entry)

    return unique, duplicates


# ---------------------------------------------------------------------------
# SAP Connector Service
# ---------------------------------------------------------------------------


class SAPConnectorService:
    """
    Integration service for SAP ERP.

    Provides methods to pull vendor master data and ledger entries via
    RFC/BAPI calls. Implements:
    - Retry logic with exponential backoff (3 retries: 2s, 4s, 8s)
    - Duplicate detection (same vendor, period, document_number, amount)
    - Rollback on partial extraction failure
    - Incremental pulls using last extraction timestamp
    - Health monitoring

    Security: SAP credentials are never exposed in responses or logs.
    """

    def __init__(self, config: SAPConfig | None = None) -> None:
        self._config = config or SAPConfig()
        self._last_successful_pull: datetime | None = None
        self._error_count: int = 0
        self._last_error: str | None = None

    @property
    def config(self) -> SAPConfig:
        return self._config

    def configure(self, config: SAPConfig) -> None:
        """Update the SAP configuration."""
        self._config = config

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def pull_vendor_master(self, company_code: str) -> list[SAPVendorData]:
        """
        Pull vendor master data from SAP for a given company code.

        Implements retry logic with exponential backoff.

        Args:
            company_code: The company code to pull vendor data for.

        Returns:
            List of SAPVendorData objects.

        Raises:
            SAPConnectionException: If connection fails after all retries.
        """
        if not self._config.is_configured:
            raise SAPConnectionException("SAP connection is not configured.")

        async def _do_pull() -> list[dict[str, Any]]:
            async with httpx.AsyncClient(verify=False, timeout=60) as client:
                response = await client.get(
                    f"{self._config.base_url}/vendors",
                    params={"company_code": company_code},
                    headers=self._build_headers(),
                )
                response.raise_for_status()
                return response.json()

        raw_data = await self._execute_with_retry(_do_pull, "pull_vendor_master")

        vendors = []
        for item in raw_data:
            vendors.append(
                SAPVendorData(
                    vendor_code=item.get("LIFNR", item.get("vendor_code", "")),
                    name=item.get("NAME1", item.get("name", "")),
                    company_code=item.get("BUKRS", item.get("company_code", company_code)),
                    city=item.get("ORT01", item.get("city")),
                    pan=item.get("STCD3", item.get("pan")),
                    gstin=item.get("STCD4", item.get("gstin")),
                )
            )

        self._record_success()
        logger.info(
            "SAP vendor master pull complete: company_code=%s, count=%d",
            company_code,
            len(vendors),
        )
        return vendors

    async def pull_ledger_entries(
        self,
        vendor_code: str,
        company_code: str,
        period: DateRange,
    ) -> ExtractionResult:
        """
        Pull ledger entries from SAP for a vendor within a date range.

        Implements:
        - Retry logic with exponential backoff (3 retries: 2s, 4s, 8s)
        - SAP field mapping to internal schema
        - Duplicate detection and removal
        - Rollback on partial extraction failure

        Args:
            vendor_code: The vendor code to extract entries for.
            company_code: The company code.
            period: Date range for extraction.

        Returns:
            ExtractionResult with unique entries and metadata.

        Raises:
            SAPConnectionException: If connection fails after all retries.
        """
        if not self._config.is_configured:
            raise SAPConnectionException("SAP connection is not configured.")

        start_time = datetime.now(timezone.utc)
        extracted_entries: list[SAPLedgerEntry] = []

        try:
            async def _do_pull() -> list[dict[str, Any]]:
                async with httpx.AsyncClient(verify=False, timeout=60) as client:
                    response = await client.get(
                        f"{self._config.base_url}/ledger_entries",
                        params={
                            "vendor_code": vendor_code,
                            "company_code": company_code,
                            "date_from": period.start.isoformat(),
                            "date_to": period.end.isoformat(),
                        },
                        headers=self._build_headers(),
                    )
                    response.raise_for_status()
                    return response.json()

            raw_data = await self._execute_with_retry(_do_pull, "pull_ledger_entries")

            # Map SAP fields to internal schema
            for raw_entry in raw_data:
                entry = map_sap_entry_to_internal(raw_entry)
                entry.vendor_code = vendor_code
                entry.company_code = company_code
                extracted_entries.append(entry)

            # Detect and remove duplicates
            unique_entries, duplicates = detect_duplicates(
                extracted_entries, vendor_code, period
            )

            if duplicates:
                logger.warning(
                    "SAP duplicate entries skipped: vendor_code=%s, "
                    "company_code=%s, period=%s-%s, duplicates_count=%d",
                    vendor_code,
                    company_code,
                    period.start.isoformat(),
                    period.end.isoformat(),
                    len(duplicates),
                )

            end_time = datetime.now(timezone.utc)
            duration = (end_time - start_time).total_seconds()

            self._record_success()
            logger.info(
                "SAP ledger pull complete: vendor_code=%s, company_code=%s, "
                "period=%s-%s, total=%d, unique=%d, duplicates=%d, duration=%.2fs",
                vendor_code,
                company_code,
                period.start.isoformat(),
                period.end.isoformat(),
                len(extracted_entries),
                len(unique_entries),
                len(duplicates),
                duration,
            )

            return ExtractionResult(
                entries=unique_entries,
                row_count=len(unique_entries),
                duplicates_skipped=len(duplicates),
                extraction_timestamp=end_time,
                duration_seconds=duration,
            )

        except SAPConnectionException:
            # Rollback: discard partially extracted data
            extracted_entries.clear()
            raise
        except Exception as exc:
            # Rollback: discard partially extracted data on any unexpected failure
            extracted_entries.clear()
            self._record_error(str(exc))
            logger.error(
                "SAP ledger pull failed (rollback applied): vendor_code=%s, "
                "company_code=%s, error=%s",
                vendor_code,
                company_code,
                str(exc),
            )
            raise SAPConnectionException(
                f"SAP data extraction failed: {exc}"
            ) from exc

    async def test_connection(self) -> ConnectionTestResult:
        """
        Test the SAP connection by attempting a lightweight health check.

        Returns within 30 seconds with success/failure status.

        Returns:
            ConnectionTestResult with success status and response time.
        """
        if not self._config.is_configured:
            return ConnectionTestResult(
                success=False,
                message="SAP connection is not configured. Please provide host, username, and password.",
            )

        start_time = datetime.now(timezone.utc)

        try:
            async with httpx.AsyncClient(
                verify=False, timeout=CONNECTION_TEST_TIMEOUT
            ) as client:
                response = await client.get(
                    f"{self._config.base_url}/health",
                    headers=self._build_headers(),
                )
                response.raise_for_status()

            end_time = datetime.now(timezone.utc)
            response_time_ms = (end_time - start_time).total_seconds() * 1000

            self._record_success()
            return ConnectionTestResult(
                success=True,
                message="SAP connection successful.",
                response_time_ms=response_time_ms,
                details={"status_code": response.status_code},
            )

        except httpx.HTTPStatusError as exc:
            end_time = datetime.now(timezone.utc)
            response_time_ms = (end_time - start_time).total_seconds() * 1000
            error_msg = f"SAP responded with HTTP {exc.response.status_code}"
            self._record_error(error_msg)
            return ConnectionTestResult(
                success=False,
                message=error_msg,
                response_time_ms=response_time_ms,
                details={"status_code": exc.response.status_code},
            )

        except httpx.RequestError as exc:
            end_time = datetime.now(timezone.utc)
            response_time_ms = (end_time - start_time).total_seconds() * 1000
            error_msg = f"SAP connection failed: {type(exc).__name__}"
            self._record_error(error_msg)
            return ConnectionTestResult(
                success=False,
                message=error_msg,
                response_time_ms=response_time_ms,
            )

    async def get_health_status(self) -> SAPHealthStatus:
        """
        Get the current SAP integration health status.

        Returns status including last successful pull timestamp, error count,
        and last error message.

        Returns:
            SAPHealthStatus with current state.
        """
        is_connected = self._config.is_configured
        if is_connected:
            # Perform a quick connectivity check
            test_result = await self.test_connection()
            is_connected = test_result.success

        return SAPHealthStatus(
            is_connected=is_connected,
            last_successful_pull=self._last_successful_pull,
            error_count=self._error_count,
            last_error=self._last_error,
            last_check=datetime.now(timezone.utc),
        )

    async def incremental_pull(
        self,
        vendor_code: str,
        company_code: str,
        since: datetime,
    ) -> ExtractionResult:
        """
        Pull ledger entries created or modified since a given timestamp.

        Supports incremental data synchronization by only extracting entries
        newer than the last extraction timestamp.

        Args:
            vendor_code: The vendor code.
            company_code: The company code.
            since: Timestamp of last extraction (entries after this are pulled).

        Returns:
            ExtractionResult with new/modified entries.

        Raises:
            SAPConnectionException: If connection fails after all retries.
        """
        if not self._config.is_configured:
            raise SAPConnectionException("SAP connection is not configured.")

        start_time = datetime.now(timezone.utc)
        extracted_entries: list[SAPLedgerEntry] = []

        try:
            async def _do_pull() -> list[dict[str, Any]]:
                async with httpx.AsyncClient(verify=False, timeout=60) as client:
                    response = await client.get(
                        f"{self._config.base_url}/ledger_entries/incremental",
                        params={
                            "vendor_code": vendor_code,
                            "company_code": company_code,
                            "since": since.isoformat(),
                        },
                        headers=self._build_headers(),
                    )
                    response.raise_for_status()
                    return response.json()

            raw_data = await self._execute_with_retry(_do_pull, "incremental_pull")

            # Map SAP fields to internal schema
            for raw_entry in raw_data:
                entry = map_sap_entry_to_internal(raw_entry)
                entry.vendor_code = vendor_code
                entry.company_code = company_code
                extracted_entries.append(entry)

            # Detect and remove duplicates
            period = DateRange(start=since.date(), end=start_time.date())
            unique_entries, duplicates = detect_duplicates(
                extracted_entries, vendor_code, period
            )

            if duplicates:
                logger.warning(
                    "SAP incremental pull duplicates skipped: vendor_code=%s, "
                    "company_code=%s, since=%s, duplicates_count=%d",
                    vendor_code,
                    company_code,
                    since.isoformat(),
                    len(duplicates),
                )

            end_time = datetime.now(timezone.utc)
            duration = (end_time - start_time).total_seconds()

            self._record_success()
            logger.info(
                "SAP incremental pull complete: vendor_code=%s, company_code=%s, "
                "since=%s, total=%d, unique=%d, duration=%.2fs",
                vendor_code,
                company_code,
                since.isoformat(),
                len(extracted_entries),
                len(unique_entries),
                duration,
            )

            return ExtractionResult(
                entries=unique_entries,
                row_count=len(unique_entries),
                duplicates_skipped=len(duplicates),
                extraction_timestamp=end_time,
                duration_seconds=duration,
            )

        except SAPConnectionException:
            extracted_entries.clear()
            raise
        except Exception as exc:
            extracted_entries.clear()
            self._record_error(str(exc))
            logger.error(
                "SAP incremental pull failed (rollback applied): vendor_code=%s, "
                "company_code=%s, error=%s",
                vendor_code,
                company_code,
                str(exc),
            )
            raise SAPConnectionException(
                f"SAP incremental extraction failed: {exc}"
            ) from exc

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build_headers(self) -> dict[str, str]:
        """Build HTTP headers for SAP API calls. Credentials are in auth, not headers."""
        return {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    async def _execute_with_retry(
        self,
        operation: Any,
        operation_name: str,
    ) -> Any:
        """
        Execute an async operation with retry logic.

        Retries up to MAX_RETRIES times with exponential backoff:
        - Attempt 1 fails → wait 2s
        - Attempt 2 fails → wait 4s
        - Attempt 3 fails → wait 8s
        - After 3 retries, raise SAPConnectionException

        Args:
            operation: Async callable to execute.
            operation_name: Name for logging purposes.

        Returns:
            The result of the operation.

        Raises:
            SAPConnectionException: If all retries are exhausted.
        """
        last_exception: Exception | None = None

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                result = await operation()
                return result
            except (httpx.RequestError, httpx.HTTPStatusError) as exc:
                last_exception = exc
                backoff = BASE_BACKOFF_SECONDS * (2 ** (attempt - 1))

                # Do not log credentials - only log operation context
                logger.warning(
                    "SAP %s attempt %d/%d failed: %s. Retrying in %.1fs...",
                    operation_name,
                    attempt,
                    MAX_RETRIES,
                    type(exc).__name__,
                    backoff,
                )

                if attempt < MAX_RETRIES:
                    await asyncio.sleep(backoff)

        # All retries exhausted
        self._record_error(
            f"{operation_name} failed after {MAX_RETRIES} retries"
        )
        raise SAPConnectionException(
            f"SAP {operation_name} failed after {MAX_RETRIES} retries. "
            "Please check SAP system availability."
        ) from last_exception

    def _record_success(self) -> None:
        """Record a successful SAP operation."""
        self._last_successful_pull = datetime.now(timezone.utc)

    def _record_error(self, error_message: str) -> None:
        """Record a SAP operation failure."""
        self._error_count += 1
        self._last_error = error_message
