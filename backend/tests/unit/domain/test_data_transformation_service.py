"""
Unit tests for DataTransformationService.

Tests invoice number derivation (ZUONR > XBLNR > BELNR priority fallback)
and the CLEAN function (strip leading zeros, special characters, whitespace).

Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 2.1, 2.2, 2.3, 2.4, 3.1, 3.2, 3.3, 4.1, 4.2, 4.3
"""

from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.domain.repositories.vlr.config_repository import IConfigRepository
from src.domain.services.vlr.data_transformation_service import (
    DEFAULT_SPECIAL_CHARACTERS,
    DataTransformationService,
    DerivedInvoice,
    DocumentCategory,
    InvoiceSourceField,
    INVOICE_DOC_TYPES,
    JOURNAL_DOC_TYPES,
    LedgerEntry,
    MultiCurrencyEntry,
    PAYMENT_DOC_TYPES,
    RawSAPEntry,
)


# ──────────────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_config_repo():
    """Create a mock IConfigRepository."""
    repo = MagicMock(spec=IConfigRepository)
    repo.get_clean_special_characters = AsyncMock(
        return_value=DEFAULT_SPECIAL_CHARACTERS
    )
    repo.get_document_type_category = AsyncMock(return_value=None)
    repo.is_tds_document_type = AsyncMock(return_value=False)
    return repo


@pytest.fixture
def service(mock_config_repo):
    """Create a DataTransformationService instance."""
    return DataTransformationService(config_repository=mock_config_repo)


# ──────────────────────────────────────────────────────────────────────────────
# Tests: clean_reference()
# ──────────────────────────────────────────────────────────────────────────────


class TestCleanReference:
    """Tests for the CLEAN function implementation."""

    def test_strips_leading_and_trailing_whitespace(self, service):
        """CLEAN trims leading/trailing spaces."""
        assert service.clean_reference("  ABC123  ") == "ABC123"

    def test_converts_to_uppercase(self, service):
        """CLEAN converts to uppercase."""
        assert service.clean_reference("abc123") == "ABC123"

    def test_removes_leading_zeros(self, service):
        """CLEAN removes leading zeros."""
        assert service.clean_reference("000123") == "123"

    def test_removes_default_special_characters(self, service):
        """CLEAN removes /, \\, -, _ by default."""
        assert service.clean_reference("INV/2024-001_A") == "INV2024001A"

    def test_removes_backslash(self, service):
        """CLEAN removes backslash characters."""
        assert service.clean_reference("INV\\2024") == "INV2024"

    def test_combined_clean_operations(self, service):
        """CLEAN applies all operations: whitespace, uppercase, special chars, leading zeros."""
        assert service.clean_reference("  00123/abc-def_  ") == "123ABCDEF"

    def test_empty_string_returns_empty(self, service):
        """CLEAN returns empty string for empty input."""
        assert service.clean_reference("") == ""

    def test_none_like_empty_returns_empty(self, service):
        """CLEAN handles whitespace-only input."""
        assert service.clean_reference("   ") == ""

    def test_all_zeros_returns_empty(self, service):
        """CLEAN removes all leading zeros resulting in empty string."""
        assert service.clean_reference("0000") == ""

    def test_custom_special_characters(self, service):
        """CLEAN accepts custom special character list."""
        result = service.clean_reference("INV#2024@001", special_chars=["#", "@"])
        assert result == "INV2024001"

    def test_preserves_alphanumeric_content(self, service):
        """CLEAN preserves alphanumeric characters."""
        assert service.clean_reference("INV2024001") == "INV2024001"

    def test_single_character_after_clean(self, service):
        """CLEAN handles single meaningful character after stripping."""
        assert service.clean_reference("000A") == "A"

    def test_special_chars_only_returns_empty(self, service):
        """CLEAN with only special characters returns empty."""
        assert service.clean_reference("/-\\_") == ""


# ──────────────────────────────────────────────────────────────────────────────
# Tests: derive_invoice_number() - Priority Fallback
# ──────────────────────────────────────────────────────────────────────────────


class TestDeriveInvoiceNumber:
    """Tests for invoice number derivation with ZUONR > XBLNR > BELNR priority."""

    def test_uses_zuonr_as_primary_source(self, service):
        """Requirement 1.1: ZUONR is primary source for invoice number."""
        entry = RawSAPEntry(
            zuonr="INV001",
            xblnr="REF002",
            belnr="5000001",
            gjahr="2024",
            blart="RE",
        )
        result = service.derive_invoice_number(entry)

        assert result.source_field == InvoiceSourceField.ZUONR
        assert result.raw_value == "INV001"
        assert result.invoice_number == "INV001"

    def test_falls_back_to_xblnr_when_zuonr_empty(self, service):
        """Requirement 1.2: XBLNR is secondary when ZUONR is empty."""
        entry = RawSAPEntry(
            zuonr="",
            xblnr="REF002",
            belnr="5000001",
            gjahr="2024",
            blart="RE",
        )
        result = service.derive_invoice_number(entry)

        assert result.source_field == InvoiceSourceField.XBLNR
        assert result.raw_value == "REF002"
        assert result.invoice_number == "REF002"

    def test_falls_back_to_xblnr_when_zuonr_whitespace(self, service):
        """Requirement 1.2: XBLNR used when ZUONR is whitespace-only."""
        entry = RawSAPEntry(
            zuonr="   ",
            xblnr="REF002",
            belnr="5000001",
            gjahr="2024",
            blart="KR",
        )
        result = service.derive_invoice_number(entry)

        assert result.source_field == InvoiceSourceField.XBLNR
        assert result.raw_value == "REF002"

    def test_falls_back_to_belnr_when_zuonr_and_xblnr_empty(self, service):
        """Requirement 1.3: BELNR is tertiary when both ZUONR and XBLNR empty."""
        entry = RawSAPEntry(
            zuonr="",
            xblnr="",
            belnr="5000001",
            gjahr="2024",
            blart="RE",
        )
        result = service.derive_invoice_number(entry)

        assert result.source_field == InvoiceSourceField.BELNR
        assert result.raw_value == "5000001/2024"
        assert "Invoice Number Not Found — Using Doc Number" in result.flags

    def test_belnr_fallback_stores_belnr_slash_gjahr(self, service):
        """BRD: BELNR stored as BELNR + '/' + GJAHR."""
        entry = RawSAPEntry(
            zuonr="",
            xblnr="",
            belnr="1234567890",
            gjahr="2024",
            blart="DR",
        )
        result = service.derive_invoice_number(entry)

        assert result.raw_value == "1234567890/2024"
        # After CLEAN: removes '/' → "12345678902024"
        assert result.invoice_number == "12345678902024"

    def test_belnr_without_gjahr(self, service):
        """BELNR used alone when GJAHR is empty."""
        entry = RawSAPEntry(
            zuonr="",
            xblnr="",
            belnr="5000001",
            gjahr="",
            blart="RE",
        )
        result = service.derive_invoice_number(entry)

        assert result.raw_value == "5000001"
        assert result.source_field == InvoiceSourceField.BELNR

    def test_all_sources_empty_returns_none(self, service):
        """All sources empty results in null invoice_number."""
        entry = RawSAPEntry(
            zuonr="",
            xblnr="",
            belnr="",
            gjahr="",
            blart="RE",
        )
        result = service.derive_invoice_number(entry)

        assert result.invoice_number is None
        assert result.raw_value is None
        assert result.source_field is None
        assert "Invoice Number Not Found — All Sources Empty" in result.flags

    def test_applies_clean_function_to_zuonr(self, service):
        """Requirement 1.4: CLEAN applied to ZUONR-derived value."""
        entry = RawSAPEntry(
            zuonr="  00INV/2024-001  ",
            xblnr="",
            belnr="",
            gjahr="",
            blart="RE",
        )
        result = service.derive_invoice_number(entry)

        assert result.invoice_number == "INV2024001"
        assert result.raw_value == "00INV/2024-001"

    def test_applies_clean_function_to_xblnr(self, service):
        """Requirement 1.4: CLEAN applied to XBLNR-derived value."""
        entry = RawSAPEntry(
            zuonr="",
            xblnr="  00REF-123_ABC  ",
            belnr="",
            gjahr="",
            blart="KR",
        )
        result = service.derive_invoice_number(entry)

        assert result.invoice_number == "REF123ABC"
        assert result.raw_value == "00REF-123_ABC"

    def test_stores_raw_value_preserving_original(self, service):
        """Requirement 1.5: Raw value is preserved alongside cleaned value."""
        entry = RawSAPEntry(
            zuonr="  00123/ABC  ",
            xblnr="",
            belnr="",
            gjahr="",
            blart="RE",
        )
        result = service.derive_invoice_number(entry)

        # Raw value has leading/trailing spaces stripped but content preserved
        assert result.raw_value == "00123/ABC"
        # Cleaned value has zeros, special chars removed, uppercased
        assert result.invoice_number == "123ABC"


# ──────────────────────────────────────────────────────────────────────────────
# Tests: derive_invoice_number() - Payment Documents
# ──────────────────────────────────────────────────────────────────────────────


class TestDeriveInvoiceNumberPayments:
    """Tests for payment document types (ZP, KZ, ZV)."""

    @pytest.mark.parametrize("doc_type", ["ZP", "KZ", "ZV"])
    def test_payment_docs_have_null_invoice_number(self, service, doc_type):
        """BRD: Payment docs (ZP, KZ, ZV) → invoice_number = NULL."""
        entry = RawSAPEntry(
            zuonr="INV001",
            xblnr="REF002",
            belnr="5000001",
            gjahr="2024",
            blart=doc_type,
            augbl="7000001",
        )
        result = service.derive_invoice_number(entry)

        assert result.invoice_number is None

    @pytest.mark.parametrize("doc_type", ["ZP", "KZ", "ZV"])
    def test_payment_docs_use_augbl_as_payment_reference(self, service, doc_type):
        """BRD: Payment docs use ClearingDocument (AUGBL) as payment_reference."""
        entry = RawSAPEntry(
            zuonr="INV001",
            xblnr="REF002",
            belnr="5000001",
            gjahr="2024",
            blart=doc_type,
            augbl="7000001",
        )
        result = service.derive_invoice_number(entry)

        assert result.payment_reference == "7000001"

    def test_payment_doc_with_empty_augbl(self, service):
        """Payment doc with no AUGBL returns None for payment_reference."""
        entry = RawSAPEntry(
            zuonr="INV001",
            xblnr="REF002",
            belnr="5000001",
            gjahr="2024",
            blart="ZP",
            augbl="",
        )
        result = service.derive_invoice_number(entry)

        assert result.payment_reference is None
        assert result.raw_value is None


# ──────────────────────────────────────────────────────────────────────────────
# Tests: derive_invoice_number() - Journal Entries
# ──────────────────────────────────────────────────────────────────────────────


class TestDeriveInvoiceNumberJournals:
    """Tests for journal entry document types (AB, SA)."""

    @pytest.mark.parametrize("doc_type", ["AB", "SA"])
    def test_journal_entries_have_null_invoice_number(self, service, doc_type):
        """BRD: Journal entries (AB, SA) → invoice_number = NULL."""
        entry = RawSAPEntry(
            zuonr="INV001",
            xblnr="REF002",
            belnr="5000001",
            gjahr="2024",
            blart=doc_type,
        )
        result = service.derive_invoice_number(entry)

        assert result.invoice_number is None

    @pytest.mark.parametrize("doc_type", ["AB", "SA"])
    def test_journal_entries_flagged_for_manual_review(self, service, doc_type):
        """BRD: Journal entries flagged as 'Manual Review Required'."""
        entry = RawSAPEntry(
            zuonr="INV001",
            xblnr="REF002",
            belnr="5000001",
            gjahr="2024",
            blart=doc_type,
        )
        result = service.derive_invoice_number(entry)

        assert "Journal Entry — Manual Review Required" in result.flags


# ──────────────────────────────────────────────────────────────────────────────
# Tests: derive_invoice_number() - Credit/Debit Notes
# ──────────────────────────────────────────────────────────────────────────────


class TestDeriveInvoiceNumberCreditDebitNotes:
    """Tests for credit/debit note document types (KG, RV)."""

    @pytest.mark.parametrize("doc_type", ["KG", "RV"])
    def test_credit_debit_notes_use_same_logic_as_invoices(self, service, doc_type):
        """BRD: Credit/Debit Notes (KG, RV) use same ZUONR > XBLNR > BELNR logic."""
        entry = RawSAPEntry(
            zuonr="CN001",
            xblnr="REF002",
            belnr="5000001",
            gjahr="2024",
            blart=doc_type,
        )
        result = service.derive_invoice_number(entry)

        assert result.source_field == InvoiceSourceField.ZUONR
        assert result.invoice_number == "CN001"

    @pytest.mark.parametrize("doc_type", ["KG", "RV"])
    def test_credit_debit_notes_fallback_to_xblnr(self, service, doc_type):
        """Credit/Debit Notes fall back to XBLNR when ZUONR empty."""
        entry = RawSAPEntry(
            zuonr="",
            xblnr="REF999",
            belnr="5000001",
            gjahr="2024",
            blart=doc_type,
        )
        result = service.derive_invoice_number(entry)

        assert result.source_field == InvoiceSourceField.XBLNR
        assert result.invoice_number == "REF999"


# ──────────────────────────────────────────────────────────────────────────────
# Tests: derive_invoice_number() - Case insensitive doc types
# ──────────────────────────────────────────────────────────────────────────────


class TestDeriveInvoiceNumberCaseInsensitive:
    """Verify doc type handling is case insensitive."""

    def test_lowercase_doc_type_recognized(self, service):
        """Lowercase doc types are handled correctly."""
        entry = RawSAPEntry(
            zuonr="INV001",
            blart="re",
        )
        result = service.derive_invoice_number(entry)

        assert result.source_field == InvoiceSourceField.ZUONR
        assert result.invoice_number == "INV001"

    def test_mixed_case_payment_doc_type(self, service):
        """Mixed case payment doc types work correctly."""
        entry = RawSAPEntry(
            zuonr="INV001",
            blart="Zp",
            augbl="7000001",
        )
        result = service.derive_invoice_number(entry)

        assert result.invoice_number is None
        assert result.payment_reference == "7000001"


# ──────────────────────────────────────────────────────────────────────────────
# Tests: apply_sign_adjustment()
# ──────────────────────────────────────────────────────────────────────────────


class TestSignAdjustment:
    """Tests for sign adjustment logic (SHKZG indicator).

    Requirements: 2.1, 2.2, 2.3, 2.4
    """

    # ── Requirement 2.1: H (credit) → positive ──

    def test_h_indicator_returns_positive(self, service):
        """Requirement 2.1: SHKZG = 'H' makes amount positive."""
        result = service.apply_sign_adjustment(Decimal("100.50"), "H")
        assert result == Decimal("100.50")
        assert result > 0

    def test_h_indicator_with_already_positive_amount(self, service):
        """H indicator preserves already positive amount."""
        result = service.apply_sign_adjustment(Decimal("250.00"), "H")
        assert result == Decimal("250.00")

    def test_h_indicator_with_negative_input(self, service):
        """H indicator converts negative input to positive (ABS)."""
        result = service.apply_sign_adjustment(Decimal("-100.50"), "H")
        assert result == Decimal("100.50")
        assert result > 0

    # ── Requirement 2.2: S (debit) → negative ──

    def test_s_indicator_returns_negative(self, service):
        """Requirement 2.2: SHKZG = 'S' makes amount negative."""
        result = service.apply_sign_adjustment(Decimal("100.50"), "S")
        assert result == Decimal("-100.50")
        assert result < 0

    def test_s_indicator_with_already_negative_input(self, service):
        """S indicator keeps negative sign (-1 * ABS)."""
        result = service.apply_sign_adjustment(Decimal("-200.00"), "S")
        assert result == Decimal("-200.00")
        assert result < 0

    # ── Case insensitivity ──

    def test_lowercase_h_treated_as_credit(self, service):
        """Lowercase 'h' is recognized as credit."""
        result = service.apply_sign_adjustment(Decimal("50.00"), "h")
        assert result == Decimal("50.00")

    def test_lowercase_s_treated_as_debit(self, service):
        """Lowercase 's' is recognized as debit."""
        result = service.apply_sign_adjustment(Decimal("50.00"), "s")
        assert result == Decimal("-50.00")

    def test_whitespace_padded_indicator(self, service):
        """Indicator with surrounding whitespace is handled."""
        result = service.apply_sign_adjustment(Decimal("75.00"), "  H  ")
        assert result == Decimal("75.00")

    # ── Zero amount ──

    def test_zero_amount_with_h_indicator(self, service):
        """Zero amount with H stays zero (positive zero)."""
        result = service.apply_sign_adjustment(Decimal("0"), "H")
        assert result == Decimal("0")

    def test_zero_amount_with_s_indicator(self, service):
        """Zero amount with S stays zero (negative zero equals zero)."""
        result = service.apply_sign_adjustment(Decimal("0"), "S")
        assert result == Decimal("0")

    # ── Edge cases: invalid/empty SHKZG ──

    def test_empty_shkzg_raises_value_error(self, service):
        """Empty SHKZG raises ValueError."""
        with pytest.raises(ValueError, match="SHKZG indicator is required"):
            service.apply_sign_adjustment(Decimal("100.00"), "")

    def test_whitespace_only_shkzg_raises_value_error(self, service):
        """Whitespace-only SHKZG raises ValueError."""
        with pytest.raises(ValueError, match="SHKZG indicator is required"):
            service.apply_sign_adjustment(Decimal("100.00"), "   ")

    def test_unrecognized_shkzg_raises_value_error(self, service):
        """Unrecognized SHKZG value raises ValueError."""
        with pytest.raises(ValueError, match="Unrecognized SHKZG indicator"):
            service.apply_sign_adjustment(Decimal("100.00"), "X")

    # ── Requirement 2.4: Original amount preserved (interface contract) ──

    def test_original_amount_not_mutated(self, service):
        """The original Decimal object is not mutated by sign adjustment."""
        original = Decimal("500.25")
        _ = service.apply_sign_adjustment(original, "S")
        # Original remains unchanged (Decimal is immutable, but verify contract)
        assert original == Decimal("500.25")

    def test_precision_preserved(self, service):
        """Decimal precision is maintained through sign adjustment."""
        result = service.apply_sign_adjustment(Decimal("1234.5678"), "H")
        assert result == Decimal("1234.5678")

        result_neg = service.apply_sign_adjustment(Decimal("1234.5678"), "S")
        assert result_neg == Decimal("-1234.5678")



# ──────────────────────────────────────────────────────────────────────────────
# Tests: calculate_opening_balance()
# ──────────────────────────────────────────────────────────────────────────────


class TestOpeningBalance:
    """Tests for opening balance calculation.

    Requirements: 3.1, 3.2, 3.3
    """

    def test_sums_entries_before_period_start(self, service):
        """Requirement 3.1: Opening balance = sum of entries with posting_date < period_start."""
        entries = [
            LedgerEntry(posting_date=date(2024, 1, 15), adjusted_amount=Decimal("100.00"), side="company"),
            LedgerEntry(posting_date=date(2024, 2, 10), adjusted_amount=Decimal("200.00"), side="company"),
            LedgerEntry(posting_date=date(2024, 3, 1), adjusted_amount=Decimal("50.00"), side="company"),  # NOT included (period start)
        ]
        result = service.calculate_opening_balance(entries, date(2024, 3, 1), "company")
        assert result == Decimal("300.00")

    def test_excludes_entries_on_period_start_date(self, service):
        """Entries on the period start date are NOT included in opening balance."""
        entries = [
            LedgerEntry(posting_date=date(2024, 3, 1), adjusted_amount=Decimal("500.00"), side="company"),
        ]
        result = service.calculate_opening_balance(entries, date(2024, 3, 1), "company")
        assert result == Decimal("0")

    def test_excludes_entries_after_period_start(self, service):
        """Entries after period start are excluded from opening balance."""
        entries = [
            LedgerEntry(posting_date=date(2024, 1, 10), adjusted_amount=Decimal("100.00"), side="company"),
            LedgerEntry(posting_date=date(2024, 5, 15), adjusted_amount=Decimal("999.00"), side="company"),
        ]
        result = service.calculate_opening_balance(entries, date(2024, 3, 1), "company")
        assert result == Decimal("100.00")

    def test_filters_by_side_company(self, service):
        """Requirement 3.3: Separate balances by side — company only."""
        entries = [
            LedgerEntry(posting_date=date(2024, 1, 10), adjusted_amount=Decimal("100.00"), side="company"),
            LedgerEntry(posting_date=date(2024, 1, 15), adjusted_amount=Decimal("200.00"), side="vendor"),
            LedgerEntry(posting_date=date(2024, 2, 1), adjusted_amount=Decimal("50.00"), side="company"),
        ]
        result = service.calculate_opening_balance(entries, date(2024, 3, 1), "company")
        assert result == Decimal("150.00")

    def test_filters_by_side_vendor(self, service):
        """Requirement 3.3: Separate balances by side — vendor only."""
        entries = [
            LedgerEntry(posting_date=date(2024, 1, 10), adjusted_amount=Decimal("100.00"), side="company"),
            LedgerEntry(posting_date=date(2024, 1, 15), adjusted_amount=Decimal("200.00"), side="vendor"),
            LedgerEntry(posting_date=date(2024, 2, 1), adjusted_amount=Decimal("50.00"), side="vendor"),
        ]
        result = service.calculate_opening_balance(entries, date(2024, 3, 1), "vendor")
        assert result == Decimal("250.00")

    def test_handles_mixed_positive_and_negative_amounts(self, service):
        """Opening balance correctly sums positive (H) and negative (S) entries."""
        entries = [
            LedgerEntry(posting_date=date(2024, 1, 5), adjusted_amount=Decimal("1000.00"), side="company"),
            LedgerEntry(posting_date=date(2024, 1, 10), adjusted_amount=Decimal("-300.00"), side="company"),
            LedgerEntry(posting_date=date(2024, 2, 20), adjusted_amount=Decimal("-200.00"), side="company"),
        ]
        result = service.calculate_opening_balance(entries, date(2024, 3, 1), "company")
        assert result == Decimal("500.00")

    def test_empty_entries_returns_zero(self, service):
        """No entries results in zero opening balance."""
        result = service.calculate_opening_balance([], date(2024, 3, 1), "company")
        assert result == Decimal("0")

    def test_no_entries_before_period_start_returns_zero(self, service):
        """All entries on or after period start results in zero opening balance."""
        entries = [
            LedgerEntry(posting_date=date(2024, 3, 1), adjusted_amount=Decimal("100.00"), side="company"),
            LedgerEntry(posting_date=date(2024, 4, 1), adjusted_amount=Decimal("200.00"), side="company"),
        ]
        result = service.calculate_opening_balance(entries, date(2024, 3, 1), "company")
        assert result == Decimal("0")

    def test_item_posted_before_period_cleared_within_period_still_counts(self, service):
        """
        Requirement 3.2: Items posted before period start that were cleared
        within the period still count in opening balance (they were open at period start).
        Clearing date is NOT used for eligibility — posting date is.
        """
        entries = [
            LedgerEntry(
                posting_date=date(2024, 1, 15),
                adjusted_amount=Decimal("750.00"),
                side="company",
                clearing_date=date(2024, 4, 10),  # Cleared WITHIN the period
            ),
        ]
        result = service.calculate_opening_balance(entries, date(2024, 3, 1), "company")
        assert result == Decimal("750.00")


# ──────────────────────────────────────────────────────────────────────────────
# Tests: calculate_closing_balance()
# ──────────────────────────────────────────────────────────────────────────────


class TestClosingBalance:
    """Tests for closing balance calculation.

    Requirements: 4.1, 4.2, 4.3
    """

    def test_closing_equals_opening_plus_net_movement(self, service):
        """Requirement 4.1: closing = opening + net movement during period."""
        entries = [
            LedgerEntry(posting_date=date(2024, 3, 5), adjusted_amount=Decimal("200.00"), side="company"),
            LedgerEntry(posting_date=date(2024, 3, 15), adjusted_amount=Decimal("-50.00"), side="company"),
        ]
        opening = Decimal("300.00")
        result = service.calculate_closing_balance(
            opening, entries, date(2024, 3, 1), date(2024, 3, 31), side="company"
        )
        # 300 + (200 - 50) = 450
        assert result == Decimal("450.00")

    def test_net_movement_includes_entries_on_period_start(self, service):
        """Period entries include those on the start date (inclusive)."""
        entries = [
            LedgerEntry(posting_date=date(2024, 3, 1), adjusted_amount=Decimal("100.00"), side="company"),
        ]
        opening = Decimal("0")
        result = service.calculate_closing_balance(
            opening, entries, date(2024, 3, 1), date(2024, 3, 31), side="company"
        )
        assert result == Decimal("100.00")

    def test_net_movement_includes_entries_on_period_end(self, service):
        """Period entries include those on the end date (inclusive)."""
        entries = [
            LedgerEntry(posting_date=date(2024, 3, 31), adjusted_amount=Decimal("100.00"), side="company"),
        ]
        opening = Decimal("50.00")
        result = service.calculate_closing_balance(
            opening, entries, date(2024, 3, 1), date(2024, 3, 31), side="company"
        )
        assert result == Decimal("150.00")

    def test_excludes_entries_before_period(self, service):
        """Entries before period start are not counted in net movement."""
        entries = [
            LedgerEntry(posting_date=date(2024, 2, 28), adjusted_amount=Decimal("999.00"), side="company"),
            LedgerEntry(posting_date=date(2024, 3, 5), adjusted_amount=Decimal("100.00"), side="company"),
        ]
        opening = Decimal("200.00")
        result = service.calculate_closing_balance(
            opening, entries, date(2024, 3, 1), date(2024, 3, 31), side="company"
        )
        # 200 + 100 = 300 (not 999)
        assert result == Decimal("300.00")

    def test_excludes_entries_after_period(self, service):
        """Entries after period end are not counted in net movement."""
        entries = [
            LedgerEntry(posting_date=date(2024, 3, 15), adjusted_amount=Decimal("100.00"), side="company"),
            LedgerEntry(posting_date=date(2024, 4, 1), adjusted_amount=Decimal("999.00"), side="company"),
        ]
        opening = Decimal("200.00")
        result = service.calculate_closing_balance(
            opening, entries, date(2024, 3, 1), date(2024, 3, 31), side="company"
        )
        assert result == Decimal("300.00")

    def test_filters_by_side(self, service):
        """Requirement 4.3: Separate closing balances for company and vendor sides."""
        entries = [
            LedgerEntry(posting_date=date(2024, 3, 5), adjusted_amount=Decimal("100.00"), side="company"),
            LedgerEntry(posting_date=date(2024, 3, 10), adjusted_amount=Decimal("200.00"), side="vendor"),
            LedgerEntry(posting_date=date(2024, 3, 20), adjusted_amount=Decimal("50.00"), side="company"),
        ]
        opening_company = Decimal("500.00")
        result_company = service.calculate_closing_balance(
            opening_company, entries, date(2024, 3, 1), date(2024, 3, 31), side="company"
        )
        # 500 + (100 + 50) = 650
        assert result_company == Decimal("650.00")

        opening_vendor = Decimal("300.00")
        result_vendor = service.calculate_closing_balance(
            opening_vendor, entries, date(2024, 3, 1), date(2024, 3, 31), side="vendor"
        )
        # 300 + 200 = 500
        assert result_vendor == Decimal("500.00")

    def test_no_movement_returns_opening_balance(self, service):
        """When no entries in period, closing equals opening."""
        entries = [
            LedgerEntry(posting_date=date(2024, 2, 15), adjusted_amount=Decimal("100.00"), side="company"),
        ]
        opening = Decimal("750.00")
        result = service.calculate_closing_balance(
            opening, entries, date(2024, 3, 1), date(2024, 3, 31), side="company"
        )
        assert result == Decimal("750.00")

    def test_empty_entries_returns_opening_balance(self, service):
        """Empty entry list means closing = opening."""
        result = service.calculate_closing_balance(
            Decimal("1000.00"), [], date(2024, 3, 1), date(2024, 3, 31), side="company"
        )
        assert result == Decimal("1000.00")

    def test_negative_opening_balance(self, service):
        """Negative opening balance is handled correctly."""
        entries = [
            LedgerEntry(posting_date=date(2024, 3, 10), adjusted_amount=Decimal("200.00"), side="company"),
        ]
        opening = Decimal("-500.00")
        result = service.calculate_closing_balance(
            opening, entries, date(2024, 3, 1), date(2024, 3, 31), side="company"
        )
        # -500 + 200 = -300
        assert result == Decimal("-300.00")

    def test_closing_balance_without_side_filter(self, service):
        """When side is empty, all entries in the period are summed."""
        entries = [
            LedgerEntry(posting_date=date(2024, 3, 5), adjusted_amount=Decimal("100.00"), side="company"),
            LedgerEntry(posting_date=date(2024, 3, 10), adjusted_amount=Decimal("200.00"), side="vendor"),
        ]
        opening = Decimal("0")
        result = service.calculate_closing_balance(
            opening, entries, date(2024, 3, 1), date(2024, 3, 31), side=""
        )
        assert result == Decimal("300.00")

    def test_balance_arithmetic_invariant(self, service):
        """Verify: closing = opening + sum(period entries) always holds."""
        entries = [
            LedgerEntry(posting_date=date(2024, 1, 5), adjusted_amount=Decimal("100.00"), side="company"),
            LedgerEntry(posting_date=date(2024, 3, 5), adjusted_amount=Decimal("200.00"), side="company"),
            LedgerEntry(posting_date=date(2024, 3, 20), adjusted_amount=Decimal("-75.00"), side="company"),
            LedgerEntry(posting_date=date(2024, 5, 1), adjusted_amount=Decimal("300.00"), side="company"),
        ]
        period_start = date(2024, 3, 1)
        period_end = date(2024, 3, 31)

        opening = service.calculate_opening_balance(entries, period_start, "company")
        closing = service.calculate_closing_balance(
            opening, entries, period_start, period_end, side="company"
        )

        # opening = 100 (Jan 5 entry)
        # net_movement = 200 - 75 = 125 (March entries)
        # closing = 100 + 125 = 225
        assert opening == Decimal("100.00")
        assert closing == Decimal("225.00")
        assert closing == opening + Decimal("125.00")


# ──────────────────────────────────────────────────────────────────────────────
# Tests: Multi-Currency Handling
# ──────────────────────────────────────────────────────────────────────────────


class TestMultiCurrencyHandling:
    """Tests for multi-currency handling.

    Requirements: 6.1, 6.2
    """

    # ── prepare_multi_currency_entry() ──

    def test_inr_transaction_stores_same_amounts(self, service):
        """Requirement 6.1: INR transaction has same transaction and local amounts."""
        entry = RawSAPEntry(
            wrbtr=Decimal("1000.00"),
            dmbtr=Decimal("1000.00"),
            waers="INR",
        )
        result = service.prepare_multi_currency_entry(entry)

        assert result.transaction_currency == "INR"
        assert result.transaction_amount == Decimal("1000.00")
        assert result.local_currency_amount == Decimal("1000.00")
        assert result.exchange_rate == Decimal("1")

    def test_foreign_currency_stores_both_amounts(self, service):
        """Requirement 6.1: Foreign currency entry stores both transaction and INR amounts."""
        entry = RawSAPEntry(
            wrbtr=Decimal("100.00"),  # 100 USD
            dmbtr=Decimal("8300.00"),  # 8300 INR
            waers="USD",
        )
        result = service.prepare_multi_currency_entry(entry)

        assert result.transaction_currency == "USD"
        assert result.transaction_amount == Decimal("100.00")
        assert result.local_currency_amount == Decimal("8300.00")
        assert result.exchange_rate == Decimal("83")

    def test_exchange_rate_calculated_correctly(self, service):
        """Exchange rate = local_amount / transaction_amount."""
        entry = RawSAPEntry(
            wrbtr=Decimal("200.00"),  # 200 EUR
            dmbtr=Decimal("18000.00"),  # 18000 INR
            waers="EUR",
        )
        result = service.prepare_multi_currency_entry(entry)

        assert result.exchange_rate == Decimal("90")

    def test_zero_transaction_amount_exchange_rate_defaults_to_one(self, service):
        """When transaction amount is zero, exchange rate defaults to 1."""
        entry = RawSAPEntry(
            wrbtr=Decimal("0"),
            dmbtr=Decimal("0"),
            waers="USD",
        )
        result = service.prepare_multi_currency_entry(entry)

        assert result.exchange_rate == Decimal("1")

    def test_empty_currency_defaults_to_inr(self, service):
        """Empty currency code defaults to INR."""
        entry = RawSAPEntry(
            wrbtr=Decimal("500.00"),
            dmbtr=Decimal("500.00"),
            waers="",
        )
        result = service.prepare_multi_currency_entry(entry)

        assert result.transaction_currency == "INR"

    def test_currency_code_normalized_uppercase(self, service):
        """Currency code is normalized to uppercase."""
        entry = RawSAPEntry(
            wrbtr=Decimal("100.00"),
            dmbtr=Decimal("8300.00"),
            waers="  usd  ",
        )
        result = service.prepare_multi_currency_entry(entry)

        assert result.transaction_currency == "USD"

    def test_returns_multi_currency_entry_dataclass(self, service):
        """Result is a MultiCurrencyEntry dataclass."""
        entry = RawSAPEntry(
            wrbtr=Decimal("50.00"),
            dmbtr=Decimal("4500.00"),
            waers="GBP",
        )
        result = service.prepare_multi_currency_entry(entry)

        assert isinstance(result, MultiCurrencyEntry)

    # ── get_comparison_amount() ──

    def test_comparison_amount_uses_local_currency_by_default(self, service):
        """Requirement 6.2: Reconciliation uses local currency (INR) by default."""
        entry = LedgerEntry(
            posting_date=date(2024, 3, 1),
            adjusted_amount=Decimal("100.00"),  # Transaction currency amount
            local_currency_amount=Decimal("8300.00"),  # INR equivalent
            transaction_currency="USD",
        )
        result = DataTransformationService.get_comparison_amount(entry)

        assert result == Decimal("8300.00")

    def test_comparison_amount_returns_adjusted_when_local_is_none(self, service):
        """If local_currency_amount is None, falls back to adjusted_amount."""
        entry = LedgerEntry(
            posting_date=date(2024, 3, 1),
            adjusted_amount=Decimal("5000.00"),
            local_currency_amount=None,
            transaction_currency="INR",
        )
        result = DataTransformationService.get_comparison_amount(entry)

        assert result == Decimal("5000.00")

    def test_comparison_amount_with_use_local_false_returns_adjusted(self, service):
        """When use_local_currency=False, returns adjusted_amount directly."""
        entry = LedgerEntry(
            posting_date=date(2024, 3, 1),
            adjusted_amount=Decimal("100.00"),
            local_currency_amount=Decimal("8300.00"),
            transaction_currency="USD",
        )
        result = DataTransformationService.get_comparison_amount(entry, use_local_currency=False)

        assert result == Decimal("100.00")

    def test_inr_entries_comparison_amount_same_either_way(self, service):
        """INR entries have the same comparison amount regardless of flag."""
        entry = LedgerEntry(
            posting_date=date(2024, 3, 1),
            adjusted_amount=Decimal("5000.00"),
            local_currency_amount=Decimal("5000.00"),
            transaction_currency="INR",
        )
        local_result = DataTransformationService.get_comparison_amount(entry, use_local_currency=True)
        txn_result = DataTransformationService.get_comparison_amount(entry, use_local_currency=False)

        assert local_result == Decimal("5000.00")
        assert txn_result == Decimal("5000.00")

    def test_comparison_ensures_same_currency_for_matching(self, service):
        """Requirement 6.2: Entries in different currencies compare using local currency."""
        # USD entry
        usd_entry = LedgerEntry(
            posting_date=date(2024, 3, 1),
            adjusted_amount=Decimal("100.00"),
            local_currency_amount=Decimal("8300.00"),
            transaction_currency="USD",
        )
        # EUR entry
        eur_entry = LedgerEntry(
            posting_date=date(2024, 3, 1),
            adjusted_amount=Decimal("92.22"),
            local_currency_amount=Decimal("8300.00"),
            transaction_currency="EUR",
        )

        # When comparing in local currency, both resolve to 8300 INR
        usd_comparison = DataTransformationService.get_comparison_amount(usd_entry)
        eur_comparison = DataTransformationService.get_comparison_amount(eur_entry)

        assert usd_comparison == eur_comparison == Decimal("8300.00")

    # ── LedgerEntry dataclass fields ──

    def test_ledger_entry_has_transaction_currency_field(self, service):
        """LedgerEntry includes transaction_currency field."""
        entry = LedgerEntry(
            posting_date=date(2024, 3, 1),
            adjusted_amount=Decimal("100.00"),
            transaction_currency="USD",
        )
        assert entry.transaction_currency == "USD"

    def test_ledger_entry_has_local_currency_amount_field(self, service):
        """LedgerEntry includes local_currency_amount field."""
        entry = LedgerEntry(
            posting_date=date(2024, 3, 1),
            adjusted_amount=Decimal("100.00"),
            local_currency_amount=Decimal("8300.00"),
        )
        assert entry.local_currency_amount == Decimal("8300.00")

    def test_ledger_entry_defaults_transaction_currency_to_inr(self, service):
        """LedgerEntry transaction_currency defaults to INR."""
        entry = LedgerEntry(
            posting_date=date(2024, 3, 1),
            adjusted_amount=Decimal("500.00"),
        )
        assert entry.transaction_currency == "INR"

    def test_ledger_entry_defaults_local_currency_amount_to_none(self, service):
        """LedgerEntry local_currency_amount defaults to None."""
        entry = LedgerEntry(
            posting_date=date(2024, 3, 1),
            adjusted_amount=Decimal("500.00"),
        )
        assert entry.local_currency_amount is None


# ──────────────────────────────────────────────────────────────────────────────
# Tests: tag_tds_entries()
# ──────────────────────────────────────────────────────────────────────────────


class TestTDSTagging:
    """Tests for TDS tagging and linking logic.

    Requirements: 5.1, 5.2, 5.3
    """

    # ── Requirement 5.1: Tag entries with TDS document types ──

    def test_tags_tds_entry_by_document_type(self, service):
        """Requirement 5.1: Entries with TDS document type are tagged as is_tds=True."""
        entries = [
            LedgerEntry(
                posting_date=date(2024, 3, 1),
                adjusted_amount=Decimal("500.00"),
                side="company",
                document_type="TD",
                entry_id="entry-1",
                reference_number="INV001",
            ),
        ]
        tds_types = {"TD"}
        result = service.tag_tds_entries(entries, tds_document_types=tds_types)
        assert result[0].is_tds is True

    def test_non_tds_entries_remain_untagged(self, service):
        """Non-TDS document types are not tagged."""
        entries = [
            LedgerEntry(
                posting_date=date(2024, 3, 1),
                adjusted_amount=Decimal("1000.00"),
                side="company",
                document_type="RE",
                entry_id="entry-1",
                reference_number="INV001",
            ),
        ]
        tds_types = {"TD"}
        result = service.tag_tds_entries(entries, tds_document_types=tds_types)
        assert result[0].is_tds is False

    def test_multiple_tds_entries_all_tagged(self, service):
        """Multiple TDS entries are all tagged correctly."""
        entries = [
            LedgerEntry(
                posting_date=date(2024, 3, 1),
                adjusted_amount=Decimal("100.00"),
                side="company",
                document_type="TD",
                entry_id="entry-1",
                reference_number="INV001",
            ),
            LedgerEntry(
                posting_date=date(2024, 3, 5),
                adjusted_amount=Decimal("200.00"),
                side="company",
                document_type="WT",
                entry_id="entry-2",
                reference_number="INV002",
            ),
            LedgerEntry(
                posting_date=date(2024, 3, 10),
                adjusted_amount=Decimal("1000.00"),
                side="company",
                document_type="RE",
                entry_id="entry-3",
                reference_number="INV003",
            ),
        ]
        tds_types = {"TD", "WT"}
        result = service.tag_tds_entries(entries, tds_document_types=tds_types)
        assert result[0].is_tds is True
        assert result[1].is_tds is True
        assert result[2].is_tds is False

    def test_tds_tagging_case_insensitive(self, service):
        """TDS document type matching is case insensitive."""
        entries = [
            LedgerEntry(
                posting_date=date(2024, 3, 1),
                adjusted_amount=Decimal("100.00"),
                side="company",
                document_type="td",
                entry_id="entry-1",
                reference_number="INV001",
            ),
        ]
        tds_types = {"TD"}
        result = service.tag_tds_entries(entries, tds_document_types=tds_types)
        assert result[0].is_tds is True

    def test_empty_document_type_not_tagged(self, service):
        """Entries with empty document_type are not tagged as TDS."""
        entries = [
            LedgerEntry(
                posting_date=date(2024, 3, 1),
                adjusted_amount=Decimal("100.00"),
                side="company",
                document_type="",
                entry_id="entry-1",
                reference_number="INV001",
            ),
        ]
        tds_types = {"TD"}
        result = service.tag_tds_entries(entries, tds_document_types=tds_types)
        assert result[0].is_tds is False

    # ── Requirement 5.2: Link TDS entries to parent invoices by reference ──

    def test_links_tds_entry_to_parent_by_reference_number(self, service):
        """Requirement 5.2: TDS entry linked to parent invoice by matching reference_number."""
        entries = [
            LedgerEntry(
                posting_date=date(2024, 3, 1),
                adjusted_amount=Decimal("1000.00"),
                side="company",
                document_type="RE",
                entry_id="parent-1",
                reference_number="INV001",
            ),
            LedgerEntry(
                posting_date=date(2024, 3, 5),
                adjusted_amount=Decimal("100.00"),
                side="company",
                document_type="TD",
                entry_id="tds-1",
                reference_number="INV001",
            ),
        ]
        tds_types = {"TD"}
        result = service.tag_tds_entries(entries, tds_document_types=tds_types)

        assert result[1].is_tds is True
        assert result[1].tds_parent_entry_id == "parent-1"

    def test_links_tds_entry_to_parent_by_document_number(self, service):
        """TDS entry linked to parent when reference matches parent's document_number."""
        entries = [
            LedgerEntry(
                posting_date=date(2024, 3, 1),
                adjusted_amount=Decimal("1000.00"),
                side="company",
                document_type="RE",
                entry_id="parent-1",
                document_number="DOC5001",
                reference_number="",
            ),
            LedgerEntry(
                posting_date=date(2024, 3, 5),
                adjusted_amount=Decimal("100.00"),
                side="company",
                document_type="TD",
                entry_id="tds-1",
                reference_number="DOC5001",
            ),
        ]
        tds_types = {"TD"}
        result = service.tag_tds_entries(entries, tds_document_types=tds_types)

        assert result[1].is_tds is True
        assert result[1].tds_parent_entry_id == "parent-1"

    def test_linking_uses_clean_reference_for_matching(self, service):
        """Linking uses CLEAN function so leading zeros/special chars don't prevent match."""
        entries = [
            LedgerEntry(
                posting_date=date(2024, 3, 1),
                adjusted_amount=Decimal("1000.00"),
                side="company",
                document_type="RE",
                entry_id="parent-1",
                reference_number="00INV/001",
            ),
            LedgerEntry(
                posting_date=date(2024, 3, 5),
                adjusted_amount=Decimal("100.00"),
                side="company",
                document_type="TD",
                entry_id="tds-1",
                reference_number="INV-001",
            ),
        ]
        tds_types = {"TD"}
        result = service.tag_tds_entries(entries, tds_document_types=tds_types)

        # Both clean to "INV001"
        assert result[1].tds_parent_entry_id == "parent-1"

    # ── Requirement 5.3: Flag unlinked TDS entries for manual review ──

    def test_flags_unlinked_tds_entry_for_manual_review(self, service):
        """Requirement 5.3: TDS entry with no matching parent is flagged."""
        entries = [
            LedgerEntry(
                posting_date=date(2024, 3, 1),
                adjusted_amount=Decimal("1000.00"),
                side="company",
                document_type="RE",
                entry_id="parent-1",
                reference_number="INV001",
            ),
            LedgerEntry(
                posting_date=date(2024, 3, 5),
                adjusted_amount=Decimal("100.00"),
                side="company",
                document_type="TD",
                entry_id="tds-1",
                reference_number="UNKNOWN_REF",
            ),
        ]
        tds_types = {"TD"}
        result = service.tag_tds_entries(entries, tds_document_types=tds_types)

        assert result[1].is_tds is True
        assert result[1].tds_parent_entry_id is None
        assert "TDS Entry \u2014 No Parent Invoice Found" in result[1].flags

    def test_tds_entry_with_empty_reference_flagged(self, service):
        """TDS entry with empty reference_number cannot link, gets flagged."""
        entries = [
            LedgerEntry(
                posting_date=date(2024, 3, 1),
                adjusted_amount=Decimal("1000.00"),
                side="company",
                document_type="RE",
                entry_id="parent-1",
                reference_number="INV001",
            ),
            LedgerEntry(
                posting_date=date(2024, 3, 5),
                adjusted_amount=Decimal("100.00"),
                side="company",
                document_type="TD",
                entry_id="tds-1",
                reference_number="",
            ),
        ]
        tds_types = {"TD"}
        result = service.tag_tds_entries(entries, tds_document_types=tds_types)

        assert result[1].is_tds is True
        assert result[1].tds_parent_entry_id is None
        assert "TDS Entry \u2014 No Parent Invoice Found" in result[1].flags

    def test_flag_not_duplicated_on_repeated_calls(self, service):
        """Calling tag_tds_entries twice doesn't duplicate the flag."""
        entries = [
            LedgerEntry(
                posting_date=date(2024, 3, 5),
                adjusted_amount=Decimal("100.00"),
                side="company",
                document_type="TD",
                entry_id="tds-1",
                reference_number="NO_MATCH",
            ),
        ]
        tds_types = {"TD"}
        service.tag_tds_entries(entries, tds_document_types=tds_types)
        service.tag_tds_entries(entries, tds_document_types=tds_types)

        flag_count = entries[0].flags.count("TDS Entry \u2014 No Parent Invoice Found")
        assert flag_count == 1

    # ── Edge cases ──

    def test_empty_entries_list(self, service):
        """tag_tds_entries handles empty list gracefully."""
        result = service.tag_tds_entries([], tds_document_types={"TD"})
        assert result == []

    def test_no_tds_types_provided(self, service):
        """When no TDS types provided (None), no entries are tagged."""
        entries = [
            LedgerEntry(
                posting_date=date(2024, 3, 1),
                adjusted_amount=Decimal("100.00"),
                side="company",
                document_type="TD",
                entry_id="entry-1",
                reference_number="INV001",
            ),
        ]
        result = service.tag_tds_entries(entries, tds_document_types=None)
        assert result[0].is_tds is False

    def test_tds_entry_does_not_link_to_another_tds_entry(self, service):
        """TDS entries should only link to non-TDS parent invoices."""
        entries = [
            LedgerEntry(
                posting_date=date(2024, 3, 1),
                adjusted_amount=Decimal("50.00"),
                side="company",
                document_type="TD",
                entry_id="tds-1",
                reference_number="INV001",
            ),
            LedgerEntry(
                posting_date=date(2024, 3, 5),
                adjusted_amount=Decimal("100.00"),
                side="company",
                document_type="TD",
                entry_id="tds-2",
                reference_number="INV001",
            ),
        ]
        tds_types = {"TD"}
        result = service.tag_tds_entries(entries, tds_document_types=tds_types)

        # Both are TDS, neither should link to the other
        assert result[0].tds_parent_entry_id is None
        assert result[1].tds_parent_entry_id is None
        assert "TDS Entry \u2014 No Parent Invoice Found" in result[0].flags
        assert "TDS Entry \u2014 No Parent Invoice Found" in result[1].flags

    def test_returns_modified_same_list(self, service):
        """tag_tds_entries modifies and returns the same list (in-place mutation)."""
        entries = [
            LedgerEntry(
                posting_date=date(2024, 3, 1),
                adjusted_amount=Decimal("100.00"),
                side="company",
                document_type="TD",
                entry_id="tds-1",
                reference_number="INV001",
            ),
        ]
        tds_types = {"TD"}
        result = service.tag_tds_entries(entries, tds_document_types=tds_types)
        assert result is entries


# ──────────────────────────────────────────────────────────────────────────────
# Tests: classify_document_type()
# ──────────────────────────────────────────────────────────────────────────────


class TestDocumentTypeClassification:
    """Tests for document type classification.

    Requirements: 7.1, 7.2, 7.3, 7.4, 7.5
    """

    # ── Requirement 7.1: RE, KR, DR → Invoice ──

    @pytest.mark.parametrize("doc_type", ["RE", "KR", "DR"])
    def test_invoice_document_types(self, service, doc_type):
        """Requirement 7.1: RE, KR, DR classified as Invoice."""
        result = service.classify_document_type(doc_type)
        assert result == DocumentCategory.INVOICE

    # ── Requirement 7.2: ZP, KZ, ZV → Payment ──

    @pytest.mark.parametrize("doc_type", ["ZP", "KZ", "ZV"])
    def test_payment_document_types(self, service, doc_type):
        """Requirement 7.2: ZP, KZ, ZV classified as Payment."""
        result = service.classify_document_type(doc_type)
        assert result == DocumentCategory.PAYMENT

    # ── Requirement 7.3: KG → Credit Note ──

    def test_credit_note_document_type(self, service):
        """Requirement 7.3: KG classified as Credit Note."""
        result = service.classify_document_type("KG")
        assert result == DocumentCategory.CREDIT_NOTE

    # ── Requirement 7.4: RV → Debit Note ──

    def test_debit_note_document_type(self, service):
        """Requirement 7.4: RV classified as Debit Note."""
        result = service.classify_document_type("RV")
        assert result == DocumentCategory.DEBIT_NOTE

    # ── Case insensitivity ──

    @pytest.mark.parametrize("doc_type,expected", [
        ("re", DocumentCategory.INVOICE),
        ("kr", DocumentCategory.INVOICE),
        ("zp", DocumentCategory.PAYMENT),
        ("kz", DocumentCategory.PAYMENT),
        ("kg", DocumentCategory.CREDIT_NOTE),
        ("rv", DocumentCategory.DEBIT_NOTE),
    ])
    def test_case_insensitive_classification(self, service, doc_type, expected):
        """Document type classification is case insensitive."""
        result = service.classify_document_type(doc_type)
        assert result == expected

    # ── Whitespace handling ──

    def test_strips_whitespace_before_classification(self, service):
        """Leading/trailing whitespace is stripped before classification."""
        result = service.classify_document_type("  RE  ")
        assert result == DocumentCategory.INVOICE

    # ── Unknown document types → Other ──

    @pytest.mark.parametrize("doc_type", ["XX", "AB", "SA", "ZZ", "QQ"])
    def test_unknown_document_types_return_other(self, service, doc_type):
        """Unknown document types default to 'Other' category."""
        result = service.classify_document_type(doc_type)
        assert result == DocumentCategory.OTHER

    # ── Edge cases: empty/None-like inputs ──

    def test_empty_string_returns_other(self, service):
        """Empty string returns 'Other' category."""
        result = service.classify_document_type("")
        assert result == DocumentCategory.OTHER

    def test_whitespace_only_returns_other(self, service):
        """Whitespace-only string returns 'Other' category."""
        result = service.classify_document_type("   ")
        assert result == DocumentCategory.OTHER

    # ── Async version uses config repo (Requirement 7.5) ──

    @pytest.mark.asyncio
    async def test_async_version_checks_config_repo_first(self, service, mock_config_repo):
        """Requirement 7.5: Async version checks configurable mapping from DB first."""
        # Configure mock to return a custom mapping
        mock_config_repo.get_document_type_category = AsyncMock(return_value="TDS")

        result = await service.classify_document_type_async("XX")

        mock_config_repo.get_document_type_category.assert_called_once_with("XX")
        assert result == "TDS"

    @pytest.mark.asyncio
    async def test_async_version_falls_back_to_defaults_when_config_returns_none(
        self, service, mock_config_repo
    ):
        """Async version falls back to defaults when config repo returns None."""
        mock_config_repo.get_document_type_category = AsyncMock(return_value=None)

        result = await service.classify_document_type_async("RE")

        assert result == DocumentCategory.INVOICE

    @pytest.mark.asyncio
    async def test_async_version_returns_other_for_unknown_unconfigured(
        self, service, mock_config_repo
    ):
        """Async version returns 'Other' for unknown types not in config."""
        mock_config_repo.get_document_type_category = AsyncMock(return_value=None)

        result = await service.classify_document_type_async("ZZ")

        assert result == DocumentCategory.OTHER

    @pytest.mark.asyncio
    async def test_async_version_handles_empty_input(self, service, mock_config_repo):
        """Async version returns 'Other' for empty input without calling repo."""
        result = await service.classify_document_type_async("")

        assert result == DocumentCategory.OTHER
        mock_config_repo.get_document_type_category.assert_not_called()

    # ── Default mapping completeness ──

    def test_default_mapping_contains_all_brd_types(self, service):
        """Default mapping covers all document types specified in BRD."""
        mapping = service.DEFAULT_DOCUMENT_TYPE_MAPPING
        assert mapping["RE"] == DocumentCategory.INVOICE
        assert mapping["KR"] == DocumentCategory.INVOICE
        assert mapping["DR"] == DocumentCategory.INVOICE
        assert mapping["ZP"] == DocumentCategory.PAYMENT
        assert mapping["KZ"] == DocumentCategory.PAYMENT
        assert mapping["ZV"] == DocumentCategory.PAYMENT
        assert mapping["KG"] == DocumentCategory.CREDIT_NOTE
        assert mapping["RV"] == DocumentCategory.DEBIT_NOTE

    def test_default_mapping_has_exactly_8_entries(self, service):
        """Default mapping contains exactly 8 entries per BRD."""
        assert len(service.DEFAULT_DOCUMENT_TYPE_MAPPING) == 8
