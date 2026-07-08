"""
Column mapping service for vendor statement uploads.

Handles file preview generation, auto-mapping of column headers
to transaction type tags, and template persistence per vendor.

Requirements: 9.1, 9.2, 9.3, 10.1, 10.2, 10.3, 11.1, 11.2, 11.3, 11.4
"""

import csv
import io
from dataclasses import dataclass, field
from enum import Enum
from uuid import UUID


# ──────────────────────────────────────────────────────────────────────────────
# Enums and Constants
# ──────────────────────────────────────────────────────────────────────────────


class TransactionTypeTag(str, Enum):
    """12 transaction type tags for column mapping."""

    INVOICE = "INVOICE"
    PAYMENT = "PAYMENT"
    TDS = "TDS"
    CREDIT_NOTE = "CREDIT_NOTE"
    DEBIT_NOTE = "DEBIT_NOTE"
    OPENING_BALANCE = "OPENING_BALANCE"
    CLOSING_BALANCE = "CLOSING_BALANCE"
    DATE = "DATE"
    REFERENCE = "REFERENCE"
    AMOUNT = "AMOUNT"
    DESCRIPTION = "DESCRIPTION"
    IGNORE = "IGNORE"


class ConfidenceLevel(str, Enum):
    """Confidence level for auto-mapping suggestions."""

    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"


# Maximum number of preview rows to return
PREVIEW_ROW_COUNT = 10


# ──────────────────────────────────────────────────────────────────────────────
# Data Classes
# ──────────────────────────────────────────────────────────────────────────────


@dataclass
class FilePreview:
    """Preview of an uploaded file showing headers and first N rows."""

    headers: list[str]
    rows: list[list[str]]
    total_row_count: int
    filename: str


@dataclass
class ColumnSuggestion:
    """Auto-mapping suggestion for a single column."""

    column_index: int
    header: str
    suggested_tag: TransactionTypeTag | None
    confidence: ConfidenceLevel | None

    @property
    def should_preselect(self) -> bool:
        """High confidence suggestions are pre-selected in the dropdown."""
        return self.confidence == ConfidenceLevel.HIGH


@dataclass
class ColumnMappingEntry:
    """A single column-to-tag mapping entry."""

    column_index: int
    header: str
    tag: TransactionTypeTag


@dataclass
class ColumnMapping:
    """Complete column mapping configuration for a vendor file."""

    mappings: list[ColumnMappingEntry] = field(default_factory=list)

    def to_dict_list(self) -> list[dict]:
        """Serialize to a list of dicts for persistence."""
        return [
            {
                "column_index": m.column_index,
                "header": m.header,
                "tag": m.tag.value,
            }
            for m in self.mappings
        ]

    @classmethod
    def from_dict_list(cls, data: list[dict]) -> "ColumnMapping":
        """Deserialize from a list of dicts."""
        mappings = [
            ColumnMappingEntry(
                column_index=item["column_index"],
                header=item["header"],
                tag=TransactionTypeTag(item["tag"]),
            )
            for item in data
        ]
        return cls(mappings=mappings)


# ──────────────────────────────────────────────────────────────────────────────
# Header Library
# ──────────────────────────────────────────────────────────────────────────────


@dataclass
class HeaderLibraryEntry:
    """A single entry in the known header library."""

    known_headers: list[str]
    tag: TransactionTypeTag
    confidence: ConfidenceLevel


class HeaderLibrary:
    """
    Known header library for auto-mapping intelligence.

    Maps common column header names to transaction type tags with
    confidence levels based on BRD Table 22.
    """

    def __init__(self, entries: list[HeaderLibraryEntry] | None = None) -> None:
        if entries is not None:
            self._entries = entries
        else:
            self._entries = self._default_entries()

    @staticmethod
    def _default_entries() -> list[HeaderLibraryEntry]:
        """Default header library from BRD Table 22."""
        return [
            HeaderLibraryEntry(
                known_headers=[
                    "invoice no", "inv no", "invoice number", "bill no",
                    "invoice", "inv num", "bill number", "invoice ref",
                ],
                tag=TransactionTypeTag.INVOICE,
                confidence=ConfidenceLevel.HIGH,
            ),
            HeaderLibraryEntry(
                known_headers=[
                    "payment ref", "utr", "neft ref", "cheque no",
                    "payment reference", "payment no", "pay ref",
                    "cheque number", "utr no", "utr number",
                ],
                tag=TransactionTypeTag.PAYMENT,
                confidence=ConfidenceLevel.HIGH,
            ),
            HeaderLibraryEntry(
                known_headers=[
                    "amount", "amt", "value", "total",
                    "net amount", "gross amount", "invoice amount",
                    "debit", "credit",
                ],
                tag=TransactionTypeTag.AMOUNT,
                confidence=ConfidenceLevel.HIGH,
            ),
            HeaderLibraryEntry(
                known_headers=[
                    "date", "posting date", "doc date", "invoice date",
                    "transaction date", "entry date", "document date",
                    "payment date", "value date",
                ],
                tag=TransactionTypeTag.DATE,
                confidence=ConfidenceLevel.HIGH,
            ),
            HeaderLibraryEntry(
                known_headers=[
                    "description", "narration", "particulars", "text",
                    "remarks", "narrative", "details", "memo",
                ],
                tag=TransactionTypeTag.DESCRIPTION,
                confidence=ConfidenceLevel.HIGH,
            ),
            HeaderLibraryEntry(
                known_headers=[
                    "tds", "tax deducted", "withholding tax",
                    "tds amount", "tax deducted at source",
                ],
                tag=TransactionTypeTag.TDS,
                confidence=ConfidenceLevel.HIGH,
            ),
            HeaderLibraryEntry(
                known_headers=[
                    "credit note", "cn", "credit memo",
                    "credit note no", "cn no", "cn number",
                ],
                tag=TransactionTypeTag.CREDIT_NOTE,
                confidence=ConfidenceLevel.HIGH,
            ),
            HeaderLibraryEntry(
                known_headers=[
                    "debit note", "dn", "debit memo",
                    "debit note no", "dn no", "dn number",
                ],
                tag=TransactionTypeTag.DEBIT_NOTE,
                confidence=ConfidenceLevel.HIGH,
            ),
            HeaderLibraryEntry(
                known_headers=[
                    "reference", "ref", "ref no", "reference number",
                    "ref number", "document number", "doc no",
                ],
                tag=TransactionTypeTag.REFERENCE,
                confidence=ConfidenceLevel.MEDIUM,
            ),
            HeaderLibraryEntry(
                known_headers=[
                    "opening balance", "opening bal", "op bal",
                    "opening", "ob",
                ],
                tag=TransactionTypeTag.OPENING_BALANCE,
                confidence=ConfidenceLevel.MEDIUM,
            ),
            HeaderLibraryEntry(
                known_headers=[
                    "closing balance", "closing bal", "cl bal",
                    "closing", "cb",
                ],
                tag=TransactionTypeTag.CLOSING_BALANCE,
                confidence=ConfidenceLevel.MEDIUM,
            ),
        ]

    @property
    def entries(self) -> list[HeaderLibraryEntry]:
        """Get all library entries."""
        return self._entries


# ──────────────────────────────────────────────────────────────────────────────
# Column Mapping Service
# ──────────────────────────────────────────────────────────────────────────────


class ColumnMappingService:
    """
    Maps uploaded vendor statement columns to transaction type tags.

    Provides:
    - File preview (first 10 rows)
    - Auto-mapping intelligence using header library
    - Template persistence per vendor
    - Template auto-application for returning vendors
    """

    def __init__(
        self,
        template_repository: "IColumnMappingTemplateRepository",
        header_library: HeaderLibrary | None = None,
    ) -> None:
        from src.domain.repositories.vlr.column_mapping_template_repository import (
            IColumnMappingTemplateRepository,
        )

        self._template_repo = template_repository
        self._header_library = header_library or HeaderLibrary()

    def generate_preview(self, file_content: bytes, filename: str) -> FilePreview:
        """
        Return first 10 rows of an uploaded file.

        Supports CSV and Excel (.xlsx) formats.

        Args:
            file_content: Raw bytes of the uploaded file.
            filename: Original filename (used for type detection).

        Returns:
            FilePreview containing headers and up to 10 data rows.

        Raises:
            ValueError: If the file format is unsupported or cannot be parsed.
        """
        lower_name = filename.lower()

        if lower_name.endswith(".csv"):
            return self._preview_csv(file_content, filename)
        elif lower_name.endswith(".xlsx"):
            return self._preview_excel(file_content, filename)
        else:
            raise ValueError(
                f"Unsupported file format: {filename}. Only CSV and XLSX are supported."
            )

    def auto_map_columns(self, headers: list[str]) -> list[ColumnSuggestion]:
        """
        Compare headers against known header library, assign confidence scores.

        For each header:
        - Exact match (case-insensitive) → High confidence
        - Substring/contains match → Medium confidence
        - Partial word overlap → Low confidence
        - No match → suggestion is None

        Args:
            headers: List of column header strings from the uploaded file.

        Returns:
            List of ColumnSuggestion objects, one per header.
        """
        suggestions: list[ColumnSuggestion] = []

        for col_idx, header in enumerate(headers):
            suggestion = self._match_header(col_idx, header)
            suggestions.append(suggestion)

        return suggestions

    async def apply_template(self, vendor_id: UUID) -> ColumnMapping | None:
        """
        Load and apply saved template for a vendor.

        Args:
            vendor_id: UUID of the vendor.

        Returns:
            ColumnMapping if a template exists, None otherwise.
        """
        template = await self._template_repo.get_by_vendor(vendor_id)
        if template is None:
            return None

        mapping_config = template.mapping_config
        if not isinstance(mapping_config, list):
            return None

        return ColumnMapping.from_dict_list(mapping_config)

    async def save_template(
        self,
        vendor_id: UUID,
        mapping: ColumnMapping,
        created_by: str = "system",
    ) -> None:
        """
        Persist column mapping as vendor template.

        If a template already exists for the vendor, it is updated.

        Args:
            vendor_id: UUID of the vendor.
            mapping: The column mapping to save.
            created_by: Username of the person saving the template.
        """
        template_data = {
            "vendor_id": vendor_id,
            "mapping_config": mapping.to_dict_list(),
            "created_by": created_by,
        }
        await self._template_repo.save(template_data)

    # ──────────────────────────────────────────────────────────────────────────
    # Private Methods
    # ──────────────────────────────────────────────────────────────────────────

    def _preview_csv(self, file_content: bytes, filename: str) -> FilePreview:
        """Parse CSV and return preview."""
        try:
            text_content = file_content.decode("utf-8")
        except UnicodeDecodeError:
            text_content = file_content.decode("latin-1")

        reader = csv.reader(io.StringIO(text_content))
        all_rows = list(reader)

        if not all_rows:
            raise ValueError("File is empty or has no header row.")

        headers = [h.strip() for h in all_rows[0]]
        data_rows = all_rows[1:]

        # Return up to PREVIEW_ROW_COUNT rows
        preview_rows = [
            [cell.strip() for cell in row]
            for row in data_rows[:PREVIEW_ROW_COUNT]
        ]

        # Ensure all rows have the same number of columns as headers
        for i, row in enumerate(preview_rows):
            if len(row) < len(headers):
                preview_rows[i] = row + [""] * (len(headers) - len(row))
            elif len(row) > len(headers):
                preview_rows[i] = row[:len(headers)]

        return FilePreview(
            headers=headers,
            rows=preview_rows,
            total_row_count=len(data_rows),
            filename=filename,
        )

    def _preview_excel(self, file_content: bytes, filename: str) -> FilePreview:
        """Parse Excel (.xlsx) and return preview."""
        try:
            import openpyxl
        except ImportError:
            raise ValueError(
                "Excel file support requires the 'openpyxl' library."
            )

        workbook = openpyxl.load_workbook(
            io.BytesIO(file_content), read_only=True, data_only=True
        )
        sheet = workbook.active

        if sheet is None:
            workbook.close()
            raise ValueError("Excel file has no active worksheet.")

        rows = list(sheet.iter_rows(values_only=True))
        workbook.close()

        if not rows:
            raise ValueError("File is empty or has no header row.")

        # First row is headers
        headers = [
            str(h).strip() if h is not None else ""
            for h in rows[0]
        ]
        data_rows = rows[1:]

        # Return up to PREVIEW_ROW_COUNT rows
        preview_rows: list[list[str]] = []
        for row in data_rows[:PREVIEW_ROW_COUNT]:
            str_row = [
                str(cell).strip() if cell is not None else ""
                for cell in row
            ]
            # Normalize row length to match headers
            if len(str_row) < len(headers):
                str_row = str_row + [""] * (len(headers) - len(str_row))
            elif len(str_row) > len(headers):
                str_row = str_row[:len(headers)]
            preview_rows.append(str_row)

        return FilePreview(
            headers=headers,
            rows=preview_rows,
            total_row_count=len(data_rows),
            filename=filename,
        )

    def _match_header(self, col_idx: int, header: str) -> ColumnSuggestion:
        """
        Match a single header against the header library.

        Matching strategy (in priority order):
        1. Exact match (case-insensitive) → uses entry's defined confidence
        2. Header contains a known header as substring → Medium confidence
        3. Known header contains the file header as substring → Low confidence
        4. No match → None tag and confidence
        """
        normalized_header = header.strip().lower()

        if not normalized_header:
            return ColumnSuggestion(
                column_index=col_idx,
                header=header,
                suggested_tag=None,
                confidence=None,
            )

        # Try exact match first (highest priority)
        best_match: tuple[TransactionTypeTag, ConfidenceLevel] | None = None

        for entry in self._header_library.entries:
            for known_header in entry.known_headers:
                known_lower = known_header.lower()

                # Exact match
                if normalized_header == known_lower:
                    return ColumnSuggestion(
                        column_index=col_idx,
                        header=header,
                        suggested_tag=entry.tag,
                        confidence=entry.confidence,
                    )

        # Try contains match: file header contains a known header
        for entry in self._header_library.entries:
            for known_header in entry.known_headers:
                known_lower = known_header.lower()
                if known_lower in normalized_header and len(known_lower) >= 3:
                    if best_match is None:
                        best_match = (entry.tag, ConfidenceLevel.MEDIUM)
                    break
            if best_match:
                break

        # Try reverse contains: known header contains the file header
        if best_match is None:
            for entry in self._header_library.entries:
                for known_header in entry.known_headers:
                    known_lower = known_header.lower()
                    if (
                        normalized_header in known_lower
                        and len(normalized_header) >= 3
                    ):
                        best_match = (entry.tag, ConfidenceLevel.LOW)
                        break
                if best_match:
                    break

        if best_match:
            return ColumnSuggestion(
                column_index=col_idx,
                header=header,
                suggested_tag=best_match[0],
                confidence=best_match[1],
            )

        return ColumnSuggestion(
            column_index=col_idx,
            header=header,
            suggested_tag=None,
            confidence=None,
        )
