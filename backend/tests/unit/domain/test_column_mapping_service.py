"""
Unit tests for ColumnMappingService.

Tests file preview generation, auto-mapping intelligence with confidence scores,
template application and saving.

Requirements: 9.1, 9.2, 9.3, 10.1, 10.2, 10.3, 11.1, 11.2, 11.3, 11.4
"""

import csv
import io
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from src.domain.services.vlr.column_mapping_service import (
    ColumnMapping,
    ColumnMappingEntry,
    ColumnMappingService,
    ColumnSuggestion,
    ConfidenceLevel,
    FilePreview,
    HeaderLibrary,
    HeaderLibraryEntry,
    PREVIEW_ROW_COUNT,
    TransactionTypeTag,
)


# ──────────────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_template_repo():
    """Create a mock IColumnMappingTemplateRepository."""
    repo = MagicMock()
    repo.get_by_vendor = AsyncMock(return_value=None)
    repo.save = AsyncMock(return_value=None)
    repo.delete = AsyncMock(return_value=None)
    return repo


@pytest.fixture
def header_library():
    """Create a default HeaderLibrary."""
    return HeaderLibrary()


@pytest.fixture
def service(mock_template_repo, header_library):
    """Create a ColumnMappingService instance."""
    return ColumnMappingService(
        template_repository=mock_template_repo,
        header_library=header_library,
    )


def _create_csv_bytes(headers: list[str], rows: list[list[str]]) -> bytes:
    """Helper to create CSV file bytes."""
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(headers)
    for row in rows:
        writer.writerow(row)
    return output.getvalue().encode("utf-8")


# ──────────────────────────────────────────────────────────────────────────────
# Tests: TransactionTypeTag Enum
# ──────────────────────────────────────────────────────────────────────────────


class TestTransactionTypeTag:
    """Tests for the 12 transaction type tags."""

    def test_has_12_tags(self):
        """Requirement 9.3: Support 12 transaction type tags."""
        assert len(TransactionTypeTag) == 12

    def test_all_required_tags_exist(self):
        """All 12 BRD-specified tags exist."""
        expected_tags = [
            "INVOICE", "PAYMENT", "TDS", "CREDIT_NOTE", "DEBIT_NOTE",
            "OPENING_BALANCE", "CLOSING_BALANCE", "DATE", "REFERENCE",
            "AMOUNT", "DESCRIPTION", "IGNORE",
        ]
        for tag_name in expected_tags:
            assert hasattr(TransactionTypeTag, tag_name)

    def test_tag_values_are_strings(self):
        """Tag values are string values matching the name."""
        assert TransactionTypeTag.INVOICE.value == "INVOICE"
        assert TransactionTypeTag.CREDIT_NOTE.value == "CREDIT_NOTE"


# ──────────────────────────────────────────────────────────────────────────────
# Tests: generate_preview() - CSV
# ──────────────────────────────────────────────────────────────────────────────


class TestGeneratePreviewCSV:
    """Tests for CSV file preview generation."""

    def test_returns_first_10_rows(self, service):
        """Requirement 9.1: Display first 10 rows as preview."""
        headers = ["Invoice No", "Amount", "Date"]
        rows = [[f"INV{i:03d}", f"{i * 100}.00", f"2024-01-{i:02d}"] for i in range(1, 21)]
        file_content = _create_csv_bytes(headers, rows)

        preview = service.generate_preview(file_content, "test.csv")

        assert len(preview.rows) == PREVIEW_ROW_COUNT
        assert preview.rows[0] == ["INV001", "100.00", "2024-01-01"]
        assert preview.rows[9] == ["INV010", "1000.00", "2024-01-10"]

    def test_returns_fewer_rows_if_file_has_less_than_10(self, service):
        """Preview returns all rows if file has fewer than 10."""
        headers = ["Col1", "Col2"]
        rows = [["a", "b"], ["c", "d"], ["e", "f"]]
        file_content = _create_csv_bytes(headers, rows)

        preview = service.generate_preview(file_content, "small.csv")

        assert len(preview.rows) == 3

    def test_returns_correct_headers(self, service):
        """Preview includes the file headers."""
        headers = ["Invoice No", "Amount", "Date", "Description"]
        rows = [["INV001", "100", "2024-01-01", "Test"]]
        file_content = _create_csv_bytes(headers, rows)

        preview = service.generate_preview(file_content, "test.csv")

        assert preview.headers == ["Invoice No", "Amount", "Date", "Description"]

    def test_returns_total_row_count(self, service):
        """Preview includes the total row count (excluding header)."""
        headers = ["A", "B"]
        rows = [["1", "2"]] * 50
        file_content = _create_csv_bytes(headers, rows)

        preview = service.generate_preview(file_content, "large.csv")

        assert preview.total_row_count == 50
        assert len(preview.rows) == 10

    def test_returns_filename(self, service):
        """Preview includes the original filename."""
        headers = ["A"]
        rows = [["1"]]
        file_content = _create_csv_bytes(headers, rows)

        preview = service.generate_preview(file_content, "vendor_statement.csv")

        assert preview.filename == "vendor_statement.csv"

    def test_empty_file_raises_error(self, service):
        """Empty file raises ValueError."""
        with pytest.raises(ValueError, match="empty"):
            service.generate_preview(b"", "empty.csv")

    def test_header_only_file_returns_zero_rows(self, service):
        """File with only headers returns preview with 0 rows."""
        file_content = "Invoice No,Amount,Date\n".encode("utf-8")

        preview = service.generate_preview(file_content, "headers_only.csv")

        assert preview.headers == ["Invoice No", "Amount", "Date"]
        assert preview.rows == []
        assert preview.total_row_count == 0

    def test_handles_whitespace_in_cells(self, service):
        """Whitespace in cell values is stripped."""
        headers = ["Name", "Value"]
        rows = [["  Hello  ", "  World  "]]
        file_content = _create_csv_bytes(headers, rows)

        preview = service.generate_preview(file_content, "test.csv")

        assert preview.rows[0] == ["Hello", "World"]

    def test_handles_latin1_encoding(self, service):
        """Latin-1 encoded files are handled correctly."""
        content = "Name,Amount\nCafé,100\n".encode("latin-1")

        preview = service.generate_preview(content, "latin.csv")

        assert preview.headers == ["Name", "Amount"]
        assert preview.rows[0][0] == "Café"


# ──────────────────────────────────────────────────────────────────────────────
# Tests: generate_preview() - Excel
# ──────────────────────────────────────────────────────────────────────────────


class TestGeneratePreviewExcel:
    """Tests for Excel file preview generation."""

    def test_unsupported_format_raises_error(self, service):
        """Unsupported file format raises ValueError."""
        with pytest.raises(ValueError, match="Unsupported file format"):
            service.generate_preview(b"content", "file.pdf")

    def test_xlsx_without_openpyxl_raises_error(self, service):
        """Excel preview raises error when openpyxl is not available."""
        with patch.dict("sys.modules", {"openpyxl": None}):
            with pytest.raises((ValueError, ImportError)):
                service.generate_preview(b"\x50\x4b", "test.xlsx")


# ──────────────────────────────────────────────────────────────────────────────
# Tests: auto_map_columns() - Exact Matches
# ──────────────────────────────────────────────────────────────────────────────


class TestAutoMapColumnsExact:
    """Tests for exact header matching with high confidence."""

    def test_exact_match_invoice_no(self, service):
        """Requirement 11.1: 'Invoice No' matches INVOICE with High confidence."""
        suggestions = service.auto_map_columns(["Invoice No"])

        assert len(suggestions) == 1
        assert suggestions[0].suggested_tag == TransactionTypeTag.INVOICE
        assert suggestions[0].confidence == ConfidenceLevel.HIGH

    def test_exact_match_case_insensitive(self, service):
        """Matching is case-insensitive."""
        suggestions = service.auto_map_columns(["INVOICE NO"])

        assert suggestions[0].suggested_tag == TransactionTypeTag.INVOICE
        assert suggestions[0].confidence == ConfidenceLevel.HIGH

    def test_exact_match_amount(self, service):
        """'Amount' matches AMOUNT with High confidence."""
        suggestions = service.auto_map_columns(["Amount"])

        assert suggestions[0].suggested_tag == TransactionTypeTag.AMOUNT
        assert suggestions[0].confidence == ConfidenceLevel.HIGH

    def test_exact_match_date(self, service):
        """'Date' matches DATE with High confidence."""
        suggestions = service.auto_map_columns(["Date"])

        assert suggestions[0].suggested_tag == TransactionTypeTag.DATE
        assert suggestions[0].confidence == ConfidenceLevel.HIGH

    def test_exact_match_description(self, service):
        """'Description' matches DESCRIPTION with High confidence."""
        suggestions = service.auto_map_columns(["Description"])

        assert suggestions[0].suggested_tag == TransactionTypeTag.DESCRIPTION
        assert suggestions[0].confidence == ConfidenceLevel.HIGH

    def test_exact_match_tds(self, service):
        """'TDS' matches TDS with High confidence."""
        suggestions = service.auto_map_columns(["TDS"])

        assert suggestions[0].suggested_tag == TransactionTypeTag.TDS
        assert suggestions[0].confidence == ConfidenceLevel.HIGH

    def test_exact_match_payment_ref(self, service):
        """'Payment Ref' matches PAYMENT with High confidence."""
        suggestions = service.auto_map_columns(["Payment Ref"])

        assert suggestions[0].suggested_tag == TransactionTypeTag.PAYMENT
        assert suggestions[0].confidence == ConfidenceLevel.HIGH

    def test_exact_match_credit_note(self, service):
        """'Credit Note' matches CREDIT_NOTE with High confidence."""
        suggestions = service.auto_map_columns(["Credit Note"])

        assert suggestions[0].suggested_tag == TransactionTypeTag.CREDIT_NOTE
        assert suggestions[0].confidence == ConfidenceLevel.HIGH

    def test_exact_match_debit_note(self, service):
        """'Debit Note' matches DEBIT_NOTE with High confidence."""
        suggestions = service.auto_map_columns(["Debit Note"])

        assert suggestions[0].suggested_tag == TransactionTypeTag.DEBIT_NOTE
        assert suggestions[0].confidence == ConfidenceLevel.HIGH

    def test_exact_match_utr(self, service):
        """'UTR' matches PAYMENT with High confidence."""
        suggestions = service.auto_map_columns(["UTR"])

        assert suggestions[0].suggested_tag == TransactionTypeTag.PAYMENT
        assert suggestions[0].confidence == ConfidenceLevel.HIGH

    def test_exact_match_narration(self, service):
        """'Narration' matches DESCRIPTION with High confidence."""
        suggestions = service.auto_map_columns(["Narration"])

        assert suggestions[0].suggested_tag == TransactionTypeTag.DESCRIPTION
        assert suggestions[0].confidence == ConfidenceLevel.HIGH


# ──────────────────────────────────────────────────────────────────────────────
# Tests: auto_map_columns() - Confidence Levels
# ──────────────────────────────────────────────────────────────────────────────


class TestAutoMapColumnsConfidence:
    """Tests for confidence level assignment."""

    def test_high_confidence_preselects(self, service):
        """Requirement 11.3: High confidence → pre-select in dropdown."""
        suggestions = service.auto_map_columns(["Invoice No"])

        assert suggestions[0].confidence == ConfidenceLevel.HIGH
        assert suggestions[0].should_preselect is True

    def test_medium_confidence_does_not_preselect(self, service):
        """Requirement 11.4: Medium confidence → suggestion without pre-selecting."""
        suggestions = service.auto_map_columns(["Reference"])

        assert suggestions[0].confidence == ConfidenceLevel.MEDIUM
        assert suggestions[0].should_preselect is False

    def test_no_match_returns_none_confidence(self, service):
        """Unrecognized headers get None tag and confidence."""
        suggestions = service.auto_map_columns(["XYZ_UNKNOWN_COL"])

        assert suggestions[0].suggested_tag is None
        assert suggestions[0].confidence is None
        assert suggestions[0].should_preselect is False

    def test_contains_match_returns_medium_confidence(self, service):
        """Header containing a known header gets Medium confidence."""
        suggestions = service.auto_map_columns(["Vendor Invoice Number Details"])

        assert suggestions[0].suggested_tag == TransactionTypeTag.INVOICE
        assert suggestions[0].confidence == ConfidenceLevel.MEDIUM


# ──────────────────────────────────────────────────────────────────────────────
# Tests: auto_map_columns() - Multiple Columns
# ──────────────────────────────────────────────────────────────────────────────


class TestAutoMapColumnsMultiple:
    """Tests for mapping multiple columns at once."""

    def test_maps_multiple_columns(self, service):
        """Maps multiple columns in a single call."""
        headers = ["Invoice No", "Amount", "Date", "Narration", "Misc"]
        suggestions = service.auto_map_columns(headers)

        assert len(suggestions) == 5
        assert suggestions[0].suggested_tag == TransactionTypeTag.INVOICE
        assert suggestions[1].suggested_tag == TransactionTypeTag.AMOUNT
        assert suggestions[2].suggested_tag == TransactionTypeTag.DATE
        assert suggestions[3].suggested_tag == TransactionTypeTag.DESCRIPTION
        assert suggestions[4].suggested_tag is None

    def test_column_index_is_correct(self, service):
        """Each suggestion has the correct column_index."""
        headers = ["A", "Invoice No", "B"]
        suggestions = service.auto_map_columns(headers)

        assert suggestions[0].column_index == 0
        assert suggestions[1].column_index == 1
        assert suggestions[2].column_index == 2

    def test_preserves_original_header_name(self, service):
        """Suggestions preserve the original header string."""
        headers = ["  Invoice No  ", "AMOUNT"]
        suggestions = service.auto_map_columns(headers)

        assert suggestions[0].header == "  Invoice No  "
        assert suggestions[1].header == "AMOUNT"

    def test_empty_header_returns_no_suggestion(self, service):
        """Empty or whitespace-only headers return None."""
        headers = ["", "   ", "Invoice No"]
        suggestions = service.auto_map_columns(headers)

        assert suggestions[0].suggested_tag is None
        assert suggestions[1].suggested_tag is None
        assert suggestions[2].suggested_tag == TransactionTypeTag.INVOICE


# ──────────────────────────────────────────────────────────────────────────────
# Tests: apply_template()
# ──────────────────────────────────────────────────────────────────────────────


class TestApplyTemplate:
    """Tests for template application."""

    @pytest.mark.asyncio
    async def test_returns_none_when_no_template_exists(self, service, mock_template_repo):
        """Requirement 10.2: Returns None when no template saved for vendor."""
        mock_template_repo.get_by_vendor.return_value = None

        result = await service.apply_template(uuid4())

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_mapping_from_saved_template(self, service, mock_template_repo):
        """Requirement 10.2: Auto-apply saved template for returning vendor."""
        vendor_id = uuid4()
        template_mock = MagicMock()
        template_mock.mapping_config = [
            {"column_index": 0, "header": "Invoice No", "tag": "INVOICE"},
            {"column_index": 1, "header": "Amount", "tag": "AMOUNT"},
        ]
        mock_template_repo.get_by_vendor.return_value = template_mock

        result = await service.apply_template(vendor_id)

        assert result is not None
        assert len(result.mappings) == 2
        assert result.mappings[0].tag == TransactionTypeTag.INVOICE
        assert result.mappings[1].tag == TransactionTypeTag.AMOUNT

    @pytest.mark.asyncio
    async def test_returns_none_for_invalid_mapping_config(self, service, mock_template_repo):
        """Returns None if mapping_config is not a list."""
        vendor_id = uuid4()
        template_mock = MagicMock()
        template_mock.mapping_config = {"invalid": "format"}
        mock_template_repo.get_by_vendor.return_value = template_mock

        result = await service.apply_template(vendor_id)

        assert result is None


# ──────────────────────────────────────────────────────────────────────────────
# Tests: save_template()
# ──────────────────────────────────────────────────────────────────────────────


class TestSaveTemplate:
    """Tests for template saving."""

    @pytest.mark.asyncio
    async def test_saves_template_with_correct_data(self, service, mock_template_repo):
        """Requirement 10.1: Save mapping as template associated with vendor."""
        vendor_id = uuid4()
        mapping = ColumnMapping(mappings=[
            ColumnMappingEntry(column_index=0, header="Invoice No", tag=TransactionTypeTag.INVOICE),
            ColumnMappingEntry(column_index=1, header="Amount", tag=TransactionTypeTag.AMOUNT),
        ])

        await service.save_template(vendor_id, mapping, created_by="finance_user")

        mock_template_repo.save.assert_called_once()
        call_args = mock_template_repo.save.call_args[0][0]
        assert call_args["vendor_id"] == vendor_id
        assert call_args["created_by"] == "finance_user"
        assert len(call_args["mapping_config"]) == 2
        assert call_args["mapping_config"][0]["tag"] == "INVOICE"
        assert call_args["mapping_config"][1]["tag"] == "AMOUNT"

    @pytest.mark.asyncio
    async def test_save_template_default_created_by(self, service, mock_template_repo):
        """Default created_by is 'system' when not specified."""
        vendor_id = uuid4()
        mapping = ColumnMapping(mappings=[])

        await service.save_template(vendor_id, mapping)

        call_args = mock_template_repo.save.call_args[0][0]
        assert call_args["created_by"] == "system"


# ──────────────────────────────────────────────────────────────────────────────
# Tests: ColumnMapping data class
# ──────────────────────────────────────────────────────────────────────────────


class TestColumnMapping:
    """Tests for ColumnMapping serialization."""

    def test_to_dict_list(self):
        """Serializes to a list of dicts."""
        mapping = ColumnMapping(mappings=[
            ColumnMappingEntry(column_index=0, header="Invoice No", tag=TransactionTypeTag.INVOICE),
            ColumnMappingEntry(column_index=1, header="Amt", tag=TransactionTypeTag.AMOUNT),
        ])

        result = mapping.to_dict_list()

        assert result == [
            {"column_index": 0, "header": "Invoice No", "tag": "INVOICE"},
            {"column_index": 1, "header": "Amt", "tag": "AMOUNT"},
        ]

    def test_from_dict_list(self):
        """Deserializes from a list of dicts."""
        data = [
            {"column_index": 0, "header": "Date", "tag": "DATE"},
            {"column_index": 1, "header": "TDS", "tag": "TDS"},
        ]

        mapping = ColumnMapping.from_dict_list(data)

        assert len(mapping.mappings) == 2
        assert mapping.mappings[0].tag == TransactionTypeTag.DATE
        assert mapping.mappings[1].tag == TransactionTypeTag.TDS

    def test_roundtrip_serialization(self):
        """Serialize and deserialize produces identical mapping."""
        original = ColumnMapping(mappings=[
            ColumnMappingEntry(column_index=i, header=f"Col{i}", tag=tag)
            for i, tag in enumerate(TransactionTypeTag)
        ])

        restored = ColumnMapping.from_dict_list(original.to_dict_list())

        assert len(restored.mappings) == len(original.mappings)
        for orig, rest in zip(original.mappings, restored.mappings):
            assert orig.column_index == rest.column_index
            assert orig.header == rest.header
            assert orig.tag == rest.tag


# ──────────────────────────────────────────────────────────────────────────────
# Tests: HeaderLibrary
# ──────────────────────────────────────────────────────────────────────────────


class TestHeaderLibrary:
    """Tests for the header library configuration."""

    def test_default_library_has_entries(self):
        """Default library is pre-populated."""
        library = HeaderLibrary()
        assert len(library.entries) > 0

    def test_custom_library(self):
        """Custom entries can be provided."""
        custom_entries = [
            HeaderLibraryEntry(
                known_headers=["custom_col"],
                tag=TransactionTypeTag.IGNORE,
                confidence=ConfidenceLevel.LOW,
            )
        ]
        library = HeaderLibrary(entries=custom_entries)
        assert len(library.entries) == 1
        assert library.entries[0].tag == TransactionTypeTag.IGNORE

    def test_default_library_covers_all_brd_headers(self):
        """Default library includes all BRD Table 22 headers."""
        library = HeaderLibrary()
        all_known_headers = [
            h.lower()
            for entry in library.entries
            for h in entry.known_headers
        ]

        # BRD Table 22 specified headers
        brd_headers = [
            "invoice no", "inv no", "invoice number", "bill no",
            "payment ref", "utr", "neft ref", "cheque no",
            "amount", "amt", "value", "total",
            "date", "posting date", "doc date", "invoice date",
            "description", "narration", "particulars", "text",
            "tds", "tax deducted", "withholding tax",
            "credit note", "cn",
            "debit note", "dn",
        ]

        for header in brd_headers:
            assert header in all_known_headers, f"BRD header '{header}' not in library"
