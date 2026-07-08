# Implementation Plan: VLR Complete Rebuild

## Overview

Complete rebuild of the Vendor Ledger Reconciliation (VLR) system following a 13-module build sequence. Each module builds on previous modules, progressing from core data transformation through to observability. The implementation extends existing backend services (Python/FastAPI/Celery/SQLAlchemy) and frontend features (React/PrimeReact/React Query/Redux Toolkit).

## Tasks

- [x] 1. Data Transformation Engine (Module 1)
  - [x] 1.1 Create data transformation service with invoice number derivation
    - Create `backend/src/domain/services/vlr/data_transformation_service.py`
    - Implement `derive_invoice_number()` with ZUONR > XBLNR > BELNR priority fallback
    - Implement `clean_reference()` to strip leading zeros, special characters, whitespace
    - Store both raw source value and cleaned derived invoice number
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5_

  - [ ]* 1.2 Write property tests for invoice derivation (Property 1, Property 2)
    - **Property 1: Invoice Number Derivation Priority**
    - **Property 2: Invoice Derivation Preserves Raw Value**
    - Use `hypothesis` to generate random SAP entries with various ZUONR/XBLNR/BELNR combinations
    - **Validates: Requirements 1.1, 1.2, 1.3, 1.4, 1.5**

  - [x] 1.3 Implement sign adjustment logic
    - Add `apply_sign_adjustment()` method: H → positive, S → negative
    - Preserve original unsigned amount and SHKZG indicator
    - Ensure sign adjustment runs before any balance calculation
    - _Requirements: 2.1, 2.2, 2.3, 2.4_

  - [ ]* 1.4 Write property test for sign adjustment (Property 3)
    - **Property 3: Sign Adjustment Correctness**
    - Generate random amounts with H/S indicators, verify sign and preservation
    - **Validates: Requirements 2.1, 2.2, 2.4**

  - [x] 1.5 Implement balance calculations (opening and closing)
    - Add `calculate_opening_balance()`: sum of sign-adjusted open items before period start
    - Add `calculate_closing_balance()`: opening + net movement within period
    - Calculate separate balances for company and vendor sides
    - _Requirements: 3.1, 3.2, 3.3, 4.1, 4.2, 4.3_

  - [ ]* 1.6 Write property test for balance calculation (Property 4)
    - **Property 4: Balance Calculation Arithmetic Invariant**
    - Generate random entry sets and period boundaries, verify closing = opening + net movement
    - **Validates: Requirements 3.1, 3.2, 3.3, 4.1, 4.2, 4.3**

  - [x] 1.7 Implement TDS tagging and linking
    - Add `tag_tds_entries()` method to identify TDS entries by document type
    - Link TDS entries to parent invoices by reference number
    - Flag unlinked TDS entries for manual review
    - _Requirements: 5.1, 5.2, 5.3_

  - [ ]* 1.8 Write property test for TDS tagging (Property 5)
    - **Property 5: TDS Tagging Completeness**
    - Generate entries with TDS document types, verify tagging and linking
    - **Validates: Requirements 5.1, 5.2**

  - [x] 1.9 Implement multi-currency handling
    - Store transaction currency amount and local currency (INR) equivalent
    - Ensure reconciliation matching compares amounts in the same currency
    - _Requirements: 6.1, 6.2_

  - [ ]* 1.10 Write property test for multi-currency (Property 6)
    - **Property 6: Multi-Currency Comparison Invariant**
    - Verify same-currency comparison is enforced, no cross-currency mixing
    - **Validates: Requirements 6.1, 6.2**

  - [x] 1.11 Implement document type classification
    - Add `classify_document_type()` with configurable mapping (RE/KR/DR→Invoice, ZP/KZ/ZV→Payment, KG→Credit Note, RV→Debit Note)
    - Create `vlr_document_type_mappings` database model and migration
    - Allow admin configuration without code changes
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5_

  - [ ]* 1.12 Write property test for document type classification (Property 7)
    - **Property 7: Document Type Classification Determinism**
    - Generate random doc type codes, verify deterministic single-category assignment
    - **Validates: Requirements 7.1, 7.2, 7.3, 7.4**

  - [x] 1.13 Add enhanced columns to `vlr_ledger_entries` model
    - Add columns: raw_reference, derived_invoice_number, invoice_source_field, original_amount, shkzg_indicator, adjusted_amount, transaction_currency, local_currency_amount, document_category, is_tds, tds_parent_entry_id
    - Create Alembic migration
    - _Requirements: 1.5, 2.4, 6.1, 7.1_

  - [x] 1.14 Create transformation API endpoint
    - Add `POST /api/v1/vlr/transform/{case_id}` endpoint to trigger the transformation pipeline
    - Wire service to existing case repository
    - _Requirements: 1.1, 2.1, 3.1, 4.1, 5.1, 6.1, 7.1_

- [x] 2. Checkpoint - Data Transformation Engine
  - Ensure all tests pass, ask the user if questions arise.

- [x] 3. SAP Adapter Pattern (Module 2)
  - [x] 3.1 Create SAP adapter abstract interface
    - Create `backend/src/domain/interfaces/sap_adapter_interface.py`
    - Define `SAPAdapterInterface` ABC with `pull_all_items()` and `pull_open_items()` methods
    - Accept FBL1N-equivalent parameters: vendor_code, company_code, date_from, date_to, doc_type_filters
    - _Requirements: 8.1, 8.2, 8.5_

  - [x] 3.2 Implement MockSAPAdapter for testing
    - Create `backend/src/infrastructure/external/mock_sap_adapter.py`
    - Return realistic data shapes matching the interface contract
    - Support both All Items and Open Items modes
    - _Requirements: 8.3, 8.5_

  - [x] 3.3 Implement RealSAPAdapter wrapping existing SAPConnectorService
    - Create `backend/src/infrastructure/external/real_sap_adapter.py`
    - Wrap existing `sap_connector.py` with the new abstract interface
    - Ensure zero changes required to business logic services
    - _Requirements: 8.4_

  - [ ]* 3.4 Write unit tests for SAP adapter interface contract
    - Verify MockSAPAdapter returns correct data shapes
    - Verify both adapters satisfy the interface contract
    - _Requirements: 8.1, 8.3, 8.4_

- [x] 4. Column Mapping Engine (Module 3)
  - [x] 4.1 Create column mapping database model and repository
    - Create `vlr_column_mapping_templates` model in `backend/src/infrastructure/database/models/vlr/`
    - Create `IColumnMappingTemplateRepository` interface and SQLAlchemy implementation
    - Create Alembic migration
    - _Requirements: 10.1, 10.2_

  - [x] 4.2 Implement column mapping service
    - Create `backend/src/domain/services/vlr/column_mapping_service.py`
    - Implement `generate_preview()`: return first 10 rows of uploaded file
    - Implement `auto_map_columns()`: compare headers against known library, assign confidence scores
    - Implement `apply_template()` and `save_template()` for per-vendor persistence
    - Support 12 transaction type tags: INVOICE, PAYMENT, TDS, CREDIT_NOTE, DEBIT_NOTE, OPENING_BALANCE, CLOSING_BALANCE, DATE, REFERENCE, AMOUNT, DESCRIPTION, IGNORE
    - _Requirements: 9.1, 9.2, 9.3, 10.1, 10.2, 10.3, 11.1, 11.2, 11.3, 11.4_

  - [ ]* 4.3 Write property tests for column mapping (Property 8, 9, 10)
    - **Property 8: Column Mapping Preview Row Count**
    - **Property 9: Auto-Mapping Template Application**
    - **Property 10: Auto-Mapping Confidence Validity**
    - **Validates: Requirements 9.1, 10.2, 11.1, 11.2**

  - [x] 4.4 Create column mapping API endpoints
    - Add `POST /api/v1/vlr/column-mapping/preview` for file upload and 10-row preview
    - Add `POST /api/v1/vlr/column-mapping/auto-map` for auto-mapping suggestions
    - Add `POST /api/v1/vlr/column-mapping/save-template` to save mapping template
    - Add `GET /api/v1/vlr/column-mapping/template/{vendor_id}` to retrieve saved template
    - _Requirements: 9.1, 10.1, 10.2, 11.1_

  - [x] 4.5 Build column mapping frontend component
    - Create `frontend/src/features/direct-reconciliation/components/ColumnMapping/`
    - Implement file preview grid (10 rows) with PrimeReact DataTable
    - Per-column dropdowns for tag assignment
    - Auto-mapping suggestions with confidence badges (High/Medium/Low)
    - Template save/load functionality
    - _Requirements: 9.1, 9.2, 9.3, 10.1, 10.2, 10.3, 11.1, 11.2, 11.3, 11.4_

- [x] 5. Workflow Orchestration (Module 4)
  - [x] 5.1 Create workflow database models and migrations
    - Create `vlr_workflow_step_history` model
    - Create `vlr_sla_configurations` model
    - Add workflow columns to `vlr_reconciliation_cases` (current_workflow_step, step_entered_at, sla_deadline, is_overdue)
    - Create Alembic migrations for all new tables/columns
    - _Requirements: 12.1, 12.2, 13.1_

  - [x] 5.2 Implement workflow orchestrator service
    - Create `backend/src/domain/services/vlr/workflow_orchestrator_service.py`
    - Implement `WorkflowStep` enum with all 11 steps (including Closure)
    - Define `VALID_TRANSITIONS` map per design
    - Implement `advance()` with transition validation
    - Implement `rollback()` for returning to previous step
    - Implement `check_sla_violations()` for overdue detection
    - Execute each step as a Celery task
    - _Requirements: 12.1, 12.2, 12.3, 12.4, 13.1, 13.2_

  - [ ]* 5.3 Write property tests for workflow transitions (Property 11, 12)
    - **Property 11: Workflow Transition Validity**
    - **Property 12: SLA Violation Detection**
    - Generate random state sequences, verify only valid transitions permitted
    - Generate cases with various step durations, verify overdue flagging
    - **Validates: Requirements 12.1, 12.2, 12.4, 13.2**

  - [x] 5.4 Create workflow API endpoints
    - Add `POST /api/v1/vlr/workflow/{case_id}/advance`
    - Add `POST /api/v1/vlr/workflow/{case_id}/rollback`
    - Add `GET /api/v1/vlr/workflow/{case_id}/status`
    - Add `GET /api/v1/vlr/workflow/sla-violations`
    - _Requirements: 12.1, 12.4, 13.2_

  - [x] 5.5 Create Celery tasks for workflow step execution
    - Add tasks to `backend/src/infrastructure/tasks/vlr/` for each workflow step
    - Implement SLA monitoring periodic task
    - Configure retry logic and error handling per task type
    - _Requirements: 12.3, 13.2, 13.3_

- [x] 6. Checkpoint - Core Backend Infrastructure
  - Ensure all tests pass, ask the user if questions arise.

- [x] 7. Email System (Module 5)
  - [x] 7.1 Create Jinja2 email templates
    - Create `backend/src/infrastructure/email/templates/` directory
    - Create templates: vendor_invite.html, reminder_d3.html, reminder_d7.html, reminder_d10.html, escalation.html, approval_request.html, upload_confirmation.html
    - Each template includes a direct link to the relevant case
    - _Requirements: 14.2, 16.3_

  - [x] 7.2 Enhance notification service with reminder scheduling
    - Extend `backend/src/domain/services/vlr/notification_service.py`
    - Implement `send_vendor_invite()` with unique portal link
    - Implement `send_scheduled_reminder()` for D3/D7/D10 intervals
    - Implement `send_escalation()` when all reminders exhausted
    - Implement `send_approval_request()` for finance approval notifications
    - Send all emails as Celery tasks to avoid blocking
    - _Requirements: 14.1, 14.3, 14.4, 15.1, 15.2, 15.3, 15.4, 16.1, 16.2_

  - [ ]* 7.3 Write property tests for reminder scheduling (Property 13, 14)
    - **Property 13: Reminder Schedule Correctness**
    - **Property 14: Notification Case Link Inclusion**
    - Verify D3/D7/D10 intervals and escalation after exhaustion
    - Verify all emails contain case link URL
    - **Validates: Requirements 15.1, 15.2, 15.3, 16.3**

  - [x] 7.4 Create Celery periodic task for reminder scheduling
    - Add periodic task that checks for overdue vendor engagements
    - Trigger appropriate reminder (D3, D7, D10) based on elapsed time since invite
    - Trigger escalation when max reminders exhausted
    - _Requirements: 15.1, 15.2, 15.3, 15.4_

- [x] 8. Reconciliation Engine Enhancement + Output View (Module 6)
  - [x] 8.1 Add Pass 6 (Date-proximity Match) to reconciliation engine
    - Extend `backend/src/domain/services/vlr/reconciliation_engine_service.py`
    - Implement matching by amount + date within configurable N days
    - Add to `MatchPassType` enum as `DATE_PROXIMITY = 6`
    - Renumber Unmatched Remainder to Pass 7
    - _Requirements: 17.1_

  - [x] 8.2 Implement confidence scoring and no-double-match invariant
    - Assign confidence score [0.0, 1.0] to each match result
    - Enforce exclusion: entries matched in Pass N excluded from Pass N+1 onward
    - Mark matched entries as consumed after each pass
    - _Requirements: 17.2, 17.3, 17.4, 36.1, 36.2, 36.3_

  - [ ]* 8.3 Write property tests for reconciliation engine (Property 15, 16)
    - **Property 15: No-Double-Match Invariant**
    - **Property 16: Match Confidence Score Range**
    - Generate random entry sets, run full engine, verify no entry matched twice
    - Verify all confidence scores in [0.0, 1.0]
    - **Validates: Requirements 17.2, 17.3, 17.4, 36.1, 36.2, 36.3**

  - [x] 8.4 Create reconciliation output API endpoints
    - Add `GET /api/v1/vlr/reconciliation/{case_id}/matched` (Tab 1)
    - Add `GET /api/v1/vlr/reconciliation/{case_id}/confirmation` (Tab 2)
    - Add `GET /api/v1/vlr/reconciliation/{case_id}/unmatched-company` (Tab 3)
    - Add `GET /api/v1/vlr/reconciliation/{case_id}/unmatched-vendor` (Tab 4)
    - Add `GET /api/v1/vlr/reconciliation/{case_id}/summary` (Tab 5)
    - Add `POST /api/v1/vlr/reconciliation/{case_id}/confirm` (accept/reject match)
    - _Requirements: 18.1, 19.1, 20.1, 21.1, 22.1_

  - [x] 8.5 Build reconciliation output frontend (5-tab view)
    - Create `frontend/src/features/track-reconciliation/components/ReconciliationOutput/`
    - Tab 1: Matched Items with match type and confidence score, sorting/filtering/pagination
    - Tab 2: Finance Confirmation with Accept/Reject/Clarify buttons
    - Tab 3: Unmatched-Company with Accept/Dispute/Request actions
    - Tab 4: Unmatched-Vendor with Accept/Reject/Clarify actions
    - Tab 5: Differences Summary with opening/closing balance comparison and net difference
    - Use PrimeReact DataTable with React Query hooks
    - _Requirements: 18.1, 18.2, 18.3, 18.4, 19.1, 19.2, 19.3, 19.4, 20.1, 20.2, 20.3, 21.1, 21.2, 21.3, 22.1, 22.2, 22.3, 22.4_

  - [ ]* 8.6 Write property tests for finance confirmation state transitions (Property 17, 18)
    - **Property 17: Finance Confirmation State Transitions**
    - **Property 18: Differences Summary Consistency**
    - Verify accept moves to confirmed, reject returns to unmatched, total entry count constant
    - Verify Company Closing - Vendor Closing = Net Difference
    - **Validates: Requirements 19.3, 19.4, 22.1, 22.2, 22.3, 22.4**

- [x] 9. Checkpoint - Reconciliation Core Complete
  - Ensure all tests pass, ask the user if questions arise.

- [x] 10. Frontend Wiring - Core Pages (Module 7)
  - [x] 10.1 Wire Direct Reconciliation page to backend APIs
    - Connect initiation form to case creation API
    - Add React Query hooks for case management
    - Implement loading/error/empty states
    - _Requirements: 23.1, 25.1, 25.2_

  - [x] 10.2 Wire Track Reconciliation page to backend APIs
    - Connect listing/filtering to case query APIs
    - Implement pagination with configurable page sizes
    - Add search and filter capabilities
    - _Requirements: 23.2, 25.3, 25.4_

  - [x] 10.3 Wire Request Statement page to backend APIs
    - Connect statement request form to backend
    - Add loading indicators and error handling
    - _Requirements: 23.3, 25.1, 25.2_

  - [x] 10.4 Wire Exceptions page to backend APIs
    - Connect exception listing, filtering, and resolution to backend
    - Implement pagination and search
    - _Requirements: 23.4, 25.3, 25.4_

  - [x] 10.5 Wire Notifications, Reports, and Settings pages
    - Connect Notifications page to notification history API
    - Connect Reports page to report generation and download APIs
    - Connect Settings page to configuration APIs
    - _Requirements: 23.5, 23.6, 23.7, 25.1, 25.2_

  - [x] 10.6 Wire Vendor Portal pages to backend APIs
    - Connect token validation page to `POST /api/v1/vlr/portal/validate-token`
    - Connect upload page to `POST /api/v1/vlr/portal/upload` with progress indicators
    - Connect statement view to `GET /api/v1/vlr/portal/statement/{case_id}`
    - Connect sign-off page to `POST /api/v1/vlr/portal/sign-off/{case_id}`
    - _Requirements: 24.1, 24.2, 24.3, 24.4_

  - [x] 10.7 Create vendor portal backend endpoints
    - Add `POST /api/v1/vlr/portal/validate-token` with 90-day expiry check
    - Add `POST /api/v1/vlr/portal/upload` with file handling
    - Add `GET /api/v1/vlr/portal/statement/{case_id}` for results view
    - Add `POST /api/v1/vlr/portal/sign-off/{case_id}` for vendor approval
    - _Requirements: 24.1, 24.2, 24.3, 24.4, 33.1, 33.2_

- [x] 11. Dashboard (Module 8)
  - [x] 11.1 Create dashboard backend API
    - Add `GET /api/v1/vlr/dashboard/widgets` endpoint returning all KPI data
    - Add `GET /api/v1/vlr/dashboard/recent-confirmations` endpoint
    - Implement aggregation queries: Open Cases, Pending Vendor Upload, Pending Finance Review, Overdue Cases, Cases Closed This Month, Average Cycle Time, Auto-Match Rate
    - _Requirements: 26.1, 26.2, 26.3, 26.4, 26.5, 26.6, 26.7, 26.8_

  - [x] 11.2 Build dashboard frontend module
    - Create `frontend/src/features/dashboard/` module
    - Implement widget cards for each KPI metric
    - Implement Recent Confirmations table with sortable columns
    - Use React Query with auto-refresh for real-time data
    - _Requirements: 26.1, 26.2, 26.3, 26.4, 26.5, 26.6, 26.7, 26.8_

  - [ ]* 11.3 Write property test for dashboard widget accuracy (Property 19)
    - **Property 19: Dashboard Widget Accuracy**
    - Generate random case sets, verify aggregation correctness
    - **Validates: Requirements 26.1, 26.2, 26.3, 26.4, 26.7**

- [ ] 12. Reports (Module 9)
  - [x] 12.1 Implement reconciliation summary report (10-row format)
    - Extend `backend/src/domain/services/vlr/report_service.py`
    - Generate 10-row format: Emcure Closing, adjustments, Vendor Closing, Net Diff
    - Net Difference = 0 for fully reconciled cases
    - _Requirements: 27.1, 27.2_

  - [ ]* 12.2 Write property test for reconciliation summary (Property 20)
    - **Property 20: Reconciliation Summary Report Net Difference**
    - Generate fully/partially reconciled cases, verify net difference calculation
    - **Validates: Requirements 27.1, 27.2**

  - [x] 12.3 Implement aging analysis report
    - Add `generate_aging_analysis()` with grouping by vendor, bucket, status
    - Define buckets: 0-30, 31-60, 61-90, 91-180, 180+ days
    - _Requirements: 28.1, 28.2_

  - [ ]* 12.4 Write property test for aging bucket assignment (Property 21)
    - **Property 21: Aging Bucket Assignment Correctness**
    - Generate items with various posting dates, verify deterministic bucket assignment
    - **Validates: Requirements 28.1, 28.2**

  - [x] 12.5 Implement exception, vendor status, and MIS reports
    - Add `generate_exception_report()` with resolution history
    - Add vendor status tracking report
    - Add monthly MIS report
    - _Requirements: 29.1, 29.2, 29.3_

  - [x] 12.6 Implement PDF and Excel export
    - Add `export_to_pdf()` and `export_to_excel()` methods
    - Support export for all report types
    - _Requirements: 27.3, 28.3, 29.4_

  - [x] 12.7 Create report API endpoints
    - Add `GET /api/v1/vlr/reports/reconciliation-summary/{case_id}`
    - Add `GET /api/v1/vlr/reports/aging-analysis`
    - Add `GET /api/v1/vlr/reports/exceptions`
    - Add `GET /api/v1/vlr/reports/vendor-status`
    - Add `GET /api/v1/vlr/reports/mis`
    - Add `GET /api/v1/vlr/reports/export/{report_id}`
    - _Requirements: 27.1, 28.1, 29.1, 29.2, 29.3, 29.4_

- [x] 13. Checkpoint - Reports and Dashboard
  - Ensure all tests pass, ask the user if questions arise.

- [x] 14. Recovery & Follow-up (Module 10)
  - [x] 14.1 Create recovery database models and repository
    - Create `vlr_recovery_items` model
    - Create `vlr_recovery_follow_ups` model
    - Create `IRecoveryRepository` interface and SQLAlchemy implementation
    - Create Alembic migration
    - _Requirements: 30.1, 30.2, 30.3_

  - [x] 14.2 Implement recovery service
    - Create `backend/src/domain/services/vlr/recovery_service.py`
    - Implement `create_recovery_item()`, `update_status()`, `get_overdue_items()`
    - Implement `trigger_follow_up_reminders()` for auto-triggering reminders
    - Track status transitions: Open → In Progress → Recovered/Written Off
    - Maintain follow-up log per item with timestamps
    - _Requirements: 30.1, 30.2, 30.3, 31.1, 31.2, 31.3_

  - [ ]* 14.3 Write property test for recovery follow-up (Property 22)
    - **Property 22: Recovery Follow-Up Trigger**
    - Generate recovery items with various dates, verify overdue items trigger reminders
    - **Validates: Requirements 31.1, 31.2**

  - [x] 14.4 Create recovery API endpoints
    - Add `GET /api/v1/vlr/recovery` to list recovery items
    - Add `POST /api/v1/vlr/recovery` to create recovery item
    - Add `PATCH /api/v1/vlr/recovery/{item_id}` to update status/notes
    - Add `GET /api/v1/vlr/recovery/{item_id}/follow-ups` to get follow-up log
    - _Requirements: 30.1, 31.1, 31.3_

  - [x] 14.5 Create Celery periodic task for recovery follow-up reminders
    - Add periodic task checking for overdue recovery items
    - Auto-trigger reminders based on configurable schedule
    - Log each follow-up action with timestamp
    - _Requirements: 31.1, 31.2_

- [x] 15. One-Sided Reconciliation + Business Rules (Module 11)
  - [x] 15.1 Implement one-sided reconciliation closure
    - Add one-sided closure logic to workflow orchestrator
    - Require explicit Recon_Manager approval
    - Record justification and approver details
    - Bypass net-zero check for approved one-sided closures
    - _Requirements: 32.1, 32.2, 32.3_

  - [ ]* 15.2 Write property test for one-sided closure (Property 23)
    - **Property 23: One-Sided Closure Authorization**
    - Verify Recon_Manager approval required, justification recorded
    - **Validates: Requirements 32.2, 32.3**

  - [x] 15.3 Implement portal link expiry enforcement
    - Add 90-day validity check to portal token validation
    - Display expiry message and deny access after 90 days
    - Allow Recon_Manager to generate new portal link
    - _Requirements: 33.1, 33.2, 33.3_

  - [ ]* 15.4 Write property test for portal link expiry (Property 24)
    - **Property 24: Portal Link Expiry Enforcement**
    - Generate tokens with various creation dates, verify expiry logic
    - **Validates: Requirements 33.1, 33.2**

  - [x] 15.5 Implement period overlap prevention
    - Add validation to case creation: reject if overlapping period exists for same vendor+company code
    - Return conflicting case reference on rejection
    - _Requirements: 34.1, 34.2_

  - [ ]* 15.6 Write property test for period overlap (Property 25)
    - **Property 25: Period Overlap Prevention**
    - Generate random date ranges, verify overlap detection correctness
    - **Validates: Requirements 34.1, 34.2**

  - [x] 15.7 Implement active vendor validation
    - Add vendor status check to reconciliation request creation
    - Reject requests for inactive vendors with informative message
    - _Requirements: 35.1, 35.2_

  - [ ]* 15.8 Write property test for active vendor validation (Property 26)
    - **Property 26: Active Vendor Validation**
    - Generate vendors with active/inactive status, verify rejection logic
    - **Validates: Requirements 35.1, 35.2**

  - [x] 15.9 Implement case closure net-zero condition
    - Add net-zero validation to normal closure flow
    - Reject closure if net difference ≠ 0 (with remaining difference displayed)
    - Allow bypass for approved one-sided closures
    - _Requirements: 37.1, 37.2, 37.3_

  - [ ]* 15.10 Write property test for case closure condition (Property 27)
    - **Property 27: Case Closure Net-Zero Condition**
    - Generate random balance scenarios, verify rejection/approval logic
    - **Validates: Requirements 37.1, 37.2, 37.3**

- [x] 16. Checkpoint - Business Rules Complete
  - Ensure all tests pass, ask the user if questions arise.

- [x] 17. Audit Trail (Module 12)
  - [x] 17.1 Create audit trail database model and repository
    - Create `vlr_audit_events` model (append-only, no UPDATE/DELETE)
    - Create `IAuditTrailRepository` interface with `append()` and `search()` only
    - Create Alembic migration with PostgreSQL REVOKE for UPDATE/DELETE
    - Configure 7-year retention policy
    - _Requirements: 38.1, 38.4_

  - [x] 17.2 Implement audit trail service
    - Create `backend/src/domain/services/vlr/audit_trail_service.py`
    - Implement `log_event()` for append-only logging
    - Implement `search()` with filters: user, date range, case_id, event_type
    - Implement `export()` for Excel and CSV formats
    - Capture event types: login, logout, case_created, status_changed, match_override, approval, rejection, vendor_interaction
    - _Requirements: 38.1, 38.2, 38.3, 39.1, 39.2_

  - [ ]* 17.3 Write property tests for audit trail (Property 28, 29)
    - **Property 28: Audit Trail Immutability and Completeness**
    - **Property 29: Audit Search Correctness**
    - Verify no mutation operations succeed, verify search filter correctness
    - **Validates: Requirements 38.1, 38.2, 38.3, 39.1**

  - [x] 17.4 Create audit trail API endpoints
    - Add `GET /api/v1/vlr/audit` for searching audit events with pagination
    - Add `GET /api/v1/vlr/audit/export` for exporting filtered results (Excel/CSV)
    - _Requirements: 39.1, 39.2, 39.3_

  - [x] 17.5 Integrate audit logging across all services
    - Add audit event emission to workflow transitions
    - Add audit event emission to match overrides and confirmations
    - Add audit event emission to approvals and rejections
    - Add audit event emission to vendor portal interactions
    - _Requirements: 38.2_

- [ ] 18. Structured Logging (Module 13)
  - [x] 18.1 Create structured logging service
    - Create `backend/src/infrastructure/logging/structured_logger.py`
    - Implement `log_operation()` emitting JSON entries with correlation_id, timestamp, service_name, operation_name, duration_ms, outcome_status
    - Include error_type and error_message on failure (no sensitive data)
    - _Requirements: 40.1, 40.2, 40.4_

  - [ ]* 18.2 Write property test for structured log completeness (Property 30)
    - **Property 30: Structured Log Entry Completeness**
    - Generate random operations, verify all required fields present
    - Verify no sensitive data in error entries
    - **Validates: Requirements 40.1, 40.2, 40.4**

  - [x] 18.3 Integrate structured logging across all modules
    - Add structured logging to Data Transformation Engine operations
    - Add structured logging to SAP adapter calls
    - Add structured logging to Celery task executions
    - Add structured logging to reconciliation passes
    - Add structured logging to email dispatches
    - Add structured logging to API request handling
    - _Requirements: 40.1, 40.3_

- [x] 19. Final Checkpoint - All Modules Complete
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation between major modules
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- The build sequence follows the dependency chain: transformation → SAP → mapping → workflow → email → reconciliation → frontend → dashboard → reports → recovery → rules → audit → logging
- All backend services follow existing patterns: domain services, repository interfaces, Celery tasks
- All frontend pages use React Query with loading/error/retry patterns and PrimeReact components
- Python `hypothesis` library for backend property tests, `fast-check` for frontend
- Minimum 100 iterations per property test

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.13"] },
    { "id": 1, "tasks": ["1.2", "1.3"] },
    { "id": 2, "tasks": ["1.4", "1.5"] },
    { "id": 3, "tasks": ["1.6", "1.7"] },
    { "id": 4, "tasks": ["1.8", "1.9"] },
    { "id": 5, "tasks": ["1.10", "1.11"] },
    { "id": 6, "tasks": ["1.12", "1.14", "3.1"] },
    { "id": 7, "tasks": ["3.2", "3.3"] },
    { "id": 8, "tasks": ["3.4", "4.1"] },
    { "id": 9, "tasks": ["4.2", "5.1"] },
    { "id": 10, "tasks": ["4.3", "4.4", "5.2"] },
    { "id": 11, "tasks": ["4.5", "5.3", "5.4"] },
    { "id": 12, "tasks": ["5.5", "7.1"] },
    { "id": 13, "tasks": ["7.2", "7.4"] },
    { "id": 14, "tasks": ["7.3", "8.1"] },
    { "id": 15, "tasks": ["8.2"] },
    { "id": 16, "tasks": ["8.3", "8.4"] },
    { "id": 17, "tasks": ["8.5", "8.6"] },
    { "id": 18, "tasks": ["10.1", "10.2", "10.3"] },
    { "id": 19, "tasks": ["10.4", "10.5", "10.7"] },
    { "id": 20, "tasks": ["10.6", "11.1"] },
    { "id": 21, "tasks": ["11.2", "11.3", "12.1"] },
    { "id": 22, "tasks": ["12.2", "12.3"] },
    { "id": 23, "tasks": ["12.4", "12.5"] },
    { "id": 24, "tasks": ["12.6", "12.7"] },
    { "id": 25, "tasks": ["14.1"] },
    { "id": 26, "tasks": ["14.2", "14.4"] },
    { "id": 27, "tasks": ["14.3", "14.5", "15.1"] },
    { "id": 28, "tasks": ["15.2", "15.3", "15.5"] },
    { "id": 29, "tasks": ["15.4", "15.6", "15.7"] },
    { "id": 30, "tasks": ["15.8", "15.9"] },
    { "id": 31, "tasks": ["15.10", "17.1"] },
    { "id": 32, "tasks": ["17.2"] },
    { "id": 33, "tasks": ["17.3", "17.4"] },
    { "id": 34, "tasks": ["17.5", "18.1"] },
    { "id": 35, "tasks": ["18.2", "18.3"] }
  ]
}
```
