"""
File parser service for validating and parsing vendor/company ledger files.

Supports CSV and Excel (.xlsx) file formats with:
- File type detection
- File size limit enforcement (10MB)
- Mandatory column validation
- Configurable field mapping
- Entry parsing into LedgerEntry-compatible data structures

Requirements: 1.2, 1.4, 4.3, 4.4, 16.5, 17.5
"""

import csv
import io
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import IO, Any

from src.domain.exceptions.vlr import FileValidationException


class FileType(str, Enum):
    """Supported file types for ledger uploads."""

    CSV = "csv"
    EXCEL = "xlsx"


# Default maximum file size: 10MB
MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024

# Mandatory columns that must exist in uploaded files
MANDATORY_COLUMNS = frozenset(
    ["document_number", "amount", "posting_date", "reference_number"]
)

# Default field mapping: maps internal field names to expected CSV/Excel column headers
# Keys are internal LedgerEntry field names, values are lists of acceptable header names
DEFAULT_FIELD_MAPPING: dict[str, list[str]] = {
    "document_number": ["document_number", "doc_number", "doc_no", "belnr"],
    "amount": ["amount", "amt", "dmbtr", "value"],
    "posting_date": ["posting_date", "post_date", "budat", "date"],
    "reference_number": ["reference_number", "ref_number", "ref_no", "zuonr"],
    "document_type": ["document_type", "doc_type", "blart", "type"],
    "clearing_date": ["clearing_date", "clear_date", "augdt"],
    "clearing_document": ["clearing_document", "clear_doc", "augbl"],
    "assignment_number": ["assignment_number", "assignment", "zuonr_assign"],
    "currency": ["currency", "curr", "waers"],
    "description": ["description", "desc", "text", "narration"],
}


@dataclass
class ParsedLedgerEntry:
    """
    Parsed ledger entry from a file upload.

    Maps to LedgerEntry model fields for database storage.
    """

    document_number: str
    amount: Decimal
    posting_date: date
    reference_number: str
    document_type: str | None = None
    clearing_date: date | None = None
    clearing_document: str | None = None
    assignment_number: str | None = None
    currency: str = "INR"
    description: str | None = None


@dataclass
class FileValidationResult:
    """Result of file validation - either success with entries or failure with errors."""

    is_valid: bool
    entries: list[ParsedLedgerEntry] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    row_count: int = 0
    file_type: FileType | None = None


class FileParserService:
    """
    Service for validating and parsing uploaded ledger files.

    Supports CSV and Excel formats with configurable field mapping
    and mandatory column validation.
    """

    def __init__(
        self,
        field_mapping: dict[str, list[str]] | None = None,
        max_file_size_bytes: int = MAX_FILE_SIZE_BYTES,
    ) -> None:
        """
        Initialize the file parser service.

        Args:
            field_mapping: Custom field mapping overriding defaults.
                           Keys are internal field names, values are lists
                           of acceptable CSV/Excel column header names.
            max_file_size_bytes: Maximum allowed file size in bytes (default 10MB).
        """
        self.field_mapping = field_mapping or DEFAULT_FIELD_MAPPING
        self.max_file_size_bytes = max_file_size_bytes

    def detect_file_type(self, filename: str) -> FileType:
        """
        Detect the file type from its filename extension.

        Args:
            filename: Name of the uploaded file.

        Returns:
            FileType enum value.

        Raises:
            FileValidationException: If the file type is not supported.
        """
        lower_name = filename.lower()
        if lower_name.endswith(".csv"):
            return FileType.CSV
        elif lower_name.endswith(".xlsx"):
            return FileType.EXCEL
        elif lower_name.endswith(".xls"):
            raise FileValidationException(
                errors=["Unsupported file type: .xls. Please use .xlsx or .csv format."]
            )
        else:
            extension = lower_name.rsplit(".", 1)[-1] if "." in lower_name else "unknown"
            raise FileValidationException(
                errors=[
                    f"Unsupported file type: .{extension}. "
                    "Only CSV (.csv) and Excel (.xlsx) formats are accepted."
                ]
            )

    def validate_file_size(self, file_content: bytes) -> None:
        """
        Validate that the file does not exceed the size limit.

        Args:
            file_content: Raw file bytes.

        Raises:
            FileValidationException: If file exceeds size limit.
        """
        if len(file_content) > self.max_file_size_bytes:
            size_mb = len(file_content) / (1024 * 1024)
            limit_mb = self.max_file_size_bytes / (1024 * 1024)
            raise FileValidationException(
                errors=[
                    f"File size ({size_mb:.1f}MB) exceeds the maximum "
                    f"allowed size ({limit_mb:.0f}MB)."
                ]
            )

    def validate_and_parse(
        self,
        file_content: bytes,
        filename: str,
    ) -> FileValidationResult:
        """
        Validate and parse a ledger file.

        Performs the following checks in order:
        1. File type detection from filename
        2. File size validation
        3. Column structure validation (mandatory columns present)
        4. Row-level data parsing and validation

        Args:
            file_content: Raw bytes of the uploaded file.
            filename: Original filename (used for type detection).

        Returns:
            FileValidationResult with parsed entries or validation errors.

        Raises:
            FileValidationException: For fatal validation failures
                                     (unsupported type, size exceeded).
        """
        # Step 1: Detect file type
        file_type = self.detect_file_type(filename)

        # Step 2: Validate file size
        self.validate_file_size(file_content)

        # Step 3 & 4: Parse based on file type
        if file_type == FileType.CSV:
            return self._parse_csv(file_content, file_type)
        else:
            return self._parse_excel(file_content, file_type)

    def _parse_csv(
        self, file_content: bytes, file_type: FileType
    ) -> FileValidationResult:
        """Parse and validate a CSV file."""
        try:
            # Try UTF-8 first, then fall back to latin-1
            try:
                text_content = file_content.decode("utf-8")
            except UnicodeDecodeError:
                text_content = file_content.decode("latin-1")

            reader = csv.DictReader(io.StringIO(text_content))

            if reader.fieldnames is None:
                return FileValidationResult(
                    is_valid=False,
                    errors=["File is empty or has no header row."],
                    file_type=file_type,
                )

            # Normalize headers (strip whitespace, lowercase)
            raw_headers = [h.strip().lower() for h in reader.fieldnames]

            # Validate mandatory columns
            column_mapping = self._resolve_column_mapping(raw_headers)
            missing_columns = self._check_mandatory_columns(column_mapping)

            if missing_columns:
                return FileValidationResult(
                    is_valid=False,
                    errors=[
                        f"Missing mandatory column(s): {', '.join(sorted(missing_columns))}"
                    ],
                    file_type=file_type,
                )

            # Parse rows
            entries: list[ParsedLedgerEntry] = []
            row_errors: list[str] = []

            for row_idx, row in enumerate(reader, start=2):  # start=2 (header is row 1)
                # Normalize row keys
                normalized_row = {
                    k.strip().lower(): v.strip() if v else ""
                    for k, v in row.items()
                    if k is not None
                }

                entry_or_error = self._parse_row(normalized_row, column_mapping, row_idx)
                if isinstance(entry_or_error, str):
                    row_errors.append(entry_or_error)
                else:
                    entries.append(entry_or_error)

            if row_errors:
                return FileValidationResult(
                    is_valid=False,
                    errors=row_errors,
                    row_count=len(entries) + len(row_errors),
                    file_type=file_type,
                )

            return FileValidationResult(
                is_valid=True,
                entries=entries,
                row_count=len(entries),
                file_type=file_type,
            )

        except csv.Error as e:
            return FileValidationResult(
                is_valid=False,
                errors=[f"CSV parsing error: {e!s}"],
                file_type=file_type,
            )

    def _parse_excel(
        self, file_content: bytes, file_type: FileType
    ) -> FileValidationResult:
        """Parse and validate an Excel (.xlsx) file."""
        try:
            import openpyxl
        except ImportError:
            raise FileValidationException(
                errors=[
                    "Excel file support requires the 'openpyxl' library. "
                    "Please contact the system administrator."
                ]
            )

        try:
            workbook = openpyxl.load_workbook(
                io.BytesIO(file_content), read_only=True, data_only=True
            )
            sheet = workbook.active

            if sheet is None:
                return FileValidationResult(
                    is_valid=False,
                    errors=["Excel file has no active worksheet."],
                    file_type=file_type,
                )

            rows = list(sheet.iter_rows(values_only=True))

            if not rows:
                return FileValidationResult(
                    is_valid=False,
                    errors=["File is empty or has no header row."],
                    file_type=file_type,
                )

            # First row is the header
            raw_headers = [
                str(h).strip().lower() if h is not None else ""
                for h in rows[0]
            ]

            # Validate mandatory columns
            column_mapping = self._resolve_column_mapping(raw_headers)
            missing_columns = self._check_mandatory_columns(column_mapping)

            if missing_columns:
                return FileValidationResult(
                    is_valid=False,
                    errors=[
                        f"Missing mandatory column(s): {', '.join(sorted(missing_columns))}"
                    ],
                    file_type=file_type,
                )

            # Parse data rows
            entries: list[ParsedLedgerEntry] = []
            row_errors: list[str] = []

            for row_idx, row_data in enumerate(rows[1:], start=2):
                # Build a dict from header -> value
                row_dict: dict[str, str] = {}
                for col_idx, header in enumerate(raw_headers):
                    if col_idx < len(row_data):
                        cell_value = row_data[col_idx]
                        row_dict[header] = str(cell_value).strip() if cell_value is not None else ""
                    else:
                        row_dict[header] = ""

                # Skip entirely empty rows
                if all(v == "" or v == "None" for v in row_dict.values()):
                    continue

                entry_or_error = self._parse_row(row_dict, column_mapping, row_idx)
                if isinstance(entry_or_error, str):
                    row_errors.append(entry_or_error)
                else:
                    entries.append(entry_or_error)

            workbook.close()

            if row_errors:
                return FileValidationResult(
                    is_valid=False,
                    errors=row_errors,
                    row_count=len(entries) + len(row_errors),
                    file_type=file_type,
                )

            return FileValidationResult(
                is_valid=True,
                entries=entries,
                row_count=len(entries),
                file_type=file_type,
            )

        except Exception as e:
            if "openpyxl" in str(type(e).__module__):
                return FileValidationResult(
                    is_valid=False,
                    errors=[f"Excel parsing error: {e!s}"],
                    file_type=file_type,
                )
            raise

    def _resolve_column_mapping(
        self, headers: list[str]
    ) -> dict[str, str | None]:
        """
        Resolve the mapping from internal field names to actual column headers.

        For each internal field, finds the first matching header from the
        configured acceptable names.

        Args:
            headers: Normalized (lowercase, stripped) header names from the file.

        Returns:
            Dictionary mapping internal field names to matched header names (or None).
        """
        mapping: dict[str, str | None] = {}

        for internal_field, acceptable_names in self.field_mapping.items():
            matched_header: str | None = None
            for name in acceptable_names:
                if name.lower() in headers:
                    matched_header = name.lower()
                    break
            mapping[internal_field] = matched_header

        return mapping

    def _check_mandatory_columns(
        self, column_mapping: dict[str, str | None]
    ) -> list[str]:
        """
        Check that all mandatory columns are present in the resolved mapping.

        Returns:
            List of missing mandatory column names (empty if all present).
        """
        missing: list[str] = []
        for col_name in MANDATORY_COLUMNS:
            if column_mapping.get(col_name) is None:
                missing.append(col_name)
        return missing

    def _parse_row(
        self,
        row: dict[str, str],
        column_mapping: dict[str, str | None],
        row_number: int,
    ) -> ParsedLedgerEntry | str:
        """
        Parse a single row into a ParsedLedgerEntry.

        Args:
            row: Dictionary of column_header -> value for this row.
            column_mapping: Resolved mapping from internal fields to headers.
            row_number: Row number in the file (for error reporting).

        Returns:
            ParsedLedgerEntry on success, or error string on failure.
        """

        def get_value(field_name: str) -> str:
            header = column_mapping.get(field_name)
            if header is None:
                return ""
            return row.get(header, "")

        # Parse mandatory fields
        document_number = get_value("document_number")
        amount_str = get_value("amount")
        posting_date_str = get_value("posting_date")
        reference_number = get_value("reference_number")

        # Validate mandatory field values
        errors: list[str] = []

        if not document_number:
            errors.append("document_number is empty")

        if not amount_str:
            errors.append("amount is empty")

        if not posting_date_str:
            errors.append("posting_date is empty")

        if not reference_number:
            errors.append("reference_number is empty")

        if errors:
            return f"Row {row_number}: {'; '.join(errors)}"

        # Parse amount
        try:
            # Handle common numeric formats (commas as thousands separator)
            cleaned_amount = amount_str.replace(",", "")
            amount = Decimal(cleaned_amount)
        except (InvalidOperation, ValueError):
            return f"Row {row_number}: Invalid amount value '{amount_str}'"

        # Parse posting_date
        posting_date = self._parse_date(posting_date_str)
        if posting_date is None:
            return f"Row {row_number}: Invalid posting_date format '{posting_date_str}'"

        # Parse optional fields
        document_type = get_value("document_type") or None
        clearing_date_str = get_value("clearing_date")
        clearing_date = self._parse_date(clearing_date_str) if clearing_date_str else None
        clearing_document = get_value("clearing_document") or None
        assignment_number = get_value("assignment_number") or None
        currency = get_value("currency") or "INR"
        description = get_value("description") or None

        return ParsedLedgerEntry(
            document_number=document_number,
            amount=amount,
            posting_date=posting_date,
            reference_number=reference_number,
            document_type=document_type,
            clearing_date=clearing_date,
            clearing_document=clearing_document,
            assignment_number=assignment_number,
            currency=currency,
            description=description,
        )

    def _parse_date(self, date_str: str) -> date | None:
        """
        Parse a date string, supporting multiple common formats.

        Supported formats:
        - YYYY-MM-DD (ISO)
        - DD/MM/YYYY
        - DD-MM-YYYY
        - MM/DD/YYYY
        - DD.MM.YYYY

        Returns:
            date object on success, None on failure.
        """
        date_str = date_str.strip()
        if not date_str:
            return None

        formats = [
            "%Y-%m-%d",
            "%d/%m/%Y",
            "%d-%m-%Y",
            "%m/%d/%Y",
            "%d.%m.%Y",
            "%Y/%m/%d",
        ]

        for fmt in formats:
            try:
                return datetime.strptime(date_str, fmt).date()
            except ValueError:
                continue

        return None
