"""
Company ledger splitting service.

When a user uploads ONE consolidated company ledger file that contains
rows for multiple vendors (identified by PAN or vendor/party code), this
service figures out which row belongs to which vendor so each vendor's
ReconciliationCase only receives its own entries — which in turn means the
reconciliation engine (which already operates strictly per case_id) only
ever matches lines belonging to that one vendor.

This does NOT change matching logic itself: ReconciliationEngineService
already scopes to a single case_id. The only gap was that consolidated
uploads were dumping every row into the first case of the request.

Requirements: consolidated multi-vendor ledger upload + PAN-based
reconciliation scoping.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from src.domain.services.vlr.file_parser_service import ParsedLedgerEntry

# Column header aliases (lower-cased) that likely hold a PAN number.
PAN_HEADER_ALIASES: tuple[str, ...] = (
    "pan",
    "pan no",
    "pan no.",
    "pan number",
    "pan card no",
    "pan card number",
    "vendor pan",
    "party pan",
    "supplier pan",
    "vendor pan no",
    "party pan no",
    "pancard",
    "pan card",
)

# Column header aliases (lower-cased) that likely hold the vendor/party code.
VENDOR_CODE_HEADER_ALIASES: tuple[str, ...] = (
    "vendor code",
    "vendor_code",
    "party code",
    "party_code",
    "supplier code",
    "vendor id",
    "party id",
    "account code",
)

# Indian PAN format: 5 letters, 4 digits, 1 letter (e.g. ABCDE1234F).
PAN_PATTERN = re.compile(r"^[A-Za-z]{5}[0-9]{4}[A-Za-z]$")


def normalize_identifier(value: str | None) -> str:
    """Normalize a PAN/vendor-code value for comparison (trim + uppercase)."""
    return (value or "").strip().upper()


def detect_identifier_header(
    raw_headers: list[str],
    sample_rows: list[dict[str, str]],
) -> tuple[str | None, str | None]:
    """
    Determine which column (by its lower-cased header key) identifies the
    vendor for each row of a consolidated ledger, and whether it holds a
    PAN or a vendor/party code.

    Detection order:
      1. Header name matches a known PAN alias.
      2. Header name matches a known vendor/party-code alias.
      3. Sniff sample row values: if every non-blank value in a column is
         PAN-shaped, treat that column as the PAN column even if its header
         name isn't recognized.

    Args:
        raw_headers: Original (mixed-case) headers from the uploaded file.
        sample_rows: A handful of parsed rows (header_lower -> value) used
            for the value-sniffing fallback.

    Returns:
        (header_key_lower, "pan" | "vendor_code") or (None, None).
    """
    lower_headers = [h.strip().lower() for h in raw_headers if h and h.strip()]

    for h in lower_headers:
        if h in PAN_HEADER_ALIASES:
            return h, "pan"

    for h in lower_headers:
        if h in VENDOR_CODE_HEADER_ALIASES:
            return h, "vendor_code"

    # Fallback: sniff column values for PAN-shaped strings.
    if sample_rows:
        for h in lower_headers:
            values = [row.get(h, "") for row in sample_rows if row.get(h)]
            if not values:
                continue
            matches = sum(1 for v in values if PAN_PATTERN.match(v.strip()))
            if matches == len(values):
                return h, "pan"

    return None, None


@dataclass
class SplitResult:
    """Outcome of grouping a consolidated ledger's entries by identifier value."""

    # normalized identifier value -> entries carrying that value
    grouped: dict[str, list[ParsedLedgerEntry]] = field(default_factory=dict)
    # entries where the identifier column was blank/missing on that row
    blank_identifier: list[ParsedLedgerEntry] = field(default_factory=list)
    identifier_header: str = ""


def split_entries_by_identifier(
    entries: list[ParsedLedgerEntry],
    identifier_header: str,
) -> SplitResult:
    """
    Group parsed entries by the normalized value found in `identifier_header`
    within each entry's raw_data.

    Note: this only groups by identifier value. Matching those groups to an
    actual vendor/case (and deciding what's "unmatched") is the caller's job,
    since it requires the request's vendor PAN/code map.
    """
    result = SplitResult(identifier_header=identifier_header)

    for entry in entries:
        raw = entry.raw_data or {}
        raw_value = raw.get(identifier_header, "")
        key = normalize_identifier(raw_value)

        if not key:
            result.blank_identifier.append(entry)
            continue

        result.grouped.setdefault(key, []).append(entry)

    return result


@dataclass
class VendorMatchResult:
    """
    Outcome of matching a consolidated ledger's rows against a set of known
    vendors (identified by PAN or vendor_code).

    `vendors` passed to `match_entries_to_vendors` can be ANY status (active,
    inactive) — this function only matches identifier values to vendor
    records. It's the caller's job to decide what to do with inactive
    matches (e.g. still report them, but don't create a case for them).
    """

    identifier_column: str | None = None
    id_type: str | None = None  # "pan" | "vendor_code" | None
    # vendor.id -> entries belonging to that vendor
    matched_by_vendor_id: dict = field(default_factory=dict)
    # normalized identifier value -> entries with no matching vendor at all
    unmatched_by_identifier: dict = field(default_factory=dict)
    # rows where the identifier column was blank
    blank_identifier_entries: list = field(default_factory=list)


def build_split_ledger_csv(
    entries: list[ParsedLedgerEntry],
    raw_headers: list[str],
) -> bytes:
    """
    Reconstruct a CSV containing ONLY the given entries (i.e. one vendor's
    slice of a consolidated ledger), preserving every original column from
    the uploaded file via each entry's `raw_data`.

    This is what gets stored/downloaded per-case for a split upload — never
    the original file's raw bytes, which would contain every other vendor's
    rows too.

    Args:
        entries: The subset of parsed entries belonging to one vendor.
        raw_headers: Original (mixed-case) headers from the uploaded file,
            used to preserve column order and casing in the output.

    Returns:
        UTF-8 (with BOM, for Excel compatibility) CSV bytes.
    """
    import csv
    import io

    # raw_data is keyed by the lowercased/stripped header (see
    # FileParserService), so map back to the original header casing for a
    # faithful reproduction of what the user uploaded.
    lower_to_original = {h.strip().lower(): h.strip() for h in raw_headers if h and h.strip()}

    # Preserve column order from the original file; fall back to whatever
    # keys actually appear in the data if headers weren't available.
    ordered_lower_headers = [h.strip().lower() for h in raw_headers if h and h.strip()]
    if not ordered_lower_headers:
        seen: dict[str, None] = {}
        for entry in entries:
            for k in (entry.raw_data or {}):
                seen.setdefault(k, None)
        ordered_lower_headers = list(seen.keys())

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow([lower_to_original.get(h, h) for h in ordered_lower_headers])

    for entry in entries:
        raw = entry.raw_data or {}
        writer.writerow([raw.get(h, "") for h in ordered_lower_headers])

    return buffer.getvalue().encode("utf-8-sig")


def match_entries_to_vendors(
    entries: list[ParsedLedgerEntry],
    raw_headers: list[str],
    vendors: list,
) -> VendorMatchResult:
    """
    Detect the PAN/vendor-code column in a consolidated ledger and group its
    rows by which vendor (from `vendors`) each row belongs to.

    Args:
        entries: Parsed rows from the uploaded file.
        raw_headers: Original headers from the uploaded file.
        vendors: Vendor-like objects exposing `.id`, `.pan`, `.vendor_code`
            (any status — active/inactive filtering is the caller's concern).

    Returns:
        VendorMatchResult grouping entries by matched vendor id, plus
        whatever couldn't be matched to any vendor in `vendors`.
    """
    sample_rows = [e.raw_data for e in entries[:20] if e.raw_data]
    header, id_type = detect_identifier_header(raw_headers, sample_rows)

    result = VendorMatchResult(identifier_column=header, id_type=id_type)
    if header is None:
        return result

    # Match against BOTH the vendor's `pan` and `vendor_code` fields,
    # regardless of which one the file's column looks like. Vendor master
    # data isn't always clean — some vendors get onboarded with the PAN
    # value stored in vendor_code (e.g. via a bulk import template) instead
    # of the dedicated pan column. Checking only one field caused vendors
    # that ARE in the master to be reported as "missing".
    lookup: dict[str, object] = {}
    for vendor in vendors:
        pan = getattr(vendor, "pan", None)
        if pan:
            lookup.setdefault(normalize_identifier(pan), vendor)
        vendor_code = getattr(vendor, "vendor_code", None)
        if vendor_code:
            lookup.setdefault(normalize_identifier(vendor_code), vendor)

    split_result = split_entries_by_identifier(entries, header)
    for key, group_entries in split_result.grouped.items():
        vendor = lookup.get(key)
        if vendor is None:
            result.unmatched_by_identifier[key] = group_entries
        else:
            result.matched_by_vendor_id.setdefault(vendor.id, []).extend(group_entries)

    result.blank_identifier_entries = split_result.blank_identifier
    return result
