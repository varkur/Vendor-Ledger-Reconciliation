# Requirements Document

## Introduction

This document specifies the requirements for a complete rebuild of the Vendor Ledger Reconciliation (VLR) application. The system automates the reconciliation of company ledger entries (from SAP) against vendor-provided statements, supporting a 10-step workflow from initiation through vendor sign-off. The rebuild encompasses 13 modules covering data transformation, SAP integration, column mapping, workflow orchestration, email notifications, reconciliation output, frontend wiring, dashboards, reports, recovery tracking, business rules, audit trails, and structured logging.

## Glossary

- **VLR_System**: The Vendor Ledger Reconciliation application comprising backend (Python/FastAPI, SQLAlchemy, Celery, PostgreSQL) and frontend (TypeScript, React, PrimeReact, Vite, React Query, Redux Toolkit, Axios)
- **Data_Transformation_Engine**: The backend module responsible for invoice number derivation, sign adjustment, balance calculation, TDS tagging, and document type classification
- **SAP_Adapter**: The pluggable interface layer (SAPAdapterInterface) that abstracts SAP RFC connectivity from business logic, supporting MockSAPAdapter for testing
- **Column_Mapping_Engine**: The UI and backend module that allows users to map uploaded vendor statement columns to transaction type tags
- **Workflow_Orchestrator**: The Celery-based state machine managing the 10-step reconciliation lifecycle
- **Email_Service**: The SMTP/Jinja2-based notification system handling vendor invites, reminders, and escalations
- **Reconciliation_Engine**: The multi-pass matching algorithm that compares company and vendor ledger entries
- **Reconciliation_Output_View**: The 5-tab frontend UI displaying match results, unmatched items, and differences summary
- **Dashboard_Module**: The real-time widget-based overview page showing reconciliation KPIs
- **Reports_Module**: The module generating reconciliation summary, aging analysis, exception, vendor status, and MIS reports
- **Recovery_Module**: The module tracking recoverable amounts and follow-up reminders
- **Audit_Trail_Module**: The immutable event logging system with 7-year retention
- **Vendor_Portal**: The external-facing portal where vendors authenticate via token, upload statements, and sign off
- **ZUONR**: SAP assignment number field
- **XBLNR**: SAP reference document number field
- **BELNR**: SAP accounting document number field
- **SHKZG**: SAP debit/credit indicator field (H = credit, S = debit)
- **CLEAN_Function**: A text normalization function that strips leading zeros, special characters, and whitespace from reference numbers
- **TDS**: Tax Deducted at Source entries that require special tagging and linking
- **Reconciliation_Case**: A single reconciliation instance for one vendor within a specific period
- **Finance_User**: An internal user with the Finance Reviewer role
- **Recon_Manager**: An internal user with the Reconciliation Manager role
- **Vendor_User**: An external user accessing the Vendor Portal via token-based authentication

## Requirements

### Requirement 1: Invoice Number Derivation

**User Story:** As a Finance_User, I want the system to automatically derive a consistent invoice number from SAP data, so that matching against vendor statements uses normalized reference values.

#### Acceptance Criteria

1. WHEN a SAP ledger entry is loaded, THE Data_Transformation_Engine SHALL derive the invoice number using ZUONR as the primary source
2. IF ZUONR is empty or null, THEN THE Data_Transformation_Engine SHALL fall back to XBLNR as the secondary source
3. IF both ZUONR and XBLNR are empty or null, THEN THE Data_Transformation_Engine SHALL fall back to BELNR as the tertiary source
4. WHEN an invoice number is derived from any source, THE Data_Transformation_Engine SHALL apply the CLEAN_Function to strip leading zeros, special characters, and whitespace
5. THE Data_Transformation_Engine SHALL store both the raw source value and the cleaned derived invoice number for each entry

### Requirement 2: Sign Adjustment Logic

**User Story:** As a Finance_User, I want amounts to be automatically adjusted based on debit/credit indicators, so that reconciliation compares correctly signed values.

#### Acceptance Criteria

1. WHEN a SAP entry has SHKZG value of "H" (credit), THE Data_Transformation_Engine SHALL convert the amount to a positive value
2. WHEN a SAP entry has SHKZG value of "S" (debit), THE Data_Transformation_Engine SHALL convert the amount to a negative value
3. THE Data_Transformation_Engine SHALL apply sign adjustment before any balance calculation or matching operation
4. THE Data_Transformation_Engine SHALL preserve the original unsigned amount and SHKZG indicator alongside the adjusted amount

### Requirement 3: Opening Balance Calculation

**User Story:** As a Finance_User, I want the system to calculate the opening balance for a reconciliation period, so that the reconciliation output includes accurate starting positions.

#### Acceptance Criteria

1. WHEN a reconciliation period is defined, THE Data_Transformation_Engine SHALL calculate the opening balance as the sum of all sign-adjusted open items with a posting date before the period start date
2. THE Data_Transformation_Engine SHALL include only items that remain uncleared as of the period start date in the opening balance calculation
3. THE Data_Transformation_Engine SHALL calculate separate opening balances for company ledger and vendor ledger sides

### Requirement 4: Closing Balance Calculation

**User Story:** As a Finance_User, I want the system to calculate the closing balance for a reconciliation period, so that I can verify the net position at period end.

#### Acceptance Criteria

1. THE Data_Transformation_Engine SHALL calculate the closing balance as opening balance plus net movement during the reconciliation period
2. THE Data_Transformation_Engine SHALL define net movement as the sum of all sign-adjusted entries with posting dates within the reconciliation period
3. THE Data_Transformation_Engine SHALL calculate separate closing balances for company ledger and vendor ledger sides

### Requirement 5: TDS Row Tagging and Linking

**User Story:** As a Finance_User, I want TDS entries to be automatically identified and linked to their parent invoices, so that TDS differences are explained during reconciliation.

#### Acceptance Criteria

1. WHEN a ledger entry has a document type associated with TDS, THE Data_Transformation_Engine SHALL tag the entry as a TDS row
2. WHEN a TDS row is identified, THE Data_Transformation_Engine SHALL attempt to link the TDS entry to its parent invoice using the reference number
3. IF a TDS entry cannot be linked to a parent invoice, THEN THE Data_Transformation_Engine SHALL flag the entry for manual review

### Requirement 6: Multi-Currency Handling

**User Story:** As a Finance_User, I want the system to handle transactions in multiple currencies, so that reconciliation works correctly for vendors with foreign currency transactions.

#### Acceptance Criteria

1. THE Data_Transformation_Engine SHALL store both the transaction currency amount and the local currency (INR) equivalent for each entry
2. WHEN performing reconciliation matching, THE Reconciliation_Engine SHALL compare amounts in the same currency
3. THE Reconciliation_Output_View SHALL display both transaction currency and local currency values when they differ

### Requirement 7: Document Type Classification

**User Story:** As a Finance_User, I want ledger entries classified by document type, so that reconciliation analysis can group and filter by transaction category.

#### Acceptance Criteria

1. THE Data_Transformation_Engine SHALL classify entries with document types RE, KR, or DR as Invoice
2. THE Data_Transformation_Engine SHALL classify entries with document types ZP, KZ, or ZV as Payment
3. THE Data_Transformation_Engine SHALL classify entries with document type KG as Credit Note
4. THE Data_Transformation_Engine SHALL classify entries with document type RV as Debit Note
5. WHERE the document type classification mapping is configurable, THE VLR_System SHALL allow administrators to add, modify, or remove document type to category mappings without code changes

### Requirement 8: SAP Adapter Pluggable Interface

**User Story:** As a developer, I want the SAP integration layer to be a pluggable adapter, so that the real RFC adapter can be swapped in without modifying business logic.

#### Acceptance Criteria

1. THE SAP_Adapter SHALL define an abstract interface (SAPAdapterInterface) with methods for pulling All Items and Open Items
2. THE SAP_Adapter SHALL accept FBL1N-equivalent parameters including vendor code (LIFNR), company code (BUKRS), posting date range (BUDAT), and document type filters
3. THE VLR_System SHALL include a MockSAPAdapter implementation that returns realistic data shapes matching the interface contract
4. WHEN the real RFC adapter is deployed, THE VLR_System SHALL require zero changes to business logic services that consume the SAP_Adapter interface
5. THE SAP_Adapter SHALL support both All Items pull (cleared and open) and Open Items pull (uncleared only) modes

### Requirement 9: Column Mapping Preview

**User Story:** As a Finance_User, I want to preview uploaded vendor statement data before mapping columns, so that I can verify the file content and assign correct column types.

#### Acceptance Criteria

1. WHEN a vendor statement file is uploaded, THE Column_Mapping_Engine SHALL display the first 10 rows of the file as a preview
2. THE Column_Mapping_Engine SHALL display a dropdown for each column header allowing assignment of transaction type tags
3. THE Column_Mapping_Engine SHALL support the following transaction type tags: INVOICE, PAYMENT, TDS, CREDIT_NOTE, DEBIT_NOTE, OPENING_BALANCE, CLOSING_BALANCE, DATE, REFERENCE, AMOUNT, DESCRIPTION, IGNORE

### Requirement 10: Column Mapping Templates

**User Story:** As a Finance_User, I want column mapping configurations saved per vendor, so that subsequent uploads from the same vendor are mapped automatically.

#### Acceptance Criteria

1. WHEN a column mapping is completed for a vendor, THE Column_Mapping_Engine SHALL offer to save the mapping as a template associated with that vendor
2. WHEN a file is uploaded for a vendor with an existing mapping template, THE Column_Mapping_Engine SHALL auto-apply the saved template
3. THE Column_Mapping_Engine SHALL allow users to modify an auto-applied template before confirming the mapping

### Requirement 11: Auto-Mapping Intelligence

**User Story:** As a Finance_User, I want the system to suggest column mappings based on header names, so that common formats are mapped quickly with minimal manual effort.

#### Acceptance Criteria

1. WHEN a file is uploaded, THE Column_Mapping_Engine SHALL compare column headers against a known header library to suggest mappings
2. THE Column_Mapping_Engine SHALL assign a confidence score (High, Medium, or Low) to each auto-mapping suggestion
3. WHEN confidence is High, THE Column_Mapping_Engine SHALL pre-select the suggested mapping in the dropdown
4. WHEN confidence is Medium or Low, THE Column_Mapping_Engine SHALL display the suggestion as a recommendation without pre-selecting

### Requirement 12: 10-Step Workflow Orchestration

**User Story:** As a Finance_User, I want the reconciliation process to follow a defined 10-step workflow with status tracking, so that each case progresses through the correct lifecycle stages.

#### Acceptance Criteria

1. THE Workflow_Orchestrator SHALL implement the following steps in sequence: Initiation, SAP Pull, Transformation, Finance Review, Column Mapping, Vendor Engagement, Auto-Reconciliation, Exception Resolution, Finance Approval, Vendor Sign-Off, and Closure
2. THE Workflow_Orchestrator SHALL track the current status of each Reconciliation_Case at all times
3. THE Workflow_Orchestrator SHALL execute each workflow step as a Celery task enabling asynchronous processing
4. THE Workflow_Orchestrator SHALL support rollback capability allowing a case to return to a previous step when an error occurs or when explicitly requested by a Recon_Manager

### Requirement 13: Workflow SLA Monitoring

**User Story:** As a Recon_Manager, I want SLA tracking per workflow step, so that I can identify overdue cases and take corrective action.

#### Acceptance Criteria

1. THE Workflow_Orchestrator SHALL define configurable SLA durations for each workflow step
2. WHEN a workflow step exceeds its SLA duration, THE Workflow_Orchestrator SHALL flag the case as overdue
3. WHEN a case becomes overdue, THE Email_Service SHALL send an escalation notification to the assigned Recon_Manager

### Requirement 14: Email Vendor Invite

**User Story:** As a Finance_User, I want the system to automatically send vendor invite emails with portal access links, so that vendors can upload their statements without manual coordination.

#### Acceptance Criteria

1. WHEN the Vendor Engagement step is reached, THE Email_Service SHALL send an invite email to the vendor contact with a unique portal link
2. THE Email_Service SHALL use configurable Jinja2 templates for the invite email content
3. THE Email_Service SHALL send emails via SMTP integration
4. THE Email_Service SHALL schedule email sending as a Celery task to avoid blocking the main process

### Requirement 15: Email Auto-Reminders

**User Story:** As a Finance_User, I want automatic reminders sent to non-responsive vendors, so that statement uploads happen within acceptable timelines.

#### Acceptance Criteria

1. IF a vendor has not uploaded a statement within 3 days of the invite, THEN THE Email_Service SHALL send a first reminder (D3)
2. IF a vendor has not uploaded a statement within 7 days of the invite, THEN THE Email_Service SHALL send a second reminder (D7)
3. IF a vendor has not uploaded a statement within 10 days of the invite, THEN THE Email_Service SHALL send a third reminder (D10)
4. WHEN all reminders are exhausted without response, THE Email_Service SHALL send an escalation notification to the assigned Recon_Manager

### Requirement 16: Email Notifications for Approvals

**User Story:** As a Finance_User, I want email notifications when my approval is required, so that I can act on pending reconciliation cases promptly.

#### Acceptance Criteria

1. WHEN a Reconciliation_Case reaches the Finance Approval step, THE Email_Service SHALL send an approval request notification to the assigned Finance_User
2. WHEN a vendor upload is confirmed, THE Email_Service SHALL send an upload confirmation notification to the Finance_User who initiated the reconciliation
3. THE Email_Service SHALL include a direct link to the relevant case in all notification emails

### Requirement 17: Reconciliation Multi-Pass Matching

**User Story:** As a Finance_User, I want the system to automatically match company and vendor entries using multiple matching strategies, so that the maximum number of entries are reconciled without manual effort.

#### Acceptance Criteria

1. THE Reconciliation_Engine SHALL execute matching passes in the following sequence: Pass 1 (Exact Match), Pass 2 (Tolerance Match), Pass 3 (Fuzzy Reference Match), Pass 4 (One-to-Many), Pass 5 (Many-to-One), Pass 6 (Date-proximity Match), Pass 7 (Unmatched Remainder)
2. THE Reconciliation_Engine SHALL assign a confidence score to each match result
3. THE Reconciliation_Engine SHALL enforce a no-double-match invariant where no entry is matched more than once across all passes
4. WHEN Pass 1 produces matches, THE Reconciliation_Engine SHALL exclude those matched entries from all subsequent passes


### Requirement 18: Reconciliation Output - Matched Items Tab

**User Story:** As a Finance_User, I want to view all matched entries with their match type and confidence score, so that I can review auto-reconciliation results.

#### Acceptance Criteria

1. THE Reconciliation_Output_View SHALL display a Matched Items tab (Tab 1) listing all matched entry pairs and groups
2. THE Reconciliation_Output_View SHALL show the match type (Exact, Tolerance, Fuzzy, One-to-Many, Many-to-One, Date-proximity) for each match
3. THE Reconciliation_Output_View SHALL show the confidence score for each match result
4. THE Reconciliation_Output_View SHALL support sorting, filtering, and pagination on the Matched Items tab

### Requirement 19: Reconciliation Output - Finance Confirmation Tab

**User Story:** As a Finance_User, I want a dedicated tab for entries requiring my confirmation, so that I can accept, reject, or request clarification on uncertain matches.

#### Acceptance Criteria

1. THE Reconciliation_Output_View SHALL display a Finance Confirmation Required tab (Tab 2) listing matches that need manual review
2. THE Reconciliation_Output_View SHALL provide Accept, Reject, and Clarify action buttons for each entry on Tab 2
3. WHEN a Finance_User accepts a match on Tab 2, THE VLR_System SHALL move the entry to the confirmed matches list
4. WHEN a Finance_User rejects a match on Tab 2, THE VLR_System SHALL move the entries back to the unmatched pool

### Requirement 20: Reconciliation Output - Unmatched Company Ledger Tab

**User Story:** As a Finance_User, I want to see entries in the company ledger that have no vendor match, so that I can decide on appropriate resolution actions.

#### Acceptance Criteria

1. THE Reconciliation_Output_View SHALL display an Unmatched-Company Ledger tab (Tab 3) listing company entries with no vendor match
2. THE Reconciliation_Output_View SHALL provide Accept, Dispute, and Request actions for each entry on Tab 3
3. THE Reconciliation_Output_View SHALL display the document type, amount, posting date, and reference number for each unmatched company entry

### Requirement 21: Reconciliation Output - Unmatched Vendor Ledger Tab

**User Story:** As a Finance_User, I want to see entries in the vendor statement that have no company match, so that I can investigate discrepancies.

#### Acceptance Criteria

1. THE Reconciliation_Output_View SHALL display an Unmatched-Vendor Ledger tab (Tab 4) listing vendor entries with no company match
2. THE Reconciliation_Output_View SHALL provide Accept, Reject, and Clarify actions for each entry on Tab 4
3. THE Reconciliation_Output_View SHALL display the mapped transaction type, amount, date, and reference for each unmatched vendor entry

### Requirement 22: Reconciliation Output - Differences Summary Tab

**User Story:** As a Finance_User, I want a summary view showing opening/closing balance comparisons and totals by transaction type, so that I can assess the overall reconciliation status at a glance.

#### Acceptance Criteria

1. THE Reconciliation_Output_View SHALL display a Differences Summary tab (Tab 5) showing opening balance comparison between company and vendor
2. THE Reconciliation_Output_View SHALL display closing balance comparison between company and vendor on Tab 5
3. THE Reconciliation_Output_View SHALL display totals grouped by transaction type (Invoice, Payment, Credit Note, Debit Note) on Tab 5
4. THE Reconciliation_Output_View SHALL display the net difference between company and vendor ledgers on Tab 5

### Requirement 23: Frontend API Wiring - Core Pages

**User Story:** As a Finance_User, I want all application pages connected to real backend data, so that the interface displays live information instead of hardcoded content.

#### Acceptance Criteria

1. THE VLR_System SHALL connect the Direct Reconciliation page to backend APIs for initiating and managing reconciliation cases
2. THE VLR_System SHALL connect the Track Reconciliation page to backend APIs for listing and filtering all reconciliation cases with their statuses
3. THE VLR_System SHALL connect the Request Statement page to backend APIs for creating vendor statement requests
4. THE VLR_System SHALL connect the Exceptions page to backend APIs for listing, filtering, and resolving exceptions
5. THE VLR_System SHALL connect the Notifications page to backend APIs for listing notification history
6. THE VLR_System SHALL connect the Reports page to backend APIs for generating and downloading reports
7. THE VLR_System SHALL connect the Settings page to backend APIs for managing application configuration

### Requirement 24: Frontend API Wiring - Vendor Portal

**User Story:** As a Vendor_User, I want the vendor portal to work with real backend services, so that I can authenticate, upload statements, view reconciliation status, and sign off on results.

#### Acceptance Criteria

1. THE Vendor_Portal SHALL connect the authentication page to backend token validation APIs
2. THE Vendor_Portal SHALL connect the upload page to backend file upload APIs with progress indicators
3. THE Vendor_Portal SHALL connect the statement view page to backend APIs for displaying reconciliation results
4. THE Vendor_Portal SHALL connect the sign-off page to backend APIs for recording vendor approval

### Requirement 25: Frontend Loading and Error States

**User Story:** As a Finance_User, I want proper loading indicators and error messages on all pages, so that I understand the system state during data fetches and failures.

#### Acceptance Criteria

1. WHILE data is being fetched from backend APIs, THE VLR_System SHALL display loading indicators on the affected page sections
2. IF a backend API call fails, THEN THE VLR_System SHALL display a user-friendly error message with a retry option
3. THE VLR_System SHALL implement pagination on all list views with configurable page sizes
4. THE VLR_System SHALL implement search and filter capabilities on all list views

### Requirement 26: Dashboard Real-Time Widgets

**User Story:** As a Finance_User, I want a dashboard showing key reconciliation metrics, so that I can monitor workload and performance at a glance.

#### Acceptance Criteria

1. THE Dashboard_Module SHALL display the count of Open Cases (active reconciliations not yet closed)
2. THE Dashboard_Module SHALL display the count of cases Pending Vendor Upload
3. THE Dashboard_Module SHALL display the count of cases Pending Finance Review
4. THE Dashboard_Module SHALL display the count of Overdue Cases (exceeding SLA)
5. THE Dashboard_Module SHALL display the count of Cases Closed This Month
6. THE Dashboard_Module SHALL display the Average Cycle Time (mean days from initiation to closure)
7. THE Dashboard_Module SHALL display the Auto-Match Rate (percentage of entries matched automatically)
8. THE Dashboard_Module SHALL display a Recent Confirmations table with sortable columns

### Requirement 27: Reconciliation Summary Report

**User Story:** As a Finance_User, I want a reconciliation summary report in the standard 10-row format, so that the final output follows the prescribed BRD structure.

#### Acceptance Criteria

1. THE Reports_Module SHALL generate a Reconciliation Summary Report containing: Emcure Closing Balance, adjustment rows (unmatched items, TDS differences, timing differences), Adjusted Emcure Balance, Vendor Closing Balance, adjustment rows, Adjusted Vendor Balance, and Net Difference
2. THE Reports_Module SHALL ensure the Net Difference row equals zero for a fully reconciled case
3. THE Reports_Module SHALL support export of the Reconciliation Summary Report in PDF and Excel formats

### Requirement 28: Aging Analysis Report

**User Story:** As a Recon_Manager, I want aging analysis reports by vendor, bucket, and status, so that I can identify long-outstanding items and prioritize follow-ups.

#### Acceptance Criteria

1. THE Reports_Module SHALL generate an Aging Analysis Report groupable by vendor, aging bucket, and reconciliation status
2. THE Reports_Module SHALL define aging buckets as: 0-30 days, 31-60 days, 61-90 days, 91-180 days, and over 180 days
3. THE Reports_Module SHALL support export of the Aging Analysis Report in PDF and Excel formats

### Requirement 29: Exception and Audit Reports

**User Story:** As a Recon_Manager, I want exception reports with full audit trails, so that I can investigate discrepancies and review all actions taken.

#### Acceptance Criteria

1. THE Reports_Module SHALL generate an Exception Report listing all unmatched and disputed items with their resolution history
2. THE Reports_Module SHALL generate a Vendor Status Tracking Report showing each vendor's reconciliation progress
3. THE Reports_Module SHALL generate a monthly MIS Report summarizing reconciliation activity across all vendors
4. THE Reports_Module SHALL support export of all reports in PDF and Excel formats

### Requirement 30: Recovery Register

**User Story:** As a Finance_User, I want a register of amounts recoverable from vendors, so that I can track and follow up on outstanding recoveries.

#### Acceptance Criteria

1. THE Recovery_Module SHALL maintain a register of items identified as recoverable from vendors
2. THE Recovery_Module SHALL track the recovery status (Open, In Progress, Recovered, Written Off) for each item
3. THE Recovery_Module SHALL record the recovery amount, vendor, case reference, and date identified for each item

### Requirement 31: Recovery Follow-Up Reminders

**User Story:** As a Finance_User, I want automatic follow-up reminders for pending recoveries, so that recoverable amounts are not forgotten.

#### Acceptance Criteria

1. THE Recovery_Module SHALL auto-trigger follow-up reminders on a configurable schedule for open recovery items
2. THE Recovery_Module SHALL maintain a follow-up log per item recording each action taken with a timestamp
3. THE Recovery_Module SHALL allow Finance_User to update the recovery status and add notes after each follow-up action

### Requirement 32: One-Sided Reconciliation Closure

**User Story:** As a Recon_Manager, I want to close a reconciliation case unilaterally when a vendor is non-responsive, so that cases do not remain open indefinitely.

#### Acceptance Criteria

1. WHEN a vendor has not responded after all reminder cycles, THE VLR_System SHALL allow the Recon_Manager to initiate one-sided closure
2. THE VLR_System SHALL require explicit Recon_Manager approval for one-sided reconciliation closure
3. THE VLR_System SHALL record the justification and approver details for every one-sided closure

### Requirement 33: Portal Link Validity

**User Story:** As a Recon_Manager, I want vendor portal links to expire after 90 days, so that late vendor responses are controlled and security is maintained.

#### Acceptance Criteria

1. THE Vendor_Portal SHALL enforce a 90-day validity period for portal access links sent to vendors
2. IF a vendor accesses a portal link after the 90-day expiry, THEN THE Vendor_Portal SHALL display an expiry message and deny access
3. THE VLR_System SHALL allow a Recon_Manager to generate a new portal link for a vendor if the original has expired

### Requirement 34: Business Rule - Period Overlap Prevention

**User Story:** As a Finance_User, I want the system to prevent creating overlapping reconciliation periods for the same vendor, so that data integrity is maintained.

#### Acceptance Criteria

1. WHEN a new Reconciliation_Case is initiated, THE VLR_System SHALL validate that the requested period does not overlap with any existing active or closed case for the same vendor and company code
2. IF a period overlap is detected, THEN THE VLR_System SHALL reject the case creation and display the conflicting case reference

### Requirement 35: Business Rule - Active Vendor Required

**User Story:** As a Finance_User, I want the system to prevent reconciliation requests for inactive vendors, so that reconciliation efforts target valid vendor relationships.

#### Acceptance Criteria

1. WHEN a new reconciliation request is created, THE VLR_System SHALL verify that the vendor has an active status in the vendor master
2. IF the vendor is inactive, THEN THE VLR_System SHALL reject the request and inform the user that an active vendor is required

### Requirement 36: Business Rule - Match Exclusion After Pass 1

**User Story:** As a Finance_User, I want entries matched in Pass 1 (exact match) excluded from all subsequent matching passes, so that exact matches are never overwritten by lower-confidence matches.

#### Acceptance Criteria

1. WHEN Pass 1 (Exact Match) completes, THE Reconciliation_Engine SHALL mark all matched entries as consumed
2. THE Reconciliation_Engine SHALL exclude all consumed entries from Pass 2 through Pass 7 processing
3. THE Reconciliation_Engine SHALL apply the same exclusion rule after each subsequent pass (entries matched in Pass N are excluded from Pass N+1 onward)

### Requirement 37: Business Rule - Case Closure Condition

**User Story:** As a Finance_User, I want the system to enforce that a case can only be closed when the net difference is zero, so that only fully reconciled cases are marked as complete.

#### Acceptance Criteria

1. WHEN a user attempts to close a Reconciliation_Case, THE VLR_System SHALL verify that the net difference between company and vendor adjusted balances equals zero
2. IF the net difference is not zero, THEN THE VLR_System SHALL reject the closure and display the remaining difference amount
3. WHERE one-sided closure is approved by Recon_Manager, THE VLR_System SHALL allow closure regardless of the net difference value

### Requirement 38: Immutable Audit Event Logging

**User Story:** As a Recon_Manager, I want all system actions logged immutably, so that a complete audit trail exists for compliance and investigation purposes.

#### Acceptance Criteria

1. THE Audit_Trail_Module SHALL log every significant system event as an immutable record (no update or delete operations permitted on audit entries)
2. THE Audit_Trail_Module SHALL capture the following event types: login/logout, case creation, status changes, match overrides, approvals, rejections, and vendor interactions
3. THE Audit_Trail_Module SHALL record the actor (user ID and username), timestamp, case ID, event type, and event details for each audit entry
4. THE Audit_Trail_Module SHALL retain all audit records for a minimum of 7 years

### Requirement 39: Audit Trail Search and Export

**User Story:** As a Recon_Manager, I want to search and export audit trail data, so that I can investigate specific events and provide evidence for audits.

#### Acceptance Criteria

1. THE Audit_Trail_Module SHALL support searching audit records by user, date range, case ID, and event type
2. THE Audit_Trail_Module SHALL support export of search results in Excel and CSV formats
3. THE Audit_Trail_Module SHALL return search results with pagination to handle large result sets

### Requirement 40: Structured JSON Logging

**User Story:** As a developer, I want all key operations logged in structured JSON format, so that logs are parseable for observability tooling and debugging.

#### Acceptance Criteria

1. THE VLR_System SHALL emit structured JSON log entries for all key backend operations including API requests, Celery task executions, SAP pulls, reconciliation passes, and email dispatches
2. THE VLR_System SHALL include correlation ID, timestamp, service name, operation name, duration, and outcome status in each structured log entry
3. THE VLR_System SHALL apply structured logging as a cross-cutting concern from module 1 (Data Transformation Engine) onward across all modules
4. IF an operation fails, THEN THE VLR_System SHALL include the error type and error message in the structured log entry without exposing sensitive data
