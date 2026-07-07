"""
Unit tests for FileParserService.

Tests CSV and Excel file validation, parsing, file type detection,
size limit enforcement, mandatory column validation, configurable
field mapping, and row-level entry parsing.

Requirements: 1.2, 1.4, 4.3, 4.4, 16.5, 17.5
"""

import pytest
from decimal import Decimal
from datetime import date

from src.domain.exceptions.vlr import FileValidationException
from src.domain.services.vlr.file_parser_service import (
    DEFAULT_FIELD_MAPPING,
    MANDATORY_COLUMNS,
    MAX_FILE_SIZE_BYTES,
    FileParserService,
    FileType,
    FileValidationResult,
    ParsedLedgerEntry,
)


# ─── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def parser() -> FileParserService:
    """Create a default FileParserService instance."""
    return FileParserService()


@pytest.fixture
def small_parser() -> FileParserService:
    """Create a FileParserService with a small size limit for testing."""
    return FileParserService(max_file_size_bytes=100)


def make_csv(headers: list[str], rows: list[list[str]]) -> bytes:
    """Helper to create CSV file content from headers and rows."""
    lines = [",".join(headers)]
    for row in rows:
        lines.append(",".join(row))
    return "\n".join(lines).encode("utf-8")


def make_valid_csv(num_rows: int = 1) -> bytes:
    """Create a valid CSV with the mandatory columns."""
    headers = ["document_number", "amount", "posting_date", "reference_number"]
    rows = []
    for i in range(num_rows):
        rows.append([f"DOC{i+1:03d}", f"{100.0 + i}", "2024-01-15", f"REF{i+1:03d}"])
    return make_csv(headers, rows)


# ─── File Type Detection Tests ────────────────────────────────────────────────


class TestFileTypeDetection:
    """Tests for detect_file_type method."""

    def test_detect_csv_file(self, parser: FileParserService):
        """Should detect .csv as CSV type."""
        assert parser.detect_file_type("ledger.csv") == FileType.CSV

    def test_detect_csv_uppercase(self, parser: FileParserService):
        """Should detect .CSV (uppercase) as CSV type."""
        assert parser.detect_file_type("LEDGER.CSV") == FileType.CSV

    def test_detect_xlsx_file(self, parser: FileParserService):
        """Should detect .xlsx as Excel type."""
        assert parser.detect_file_type("ledger.xlsx") == FileType.EXCEL

    def test_detect_xlsx_mixed_case(self, parser: FileParserService):
        """Should detect .XLSX (uppercase) as Excel type."""
        assert parser.detect_file_type("LEDGER.XLSX") == FileType.EXCEL

    def test_reject_xls_format(self, parser: FileParserService):
        """Should reject .xls (old Excel format) with appropriate message."""
        with pytest.raises(FileValidationException) as exc_info:
            parser.detect_file_type("ledger.xls")
        assert ".xls" in str(exc_info.value)
        assert ".xlsx" in str(exc_info.value)

    def test_reject_unsupported_format(self, parser: FileParserService):
        """Should reject unsupported file types."""
        with pytest.raises(FileValidationException) as exc_info:
            parser.detect_file_type("ledger.pdf")
        assert "pdf" in str(exc_info.value)

    def test_reject_no_extension(self, parser: FileParserService):
        """Should reject files with no extension."""
        with pytest.raises(FileValidationException):
            parser.detect_file_type("ledger")


# ─── File Size Validation Tests ───────────────────────────────────────────────


class TestFileSizeValidation:
    """Tests for validate_file_size method."""

    def test_accept_file_within_limit(self, parser: FileParserService):
        """Should accept file under 10MB."""
        content = b"x" * (5 * 1024 * 1024)  # 5MB
        parser.validate_file_size(content)  # Should not raise

    def test_accept_file_at_limit(self, parser: FileParserService):
        """Should accept file exactly at 10MB."""
        content = b"x" * MAX_FILE_SIZE_BYTES
        parser.validate_file_size(content)  # Should not raise

    def test_reject_file_exceeding_limit(self, parser: FileParserService):
        """Should reject file exceeding 10MB."""
        content = b"x" * (MAX_FILE_SIZE_BYTES + 1)
        with pytest.raises(FileValidationException) as exc_info:
            parser.validate_file_size(content)
        assert "exceeds" in str(exc_info.value)

    def test_custom_size_limit(self, small_parser: FileParserService):
        """Should respect custom max file size."""
        content = b"x" * 101
        with pytest.raises(FileValidationException):
            small_parser.validate_file_size(content)

    def test_empty_file_passes_size_check(self, parser: FileParserService):
        """Empty file should pass size validation."""
        parser.validate_file_size(b"")  # Should not raise


# ─── Mandatory Column Validation Tests ────────────────────────────────────────


class TestMandatoryColumnValidation:
    """Tests for mandatory column detection in CSV files."""

    def test_all_mandatory_columns_present(self, parser: FileParserService):
        """Should pass when all mandatory columns are present."""
        content = make_valid_csv()
        result = parser.validate_and_parse(content, "test.csv")
        assert result.is_valid is True

    def test_missing_document_number(self, parser: FileParserService):
        """Should fail when document_number column is missing."""
        content = make_csv(
            ["amount", "posting_date", "reference_number"],
            [["100.00", "2024-01-15", "REF001"]],
        )
        result = parser.validate_and_parse(content, "test.csv")
        assert result.is_valid is False
        assert "document_number" in result.errors[0]

    def test_missing_amount(self, parser: FileParserService):
        """Should fail when amount column is missing."""
        content = make_csv(
            ["document_number", "posting_date", "reference_number"],
            [["DOC001", "2024-01-15", "REF001"]],
        )
        result = parser.validate_and_parse(content, "test.csv")
        assert result.is_valid is False
        assert "amount" in result.errors[0]

    def test_missing_posting_date(self, parser: FileParserService):
        """Should fail when posting_date column is missing."""
        content = make_csv(
            ["document_number", "amount", "reference_number"],
            [["DOC001", "100.00", "REF001"]],
        )
        result = parser.validate_and_parse(content, "test.csv")
        assert result.is_valid is False
        assert "posting_date" in result.errors[0]

    def test_missing_reference_number(self, parser: FileParserService):
        """Should fail when reference_number column is missing."""
        content = make_csv(
            ["document_number", "amount", "posting_date"],
            [["DOC001", "100.00", "2024-01-15"]],
        )
        result = parser.validate_and_parse(content, "test.csv")
        assert result.is_valid is False
        assert "reference_number" in result.errors[0]

    def test_missing_multiple_columns(self, parser: FileParserService):
        """Should report all missing mandatory columns."""
        content = make_csv(
            ["some_column", "other_column"],
            [["value1", "value2"]],
        )
        result = parser.validate_and_parse(content, "test.csv")
        assert result.is_valid is False
        # All mandatory columns should be reported missing
        error_text = result.errors[0]
        assert "amount" in error_text
        assert "document_number" in error_text
        assert "posting_date" in error_text
        assert "reference_number" in error_text

    def test_empty_file(self, parser: FileParserService):
        """Should fail for empty file with no headers."""
        result = parser.validate_and_parse(b"", "test.csv")
        assert result.is_valid is False
        assert "empty" in result.errors[0].lower() or "header" in result.errors[0].lower()


# ─── Field Mapping Tests ──────────────────────────────────────────────────────


class TestFieldMapping:
    """Tests for configurable field mapping."""

    def test_default_mapping_accepts_standard_names(self, parser: FileParserService):
        """Should accept standard column names from DEFAULT_FIELD_MAPPING."""
        content = make_valid_csv()
        result = parser.validate_and_parse(content, "test.csv")
        assert result.is_valid is True

    def test_alternative_column_names(self, parser: FileParserService):
        """Should accept alternative column names defined in field mapping."""
        content = make_csv(
            ["belnr", "dmbtr", "budat", "zuonr"],
            [["DOC001", "500.00", "2024-03-10", "REF001"]],
        )
        result = parser.validate_and_parse(content, "test.csv")
        assert result.is_valid is True
        assert result.entries[0].document_number == "DOC001"
        assert result.entries[0].amount == Decimal("500.00")

    def test_custom_field_mapping(self):
        """Should use custom field mapping when provided."""
        custom_mapping = {
            "document_number": ["invoice_no"],
            "amount": ["total"],
            "posting_date": ["date"],
            "reference_number": ["ref"],
        }
        parser = FileParserService(field_mapping=custom_mapping)

        content = make_csv(
            ["invoice_no", "total", "date", "ref"],
            [["INV001", "250.00", "2024-06-01", "R001"]],
        )
        result = parser.validate_and_parse(content, "test.csv")
        assert result.is_valid is True
        assert result.entries[0].document_number == "INV001"
        assert result.entries[0].amount == Decimal("250.00")

    def test_case_insensitive_headers(self, parser: FileParserService):
        """Should match column headers case-insensitively."""
        content = make_csv(
            ["Document_Number", "AMOUNT", "Posting_Date", "Reference_Number"],
            [["DOC001", "100.00", "2024-01-15", "REF001"]],
        )
        result = parser.validate_and_parse(content, "test.csv")
        assert result.is_valid is True

    def test_headers_with_whitespace(self, parser: FileParserService):
        """Should handle column headers with leading/trailing whitespace."""
        content = " document_number , amount , posting_date , reference_number \nDOC001,100.00,2024-01-15,REF001\n".encode("utf-8")
        result = parser.validate_and_parse(content, "test.csv")
        assert result.is_valid is True


# ─── CSV Parsing Tests ────────────────────────────────────────────────────────


class TestCSVParsing:
    """Tests for CSV row parsing and entry creation."""

    def test_parse_single_valid_row(self, parser: FileParserService):
        """Should parse a single valid row into ParsedLedgerEntry."""
        content = make_valid_csv(1)
        result = parser.validate_and_parse(content, "test.csv")

        assert result.is_valid is True
        assert len(result.entries) == 1
        assert result.row_count == 1
        entry = result.entries[0]
        assert entry.document_number == "DOC001"
        assert entry.amount == Decimal("100.0")
        assert entry.posting_date == date(2024, 1, 15)
        assert entry.reference_number == "REF001"

    def test_parse_multiple_rows(self, parser: FileParserService):
        """Should parse multiple valid rows."""
        content = make_valid_csv(5)
        result = parser.validate_and_parse(content, "test.csv")

        assert result.is_valid is True
        assert len(result.entries) == 5
        assert result.row_count == 5

    def test_parse_optional_fields(self, parser: FileParserService):
        """Should parse optional fields when present."""
        headers = [
            "document_number", "amount", "posting_date", "reference_number",
            "document_type", "clearing_date", "clearing_document",
            "assignment_number", "currency", "description",
        ]
        rows = [[
            "DOC001", "1500.50", "2024-02-20", "REF001",
            "KR", "2024-03-01", "CLR001",
            "ASN001", "USD", "Payment for services",
        ]]
        content = make_csv(headers, rows)
        result = parser.validate_and_parse(content, "test.csv")

        assert result.is_valid is True
        entry = result.entries[0]
        assert entry.document_type == "KR"
        assert entry.clearing_date == date(2024, 3, 1)
        assert entry.clearing_document == "CLR001"
        assert entry.assignment_number == "ASN001"
        assert entry.currency == "USD"
        assert entry.description == "Payment for services"

    def test_default_currency_inr(self, parser: FileParserService):
        """Should default currency to INR when not specified."""
        content = make_valid_csv()
        result = parser.validate_and_parse(content, "test.csv")
        assert result.entries[0].currency == "INR"

    def test_empty_mandatory_field_value(self, parser: FileParserService):
        """Should report error for empty mandatory field values."""
        content = make_csv(
            ["document_number", "amount", "posting_date", "reference_number"],
            [["", "100.00", "2024-01-15", "REF001"]],
        )
        result = parser.validate_and_parse(content, "test.csv")
        assert result.is_valid is False
        assert "Row 2" in result.errors[0]
        assert "document_number" in result.errors[0]

    def test_invalid_amount_format(self, parser: FileParserService):
        """Should report error for invalid amount values."""
        content = make_csv(
            ["document_number", "amount", "posting_date", "reference_number"],
            [["DOC001", "not_a_number", "2024-01-15", "REF001"]],
        )
        result = parser.validate_and_parse(content, "test.csv")
        assert result.is_valid is False
        assert "amount" in result.errors[0].lower() or "Invalid" in result.errors[0]

    def test_amount_with_commas(self, parser: FileParserService):
        """Should handle amounts with comma as thousands separator."""
        content = make_csv(
            ["document_number", "amount", "posting_date", "reference_number"],
            [["DOC001", "\"1,500,000.75\"", "2024-01-15", "REF001"]],
        )
        result = parser.validate_and_parse(content, "test.csv")
        assert result.is_valid is True
        assert result.entries[0].amount == Decimal("1500000.75")

    def test_invalid_date_format(self, parser: FileParserService):
        """Should report error for unrecognized date formats."""
        content = make_csv(
            ["document_number", "amount", "posting_date", "reference_number"],
            [["DOC001", "100.00", "not-a-date", "REF001"]],
        )
        result = parser.validate_and_parse(content, "test.csv")
        assert result.is_valid is False
        assert "posting_date" in result.errors[0].lower() or "date" in result.errors[0].lower()

    def test_multiple_date_formats(self, parser: FileParserService):
        """Should support multiple date formats (ISO, DD/MM/YYYY, DD-MM-YYYY)."""
        headers = ["document_number", "amount", "posting_date", "reference_number"]
        rows = [
            ["DOC001", "100.00", "2024-01-15", "REF001"],      # ISO
            ["DOC002", "200.00", "15/01/2024", "REF002"],      # DD/MM/YYYY
            ["DOC003", "300.00", "15-01-2024", "REF003"],      # DD-MM-YYYY
            ["DOC004", "400.00", "15.01.2024", "REF004"],      # DD.MM.YYYY
        ]
        content = make_csv(headers, rows)
        result = parser.validate_and_parse(content, "test.csv")

        assert result.is_valid is True
        assert len(result.entries) == 4
        assert result.entries[0].posting_date == date(2024, 1, 15)
        assert result.entries[1].posting_date == date(2024, 1, 15)
        assert result.entries[2].posting_date == date(2024, 1, 15)
        assert result.entries[3].posting_date == date(2024, 1, 15)

    def test_partial_row_errors(self, parser: FileParserService):
        """Should report errors per row and not include errored rows in entries."""
        headers = ["document_number", "amount", "posting_date", "reference_number"]
        rows = [
            ["DOC001", "100.00", "2024-01-15", "REF001"],  # valid
            ["DOC002", "invalid", "2024-01-15", "REF002"],  # invalid amount
        ]
        content = make_csv(headers, rows)
        result = parser.validate_and_parse(content, "test.csv")

        assert result.is_valid is False
        assert len(result.errors) == 1
        assert "Row 3" in result.errors[0]

    def test_utf8_encoding(self, parser: FileParserService):
        """Should handle UTF-8 encoded files."""
        content = "document_number,amount,posting_date,reference_number\nDÖC001,100.00,2024-01-15,RÉF001\n".encode("utf-8")
        result = parser.validate_and_parse(content, "test.csv")
        assert result.is_valid is True
        assert result.entries[0].document_number == "DÖC001"

    def test_latin1_encoding_fallback(self, parser: FileParserService):
        """Should fall back to latin-1 encoding if UTF-8 fails."""
        content = "document_number,amount,posting_date,reference_number\nDOC001,100.00,2024-01-15,REF001\n".encode("latin-1")
        result = parser.validate_and_parse(content, "test.csv")
        assert result.is_valid is True

    def test_file_type_in_result(self, parser: FileParserService):
        """Should include the detected file type in the result."""
        content = make_valid_csv()
        result = parser.validate_and_parse(content, "test.csv")
        assert result.file_type == FileType.CSV


# ─── Full Validate And Parse Integration Tests ────────────────────────────────


class TestValidateAndParse:
    """Integration tests for the full validate_and_parse flow."""

    def test_unsupported_file_type_raises(self, parser: FileParserService):
        """Should raise FileValidationException for unsupported types."""
        with pytest.raises(FileValidationException):
            parser.validate_and_parse(b"some data", "test.pdf")

    def test_oversized_file_raises(self, parser: FileParserService):
        """Should raise FileValidationException for oversized files."""
        huge_content = b"x" * (MAX_FILE_SIZE_BYTES + 1)
        with pytest.raises(FileValidationException):
            parser.validate_and_parse(huge_content, "test.csv")

    def test_valid_csv_returns_success_result(self, parser: FileParserService):
        """Should return valid result for well-formed CSV."""
        content = make_valid_csv(3)
        result = parser.validate_and_parse(content, "ledger_data.csv")

        assert result.is_valid is True
        assert len(result.entries) == 3
        assert result.row_count == 3
        assert result.file_type == FileType.CSV
        assert result.errors == []

    def test_negative_amounts(self, parser: FileParserService):
        """Should handle negative amounts (credit entries)."""
        content = make_csv(
            ["document_number", "amount", "posting_date", "reference_number"],
            [["DOC001", "-5000.00", "2024-01-15", "REF001"]],
        )
        result = parser.validate_and_parse(content, "test.csv")
        assert result.is_valid is True
        assert result.entries[0].amount == Decimal("-5000.00")

    def test_zero_amount(self, parser: FileParserService):
        """Should handle zero amount entries."""
        content = make_csv(
            ["document_number", "amount", "posting_date", "reference_number"],
            [["DOC001", "0.00", "2024-01-15", "REF001"]],
        )
        result = parser.validate_and_parse(content, "test.csv")
        assert result.is_valid is True
        assert result.entries[0].amount == Decimal("0.00")

    def test_large_amounts(self, parser: FileParserService):
        """Should handle very large decimal amounts."""
        content = make_csv(
            ["document_number", "amount", "posting_date", "reference_number"],
            [["DOC001", "99999999999.99", "2024-01-15", "REF001"]],
        )
        result = parser.validate_and_parse(content, "test.csv")
        assert result.is_valid is True
        assert result.entries[0].amount == Decimal("99999999999.99")
