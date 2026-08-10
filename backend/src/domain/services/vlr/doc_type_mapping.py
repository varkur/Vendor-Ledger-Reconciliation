"""
Default document type mapping for SAP company ledger entries.
Maps SAP document type codes to standardized categories used by the reconciliation engine.
"""

# SAP Document Type → Standard Category
DEFAULT_DOC_TYPE_MAP: dict[str, str] = {
    # Invoices
    "KR": "Invoice",
    "M9": "Invoice",
    "MA": "Invoice",
    "MI": "Invoice",
    "MF": "Invoice",
    "AA": "Invoice",
    "MH": "Invoice",
    "MN": "Invoice",
    "M7": "Invoice",
    "M8": "Invoice",
    # Vendor-side (Tally-style) invoice doc type — confirmed against real
    # Firmway export data: "Party DocType=invoice | Party Original DocType=RV".
    "RV": "Invoice",
    "INV": "Invoice",
    # Debit Note
    "KG": "Debit Note",
    # Credit Note
    "CM": "Credit Note",
    # Knocking Off / Clearing
    "AB": "Knocking Off",
    # Journal / Adjusted
    "SA": "Adjusted",
    # Payment
    "KZ": "Payment",
    # Vendor-side (Tally-style) payment/clearing doc type — confirmed against
    # real Firmway export data: "Party DocType=payment | Party Original DocType=DZ".
    "DZ": "Payment",
    "REFUND": "Payment",
    # Receipt
    "RO": "Receipt",
    "REC": "Receipt",
    # TDS
    "KA": "TDS Adjusted",
    # Opening / Closing Balance markers
    "OP": "Opening Balance",
    "CL": "Closing Balance",
    "BAL": "Opening Balance",
}

# Standard Firmway categories for the mapping dropdown
STANDARD_CATEGORIES = [
    "Invoice",
    "Payment",
    "Debit Note",
    "Credit Note",
    "Journal",
    "Adjusted",
    "Receipt",
    "Knocking Off",
    "TDS Adjusted",
    "Opening Balance",
    "Closing Balance",
]


def classify_document_type(doc_type_code: str) -> str:
    """
    Classify a document type code into a standard category.
    Returns the category string, or 'Unknown' if not mapped.
    """
    if not doc_type_code:
        return "Unknown"
    return DEFAULT_DOC_TYPE_MAP.get(doc_type_code.strip().upper(), "Unknown")
