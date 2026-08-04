"""
Reconciliation export service.

Builds a multi-sheet Excel workbook matching the reference Firmway export format:
  1. Summary       — header block + "Reconciliation Statement" table
  2. Reconciliation — ALL entries (matched pairs on one row, one-sided otherwise),
                      colour-coded: blue=company, yellow=party, red=difference,
                      green=metadata.
  3. Annexure sheets — one per difference category (named by annexure number),
                      referenced from the Summary "Annexure" column.
  4. Party         — all vendor/party-side entries.

The workbook is generated purely from persisted data (ledger entries + match
results) so it reflects exactly what the engine produced.
"""

from __future__ import annotations

import io
from datetime import datetime
from decimal import Decimal

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter


# ── Colour palette (matches the reference export) ──
FILL_COMPANY = PatternFill("solid", fgColor="1E88E5")   # blue
FILL_PARTY = PatternFill("solid", fgColor="F4C20D")     # yellow
FILL_DIFF = PatternFill("solid", fgColor="E53935")      # red
FILL_META = PatternFill("solid", fgColor="7CB342")      # green
FILL_GROUP = PatternFill("solid", fgColor="F4C20D")     # yellow group header (summary)
FILL_GREEN = PatternFill("solid", fgColor="7CB342")     # green header (summary)
WHITE_BOLD = Font(bold=True, color="FFFFFF")
BOLD = Font(bold=True)


# ── Match pass → human-readable classification ──
# Labels are constrained to the reference system's classification taxonomy so
# the export's "Classification" column values are valid members of that set:
#   Amount Matched - Recommended, Closing Balance, Date and Amount Matched,
#   Date and Amount Matched - Recommended, Invoice Number Matched,
#   Multiple Based on Date, Multiple Based on Invoice Number,
#   Multiple Based on Invoice Number and Date, Opening Balance,
#   Payment Matched - Recommended, Reversal Entries, TDS Booked by Party,
#   Unmatched
# pass numbers per MatchPassType: 1 EXACT, 2 TOLERANCE, 3 FUZZY_REFERENCE,
# 4 ONE_TO_MANY, 5 MANY_TO_ONE, 6 DATE_PROXIMITY
PASS_CLASSIFICATION: dict[int, str] = {
    1: "Invoice Number Matched",          # exact match on amount+date+reference(invoice no)
    2: "Date and Amount Matched",         # tolerance on amount within date window
    3: "Invoice Number Matched",          # fuzzy match on reference/invoice number
    4: "Multiple Based on Date",          # one company ↔ many party (subset-sum by date)
    5: "Multiple Based on Date",          # many company ↔ one party
    6: "Date and Amount Matched - Recommended",  # date-proximity fallback
}

# Match pass → derived rule code (our own taxonomy, prefixed VLR-)
PASS_RULE_CODE: dict[int, str] = {
    1: "VLR-EXACT-1.0",
    2: "VLR-TOLERANCE-2.0",
    3: "VLR-FUZZYREF-3.0",
    4: "VLR-ONE2MANY-4.0",
    5: "VLR-MANY2ONE-5.0",
    6: "VLR-DATEPROX-6.0",
}


def _classification(pass_number: int | None) -> str:
    if pass_number is None:
        return "Unmatched"
    # Pass 8 = manual link (see manual_link endpoint). Treat as a valid match
    # classification rather than the "Unmatched" fallback.
    if int(pass_number) == 8:
        return "Invoice Number Matched"
    if int(pass_number) == 9:
        return "Reversal Entries"
    return PASS_CLASSIFICATION.get(int(pass_number), "Date and Amount Matched")


def _invoice_number(entry) -> str:
    """
    Best invoice number for an entry. Prefers the derived/document number, but
    when that's a synthetic placeholder (BAL_ROW_*) or blank, recovers the real
    value from the original uploaded row (raw_data) using common invoice-column
    header aliases.
    """
    if entry is None:
        return ""
    derived = getattr(entry, "derived_invoice_number", None)
    doc = getattr(entry, "document_number", None)
    for candidate in (derived, doc):
        if candidate and not str(candidate).startswith("BAL_ROW_"):
            return str(candidate)
    # Fall back to the original uploaded row.
    val = _raw(entry, [
        "inv no", "inv no.", "invoice no", "invoice no.", "invoice number",
        "inv number", "trx number", "transaction number", "bill no",
        "document number", "doc no", "voucher no", "vch no.", "reference",
    ], "")
    if val:
        return str(val)
    # Last resort: whatever we had (may be the placeholder).
    return str(derived or doc or "")


def _entry_signals(entry) -> str:
    """Concatenate the entry's type/category/remark/narration into one
    lowercase blob for keyword detection. Pulls from both the modelled fields
    and the original uploaded row (raw_data)."""
    if entry is None:
        return ""
    parts = [
        getattr(entry, "document_type", "") or "",
        getattr(entry, "document_category", "") or "",
        getattr(entry, "description", "") or "",
    ]
    raw = getattr(entry, "raw_data", None) or {}
    if raw:
        # Type / Remark / Narration style columns most often carry the markers.
        for k, v in raw.items():
            kl = str(k).strip().lower()
            if any(t in kl for t in ("type", "remark", "narration", "particular", "description", "text")):
                parts.append(str(v or ""))
    return " ".join(parts).lower()


def _special_classification(entry) -> str | None:
    """
    Detect entry-intrinsic classifications that don't depend on the match pass:
    Opening Balance, Closing Balance, Reversal Entries (knock-off), and
    TDS Booked by Party. Returns None when no special class applies (so the
    caller falls back to the pass-based classification).
    """
    if entry is None:
        return None
    sig = _entry_signals(entry)
    dtype = (getattr(entry, "document_type", "") or "").strip().lower()

    # Opening / Closing balance rows (Type "op"/"CL" or "opening/closing bal").
    if "opening bal" in sig or dtype in ("op", "ob", "opbal"):
        return "Opening Balance"
    if "closing bal" in sig or dtype in ("cl", "cb", "clbal"):
        return "Closing Balance"

    # Reversal / knock-off entries. SAP doc type "AB" is the reversal doc type;
    # the category is mapped to "knocking off" in the reference.
    if dtype == "ab" or "knock" in sig or "reversal" in sig or "reverse" in sig:
        return "Reversal Entries"

    # TDS entries (tagged by the transformation pass, or doc type/remark = TDS).
    if getattr(entry, "is_tds", False) or "tds" in sig or dtype in ("tds", "wt"):
        return "TDS Booked by Party"

    return None


def _rule_code(pass_number: int | None) -> str:
    if pass_number is None:
        return ""
    if int(pass_number) == 8:
        return "VLR-MANUAL-8.0"
    if int(pass_number) == 9:
        return "VLR-REVERSAL-9.0"
    return PASS_RULE_CODE.get(int(pass_number), "VLR-MATCH")


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
        # raw_data keys are the normalized (lowercased, stripped) source headers
        norm = {str(k).strip().lower(): v for k, v in raw.items()}
        for alias in header_aliases:
            v = norm.get(alias.strip().lower())
            if v not in (None, "", "None"):
                return v
    return fallback


# ── Difference-category → Summary status labels + annexure buckets ──
# Maps a document_category to the two summary "not booked by" lines.
CATEGORY_TO_SUMMARY = {
    "Invoice": {
        "group": "Invoice Difference",
        "company_missing": "Invoice not booked by Company",
        "party_missing": "Invoice not booked by Party",
        "company_action": "Vendor to provide the invoice copies",
        "party_action": "Vendor to check the reason for invoice not appearing",
    },
    "Credit Note": {
        "group": "Debit Note / Credit Note Difference",
        "company_missing": "Credit Note not booked by Company",
        "party_missing": "Credit Note not booked by Party",
        "company_action": "Company to book the Credit Note and recover from Vendor",
        "party_action": "Vendor to book the Credit Note",
    },
    "Debit Note": {
        "group": "Debit Note / Credit Note Difference",
        "company_missing": "Debit Note not booked by Company",
        "party_missing": "Debit Note not booked by Party",
        "company_action": "Company to book the Debit Note and recover from Vendor",
        "party_action": "Vendor to book the Debit Note",
    },
    "Payment": {
        "group": "Payment / receipt Difference",
        "company_missing": "Payment not booked by Company",
        "party_missing": "Payment not booked by Party",
        "company_action": "Company to book the payment entries",
        "party_action": "Vendor to check the payment details",
    },
    "Receipt": {
        "group": "Payment / receipt Difference",
        "company_missing": "Receipt not booked by Company",
        "party_missing": "Receipt not booked by Party",
        "company_action": "Company to book the receipt entries",
        "party_action": "Vendor to check the receipt details",
    },
}
DEFAULT_SUMMARY = {
    "group": "Other Differences",
    "company_missing": "Other entry not booked by Company",
    "party_missing": "Other entry not booked by Party",
    "company_action": "",
    "party_action": "",
}


class ReconciliationExportService:
    """Builds the reconciliation export workbook from persisted case data."""

    # Full 46-column header for the Reconciliation sheet (matches reference).
    RECON_HEADERS = [
        "Company Id", "Party Id", "Matched Id", "Status", "Classification",
        "Company Statement Type", "Company Invoice Date", "Company Invoice Number",
        "Company DocType", "Company Original DocType", "Company Narration", "Company Amount",
        "Party Statement Type", "Party Invoice Date", "Party Invoice Number",
        "Party DocType", "Party Original DocType", "Party Narration", "Party Amount",
        "Difference", "Matched Rule", "Reco Data & Time", "Remark", "Party Code",
        "Daybook Name", "Company Clearing Document Number", "Company Clearing Date",
        "Company TDS Amount", "Company Posting Date", "Company Code", "Supplier",
        "Document Number", "Business Area", "Assignment", "Document Header Text",
        "Tax Code", "Year/Month", "Reference", "Profit Center", "Posting Date",
        "Amount in Doc. Curr.", "Document Currency", "Local Currency", "Entry Date",
        "Withhldg Tax Base Amount", "Payment Date",
    ]

    # Column groups (1-indexed) for colour coding the Reconciliation header.
    COMPANY_COLS = list(range(6, 13))     # Company Statement Type .. Company Amount
    PARTY_COLS = list(range(13, 20))      # Party Statement Type .. Party Amount
    DIFF_COLS = [20]                       # Difference
    META_COLS = list(range(1, 6)) + list(range(21, 47))  # ids/status/class + tail meta

    PARTY_HEADERS = [
        "Party Id", "Matched Id", "Status", "Classification", "Party Statement Type",
        "Party Invoice Date", "Party Invoice Number", "Party DocType",
        "Party Original DocType", "Party Narration", "Party Amount", "Matched Rule",
        "Reco Data & Time", "Party Clearing Document Number", "Party Clearing Date",
        "Party TDS Amount", "Party Posting Date",
    ]

    def build(
        self,
        *,
        case,
        vendor,
        company_entries: list,
        vendor_entries: list,
        match_results: list,
        reco_datetime: datetime,
        period_start,
        period_end,
        party_code: str = "",
        tolerance_amount: str = "1.0 Rs",
        tds_percentage: str = "0.0 - 10.0",
        date_tolerance: str = "0 - 15",
    ) -> bytes:
        wb = Workbook()
        # Index entries by id for quick lookup.
        by_id = {str(e.id): e for e in company_entries + vendor_entries}

        self._reco_dt = reco_datetime.strftime("%d-%b-%y %I:%M %p")
        self._party_code = party_code

        # Build match linkage: entry_id -> match record
        entry_match: dict[str, object] = {}
        for m in match_results:
            for cid in (m.company_entry_ids or []):
                entry_match[str(cid)] = m
            for vid in (m.vendor_entry_ids or []):
                entry_match[str(vid)] = m

        rows = self._build_recon_rows(company_entries, vendor_entries, match_results, by_id)

        # ── Sheet: Summary ──
        ws_summary = wb.active
        ws_summary.title = "Summary"
        annexure_map = self._compute_summary(
            ws_summary, vendor, company_entries, vendor_entries, match_results,
            period_start, period_end, tolerance_amount, tds_percentage, date_tolerance,
        )

        # ── Sheet: Reconciliation ──
        self._write_recon_sheet(wb, rows)

        # ── Annexure sheets (one per difference bucket) ──
        self._write_annexures(wb, rows, annexure_map)

        # ── Sheet: Party ──
        self._write_party_sheet(wb, vendor_entries, entry_match)

        buf = io.BytesIO()
        wb.save(buf)
        return buf.getvalue()

    # ------------------------------------------------------------------ rows
    def _build_recon_rows(self, company_entries, vendor_entries, match_results, by_id):
        """Return a list of row dicts covering matched pairs + one-sided entries."""
        rows = []
        used = set()

        # Matched pairs/groups first (both sides present).
        for m in match_results:
            comp_ids = [str(x) for x in (m.company_entry_ids or [])]
            party_ids = [str(x) for x in (m.vendor_entry_ids or [])]
            for cid in comp_ids:
                used.add(cid)
            for vid in party_ids:
                used.add(vid)
            # Pair rows: align company[i] with party[i]; extras get their own row.
            maxlen = max(len(comp_ids), len(party_ids), 1)
            for i in range(maxlen):
                c = by_id.get(comp_ids[i]) if i < len(comp_ids) else None
                p = by_id.get(party_ids[i]) if i < len(party_ids) else None
                rows.append(self._row(c, p, m, status="Reconciled"))

        # One-sided (unmatched) entries.
        for e in company_entries:
            if str(e.id) not in used:
                rows.append(self._row(e, None, None, status=self._unmatched_status(e, "company")))
        for e in vendor_entries:
            if str(e.id) not in used:
                rows.append(self._row(None, e, None, status=self._unmatched_status(e, "party")))
        return rows

    @staticmethod
    def _unmatched_status(entry, side: str) -> str:
        # Opening/Closing balance and reversal (knock-off) entries are not a
        # genuine "not booked" reconciliation gap — give them their own status
        # so they aren't reported as missing on one side.
        special = _special_classification(entry)
        if special in ("Opening Balance", "Closing Balance", "Reversal Entries"):
            return special
        cat = (getattr(entry, "document_category", "") or "").strip()
        info = CATEGORY_TO_SUMMARY.get(cat, DEFAULT_SUMMARY)
        return info["company_missing"] if side == "company" else info["party_missing"]

    def _row(self, c, p, match, status: str) -> dict:
        pass_number = getattr(c or p, "pass_number", None)
        c_amt = _num(getattr(c, "amount", 0)) if c else 0.0
        p_amt = _num(getattr(p, "amount", 0)) if p else 0.0
        diff = (c_amt + p_amt) if (c and p) else 0.0
        # A row belongs to a match whenever it came from a match record — even
        # if this particular line only carries one side (the "extra" entries of
        # a one-to-many / many-to-one group). Classification and rule must key
        # off the match, not off both sides being present, otherwise the extra
        # lines of a group show "Unmatched" while status says "Reconciled".
        is_matched = match is not None
        # Entry-intrinsic classification (Opening/Closing Balance, Reversal,
        # TDS) takes priority over the pass-based label, and applies whether or
        # not the row was matched. Check company side first, then party.
        special = _special_classification(c) or _special_classification(p)
        if special is not None:
            classification = special
        elif is_matched:
            classification = _classification(pass_number)
        else:
            classification = "Unmatched"
        return {
            "company_id": str(c.id) if c else "",
            "party_id": str(p.id) if p else "",
            "matched_id": str(match.id) if match else "",
            "status": status,
            "classification": classification,
            "c_stmt": "ledger" if c else "",
            "c_date": _fmt_date(getattr(c, "posting_date", None)) if c else "",
            "c_invno": _invoice_number(c) if c else "",
            "c_doctype": (getattr(c, "document_category", "") or "").lower() if c else "",
            "c_origtype": getattr(c, "document_type", "") if c else "",
            "c_narr": getattr(c, "description", "") if c else "",
            "c_amt": c_amt if c else "",
            "p_stmt": "ledger" if p else "",
            "p_date": _fmt_date(getattr(p, "posting_date", None)) if p else "",
            "p_invno": _invoice_number(p) if p else "",
            "p_doctype": (getattr(p, "document_category", "") or "").lower() if p else "",
            "p_origtype": getattr(p, "document_type", "") if p else "",
            "p_narr": getattr(p, "description", "") if p else "",
            "p_amt": p_amt if p else "",
            "difference": diff,
            "rule": _rule_code(pass_number) if is_matched else "",
            "category": (getattr(c or p, "document_category", "") or ""),
            "_side": "both" if (c and p) else ("company" if c else "party"),
            # Company-side SAP detail columns — prefer the original uploaded
            # value from raw_data, falling back to the modelled field.
            "c_clearing_doc": _raw(c, ["clearing document", "clearing document number", "clearing doc"], getattr(c, "clearing_document", "") if c else ""),
            "c_clearing_date": _raw(c, ["clearing date"], _fmt_date(getattr(c, "clearing_date", None)) if c else ""),
            "c_tds_amount": _raw(c, ["tds amount", "company tds amount", "withholding tax amount", "withhldg tax amount"], ""),
            "c_posting_date": _raw(c, ["posting date"], _fmt_date(getattr(c, "posting_date", None)) if c else ""),
            "c_company_code": _raw(c, ["company code", "company"], ""),
            "c_supplier": _raw(c, ["supplier", "vendor", "vendor name", "supplier name"], ""),
            "c_docnum": _raw(c, ["document number", "document no", "doc number", "belnr"], getattr(c, "document_number", "") if c else ""),
            "c_business_area": _raw(c, ["business area"], ""),
            "c_assignment": _raw(c, ["assignment", "assignment number", "zuonr"], getattr(c, "assignment_number", "") if c else ""),
            "c_doc_header_text": _raw(c, ["document header text", "doc header text", "header text"], ""),
            "c_tax_code": _raw(c, ["tax code"], ""),
            "c_year_month": _raw(c, ["year/month", "year month", "period", "fiscal period"], ""),
            "c_reference": _raw(c, ["reference", "reference number", "xblnr"], (getattr(c, "reference_number", None) or getattr(c, "raw_reference", "")) if c else ""),
            "c_profit_center": _raw(c, ["profit center", "profit centre"], ""),
            "c_doc_amount": _raw(c, ["amount in doc. curr.", "amount in doc curr", "amount in document currency"], _num(getattr(c, "original_amount", None) if (c and getattr(c, "original_amount", None) is not None) else getattr(c, "amount", 0)) if c else ""),
            "c_doc_currency": _raw(c, ["document currency", "doc currency", "currency"], (getattr(c, "transaction_currency", None) or getattr(c, "currency", "")) if c else ""),
            "c_local_amount": _raw(c, ["local currency", "amount in local currency", "local currency amount"], _num(getattr(c, "local_currency_amount", None)) if (c and getattr(c, "local_currency_amount", None) is not None) else ""),
            "c_entry_date": _raw(c, ["entry date"], ""),
            "c_wht_base": _raw(c, ["withhldg tax base amount", "withholding tax base amount", "w/tax base amount"], ""),
            "c_payment_date": _raw(c, ["payment date"], ""),
            "c_daybook": _raw(c, ["daybook name", "daybook"], ""),
        }

    def _recon_record(self, r: dict) -> list:
        """Map a row dict to the full 46-column Reconciliation record."""
        rec = [""] * len(self.RECON_HEADERS)
        rec[0] = r["company_id"]
        rec[1] = r["party_id"]
        rec[2] = r["matched_id"]
        rec[3] = r["status"]
        rec[4] = r["classification"]
        rec[5] = r["c_stmt"]
        rec[6] = r["c_date"]
        rec[7] = r["c_invno"]
        rec[8] = r["c_doctype"]
        rec[9] = r["c_origtype"]
        rec[10] = r["c_narr"]
        rec[11] = r["c_amt"]
        rec[12] = r["p_stmt"]
        rec[13] = r["p_date"]
        rec[14] = r["p_invno"]
        rec[15] = r["p_doctype"]
        rec[16] = r["p_origtype"]
        rec[17] = r["p_narr"]
        rec[18] = r["p_amt"]
        rec[19] = r["difference"]
        rec[20] = r["rule"]
        rec[21] = self._reco_dt
        rec[23] = self._party_code
        # Company-side SAP detail columns (0-indexed against RECON_HEADERS).
        rec[24] = r["c_daybook"]           # Daybook Name
        rec[25] = r["c_clearing_doc"]      # Company Clearing Document Number
        rec[26] = r["c_clearing_date"]     # Company Clearing Date
        rec[27] = r["c_tds_amount"]        # Company TDS Amount
        rec[28] = r["c_posting_date"]      # Company Posting Date
        rec[29] = r["c_company_code"]      # Company Code
        rec[30] = r["c_supplier"]          # Supplier
        rec[31] = r["c_docnum"]            # Document Number
        rec[32] = r["c_business_area"]     # Business Area
        rec[33] = r["c_assignment"]        # Assignment
        rec[34] = r["c_doc_header_text"]   # Document Header Text
        rec[35] = r["c_tax_code"]          # Tax Code
        rec[36] = r["c_year_month"]        # Year/Month
        rec[37] = r["c_reference"]         # Reference
        rec[38] = r["c_profit_center"]     # Profit Center
        rec[39] = r["c_posting_date"]      # Posting Date
        rec[40] = r["c_doc_amount"]        # Amount in Doc. Curr.
        rec[41] = r["c_doc_currency"]      # Document Currency
        rec[42] = r["c_local_amount"]      # Local Currency
        rec[43] = r["c_entry_date"]        # Entry Date
        rec[44] = r["c_wht_base"]          # Withhldg Tax Base Amount
        rec[45] = r["c_payment_date"]      # Payment Date
        return rec

    # ------------------------------------------------------------- recon sheet
    def _write_recon_sheet(self, wb, rows):
        ws = wb.create_sheet("Reconciliation")
        ws.append(self.RECON_HEADERS)
        self._colour_recon_header(ws)
        for r in rows:
            ws.append(self._recon_record(r))
        self._autosize(ws, max_cols=25)

    def _colour_recon_header(self, ws):
        for c in range(1, len(self.RECON_HEADERS) + 1):
            cell = ws.cell(row=1, column=c)
            cell.font = WHITE_BOLD
            if c in self.COMPANY_COLS:
                cell.fill = FILL_COMPANY
            elif c in self.PARTY_COLS:
                cell.fill = FILL_PARTY
            elif c in self.DIFF_COLS:
                cell.fill = FILL_DIFF
            else:
                cell.fill = FILL_META

    # ------------------------------------------------------------- annexures
    def _write_annexures(self, wb, rows, annexure_map):
        """annexure_map: {annexure_number: (status_label, side)}."""
        for annex_no, (status_label, side) in annexure_map.items():
            matching = [r for r in rows if r["status"] == status_label]
            if not matching:
                continue
            ws = wb.create_sheet(str(annex_no))
            ws.append(self.RECON_HEADERS)
            self._colour_recon_header(ws)
            for r in matching:
                ws.append(self._recon_record(r))
            self._autosize(ws, max_cols=25)

    # ------------------------------------------------------------- party sheet
    def _write_party_sheet(self, wb, vendor_entries, entry_match):
        ws = wb.create_sheet("Party")
        ws.append(self.PARTY_HEADERS)
        for c in range(1, len(self.PARTY_HEADERS) + 1):
            cell = ws.cell(row=1, column=c)
            cell.font = WHITE_BOLD
            cell.fill = FILL_PARTY
        for e in vendor_entries:
            m = entry_match.get(str(e.id))
            pass_number = getattr(e, "pass_number", None)
            ws.append([
                str(e.id),
                str(m.id) if m else "",
                "Reconciled" if m else self._unmatched_status(e, "party"),
                _classification(pass_number) if m else "Unmatched",
                "ledger",
                _fmt_date(getattr(e, "posting_date", None)),
                getattr(e, "derived_invoice_number", None) or getattr(e, "document_number", ""),
                (getattr(e, "document_category", "") or "").lower(),
                getattr(e, "document_type", ""),
                getattr(e, "description", ""),
                _num(getattr(e, "amount", 0)),
                _rule_code(pass_number) if m else "",
                self._reco_dt,
                getattr(e, "clearing_document", "") or "",
                _fmt_date(getattr(e, "clearing_date", None)),
                "",
                _fmt_date(getattr(e, "posting_date", None)),
            ])
        self._autosize(ws, max_cols=17)

    # ------------------------------------------------------------- summary
    def _compute_summary(
        self, ws, vendor, company_entries, vendor_entries, match_results,
        period_start, period_end, tolerance_amount, tds_percentage, date_tolerance,
    ) -> dict:
        """Write the Summary sheet; return {annexure_no: (status_label, side)}."""
        vname = getattr(vendor, "name", "") or ""
        # ── Header block ──
        header_rows = [
            ("Party Name", vname, "Date Tolerance", date_tolerance),
            ("Reconciliation Period",
             f"{_fmt_date(period_start)} to {_fmt_date(period_end)}",
             "TDS Percentage", tds_percentage),
            ("Statement Type", "Ledger", "Amount Tolerance", tolerance_amount),
            ("Party Type", "Vendor", "", ""),
            ("Reconciliation Date", self._reco_dt, "", ""),
        ]
        for a, b, c, d in header_rows:
            ws.append([a, b, c, d])
        for r in range(1, 6):
            ws.cell(row=r, column=1).font = BOLD
            ws.cell(row=r, column=3).font = BOLD
            ws.cell(row=r, column=1).alignment = Alignment(horizontal="right")
            ws.cell(row=r, column=3).alignment = Alignment(horizontal="right")

        ws.append([])  # row 6 blank

        # ── "Reconciliation Statement" banner (row 7) ──
        ws.append(["Reconciliation Statement"])
        banner = ws.cell(row=7, column=1)
        banner.fill = FILL_GREEN
        banner.font = WHITE_BOLD
        ws.merge_cells(start_row=7, start_column=1, end_row=7, end_column=5)

        # ── Table header (row 8) ──
        ws.append(["Particulars", "Annexure", "Amount", "No. of Entries", "Action Required"])
        for c in range(1, 6):
            cell = ws.cell(row=8, column=c)
            cell.fill = FILL_GREEN
            cell.font = WHITE_BOLD

        # Build unmatched buckets by category/side, assigning annexure numbers.
        annexure_map: dict[int, tuple] = {}
        annex_counter = {"n": 0}

        def next_annex():
            annex_counter["n"] += 1
            return annex_counter["n"]

        def bucket(entries, side):
            """Aggregate UNMATCHED entries per (group, label, action).

            An entry is "unmatched" when it has no match_id. Opening/Closing
            balance rows are excluded (shown in their own section).
            Returns {(grp, label, action): [amount_sum, count]}.
            """
            out: dict = {}
            for e in entries:
                if getattr(e, "match_id", None):
                    continue
                cat = (getattr(e, "document_category", "") or "").strip()
                if cat in ("Opening Balance", "Closing Balance"):
                    continue
                # Balance and reversal (knock-off) entries are entry-intrinsic
                # classifications, not a cross-ledger "not booked" gap. A
                # knock-off nets within one side, so it must not surface as a
                # difference "not booked by" the other side.
                special = _special_classification(e)
                if special in ("Opening Balance", "Closing Balance", "Reversal Entries"):
                    continue
                info = CATEGORY_TO_SUMMARY.get(cat, DEFAULT_SUMMARY)
                label = info["company_missing"] if side == "company" else info["party_missing"]
                action = info["company_action"] if side == "company" else info["party_action"]
                grp = info["group"]
                key = (grp, label, action)
                agg = out.setdefault(key, [Decimal("0"), 0])
                agg[0] += Decimal(str(_num(getattr(e, "amount", 0))))
                agg[1] += 1
            return out

        def matched_bucket(entries, side):
            """Aggregate MATCHED entries (have a match_id) into a total per side.
            Excludes balance rows. Returns [amount_sum, count]."""
            amt = Decimal("0")
            cnt = 0
            for e in entries:
                if not getattr(e, "match_id", None):
                    continue
                cat = (getattr(e, "document_category", "") or "").strip()
                if cat in ("Opening Balance", "Closing Balance"):
                    continue
                amt += Decimal(str(_num(getattr(e, "amount", 0))))
                cnt += 1
            return [amt, cnt]

        comp_buckets = bucket(company_entries, "company")
        party_buckets = bucket(vendor_entries, "party")

        # Group the buckets under their difference group, in reference order.
        group_order = [
            "Invoice Difference",
            "Debit Note / Credit Note Difference",
            "Payment / receipt Difference",
            "Other Differences",
            "TDS / TCS Difference",
        ]
        # Collect detail lines per group. Company side is shown as a positive
        # "owed" amount and party side as negative so the section total reflects
        # the net difference for that category.
        lines_by_group: dict[str, list] = {g: [] for g in group_order}
        for (grp, label, action), (amt, cnt) in {**comp_buckets, **party_buckets}.items():
            lines_by_group.setdefault(grp, [])
            annex_no = next_annex()
            side = "company" if "Company" in label else "party"
            annexure_map[annex_no] = (label, side)
            lines_by_group[grp].append((label, annex_no, amt, cnt, action, side))

        # ── Closing balance section ──
        company_closing = _company_closing(company_entries)
        party_closing = _closing(vendor_entries)
        n_company_closing = _closing_count(company_entries)
        n_party_closing = _closing_count(vendor_entries)
        closing_diff = company_closing + party_closing

        row = 9
        row = self._summary_group(
            ws, row, "Closing Balance Difference",
            total_amount=closing_diff,
            total_count=n_company_closing + n_party_closing,
            detail_lines=[
                ("Closing Balance as per Company", None, company_closing, n_company_closing, "", "company"),
                ("Closing Balance as per Party", None, party_closing, n_party_closing, "", "party"),
            ],
        )

        # ── Opening balance section (counted so all balance rows appear) ──
        company_opening = _balance_sum(company_entries, "opening")
        party_opening = _balance_sum(vendor_entries, "opening")
        n_company_opening = _balance_count(company_entries, "opening")
        n_party_opening = _balance_count(vendor_entries, "opening")
        if n_company_opening or n_party_opening:
            row = self._summary_group(
                ws, row, "Opening Balance Difference",
                total_amount=company_opening + party_opening,
                total_count=n_company_opening + n_party_opening,
                detail_lines=[
                    ("Opening Balance as per Company", None, company_opening, n_company_opening, "", "company"),
                    ("Opening Balance as per Party", None, party_opening, n_party_opening,
                     "Vendor to provide the breakup of Opening Balance", "party"),
                ],
            )

        # ── Difference groups ──
        # Track the running sum of all difference sections for the final check.
        total_diff_amount = Decimal("0")
        for grp in group_order:
            lines = lines_by_group.get(grp, [])
            if not lines:
                continue
            grp_amount = sum((amt for (_l, _a, amt, _c, _act, _s) in lines), Decimal("0"))
            grp_count = sum((cnt for (_l, _a, _amt, cnt, _act, _s) in lines), 0)
            total_diff_amount += grp_amount
            row = self._summary_group(
                ws, row, grp, total_amount=grp_amount, total_count=grp_count,
                detail_lines=lines,
            )

        # ── Reconciled (matched) section ──
        # Every matched entry is accounted for here so the No. of Entries totals
        # cover the full ledgers (matched + unmatched + balances).
        comp_matched = matched_bucket(company_entries, "company")
        party_matched = matched_bucket(vendor_entries, "party")
        if comp_matched[1] or party_matched[1]:
            matched_amt = comp_matched[0] + party_matched[0]
            matched_cnt = comp_matched[1] + party_matched[1]
            row = self._summary_group(
                ws, row, "Reconciled Entries",
                total_amount=matched_amt, total_count=matched_cnt,
                detail_lines=[
                    ("Reconciled - Company", None, comp_matched[0], comp_matched[1], "", "company"),
                    ("Reconciled - Party", None, party_matched[0], party_matched[1], "", "party"),
                ],
            )

        # ── Amount Unsettled (balancing) section ──
        # The itemised differences should fully explain the closing-balance
        # difference. Any leftover is the unexplained/"unsettled" amount. Show
        # it as an explicit line so the final Difference nets to zero.
        residual = closing_diff - total_diff_amount
        if residual != 0:
            # Sign convention: a positive residual means the company side is
            # higher (vendor still owes / vendor unsettled); negative the reverse.
            if residual > 0:
                unsettled_label = "Amount Unsettled by Vendor"
                unsettled_side = "party"
            else:
                unsettled_label = "Amount Unsettled by Company"
                unsettled_side = "company"
            row = self._summary_group(
                ws, row, unsettled_label,
                total_amount=residual, total_count=None,
                detail_lines=[
                    (unsettled_label, None, residual, None,
                     "To be settled / adjusted between Company and Vendor", unsettled_side),
                ],
            )
            # Roll the residual into the itemised total so the balance closes.
            total_diff_amount += residual

        # ── Total Entries check row ──
        total_all_entries = len(company_entries) + len(vendor_entries)
        ws.append([])
        row += 1
        ws.cell(row=row, column=1, value="Total Entries (Company + Party)")
        ws.cell(row=row, column=1).font = BOLD
        ws.cell(row=row, column=4, value=total_all_entries)
        ws.cell(row=row, column=4).font = BOLD
        row += 1

        # ── Calculated Balance + final Difference (green) ──
        ws.append([])
        row += 1
        ws.cell(row=row, column=1, value="Calculated Balance")
        ws.cell(row=row, column=1).font = BOLD
        ws.cell(row=row, column=3, value=float(total_diff_amount))
        ws.cell(row=row, column=3).font = BOLD
        row += 1

        # After adding the unsettled line, the calculated balance equals the
        # closing-balance difference, so the final Difference is zero.
        final_difference = closing_diff - total_diff_amount
        ws.cell(row=row, column=1, value="Difference")
        for c in range(1, 6):
            ws.cell(row=row, column=c).fill = FILL_GREEN
            ws.cell(row=row, column=c).font = WHITE_BOLD
        ws.cell(row=row, column=3, value=float(final_difference))

        self._autosize(ws, max_cols=5)
        return annexure_map

    def _summary_group(self, ws, row, group_title, *, total_amount=None, total_count=None, detail_lines=None):
        """Write a yellow group header row (with section totals) + white detail
        rows. Returns the next free row."""
        # Group header (yellow) — carries the section total amount + entry count.
        ws.cell(row=row, column=1, value=group_title)
        if total_amount is not None:
            ws.cell(row=row, column=3, value=float(total_amount))
        if total_count is not None:
            ws.cell(row=row, column=4, value=int(total_count))
        for c in range(1, 6):
            ws.cell(row=row, column=c).fill = FILL_GROUP
            ws.cell(row=row, column=c).font = BOLD
        row += 1

        for (label, annex_no, amt, cnt, act, _side) in (detail_lines or []):
            ws.cell(row=row, column=1, value=label)
            if annex_no is not None:
                ws.cell(row=row, column=2, value=annex_no)
            ws.cell(row=row, column=3, value=float(amt))
            if cnt:
                ws.cell(row=row, column=4, value=int(cnt))
            if act:
                ws.cell(row=row, column=5, value=act)
            row += 1
        return row

    # ------------------------------------------------------------- utilities
    @staticmethod
    def _autosize(ws, max_cols: int = 20):
        for c in range(1, min(ws.max_column, max_cols) + 1):
            letter = get_column_letter(c)
            width = 12
            for row in range(1, min(ws.max_row, 200) + 1):
                v = ws.cell(row=row, column=c).value
                if v is not None:
                    width = max(width, min(len(str(v)) + 2, 40))
            ws.column_dimensions[letter].width = width


def _balance_sum(entries, keyword: str) -> Decimal:
    total = Decimal("0")
    for e in entries:
        cat = (getattr(e, "document_category", "") or "").lower()
        if keyword in cat:
            total += Decimal(str(_num(getattr(e, "amount", 0))))
    return total


def _balance_count(entries, keyword: str) -> int:
    return sum(
        1 for e in entries
        if keyword in (getattr(e, "document_category", "") or "").lower()
    )


def _closing(entries) -> Decimal:
    return _balance_sum(entries, "closing")


def _closing_count(entries) -> int:
    return _balance_count(entries, "closing")


def _company_closing(entries) -> Decimal:
    return _closing(entries)
