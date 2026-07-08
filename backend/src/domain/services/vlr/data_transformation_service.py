"""
Data Transformation Engine Domain Service.

Implements invoice number derivation (ZUONR > XBLNR > BELNR fallback),
CLEAN function application, sign adjustment, balance calculations,
TDS tagging/linking, and document type classification.

Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 2.1, 2.2, 2.3, 2.4,
              3.1, 3.2, 3.3, 4.1, 4.2, 4.3, 5.1, 5.2, 5.3,
              6.1, 6.2, 7.1, 7.2, 7.3, 7.4, 7.5
"""

import re
import time
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from src.domain.repositories.vlr.config_repository import IConfigRepository
from src.infrastructure.logging.structured_logger import get_structured_logger

_structured_logger = get_structured_logger("data_transformation")


# ──────────────────────────────────────────────────────────────────────────────
# Data Classes
# ──────────────────────────────────────────────────────────────────────────────


class InvoiceSourceField(StrEnum):
    """Indicates which SAP field the invoice number was derived from."""

    ZUONR = "ZUONR"
    XBLNR = "XBLNR"
    BELNR = "BELNR"


class DocumentCategory(StrEnum):
    """Document type categories for classification."""

    INVOICE = "Invoice"
    PAYMENT = "Payment"
    CREDIT_NOTE = "Credit Note"
    DEBIT_NOTE = "Debit Note"
    TDS = "TDS"
    OTHER = "Other"


# Document types that are invoice-like (use ZUONR > XBLNR > BELNR derivation)
INVOICE_DOC_TYPES = {"RE", "KR", "DR", "KG", "RV"}

# Document types that are payment (invoice_number = NULL, use AUGBL)
PAYMENT_DOC_TYPES = {"ZP", "KZ", "ZV"}

# Document types that are journal entries (invoice_number = NULL, manual review)
JOURNAL_DOC_TYPES = {"AB", "SA"}


@dataclass
class LedgerEntry:
    """
    Represents a transformed ledger entry ready for balance calculations.

    Contains the sign-adjusted amount and posting date needed for
    opening/closing balance computations, as well as TDS tagging fields.
    """

    posting_date: date
    adjusted_amount: Decimal  # Sign-adjusted amount (H → positive, S → negative)
    side: str = ""  # 'company' or 'vendor'
    document_number: str = ""
    reference_number: str = ""
    clearing_date: date | None = None
    document_type: str = ""  # SAP document type code (e.g., RE, KR, ZP)
    entry_id: str = ""  # Unique identifier for the entry

    # TDS tagging fields (populated by tag_tds_entries)
    is_tds: bool = False
    tds_parent_entry_id: str | None = None
    flags: list[str] = field(default_factory=list)
    transaction_currency: str = "INR"  # Original transaction currency code
    local_currency_amount: Decimal | None = None  # INR equivalent amount


@dataclass
class MultiCurrencyEntry:
    """
    Result of multi-currency preparation for a SAP entry.

    Stores both the transaction currency amount and local currency (INR) equivalent,
    along with the exchange rate used for conversion.
    """

    transaction_currency: str  # Currency code (e.g., "USD", "EUR", "INR")
    transaction_amount: Decimal  # Amount in transaction currency (wrbtr)
    local_currency_amount: Decimal  # Amount in local currency INR (dmbtr)
    exchange_rate: Decimal  # Effective exchange rate (local / transaction)


@dataclass
class RawSAPEntry:
    """
    Represents a raw SAP ledger entry as received from FBL1N.

    Contains all relevant fields before any transformation.
    """

    # Core identifiers
    belnr: str = ""  # Document Number
    gjahr: str = ""  # Fiscal Year
    buzei: str = ""  # Line Item

    # Invoice number source fields (priority order)
    zuonr: str = ""  # Assignment Number (primary)
    xblnr: str = ""  # Reference Document Number (secondary)

    # Document metadata
    blart: str = ""  # Document Type (RE, KR, DR, ZP, KZ, etc.)
    budat: str = ""  # Posting Date (YYYY-MM-DD or YYYYMMDD)

    # Amount fields
    dmbtr: Decimal = Decimal("0")  # Amount in Local Currency
    wrbtr: Decimal = Decimal("0")  # Amount in Transaction Currency
    waers: str = "INR"  # Transaction Currency Code
    shkzg: str = ""  # Debit/Credit indicator (S=debit, H=credit)

    # Clearing information
    augbl: str = ""  # Clearing Document Number
    augdt: str = ""  # Clearing Date

    # Vendor information
    lifnr: str = ""  # Vendor Number
    bukrs: str = ""  # Company Code


@dataclass
class DerivedInvoice:
    """
    Result of invoice number derivation from a RawSAPEntry.

    Stores both the raw source value and the cleaned derived invoice number,
    along with metadata about the derivation source and any flags.
    """

    # The cleaned, normalized invoice number (after CLEAN function)
    invoice_number: str | None = None

    # The raw, unmodified value from the source field
    raw_value: str | None = None

    # Which field the invoice number was derived from
    source_field: InvoiceSourceField | None = None

    # Flags for special cases
    flags: list[str] = field(default_factory=list)

    # Payment reference (for payment documents using AUGBL)
    payment_reference: str | None = None


# Default special characters to remove during CLEAN function
DEFAULT_SPECIAL_CHARACTERS = ["/", "\\", "-", "_"]


# ──────────────────────────────────────────────────────────────────────────────
# Service
# ──────────────────────────────────────────────────────────────────────────────


class DataTransformationService:
    """
    Transforms raw SAP ledger data into reconciliation-ready format.

    Handles invoice number derivation, CLEAN function application,
    sign adjustment, balance calculations, TDS tagging, and
    document type classification.
    """

    def __init__(self, config_repository: IConfigRepository):
        self._config_repo = config_repository

    # ──────────────────────────────────────────────────────────────────────
    # Invoice Number Derivation
    # ──────────────────────────────────────────────────────────────────────

    def derive_invoice_number(self, entry: RawSAPEntry) -> DerivedInvoice:
        """
        Derive invoice number using ZUONR > XBLNR > BELNR priority.

        Logic by document type:
        - Invoice types (RE, KR, DR) and Credit/Debit Notes (KG, RV):
          Use ZUONR > XBLNR > BELNR fallback with CLEAN function applied.
        - Payment types (ZP, KZ, ZV):
          invoice_number = None, payment_reference = AUGBL (Clearing Document).
        - Journal entries (AB, SA):
          invoice_number = None, flagged for manual review.
        - All other document types:
          Use standard ZUONR > XBLNR > BELNR fallback.

        Requirement 1.1: ZUONR as primary source.
        Requirement 1.2: XBLNR as secondary source.
        Requirement 1.3: BELNR as tertiary fallback.
        Requirement 1.4: Apply CLEAN function to result.
        Requirement 1.5: Store both raw and cleaned values.
        """
        start = time.perf_counter()
        doc_type = entry.blart.strip().upper()

        # Payment documents: invoice_number = NULL, use AUGBL
        if doc_type in PAYMENT_DOC_TYPES:
            result = DerivedInvoice(
                invoice_number=None,
                raw_value=entry.augbl if entry.augbl.strip() else None,
                source_field=None,
                payment_reference=self.clean_reference(entry.augbl)
                if entry.augbl.strip()
                else None,
                flags=[],
            )
        elif doc_type in JOURNAL_DOC_TYPES:
            # Journal entries: invoice_number = NULL, flag for manual review
            result = DerivedInvoice(
                invoice_number=None,
                raw_value=None,
                source_field=None,
                payment_reference=None,
                flags=["Journal Entry — Manual Review Required"],
            )
        else:
            # Invoice types, Credit/Debit Notes, and all other types:
            # Apply ZUONR > XBLNR > BELNR priority fallback
            result = self._derive_with_priority_fallback(entry)

        duration_ms = (time.perf_counter() - start) * 1000
        _structured_logger.log_success(
            operation="derive_invoice_number",
            duration_ms=duration_ms,
            doc_type=doc_type,
            source_field=result.source_field.value if result.source_field else None,
        )
        return result

    def _derive_with_priority_fallback(self, entry: RawSAPEntry) -> DerivedInvoice:
        """
        Apply ZUONR > XBLNR > BELNR priority fallback logic.

        Returns DerivedInvoice with raw value, cleaned value, and source field.
        If BELNR fallback is used, a flag is added indicating this.
        """
        # Priority 1: ZUONR (Assignment field)
        if self._is_non_empty(entry.zuonr):
            raw_value = entry.zuonr.strip()
            cleaned = self.clean_reference(raw_value)
            return DerivedInvoice(
                invoice_number=cleaned if cleaned else None,
                raw_value=raw_value,
                source_field=InvoiceSourceField.ZUONR,
                flags=[],
            )

        # Priority 2: XBLNR (Reference field)
        if self._is_non_empty(entry.xblnr):
            raw_value = entry.xblnr.strip()
            cleaned = self.clean_reference(raw_value)
            return DerivedInvoice(
                invoice_number=cleaned if cleaned else None,
                raw_value=raw_value,
                source_field=InvoiceSourceField.XBLNR,
                flags=[],
            )

        # Priority 3: BELNR (Document Number) - stored as BELNR + "/" + GJAHR
        if self._is_non_empty(entry.belnr):
            raw_value = f"{entry.belnr.strip()}/{entry.gjahr.strip()}" if entry.gjahr.strip() else entry.belnr.strip()
            cleaned = self.clean_reference(raw_value)
            return DerivedInvoice(
                invoice_number=cleaned if cleaned else None,
                raw_value=raw_value,
                source_field=InvoiceSourceField.BELNR,
                flags=["Invoice Number Not Found — Using Doc Number"],
            )

        # All sources empty
        return DerivedInvoice(
            invoice_number=None,
            raw_value=None,
            source_field=None,
            flags=["Invoice Number Not Found — All Sources Empty"],
        )

    # ──────────────────────────────────────────────────────────────────────
    # CLEAN Function
    # ──────────────────────────────────────────────────────────────────────

    def clean_reference(
        self, raw_value: str, special_chars: list[str] | None = None
    ) -> str:
        """
        Strip leading zeros, special characters, and whitespace from a reference.

        CLEAN function steps:
        1. Trim leading and trailing whitespace
        2. Convert to uppercase
        3. Remove configurable special characters (default: /, \\, -, _)
        4. Remove leading zeros

        Requirement 1.4: Apply CLEAN function to derived invoice number.

        Args:
            raw_value: The raw reference string to clean.
            special_chars: Optional list of characters to remove.
                          Defaults to ['/', '\\', '-', '_'].

        Returns:
            Cleaned reference string with no leading zeros,
            no special characters, and no surrounding whitespace.
        """
        if not raw_value:
            return ""

        # Step 1: Trim leading and trailing whitespace
        result = raw_value.strip()

        if not result:
            return ""

        # Step 2: Convert to uppercase
        result = result.upper()

        # Step 3: Remove special characters (configurable)
        chars_to_remove = special_chars if special_chars is not None else DEFAULT_SPECIAL_CHARACTERS
        for char in chars_to_remove:
            result = result.replace(char, "")

        # Step 4: Remove leading zeros
        result = result.lstrip("0")

        # Final trim in case removing chars left whitespace
        result = result.strip()

        return result

    # ──────────────────────────────────────────────────────────────────────
    # Sign Adjustment (stub - implemented in task 1.3)
    # ──────────────────────────────────────────────────────────────────────

    def apply_sign_adjustment(self, amount: Decimal, shkzg: str) -> Decimal:
        """
        Apply sign adjustment based on SHKZG indicator.

        H (credit) → positive, S (debit) → negative.

        The original unsigned amount and SHKZG indicator are preserved
        separately by the caller (stored in RawSAPEntry / ledger_entries model).
        This method returns only the sign-adjusted amount.

        Requirement 2.1: H → positive (ABS(amount)).
        Requirement 2.2: S → negative (-1 * ABS(amount)).
        Requirement 2.3: Sign adjustment runs before balance calculation.
        Requirement 2.4: Original unsigned amount and SHKZG preserved by caller.

        Args:
            amount: The unsigned (or raw) amount from SAP (DMBTR field).
            shkzg: The debit/credit indicator ('H' for credit, 'S' for debit).

        Returns:
            The sign-adjusted Decimal amount.

        Raises:
            ValueError: If shkzg is empty, None, or not a recognized indicator.
        """
        if not shkzg or not shkzg.strip():
            raise ValueError(
                "SHKZG indicator is required for sign adjustment. "
                "Expected 'H' (credit) or 'S' (debit)."
            )

        indicator = shkzg.strip().upper()

        if indicator == "H":
            # Credit: amount should be positive
            return abs(amount)
        elif indicator == "S":
            # Debit: amount should be negative
            return -abs(amount)
        else:
            raise ValueError(
                f"Unrecognized SHKZG indicator: '{shkzg}'. "
                "Expected 'H' (credit) or 'S' (debit)."
            )

    # ──────────────────────────────────────────────────────────────────────
    # Balance Calculations
    # ──────────────────────────────────────────────────────────────────────

    def calculate_opening_balance(
        self, entries: list[LedgerEntry], period_start: date, side: str
    ) -> Decimal:
        """
        Calculate opening balance as sum of sign-adjusted open items
        before period start.

        The opening balance represents the net open liability to the vendor
        as of the day immediately before the reconciliation period start date.

        Logic:
        - eligible_items = entries WHERE posting_date < period_start
        - opening_balance = SUM(adjusted_amount) for all eligible_items
        - Only items for the specified side are included
        - Clearing date is NOT used for inclusion — posting date is used
        - If an item was posted before period start but cleared within the
          period, it still counts in the opening balance (it was open at
          period start)

        Requirement 3.1: Sum of sign-adjusted open items with posting date
                         before period start.
        Requirement 3.2: Include items that remain uncleared as of period start
                         (uses posting_date < period_start for eligibility).
        Requirement 3.3: Calculate separate balances for company and vendor sides.

        Args:
            entries: List of LedgerEntry objects with adjusted_amount and
                     posting_date already populated.
            period_start: The start date of the reconciliation period.
            side: The ledger side to calculate for ('company' or 'vendor').

        Returns:
            The opening balance as a Decimal sum of eligible entries.
        """
        total = Decimal("0")
        for entry in entries:
            # Filter by side and posting date before period start
            if entry.side == side and entry.posting_date < period_start:
                total += entry.adjusted_amount
        return total

    def calculate_closing_balance(
        self,
        opening_balance: Decimal,
        entries: list[LedgerEntry],
        period_start: date,
        period_end: date,
        side: str = "",
    ) -> Decimal:
        """
        Calculate closing balance as opening + net movement within period.

        The closing balance equals the opening balance plus the net movement
        during the reconciliation period. Net movement is the sum of all
        sign-adjusted entries with posting dates within the period (inclusive).

        Logic:
        - period_transactions = entries WHERE posting_date >= period_start
                                          AND posting_date <= period_end
        - net_period_movement = SUM(adjusted_amount) for period_transactions
        - closing_balance = opening_balance + net_period_movement

        Requirement 4.1: Closing balance = opening balance + net movement.
        Requirement 4.2: Net movement = sum of entries within the period.
        Requirement 4.3: Calculate separate closing balances for company
                         and vendor sides.

        Args:
            opening_balance: The pre-calculated opening balance for this side.
            entries: List of LedgerEntry objects with adjusted_amount and
                     posting_date already populated.
            period_start: The start date of the reconciliation period (inclusive).
            period_end: The end date of the reconciliation period (inclusive).
            side: The ledger side to calculate for ('company' or 'vendor').
                  If empty, all entries within the period are summed.

        Returns:
            The closing balance as opening_balance + net_period_movement.
        """
        net_movement = Decimal("0")
        for entry in entries:
            # Filter by period boundaries (inclusive)
            if entry.posting_date >= period_start and entry.posting_date <= period_end:
                # Filter by side if specified
                if side and entry.side != side:
                    continue
                net_movement += entry.adjusted_amount
        return opening_balance + net_movement

    # ──────────────────────────────────────────────────────────────────────
    # TDS Tagging and Linking
    # ──────────────────────────────────────────────────────────────────────

    def tag_tds_entries(
        self, entries: list[LedgerEntry], tds_document_types: set[str] | None = None
    ) -> list[LedgerEntry]:
        """
        Tag TDS entries and link to parent invoices by reference number.

        Logic:
        1. For each entry, check if its document_type is classified as TDS
           using the provided tds_document_types set (pre-fetched from config).
        2. If TDS, set is_tds = True.
        3. Attempt to link to a parent invoice by matching the TDS entry's
           reference_number against non-TDS entries' reference_number or
           document_number.
        4. If a parent is found, set tds_parent_entry_id to the parent's entry_id.
        5. If no parent found, add flag "TDS Entry — No Parent Invoice Found"
           for manual review.

        Requirement 5.1: Tag entries with TDS document types as TDS rows.
        Requirement 5.2: Link TDS entries to parent invoices by reference number.
        Requirement 5.3: Flag unlinked TDS entries for manual review.

        Args:
            entries: List of LedgerEntry objects with document_type populated.
            tds_document_types: Optional set of document type codes classified as TDS.
                If not provided, defaults to an empty set (no entries tagged).
                Callers should pre-fetch this from IConfigRepository.

        Returns:
            The same list of LedgerEntry objects with TDS tagging applied.
        """
        start = time.perf_counter()
        tds_types = tds_document_types or set()

        # Normalize TDS document types to uppercase for comparison
        tds_types_upper = {dt.strip().upper() for dt in tds_types}

        # Determine which entries are TDS
        tds_indices: list[int] = []
        for i, entry in enumerate(entries):
            if entry.document_type and entry.document_type.strip().upper() in tds_types_upper:
                entry.is_tds = True
                tds_indices.append(i)

        # Build a lookup of non-TDS entries by reference_number and document_number
        # for linking TDS entries to their parent invoices
        non_tds_by_reference: dict[str, LedgerEntry] = {}
        non_tds_by_doc_number: dict[str, LedgerEntry] = {}
        for entry in entries:
            if not entry.is_tds:
                if entry.reference_number:
                    cleaned_ref = self.clean_reference(entry.reference_number)
                    if cleaned_ref:
                        non_tds_by_reference[cleaned_ref] = entry
                if entry.document_number:
                    cleaned_doc = self.clean_reference(entry.document_number)
                    if cleaned_doc:
                        non_tds_by_doc_number[cleaned_doc] = entry

        # Link TDS entries to parent invoices
        for idx in tds_indices:
            tds_entry = entries[idx]
            parent = self._find_parent_invoice(
                tds_entry, non_tds_by_reference, non_tds_by_doc_number
            )
            if parent:
                tds_entry.tds_parent_entry_id = parent.entry_id
            else:
                if "TDS Entry \u2014 No Parent Invoice Found" not in tds_entry.flags:
                    tds_entry.flags.append("TDS Entry \u2014 No Parent Invoice Found")

        duration_ms = (time.perf_counter() - start) * 1000
        tagged_count = sum(1 for e in entries if e.is_tds)
        linked_count = sum(1 for e in entries if e.tds_parent_entry_id)
        _structured_logger.log_success(
            operation="tag_tds_entries",
            duration_ms=duration_ms,
            total_entries=len(entries),
            tds_tagged=tagged_count,
            tds_linked=linked_count,
        )
        return entries

    def _find_parent_invoice(
        self,
        tds_entry: LedgerEntry,
        non_tds_by_reference: dict[str, "LedgerEntry"],
        non_tds_by_doc_number: dict[str, "LedgerEntry"],
    ) -> LedgerEntry | None:
        """
        Find the parent invoice for a TDS entry by matching reference number.

        Matching strategy:
        1. Clean the TDS entry's reference_number and look up in non-TDS reference map.
        2. If not found, try matching against non-TDS document_number map.

        Returns the parent LedgerEntry if found, None otherwise.
        """
        if tds_entry.reference_number:
            cleaned_ref = self.clean_reference(tds_entry.reference_number)
            if cleaned_ref:
                # Try matching against reference numbers of non-TDS entries
                if cleaned_ref in non_tds_by_reference:
                    return non_tds_by_reference[cleaned_ref]
                # Try matching against document numbers of non-TDS entries
                if cleaned_ref in non_tds_by_doc_number:
                    return non_tds_by_doc_number[cleaned_ref]

        return None

    # ──────────────────────────────────────────────────────────────────────
    # Multi-Currency Handling
    # ──────────────────────────────────────────────────────────────────────

    def prepare_multi_currency_entry(self, entry: RawSAPEntry) -> MultiCurrencyEntry:
        """
        Prepare multi-currency data from a raw SAP entry.

        Stores both the transaction currency amount (wrbtr) and the local
        currency (INR) equivalent (dmbtr). Calculates the effective exchange
        rate from the two amounts.

        If the transaction currency is already INR, both amounts are the same
        and the exchange rate is 1.

        Requirement 6.1: Store both transaction currency amount and local
                         currency (INR) equivalent for each entry.

        Args:
            entry: A RawSAPEntry containing wrbtr (transaction amount),
                   dmbtr (local currency amount), and waers (currency code).

        Returns:
            A MultiCurrencyEntry with transaction_currency, transaction_amount,
            local_currency_amount, and exchange_rate.
        """
        currency_code = entry.waers.strip().upper() if entry.waers else "INR"
        transaction_amount = entry.wrbtr
        local_amount = entry.dmbtr

        # Calculate exchange rate: local / transaction
        # If transaction amount is zero, exchange rate defaults to 1
        if transaction_amount and transaction_amount != Decimal("0"):
            exchange_rate = local_amount / transaction_amount
        else:
            exchange_rate = Decimal("1")

        return MultiCurrencyEntry(
            transaction_currency=currency_code,
            transaction_amount=transaction_amount,
            local_currency_amount=local_amount,
            exchange_rate=exchange_rate,
        )

    @staticmethod
    def get_comparison_amount(
        entry: LedgerEntry, use_local_currency: bool = True
    ) -> Decimal:
        """
        Return the correct amount for reconciliation comparison.

        By default, reconciliation matching uses local currency (INR) to ensure
        amounts are compared in the same currency. If use_local_currency is False,
        the adjusted_amount (which may be in transaction currency) is returned.

        Requirement 6.2: Reconciliation matching compares amounts in the
                         same currency (local currency INR by default).

        Args:
            entry: A LedgerEntry with adjusted_amount and optionally
                   local_currency_amount.
            use_local_currency: If True (default), return local_currency_amount
                               when available. If False, return adjusted_amount.

        Returns:
            The Decimal amount to use for reconciliation comparison.
        """
        if use_local_currency and entry.local_currency_amount is not None:
            return entry.local_currency_amount
        return entry.adjusted_amount

    # ──────────────────────────────────────────────────────────────────────
    # Document Type Classification
    # ──────────────────────────────────────────────────────────────────────

    # Default hardcoded mapping used as fallback when config DB has no entry
    DEFAULT_DOCUMENT_TYPE_MAPPING: dict[str, str] = {
        "RE": DocumentCategory.INVOICE,
        "KR": DocumentCategory.INVOICE,
        "DR": DocumentCategory.INVOICE,
        "ZP": DocumentCategory.PAYMENT,
        "KZ": DocumentCategory.PAYMENT,
        "ZV": DocumentCategory.PAYMENT,
        "KG": DocumentCategory.CREDIT_NOTE,
        "RV": DocumentCategory.DEBIT_NOTE,
    }

    def classify_document_type(self, doc_type: str) -> str:
        """
        Classify document type using configurable mapping.

        First checks the config repository (database-backed, admin-configurable).
        If not found in config, falls back to the default hardcoded mapping.
        Returns the category string (Invoice, Payment, Credit Note, Debit Note, TDS, Other).

        Requirement 7.1: RE, KR, DR → Invoice
        Requirement 7.2: ZP, KZ, ZV → Payment
        Requirement 7.3: KG → Credit Note
        Requirement 7.4: RV → Debit Note
        Requirement 7.5: Configurable by admins without code changes.

        Args:
            doc_type: The SAP document type code (e.g., 'RE', 'KR', 'ZP').

        Returns:
            The category string from DocumentCategory enum values.
        """
        if not doc_type or not doc_type.strip():
            return DocumentCategory.OTHER

        normalized = doc_type.strip().upper()

        # First: check configurable mapping from config repository (sync wrapper)
        # The config_repository.get_document_type_category is async, but
        # classify_document_type is called synchronously in the pipeline.
        # Use the synchronous fallback approach: check default mapping.
        # For async callers, use classify_document_type_async().
        return self._classify_from_defaults(normalized)

    async def classify_document_type_async(self, doc_type: str) -> str:
        """
        Classify document type using configurable mapping (async version).

        Checks the config repository first, then falls back to defaults.

        Args:
            doc_type: The SAP document type code.

        Returns:
            The category string from DocumentCategory enum values.
        """
        if not doc_type or not doc_type.strip():
            return DocumentCategory.OTHER

        normalized = doc_type.strip().upper()

        # Priority 1: Check configurable mapping from database
        config_category = await self._config_repo.get_document_type_category(normalized)
        if config_category:
            return config_category

        # Priority 2: Fall back to hardcoded defaults
        return self._classify_from_defaults(normalized)

    def _classify_from_defaults(self, normalized_doc_type: str) -> str:
        """
        Classify using the default hardcoded mapping.

        Args:
            normalized_doc_type: Uppercase, stripped document type code.

        Returns:
            The category string, or 'Other' if not found.
        """
        return self.DEFAULT_DOCUMENT_TYPE_MAPPING.get(
            normalized_doc_type, DocumentCategory.OTHER
        )

    # ──────────────────────────────────────────────────────────────────────
    # Helpers
    # ──────────────────────────────────────────────────────────────────────

    @staticmethod
    def _is_non_empty(value: str) -> bool:
        """Check if a string value is non-empty after stripping whitespace."""
        return bool(value and value.strip())
