"""
Mock SAP Adapter for Testing.

Returns realistic SAP ledger data matching the SAPAdapterInterface contract.
Supports both All Items and Open Items modes with deterministic seed-based
data generation for consistent testing.

Requirements: 8.3, 8.5
"""

from __future__ import annotations

import hashlib
import random
from datetime import date, timedelta
from decimal import Decimal

from src.domain.interfaces.sap_adapter_interface import SAPAdapterInterface, SAPLedgerEntry


# ──────────────────────────────────────────────────────────────────────────────
# Constants for realistic data generation
# ──────────────────────────────────────────────────────────────────────────────

# Document types with their SHKZG indicators and characteristics
# RE, KR = Invoice (credit to vendor → H)
# ZP, KZ = Payment (debit to vendor → S)
# KG = Credit Note (credit → H)
# RV = Debit Note (debit → S)
DOCUMENT_TYPE_CONFIG: dict[str, dict] = {
    "RE": {"shkzg": "H", "category": "Invoice", "weight": 30},
    "KR": {"shkzg": "H", "category": "Invoice", "weight": 15},
    "ZP": {"shkzg": "S", "category": "Payment", "weight": 20},
    "KZ": {"shkzg": "S", "category": "Payment", "weight": 15},
    "KG": {"shkzg": "H", "category": "Credit Note", "weight": 10},
    "RV": {"shkzg": "S", "category": "Debit Note", "weight": 10},
}

# Weighted list for random selection
_DOC_TYPES_WEIGHTED: list[str] = []
for _dt, _cfg in DOCUMENT_TYPE_CONFIG.items():
    _DOC_TYPES_WEIGHTED.extend([_dt] * _cfg["weight"])

# Currency distribution (mostly INR, some foreign)
CURRENCY_CONFIG: list[tuple[str, int]] = [
    ("INR", 85),
    ("USD", 10),
    ("EUR", 5),
]

_CURRENCIES_WEIGHTED: list[str] = []
for _cur, _weight in CURRENCY_CONFIG:
    _CURRENCIES_WEIGHTED.extend([_cur] * _weight)

# Amount ranges in INR (₹10,000 to ₹10,00,000)
MIN_AMOUNT = Decimal("10000")
MAX_AMOUNT = Decimal("1000000")

# Sample text descriptions for sgtxt field
SAMPLE_TEXTS: list[str] = [
    "Invoice for raw materials",
    "Payment against invoice",
    "Credit note - quality adjustment",
    "Debit note - short shipment",
    "Service charges Q{quarter}",
    "Material purchase - PO {po}",
    "Advance payment",
    "Final settlement",
    "TDS deduction",
    "Freight charges",
]


# ──────────────────────────────────────────────────────────────────────────────
# Mock SAP Adapter
# ──────────────────────────────────────────────────────────────────────────────


class MockSAPAdapter(SAPAdapterInterface):
    """
    Test adapter returning realistic SAP data shapes.

    Generates deterministic data based on a seed derived from the input parameters
    (vendor_code, company_code, dates). This ensures consistent results for the
    same query parameters across test runs.

    Features:
    - Mix of document types (RE, KR, ZP, KZ, KG, RV)
    - Proper SHKZG indicators (H for invoices/credit notes, S for payments/debit notes)
    - Realistic amount ranges (₹10,000 - ₹10,00,000)
    - ZUONR, XBLNR fields populated for invoice types
    - AUGBL populated for payment types (cleared items)
    - Various currency codes (mostly INR, some USD/EUR)
    - Dates within the requested date range
    - Deterministic output (seed-based) for consistent testing
    """

    def __init__(self, entry_count: int = 25, seed: int | None = None) -> None:
        """
        Initialize MockSAPAdapter.

        Args:
            entry_count: Number of entries to generate per pull (default: 25).
            seed: Optional fixed seed for reproducibility. If None, a seed is
                derived from query parameters for deterministic results.
        """
        self._entry_count = entry_count
        self._fixed_seed = seed

    async def pull_all_items(
        self,
        vendor_code: str,
        company_code: str,
        date_from: date,
        date_to: date,
        doc_type_filters: list[str] | None = None,
    ) -> list[SAPLedgerEntry]:
        """
        Pull all items (cleared and open) from mock SAP data.

        Returns a mix of cleared and uncleared entries within the date range.
        Approximately 60% of entries will have clearing documents (augbl populated).

        Args:
            vendor_code: SAP vendor number (LIFNR).
            company_code: SAP company code (BUKRS).
            date_from: Start of posting date range.
            date_to: End of posting date range.
            doc_type_filters: Optional list of document types to filter.

        Returns:
            List of SAPLedgerEntry objects (both cleared and uncleared).
        """
        seed = self._compute_seed(vendor_code, company_code, str(date_from), str(date_to), "all")
        rng = random.Random(seed)

        entries = self._generate_entries(
            rng=rng,
            vendor_code=vendor_code,
            company_code=company_code,
            date_from=date_from,
            date_to=date_to,
            include_cleared=True,
            clearing_ratio=0.6,
        )

        if doc_type_filters:
            entries = [e for e in entries if e.blart in doc_type_filters]

        return entries

    async def pull_open_items(
        self,
        vendor_code: str,
        company_code: str,
        key_date: date,
        doc_type_filters: list[str] | None = None,
    ) -> list[SAPLedgerEntry]:
        """
        Pull only uncleared (open) items from mock SAP data.

        Returns entries where augbl is empty (not cleared as of key_date).

        Args:
            vendor_code: SAP vendor number (LIFNR).
            company_code: SAP company code (BUKRS).
            key_date: Reference date for open item status.
            doc_type_filters: Optional list of document types to filter.

        Returns:
            List of SAPLedgerEntry objects with empty augbl (uncleared only).
        """
        seed = self._compute_seed(vendor_code, company_code, str(key_date), "", "open")
        rng = random.Random(seed)

        # Generate entries up to the key_date, then return only uncleared
        date_from = key_date - timedelta(days=180)
        entries = self._generate_entries(
            rng=rng,
            vendor_code=vendor_code,
            company_code=company_code,
            date_from=date_from,
            date_to=key_date,
            include_cleared=False,
            clearing_ratio=0.0,
        )

        # Ensure all entries have empty augbl (open items only)
        for entry in entries:
            entry.augbl = ""
            entry.augdt = ""

        if doc_type_filters:
            entries = [e for e in entries if e.blart in doc_type_filters]

        return entries

    # ──────────────────────────────────────────────────────────────────────────
    # Private helpers
    # ──────────────────────────────────────────────────────────────────────────

    def _compute_seed(self, *args: str) -> int:
        """
        Compute a deterministic seed from query parameters.

        If a fixed seed was provided at construction, use that instead.
        """
        if self._fixed_seed is not None:
            return self._fixed_seed

        combined = "|".join(args)
        hash_digest = hashlib.md5(combined.encode()).hexdigest()  # noqa: S324
        return int(hash_digest[:8], 16)

    def _generate_entries(
        self,
        rng: random.Random,
        vendor_code: str,
        company_code: str,
        date_from: date,
        date_to: date,
        include_cleared: bool,
        clearing_ratio: float,
    ) -> list[SAPLedgerEntry]:
        """
        Generate a list of realistic SAP ledger entries.

        Args:
            rng: Seeded random number generator.
            vendor_code: Vendor code to set on entries.
            company_code: Company code to set on entries.
            date_from: Earliest posting date.
            date_to: Latest posting date.
            include_cleared: Whether to include cleared entries.
            clearing_ratio: Proportion of entries that should be cleared (0.0-1.0).

        Returns:
            List of generated SAPLedgerEntry objects.
        """
        entries: list[SAPLedgerEntry] = []
        date_range_days = max((date_to - date_from).days, 1)

        for i in range(self._entry_count):
            doc_type = rng.choice(_DOC_TYPES_WEIGHTED)
            config = DOCUMENT_TYPE_CONFIG[doc_type]
            shkzg = config["shkzg"]

            # Generate posting date within range
            days_offset = rng.randint(0, date_range_days)
            posting_date = date_from + timedelta(days=days_offset)

            # Document date is typically same as or slightly before posting date
            doc_date_offset = rng.randint(0, 3)
            document_date = posting_date - timedelta(days=doc_date_offset)

            # Generate realistic amount
            amount = self._generate_amount(rng)

            # Currency selection
            currency = rng.choice(_CURRENCIES_WEIGHTED)

            # For foreign currencies, local amount differs
            local_amount = amount
            if currency != "INR":
                # Simulate exchange rate
                if currency == "USD":
                    local_amount = amount * Decimal("83.50")
                elif currency == "EUR":
                    local_amount = amount * Decimal("90.75")
                local_amount = local_amount.quantize(Decimal("0.01"))

            # Document number: 10-digit numeric
            doc_number = str(1000000000 + rng.randint(0, 999999999))

            # Fiscal year from posting date
            fiscal_year = str(posting_date.year)

            # Line item (typically 001-005)
            line_item = f"{rng.randint(1, 5):03d}"

            # Reference fields - populated based on document type
            zuonr = ""
            xblnr = ""
            if config["category"] == "Invoice":
                # Invoices typically have ZUONR and XBLNR
                zuonr = self._generate_reference_number(rng, "INV")
                xblnr = self._generate_reference_number(rng, "REF")
            elif config["category"] == "Credit Note":
                # Credit notes usually have ZUONR
                zuonr = self._generate_reference_number(rng, "CN")
            elif config["category"] == "Debit Note":
                # Debit notes usually have XBLNR
                xblnr = self._generate_reference_number(rng, "DN")

            # Clearing information
            augbl = ""
            augdt = ""
            if include_cleared and rng.random() < clearing_ratio:
                # Clearing date is after posting date
                clear_offset = rng.randint(1, 45)
                clearing_date = posting_date + timedelta(days=clear_offset)
                if clearing_date <= date_to:
                    augbl = str(2000000000 + rng.randint(0, 999999999))
                    augdt = clearing_date.strftime("%Y%m%d")

            # Text description
            text_template = rng.choice(SAMPLE_TEXTS)
            sgtxt = text_template.format(
                quarter=((posting_date.month - 1) // 3) + 1,
                po=f"PO-{rng.randint(4500000, 4599999)}",
            )

            entry = SAPLedgerEntry(
                belnr=doc_number,
                gjahr=fiscal_year,
                buzei=line_item,
                budat=posting_date.strftime("%Y%m%d"),
                bldat=document_date.strftime("%Y%m%d"),
                blart=doc_type,
                dmbtr=local_amount,
                wrbtr=amount,
                waers=currency,
                shkzg=shkzg,
                zuonr=zuonr,
                xblnr=xblnr,
                augbl=augbl,
                augdt=augdt,
                lifnr=vendor_code,
                bukrs=company_code,
                sgtxt=sgtxt,
            )
            entries.append(entry)

        return entries

    def _generate_amount(self, rng: random.Random) -> Decimal:
        """
        Generate a realistic amount between ₹10,000 and ₹10,00,000.

        Uses a log-normal-like distribution to produce more small/medium
        amounts with occasional large ones (realistic business pattern).
        """
        # Generate a value between 0 and 1 with bias toward lower values
        raw = rng.random() ** 0.7  # Slight bias toward smaller amounts
        amount_range = MAX_AMOUNT - MIN_AMOUNT
        amount = MIN_AMOUNT + (amount_range * Decimal(str(raw)))
        # Round to 2 decimal places
        return amount.quantize(Decimal("0.01"))

    def _generate_reference_number(self, rng: random.Random, prefix: str) -> str:
        """
        Generate a realistic reference number with optional leading zeros
        and special characters (to test CLEAN function).

        Examples:
            "00INV2024001234"
            "  REF/2024/5678  "
            "CN-2024-9012"
        """
        number = rng.randint(100000, 9999999)
        year = rng.choice([2023, 2024, 2025])

        # Vary the format to test CLEAN function robustness
        format_choice = rng.randint(1, 5)
        if format_choice == 1:
            # Leading zeros
            return f"00{prefix}{year}{number:07d}"
        elif format_choice == 2:
            # Surrounding whitespace
            return f"  {prefix}/{year}/{number}  "
        elif format_choice == 3:
            # Hyphens
            return f"{prefix}-{year}-{number}"
        elif format_choice == 4:
            # Slash separator
            return f"{prefix}/{year}/{number}"
        else:
            # Plain format
            return f"{prefix}{year}{number}"
