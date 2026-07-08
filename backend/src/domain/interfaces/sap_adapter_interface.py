"""
SAP Adapter Pluggable Interface.

Defines the abstract interface (SAPAdapterInterface) for SAP data retrieval,
supporting both All Items and Open Items pulls with FBL1N-equivalent parameters.
The adapter pattern enables swapping between MockSAPAdapter (testing) and
RealSAPAdapter (production RFC) without modifying business logic.

Requirements: 8.1, 8.2, 8.5
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date
from decimal import Decimal


# ──────────────────────────────────────────────────────────────────────────────
# Data Classes
# ──────────────────────────────────────────────────────────────────────────────


@dataclass
class SAPLedgerEntry:
    """
    Represents a single ledger entry returned from SAP (FBL1N report).

    Contains all standard FBL1N fields as defined in BRD Section 5.2.2.
    This is the raw data shape returned by the SAP adapter before any
    transformation by the Data Transformation Engine.
    """

    # Core document identifiers
    belnr: str = ""  # Document Number (BELNR)
    gjahr: str = ""  # Fiscal Year (GJAHR)
    buzei: str = ""  # Line Item (BUZEI)

    # Date fields
    budat: str = ""  # Posting Date (BUDAT) - format: YYYYMMDD
    bldat: str = ""  # Document Date (BLDAT) - format: YYYYMMDD

    # Document type
    blart: str = ""  # Document Type (BLART) - e.g., RE, KR, DR, ZP, KZ, ZV, KG, RV

    # Amount fields
    dmbtr: Decimal = Decimal("0")  # Amount in Local Currency (DMBTR)
    wrbtr: Decimal = Decimal("0")  # Amount in Transaction Currency (WRBTR)

    # Currency and debit/credit
    waers: str = "INR"  # Currency Code (WAERS)
    shkzg: str = ""  # Debit/Credit Indicator (SHKZG) - S=debit, H=credit

    # Reference fields
    zuonr: str = ""  # Assignment Number (ZUONR)
    xblnr: str = ""  # Reference Number (XBLNR)

    # Clearing information
    augbl: str = ""  # Clearing Document (AUGBL)
    augdt: str = ""  # Clearing Date (AUGDT) - format: YYYYMMDD

    # Vendor and company
    lifnr: str = ""  # Vendor Number (LIFNR)
    bukrs: str = ""  # Company Code (BUKRS)

    # Text
    sgtxt: str = ""  # Text (SGTXT)


# ──────────────────────────────────────────────────────────────────────────────
# Abstract Interface
# ──────────────────────────────────────────────────────────────────────────────


class SAPAdapterInterface(ABC):
    """
    Abstract SAP adapter supporting All Items and Open Items pulls.

    Implementations:
    - MockSAPAdapter: Returns realistic test data matching the interface contract
    - RealSAPAdapter: Wraps SAP RFC connectivity via existing SAPConnectorService

    The adapter accepts FBL1N-equivalent parameters (vendor code, company code,
    date range, document type filters) and returns a list of SAPLedgerEntry objects.
    """

    @abstractmethod
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

        Equivalent to SAP FBL1N with "All Items" selection.

        Args:
            vendor_code: SAP vendor number (LIFNR).
            company_code: SAP company code (BUKRS).
            date_from: Start of posting date range (BUDAT from).
            date_to: End of posting date range (BUDAT to).
            doc_type_filters: Optional list of document types to filter (BLART).
                If None, all document types are returned.

        Returns:
            List of SAPLedgerEntry objects representing all ledger items
            (both cleared and uncleared) within the specified date range.
        """
        ...

    @abstractmethod
    async def pull_open_items(
        self,
        vendor_code: str,
        company_code: str,
        key_date: date,
        doc_type_filters: list[str] | None = None,
    ) -> list[SAPLedgerEntry]:
        """
        Pull only uncleared (open) items from SAP as of a key date.

        Equivalent to SAP FBL1N with "Open Items" selection.

        Args:
            vendor_code: SAP vendor number (LIFNR).
            company_code: SAP company code (BUKRS).
            key_date: The reference date for determining open item status.
                Items not cleared as of this date are returned.
            doc_type_filters: Optional list of document types to filter (BLART).
                If None, all document types are returned.

        Returns:
            List of SAPLedgerEntry objects representing uncleared items
            as of the specified key_date.
        """
        ...
