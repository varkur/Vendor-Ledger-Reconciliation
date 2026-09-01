# Vendor Ledger Reconciliation (VLR) — App Overview

A platform for reconciling a company's ledger against each vendor's ledger —
matching invoices, payments, credit/debit notes, and TDS entries across both
sides, surfacing genuine differences, and routing them through vendor
sign-off and internal approval before closing a period.

**Stack:** FastAPI (Python) backend, React + TypeScript (Vite, PrimeReact)
frontend, PostgreSQL, Celery for background/scheduled tasks.

---

## Core Reconciliation Workflow

### 1. Request Statement (bulk, multi-vendor)
Create a reconciliation request for a period: pick company entity, fiscal
year, one or more vendors, and configure matching settings — amount
tolerance, TDS % (min/max range), GST %, date-tolerance range (min/max),
which matching passes to enable. Upload the company ledger (single
multi-vendor file with auto-detected PAN/vendor-code column, or per-vendor),
then automatically emails every selected vendor's contact(s) a portal
invite to upload their own statement.

### 2. Direct Reconciliation (single vendor, dual upload)
A lighter-weight flow for reconciling one vendor immediately: upload both
the company ledger and the vendor ledger in one sitting, map columns for
each side, and run the match without waiting on the vendor portal.

### 3. Column Mapping
Maps each side's raw file headers to standard fields (Invoice No, Invoice/
Document Date, Amount, Document Type, Party Code, Narration, Clearing Doc,
TDS Amount). Auto-detects likely columns from a header-alias library and
remembers the mapping per case. Shows a document-type breakdown (count +
amount per type) before confirming.

### 4. Matching Engine
Multi-pass reconciliation engine that runs in priority order:
1. **Exact Match** — amount + document date + invoice number identical.
2. **Tolerance Match** — invoice number matches, amount within configured
   tolerance or TDS/GST band.
3. **Fuzzy Reference Match** — invoice numbers are similar but not
   identical.
4. **One-to-Many / Many-to-One** — subset-sum grouping (e.g. one invoice
   split across several vendor entries).
5. **Date-Proximity Match** — amount matches, date within tolerance window.
6. **TDS/GST Tolerance Match** — gap explained by the configured tax rate.
7. **Amount + Date Match** — amounts equal, dates close, no reliable
   invoice number on either side.
8. **UTR-based Payment Grouping** — combines split company payments under
   the same UTR before matching against a vendor receipt.
9. **TDS Sequential Link** — links a standalone vendor TDS entry to an
   already-matched invoice pair as a third leg.
10. **Amount Mismatch** — same invoice number *and* same document date on
    both sides, but the gap doesn't fit the configured TDS/GST band; still
    matched (not left open) and flagged for review.
11. **Reversal / Knock-off & "Other Entry" netting** — same-side-only
    netting for AB/SA-type internal entries.
12. **Unmatched** — everything left over, reported as an open item on
    whichever side is missing it.

Category-aware gating ensures an invoice only matches an invoice, a payment
only a payment, etc. — the one deliberate cross-category exception being
Debit Note ↔ Credit Note.

### 5. Manual Linking & Review
For anything not auto-matched, a reviewer can manually link two entries
(with a mandatory reason from a standard status-reason list), delink an
existing match, or review/confirm passes that need human sign-off
(fuzzy/grouped/date-proximity/amount-mismatch matches).

### 6. Reconciliation Output
Tabs for Matched, Unmatched (company/vendor), and Recommended items, each
with search, filters, and inline link/delink actions. A Confirmation tab
lets the reviewer finalize the reconciliation once satisfied.

### 7. Export & Reporting
Generates a Firmway-style multi-sheet Excel export: a Summary sheet (header
info, itemized difference categories with linked annexure sheets, matched-
pair residuals like TDS/write-offs/amount-mismatch, and a zero-sum
reconciliation check), a full Reconciliation sheet, per-category annexure
sheets, and a Party sheet.

### 8. Vendor Portal
Token-based, unauthenticated access for vendors: view/validate their
invite link, upload their ledger statement, view reconciliation results,
sign off, raise a dispute, or request a new link if theirs expired.

### 9. Approvals & Workflow
Configurable approval matrix and workflow builder for routing cases through
internal approval steps before sign-off/closure; tracks workflow step
history and SLA deadlines per case.

### 10. Notifications & Reminders
Email templates (editable, with placeholders like `{{vendor_name}}`,
`{{company_name}}`, `{{portal_link}}`) drive vendor invite, reminder, and
escalation emails. Reminder scheduling and notification history are
tracked per case.

### 11. Exceptions & Recovery
Tracks reconciliation exceptions and recovery items (e.g. amounts to be
recovered from a vendor) with follow-up tracking.

### 12. Dashboard & Reports
Landing dashboard with case/request KPIs, recent sign-offs, and SLA
status; a Reports section for vendor status and reconciliation summary
reports.

---

## Vendor & Master Data Management
- **Vendor (Party) Management** — create/edit vendors, manage multiple
  contacts per vendor, bulk import/export via CSV, PAN/GSTIN capture.
- **Document Type Mapping** — maps raw SAP/Tally document type codes
  (KR, KZ, KA, KG, AB, SA, etc.) to standard categories (Invoice, Payment,
  Debit/Credit Note, TDS Adjusted, Knocking Off, Adjusted).
- **Company Profile / Entities** — manage multiple company entities
  (e.g. Emcure, Gennova, Zuventus), each with its own name, PAN, letterhead,
  and branding used in exports and outbound emails.
- **SAP Integration** — settings and a "pull" flow for sourcing company
  ledger data directly from SAP instead of a manual file upload.

## Administration
- **User Management** — user list, employee-AD import, role assignment.
- **RBAC Admin** — role/permission management and audit logs of access
  changes.
- **Settings** — email (SMTP) configuration, email templates, reminder
  intervals/escalation rules, general application settings.
- **Commission Claims** — a separate lightweight claims module alongside
  the core VLR workflow.

## Platform-Level
- Authentication via username/password and Microsoft SSO, with a service
  menu for Employee AD lookups.
- Notification history log across all outbound emails.
- Audit trail for key actions across the app.
