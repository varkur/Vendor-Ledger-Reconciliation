"""
Shared derivation of the FULL ledger-entry column set.

Both the Excel export and the reconciliation output API (matched / unmatched /
link-unmatched screens) must expose the same columns, sourced from the
original uploaded row (LedgerEntryModel.raw_data) with the modelled fields as
fallback. This module centralises that derivation so the API and the export
stay in lock-step.
"""

from __future__ import annotations


def _num(value) -> float:
    if value is None:
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _fmt_date(value) -> str:
    if value is None:
        return ""
    try:
        return value.strftime("%d-%m-%Y")
    except AttributeError:
        return str(value)


def _raw(entry, header_aliases: list[str], fallback=""):
    """Look up a value from the entry's raw_data (original uploaded row) by any
    of the given header aliases (case-insensitive). Falls back to the modelled
    value when the column wasn't in the upload."""
    if entry is None:
        return ""
    raw = getattr(entry, "raw_data", None) or {}
    if raw:
        norm = {str(k).strip().lower(): v for k, v in raw.items()}
        for alias in header_aliases:
            v = norm.get(alias.strip().lower())
            if v not in (None, "", "None"):
                return v
    return fallback


def invoice_number(entry) -> str:
    """Best invoice number: derived/document number unless it's a synthetic
    BAL_ROW_* placeholder, then recover from raw_data invoice-column aliases."""
    if entry is None:
        return ""
    derived = getattr(entry, "derived_invoice_number", None)
    doc = getattr(entry, "document_number", None)
    for candidate in (derived, doc):
        if candidate and not str(candidate).startswith("BAL_ROW_"):
            return str(candidate)
    val = _raw(entry, [
        "inv no", "inv no.", "invoice no", "invoice no.", "invoice number",
        "inv number", "trx number", "transaction number", "bill no",
        "document number", "doc no", "voucher no", "vch no.", "reference",
    ], "")
    if val:
        return str(val)
    # Never surface a synthetic BAL_ROW_* placeholder to the user. If the only
    # values we have are placeholders, return blank instead.
    for candidate in (derived, doc):
        if candidate and not str(candidate).startswith("BAL_ROW_"):
            return str(candidate)
    return ""


def build_entry_columns(entry) -> dict:
    """
    Return the full flat column set for a single ledger entry, matching the
    Excel export's column derivation. Keys are snake_case; the frontend maps
    them to display headers.
    """
    if entry is None:
        return {}

    return {
        "statement_type": "ledger",
        "invoice_date": _fmt_date(getattr(entry, "posting_date", None)),
        "invoice_number": invoice_number(entry),
        "doctype": (getattr(entry, "document_category", "") or ""),
        "original_doctype": (getattr(entry, "document_type", "") or ""),
        "narration": (getattr(entry, "description", "") or ""),
        "amount": _num(getattr(entry, "amount", 0)),
        # SAP / tail detail columns (raw_data first, modelled fallback)
        "daybook_name": str(_raw(entry, ["daybook name", "daybook"], "")),
        "clearing_document_number": str(_raw(
            entry, ["clearing document", "clearing document number", "clearing doc"],
            getattr(entry, "clearing_document", "") or "",
        )),
        "clearing_date": str(_raw(
            entry, ["clearing date"], _fmt_date(getattr(entry, "clearing_date", None)),
        )),
        "tds_amount": str(_raw(
            entry, ["tds amount", "company tds amount", "withholding tax amount", "withhldg tax amount"], "",
        )),
        "posting_date": str(_raw(
            entry, ["posting date"], _fmt_date(getattr(entry, "posting_date", None)),
        )),
        "company_code": str(_raw(entry, ["company code", "company"], "")),
        "supplier": str(_raw(entry, ["supplier", "vendor", "vendor name", "supplier name"], "")),
        "document_number": str(_raw(
            entry, ["document number", "document no", "doc number", "belnr"],
            getattr(entry, "document_number", "") or "",
        )),
        "business_area": str(_raw(entry, ["business area"], "")),
        "assignment": str(_raw(
            entry, ["assignment", "assignment number", "zuonr"],
            getattr(entry, "assignment_number", "") or "",
        )),
        "document_header_text": str(_raw(
            entry, ["document header text", "doc header text", "header text"], "",
        )),
        "tax_code": str(_raw(entry, ["tax code"], "")),
        "year_month": str(_raw(entry, ["year/month", "year month", "period", "fiscal period"], "")),
        "reference": str(_raw(
            entry, ["reference", "reference number", "xblnr"],
            (getattr(entry, "reference_number", None) or getattr(entry, "raw_reference", "") or ""),
        )),
        "profit_center": str(_raw(entry, ["profit center", "profit centre"], "")),
        "amount_in_doc_curr": _num(_raw(
            entry, ["amount in doc. curr.", "amount in doc curr", "amount in document currency"],
            _num(getattr(entry, "original_amount", None)
                 if getattr(entry, "original_amount", None) is not None
                 else getattr(entry, "amount", 0)),
        )),
        "document_currency": str(_raw(
            entry, ["document currency", "doc currency", "currency"],
            (getattr(entry, "transaction_currency", None) or getattr(entry, "currency", "") or ""),
        )),
        "local_currency": str(_raw(
            entry, ["local currency", "amount in local currency", "local currency amount"],
            _num(getattr(entry, "local_currency_amount", None))
            if getattr(entry, "local_currency_amount", None) is not None else "",
        )),
        "entry_date": str(_raw(entry, ["entry date"], "")),
        "withhldg_tax_base_amount": str(_raw(
            entry, ["withhldg tax base amount", "withholding tax base amount", "w/tax base amount"], "",
        )),
        "payment_date": str(_raw(entry, ["payment date"], "")),
    }
