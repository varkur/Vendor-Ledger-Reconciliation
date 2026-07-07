# Implementation Plan: VLR Full Implementation

## Overview

This plan transforms the existing static UI prototype of the Vendor Ledger Reconciliation (VLR) system into a fully dynamic, production-ready application. Implementation follows a bottom-up approach: database models and migrations first, then domain services, API layer, and finally frontend feature modules. Each task builds incrementally on previous ones, ensuring no orphaned code.

## Tasks

- [x] 1. Database Schema and Core Infrastructure
  - [x] 1.1 Create VLR database models and Alembic migration
    - Create SQLAlchemy ORM models in `backend/src/infrastructure/database/models/vlr/`: Vendor, VendorContact, ReconciliationRequest, ReconciliationCase, LedgerEntry, MatchResult, RecoException, ResolutionRecord, ApprovalRecord, Notification, Setting, AutomationRule, AutomationExecution, PortalSignOff
    - Implement enums: RequestStatus, CaseStatus, MatchPassType, ExceptionSeverity, ResolutionAction, LedgerSide, CaseType, NotificationType
    - Add database-level CHECK constraints for valid status transitions on ReconciliationCase and ReconciliationRequest
    - Add unique constraint on (vendor_code, company_code) for Vendor
    - Add composite unique constraint for period overlap prevention
    - Implement soft-delete columns (is_deleted, deleted_at) on Vendor and ReconciliationCase
    - Add indexes on vendor_code, request_status, case_status, created_date, company_code
    - Generate Alembic migration with forward and rollback scripts
    - _Requirements: 15.1, 15.2, 15.3, 15.4, 15.5, 15.6, 15.7, 15.8, 15.9, 15.10_

  - [ ]* 1.2 Write property tests for database constraints
    - **Property 4: Vendor Code Uniqueness Within Company**
    - **Property 9: Period Overlap Detection**
    - **Property 10: Valid Status Transitions Only**
    - **Property 30: Multi-Tenant Data Isolation**
    - **Property 31: Soft-Delete Exclusion From Queries**
    - **Validates: Requirements 2.2, 3.3, 3.7, 15.4, 15.5, 15.9, 15.10**

  - [x] 1.3 Create VLR domain exception hierarchy
    - Implement all domain exceptions in `backend/src/domain/exceptions/vlr.py`: VLRDomainException base class plus all specific exceptions (VendorNotFoundException, VendorInactiveException, OverlappingPeriodException, InvalidStatusTransitionException, CaseClosedException, UploadLimitExceededException, EditLimitExceededException, Row10NonZeroException, WriteOffThresholdExceededException, TokenExpiredException, DuplicateVendorCodeException, CompanyLedgerNotConfirmedException, IdempotencyConflictException, ConcurrentModificationException, SAPConnectionException, FileValidationException)
    - _Requirements: 17.1, 17.2, 17.3, 17.4_

  - [x] 1.4 Create VLR repository interfaces and implementations
    - Define abstract repository interfaces in `backend/src/domain/repositories/vlr/`: VendorRepository, RequestRepository, CaseRepository, LedgerEntryRepository, MatchResultRepository, ExceptionRepository, ApprovalRepository, NotificationRepository, SettingRepository, AutomationRuleRepository
    - Implement concrete repositories in `backend/src/infrastructure/database/repositories/vlr/` with async SQLAlchemy, company_code scoping, soft-delete filtering, and pagination support
    - _Requirements: 15.1, 15.4, 15.7, 15.9, 16.7_

  - [x] 1.5 Create VLR error handler and structured error responses
    - Extend the existing exception handler middleware to map VLR domain exceptions to appropriate HTTP status codes (409 for business rules, 404 for not found, etc.)
    - Ensure all error responses include error_code, message, field_path, and correlation_id
    - _Requirements: 17.1, 17.2, 17.3, 17.4_

  - [ ]* 1.6 Write property test for structured error response format
    - **Property 35: Structured Error Response Format**
    - **Validates: Requirements 17.1, 17.2, 17.3**

- [x] 2. Checkpoint - Ensure database models, migrations, and repository layer pass all tests
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 3. Vendor Management Domain and API
  - [x] 3.1 Implement VendorService domain logic
    - Create `backend/src/domain/services/vlr/vendor_service.py` with CRUD operations, soft-delete logic, bulk import validation, SAP data merge, and vendor-code uniqueness enforcement
    - Implement inactive vendor blocking for request creation
    - Implement active case check before deletion
    - Implement vendor filter/search logic (code, name, status, city, PAN)
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 2.9, 2.10_

  - [ ]* 3.2 Write property tests for vendor business rules
    - **Property 4: Vendor Code Uniqueness Within Company**
    - **Property 5: Inactive Vendor Blocks Request Creation**
    - **Property 6: Active Case Prevents Vendor Deletion**
    - **Property 7: Vendor Search Results Match Filters**
    - **Property 8: SAP Merge Preserves Manual Contacts**
    - **Validates: Requirements 2.2, 2.6, 2.8, 2.9, 2.10**

  - [x] 3.3 Implement Vendor API endpoints
    - Create `backend/src/api/v1/endpoints/vlr/vendor_controller.py` with routes: GET /, POST /, GET /{id}, PUT /{id}, DELETE /{id}, POST /bulk-import, GET /export
    - Create Pydantic request/response schemas in `backend/src/api/v1/schemas/vlr/vendor_schemas.py`
    - Wire RBAC permission checks (vlr.vendors.read, vlr.vendors.write, vlr.vendors.delete)
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.7, 2.8, 2.9, 11.2, 11.6_

  - [ ]* 3.4 Write unit tests for Vendor API endpoints
    - Test CRUD happy paths, validation errors, and permission enforcement
    - Test bulk import with valid/invalid CSV files
    - Test export to CSV and Excel formats
    - _Requirements: 2.1, 2.4, 2.5, 11.6_

- [ ] 4. SAP Integration and Data Extraction
  - [x] 4.1 Implement SAPConnectorService
    - Create `backend/src/infrastructure/external/sap_connector.py` with methods: pull_vendor_master, pull_ledger_entries, test_connection, get_health_status, incremental_pull
    - Implement SAP field mapping (ZUONR→assignment_number, BELNR→document_number, BLART→document_type, DMBTR→amount, BUDAT→posting_date, AUGDT→clearing_date, AUGBL→clearing_document)
    - Implement retry logic (3 retries with exponential backoff: 2s, 4s, 8s)
    - Implement duplicate detection (same vendor, period, document_number, amount)
    - Implement rollback on partial extraction failure
    - _Requirements: 1.1, 1.3, 1.5, 1.6, 1.7, 1.8, 20.1, 20.4, 20.7_

  - [ ]* 4.2 Write property tests for SAP field mapping and deduplication
    - **Property 1: SAP Field Mapping Round-Trip**
    - **Property 3: Duplicate SAP Entry Detection**
    - **Property 40: SAP Credentials Never Exposed**
    - **Validates: Requirements 1.3, 1.7, 20.2**

  - [x] 4.3 Implement CSV file validation and parsing service
    - Create `backend/src/domain/services/vlr/file_parser_service.py` with validation for mandatory columns, file type detection (CSV/Excel), size limit check (10MB), and entry parsing
    - Implement configurable field mapping from settings
    - _Requirements: 1.2, 1.4, 4.3, 4.4, 16.5, 17.5_

  - [ ]* 4.4 Write property tests for CSV validation
    - **Property 2: CSV Validation Rejects Invalid Structures**
    - **Property 15: Vendor File Upload Round-Trip**
    - **Validates: Requirements 1.4, 4.4, 4.7, 17.5**

  - [x] 4.5 Implement SAP pull Celery task and API endpoint
    - Create Celery task in `backend/src/infrastructure/tasks/vlr/sap_tasks.py` for async SAP data extraction
    - Create API endpoint POST /api/v1/vlr/requests/{id}/sap-pull to trigger the Celery task
    - Record extraction timestamp, row count, and status in audit log on completion
    - _Requirements: 1.1, 1.5, 16.4, 16.6_

  - [x] 4.6 Implement SAP settings API endpoints
    - Create endpoints: GET /api/v1/vlr/settings/sap-connection (masked credentials), PUT /api/v1/vlr/settings/sap-connection, POST /api/v1/vlr/settings/sap-connection/test, PUT /api/v1/vlr/settings/field-mapping
    - Ensure SAP credentials are stored encrypted and never exposed in responses or logs
    - _Requirements: 20.1, 20.2, 20.3, 20.5, 20.6_

- [x] 5. Checkpoint - Ensure vendor management and SAP integration pass all tests
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 6. Reconciliation Request Lifecycle
  - [x] 6.1 Implement RequestManagerService domain logic
    - Create `backend/src/domain/services/vlr/request_manager_service.py` with methods: create_request, clone_request, confirm_company_ledger, invite_vendor, transition_status, validate_no_overlap
    - Implement state machine enforcement for request status transitions (Draft→Active→InProgress→Review→SignOff→Closed)
    - Implement period overlap validation per vendor per company code
    - Implement case creation (exactly N cases for N selected active vendors)
    - Enforce company ledger confirmation before vendor invitation
    - Block edits on closed cases
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9, 3.10_

  - [ ]* 6.2 Write property tests for request lifecycle business rules
    - **Property 9: Period Overlap Detection**
    - **Property 10: Valid Status Transitions Only**
    - **Property 11: Request Creates Exactly N Cases**
    - **Property 12: Closed Case Rejects All Edits**
    - **Property 13: Company Ledger Required Before Invitation**
    - **Validates: Requirements 3.3, 3.5, 3.6, 3.7, 3.8**

  - [x] 6.3 Implement Request and Case API endpoints
    - Create `backend/src/api/v1/endpoints/vlr/request_controller.py`: GET /, POST /, GET /{id}, POST /{id}/clone, POST /{id}/sap-pull, GET /{id}/statistics
    - Create `backend/src/api/v1/endpoints/vlr/case_controller.py`: GET /{id}, POST /{id}/confirm-ledger, POST /{id}/invite, POST /{id}/reconcile, POST /{id}/submit-approval, GET /{id}/statement, GET /{id}/statistics
    - Create Pydantic schemas for request/response validation
    - Wire RBAC permission checks
    - _Requirements: 3.1, 3.2, 3.4, 3.5, 3.6, 3.7, 3.10, 11.2, 11.6_

  - [ ]* 6.4 Write unit tests for request and case API endpoints
    - Test request creation with valid/invalid vendors
    - Test period overlap rejection
    - Test status transition enforcement
    - Test clone functionality
    - _Requirements: 3.1, 3.3, 3.7, 3.10_

- [ ] 7. Multi-Pass Reconciliation Engine
  - [x] 7.1 Implement ReconciliationEngineService core
    - Create `backend/src/domain/services/vlr/reconciliation_engine_service.py` with the 6-pass matching algorithm
    - Implement Pass 1: Exact Match (amount + date + reference_number identical, confidence=1.0)
    - Implement Pass 2: Tolerance Match (amount within tolerance AND reference numbers match)
    - Implement Pass 3: Fuzzy Reference Match (amounts equal, reference similarity > 0.8)
    - Implement Pass 4: One-to-Many (one company entry = sum of multiple vendor entries)
    - Implement Pass 5: Many-to-One (multiple company entries sum to one vendor entry)
    - Implement Pass 6: Mark remaining as Unmatched
    - Enforce no-double-match invariant (each entry matched at most once across passes)
    - Calculate and store match statistics per pass
    - Implement clear_previous_results for re-reconciliation
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 5.8, 5.9, 5.10, 5.11, 5.12, 5.13_

  - [ ]* 7.2 Write property tests for exact match pass
    - **Property 18: Exact Match Correctness**
    - **Validates: Requirements 5.2**

  - [ ]* 7.3 Write property tests for tolerance match pass
    - **Property 19: Tolerance Match Respects Threshold**
    - **Validates: Requirements 5.3**

  - [ ]* 7.4 Write property tests for fuzzy reference match pass
    - **Property 20: Fuzzy Reference Match Threshold**
    - **Validates: Requirements 5.4**

  - [ ]* 7.5 Write property tests for engine invariants
    - **Property 16: No Entry Matched More Than Once**
    - **Property 17: Matched Plus Unmatched Equals Total (Partition Invariant)**
    - **Property 21: Match Statistics Accuracy**
    - **Property 22: Re-Reconciliation Clears Previous Results**
    - **Validates: Requirements 5.7, 5.10, 5.12, 5.13**

  - [x] 7.6 Implement reconciliation Celery task with idempotency
    - Create Celery task in `backend/src/infrastructure/tasks/vlr/reconciliation_tasks.py`
    - Implement idempotency key check to prevent duplicate engine executions
    - Provide progress status updates during execution
    - Enforce 120-second timeout for 5,000-entry matching
    - _Requirements: 16.1, 16.6, 16.9, 17.10_

  - [ ]* 7.7 Write property test for idempotency enforcement
    - **Property 37: Idempotency Key Prevents Duplicate Execution**
    - **Validates: Requirements 17.10**

- [x] 8. Checkpoint - Ensure reconciliation engine passes all tests
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 9. Exception Management
  - [x] 9.1 Implement ExceptionManagerService
    - Create `backend/src/domain/services/vlr/exception_manager_service.py`
    - Implement exception categorization by severity (Critical, High, Medium, Low) based on amount and age thresholds
    - Implement resolution actions: ACM, RDV, MTD, MAA, WOF, ESC
    - Implement Row_10 calculation: (sum company entries - sum vendor entries - sum resolved adjustments)
    - Enforce maximum 10 manual edits per case
    - Enforce write-off threshold check requiring manager approval
    - Implement bulk resolution for same-category exceptions
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7, 6.8, 6.9, 6.10_

  - [ ]* 9.2 Write property tests for exception management
    - **Property 23: Exception Severity Classification**
    - **Property 24: Row 10 Calculation Invariant**
    - **Property 25: Manual Edit Limit Enforcement**
    - **Property 26: Write-Off Threshold Requires Approval**
    - **Validates: Requirements 6.1, 6.5, 6.7, 6.8, 6.10**

  - [x] 9.3 Implement Exception API endpoints
    - Create `backend/src/api/v1/endpoints/vlr/exception_controller.py`: GET /, POST /{id}/resolve, POST /bulk-resolve, GET /categories
    - Create Pydantic schemas for exception resolution requests/responses
    - Wire RBAC permission checks
    - _Requirements: 6.2, 6.3, 6.9, 11.2_

  - [ ]* 9.4 Write unit tests for exception API endpoints
    - Test resolution actions, bulk resolve, edit limit enforcement
    - _Requirements: 6.2, 6.7, 6.9_

- [ ] 10. Approval Workflow
  - [x] 10.1 Implement ApprovalEngineService
    - Create `backend/src/domain/services/vlr/approval_engine_service.py`
    - Implement Row_10 zero validation before submission
    - Implement approve/reject/request-changes with comments
    - Implement write-off threshold check for additional senior approval
    - Implement delegation of approval authority with time-limited scope
    - Implement request closure when all cases are approved and signed off
    - Record all decisions in audit log
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7, 7.8, 7.9, 7.10_

  - [ ]* 10.2 Write property tests for approval workflow
    - **Property 27: Approval Submission Requires Zero Row 10**
    - **Property 28: Request Closes Only When All Cases Complete**
    - **Validates: Requirements 7.1, 7.2, 7.10**

  - [x] 10.3 Implement Approval API endpoints
    - Create `backend/src/api/v1/endpoints/vlr/approval_controller.py`: GET /pending, POST /{id}/approve, POST /{id}/reject, POST /{id}/delegate
    - Create Pydantic schemas for approval decisions
    - Wire RBAC (vlr.approvals.approve requires Reconciliation_Manager role permission)
    - _Requirements: 7.3, 7.4, 7.9, 11.3_

  - [ ]* 10.4 Write unit tests for approval API endpoints
    - Test approve/reject flow, Row_10 validation, delegation
    - _Requirements: 7.1, 7.4, 7.9_

- [ ] 11. Notification Service
  - [x] 11.1 Implement NotificationService
    - Create `backend/src/domain/services/vlr/notification_service.py`
    - Implement email sending with template rendering (invitation, reminder, approval, rejection, sign-off)
    - Implement retry with exponential backoff (30s, 120s, 480s) up to 3 attempts
    - Implement reminder scheduling at configurable intervals (default: 3, 7, 14 days)
    - Implement escalation when reminder count exceeds maximum
    - Log all notifications with recipient, type, timestamp, delivery status
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5, 10.6, 10.7, 10.8, 10.9, 10.10_

  - [ ]* 11.2 Write property tests for notification service
    - **Property 38: Notification Retry With Bounded Attempts**
    - **Property 39: Reminder Scheduling at Configured Intervals**
    - **Validates: Requirements 10.2, 10.9**

  - [x] 11.3 Implement Notification Celery tasks and API endpoints
    - Create Celery tasks for async email delivery and scheduled reminders in `backend/src/infrastructure/tasks/vlr/notification_tasks.py`
    - Create API endpoints: GET /api/v1/vlr/notifications/history/{case_id}, POST /api/v1/vlr/notifications/send-reminder
    - _Requirements: 10.1, 10.7, 10.10, 16.6_

- [x] 12. Checkpoint - Ensure exception management, approval, and notifications pass all tests
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 13. Vendor Portal
  - [x] 13.1 Implement Vendor Portal backend
    - Create `backend/src/api/v1/endpoints/vlr/portal_controller.py`: GET /auth/{token}, POST /upload, GET /statement, POST /sign-off
    - Implement token-based authentication (no username/password) with expiry validation
    - Implement file upload with 5-attempt limit enforcement
    - Implement digital sign-off recording (timestamp, IP, statement version)
    - Implement re-upload triggering re-reconciliation
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8, 4.9, 4.10, 4.11_

  - [ ]* 13.2 Write property tests for vendor portal
    - **Property 14: Upload Count Enforcement**
    - **Property 15: Vendor File Upload Round-Trip**
    - **Validates: Requirements 4.5, 4.6, 4.7**

  - [ ]* 13.3 Write unit tests for portal token authentication
    - Test valid token access, expired token rejection, file upload limits
    - Test sign-off recording
    - _Requirements: 4.2, 4.5, 4.9, 4.10_

- [ ] 14. Direct Reconciliation and Automation Rules
  - [x] 14.1 Implement Direct Reconciliation flow
    - Extend CaseController with direct reconciliation creation endpoint
    - Implement single-vendor case creation with inline configuration and distinct case_type="direct"
    - Implement dual file upload (company + vendor) with immediate reconciliation trigger
    - Enforce period overlap validation for direct cases
    - _Requirements: 18.1, 18.2, 18.3, 18.4, 18.5, 18.6, 18.7, 18.8_

  - [x] 14.2 Implement AutomationRuleService
    - Create `backend/src/domain/services/vlr/automation_rule_service.py`
    - Implement scheduling for recurring reconciliation (monthly, quarterly)
    - Implement auto-matching rules (confidence threshold-based auto-accept)
    - Implement auto-escalation rules (configurable days without progress)
    - Record execution history with trigger time, rule ID, outcome
    - Support enable/disable without deletion
    - _Requirements: 19.1, 19.2, 19.3, 19.4, 19.5, 19.6, 19.7_

  - [ ]* 14.3 Write property test for auto-match confidence threshold
    - **Property 42: Auto-Match Above Confidence Threshold**
    - **Validates: Requirements 19.3**

  - [x] 14.4 Implement Automation Celery tasks and API endpoints
    - Create Celery beat schedule for automation rules in `backend/src/infrastructure/tasks/vlr/automation_tasks.py`
    - Create API endpoints for automation rule CRUD and execution history
    - _Requirements: 19.1, 19.5, 19.7_

- [ ] 15. Reports and MIS
  - [x] 15.1 Implement ReportService
    - Create `backend/src/domain/services/vlr/report_service.py`
    - Implement reconciliation statement generation (entries, matches, exceptions, Row_10)
    - Implement exception report (ageing, category, resolution status)
    - Implement vendor status tracking report (response rates, upload status, sign-off)
    - Implement monthly MIS report (volumes, match rates, exception trends, ageing analysis)
    - Implement report caching within session
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.7, 9.9, 9.10_

  - [x] 15.2 Implement Report API endpoints with export
    - Create `backend/src/api/v1/endpoints/vlr/report_controller.py`: GET /reconciliation/{id}, GET /exceptions, GET /vendor-status, GET /monthly-mis, GET /{id}/export
    - Implement export to PDF and Excel formats
    - Wire RBAC (vlr.reports.read requires Reconciliation_User or Reconciliation_Manager permission)
    - _Requirements: 9.5, 9.6, 9.8, 11.2, 11.3_

- [ ] 16. Settings and Configuration
  - [x] 16.1 Implement Settings API endpoints
    - Create `backend/src/api/v1/endpoints/vlr/settings_controller.py`: GET /, PUT /tolerance, PUT /matching, PUT /notifications, PUT /approval-thresholds
    - Implement setting validation against defined ranges
    - Apply new settings to future operations without affecting in-progress cases
    - Record setting changes in audit log
    - _Requirements: 13.1, 13.2, 13.3, 13.4, 13.5, 13.6, 13.7, 13.8, 13.9, 13.10_

  - [ ]* 16.2 Write property test for settings validation
    - **Property 41: Setting Validation Against Defined Ranges**
    - **Validates: Requirements 13.9**

- [ ] 17. RBAC and Audit Integration
  - [x] 17.1 Configure VLR-specific RBAC permissions and roles
    - Seed VLR permissions into existing RBAC system: vlr.vendors.*, vlr.requests.*, vlr.cases.*, vlr.exceptions.*, vlr.approvals.*, vlr.reports.*, vlr.settings.*, vlr.portal.*
    - Configure four VLR roles (Reconciliation_User, Reconciliation_Manager, IT_Admin, Read_Only_Audit) with appropriate permission assignments
    - Ensure frontend menu visibility is controlled by vlr.menu.* permissions
    - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5, 11.7, 11.9, 11.10_

  - [ ]* 17.2 Write property tests for RBAC enforcement
    - **Property 34: RBAC Endpoint Enforcement**
    - **Validates: Requirements 11.6, 11.8**

  - [x] 17.3 Verify audit logging integration for VLR entities
    - Ensure existing automatic audit listener captures all VLR entity changes (create, update, delete)
    - Implement manual audit events for domain actions (reconciliation triggered, approval decisions, login events)
    - Verify audit entries are within the same transaction for atomicity
    - _Requirements: 12.1, 12.2, 12.3, 12.4, 12.5, 12.6, 12.7, 12.8, 12.9, 12.10_

  - [ ]* 17.4 Write property tests for audit logging
    - **Property 32: Audit Entry Immutability**
    - **Property 33: Audit Entry Atomicity**
    - **Validates: Requirements 12.4, 12.9**

- [x] 18. Checkpoint - Ensure all backend services, APIs, and property tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 19. Frontend - Vendor Management Module
  - [x] 19.1 Create Vendor Management feature module structure
    - Create `frontend/src/features/vendor-management/` with api/, components/, hooks/, pages/, schemas/, types/, store/ directories
    - Define TypeScript interfaces for Vendor, VendorContact, VendorFilters, BulkImportResult
    - Create Zod schemas for vendor form validation (create, edit, bulk import)
    - Implement TanStack Query hooks: useVendors, useVendor, useCreateVendor, useUpdateVendor, useDeleteVendor, useBulkImportVendors, useExportVendors
    - _Requirements: 2.1, 14.1, 14.7_

  - [x] 19.2 Build Vendor Management page components
    - Implement VendorListPage with PrimeReact DataTable (pagination, sorting, filtering by code/name/status/city/PAN)
    - Implement VendorCreateDialog and VendorEditDialog with React Hook Form + Zod validation
    - Implement VendorDetailPage showing contacts, activity history, and reconciliation cases
    - Implement BulkImportDialog with file upload, validation feedback, and row-level error display
    - Implement ExportButton supporting CSV and Excel formats
    - Gate all actions behind RBAC permissions using existing FieldGate and PrivateRoute patterns
    - _Requirements: 2.1, 2.4, 2.5, 2.7, 2.9, 11.7, 14.7_

  - [ ]* 19.3 Write frontend tests for Vendor Management
    - Test VendorListPage rendering with mock data
    - Test form validation with Zod schemas
    - Test RBAC gate hiding of unauthorized actions
    - _Requirements: 2.1, 2.9, 11.7_

- [ ] 20. Frontend - Request Statement Module
  - [x] 20.1 Create Request Statement feature module
    - Create `frontend/src/features/request-statement/` with standard module structure
    - Define TypeScript interfaces for ReconciliationRequest, RequestCreateDTO, ReconciliationCase
    - Create Zod schemas for request creation wizard (company code, fiscal year, date range, vendor selection, tolerance, TDS%, GST%, matching preferences)
    - Implement TanStack Query hooks: useRequests, useRequest, useCreateRequest, useCloneRequest, useTriggerSAPPull
    - _Requirements: 3.1, 3.2, 14.1, 14.7_

  - [x] 20.2 Build Request Statement wizard and pages
    - Implement multi-step wizard: Step 1 (company code, period), Step 2 (vendor selection with search), Step 3 (configuration), Step 4 (review & submit)
    - Use Redux Toolkit slice for wizard step state management
    - Implement RequestListPage with status badges and filtering
    - Implement SAP Pull progress indicator with polling
    - Implement clone request functionality
    - Display optimistic updates for status transitions
    - _Requirements: 3.1, 3.2, 3.4, 3.10, 14.2, 14.4, 14.5_

  - [ ]* 20.3 Write frontend tests for Request Statement
    - Test wizard step navigation and validation
    - Test vendor selection with filter
    - Test SAP pull progress display
    - _Requirements: 3.1, 3.2, 14.7_

- [ ] 21. Frontend - Track Reconciliation Module
  - [x] 21.1 Create Track Reconciliation feature module
    - Create `frontend/src/features/track-reconciliation/` with standard module structure
    - Define TypeScript interfaces for pipeline statistics, case detail, match results
    - Implement TanStack Query hooks: useRequestPipeline, useCaseDetail, useCaseStatement, useCaseStatistics
    - _Requirements: 8.1, 8.4, 14.1_

  - [x] 21.2 Build Track Reconciliation dashboard and case detail pages
    - Implement pipeline dashboard with summary statistics panel (total requests, cases, counts per status)
    - Implement request list with DataTable (filtering by status, date range, company code, assigned user; sorting by creation date, due date, case count, completion %)
    - Implement stage tabs: Reco Stage, Review Stage, Sign Off Stage, Action Tracker
    - Implement CaseDetailPage with full reconciliation statement (matched/unmatched entries, pass indicators, confidence scores)
    - Implement PartiesTab showing vendor response status and upload history
    - Implement ActionTrackerTab showing pending actions, escalations, overdue items
    - Ensure real-time stat updates via TanStack Query refetch on case transitions
    - Target 3-second load time through pagination and efficient queries
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7, 8.8, 8.9, 8.10, 16.3_

  - [ ]* 21.3 Write frontend tests for Track Reconciliation
    - Test dashboard rendering with pipeline statistics
    - Test stage tab switching
    - Test case detail statement display
    - _Requirements: 8.1, 8.3, 8.9_

- [ ] 22. Frontend - Direct Reconciliation Module
  - [x] 22.1 Create Direct Reconciliation feature module
    - Create `frontend/src/features/direct-reconciliation/` with standard module structure
    - Implement DirectReconciliationPage with inline creation form (vendor selection, period, tolerance config)
    - Implement dual file upload (company + vendor ledger) with drag-and-drop
    - Implement case list showing direct reconciliation cases with status, vendor, period, match %
    - Wire immediate reconciliation trigger after both files uploaded
    - Reuse reconciliation statement and exception components from track reconciliation
    - _Requirements: 18.1, 18.2, 18.3, 18.4, 18.5, 18.6, 18.7_

- [ ] 23. Frontend - Exception Management and Approval UI
  - [x] 23.1 Build exception management UI components
    - Implement ExceptionList component with PrimeReact DataTable (severity badges, category filters, age display)
    - Implement ResolutionDialog with action selection (ACM, RDV, MTD, MAA, WOF, ESC), comments, and confirmation
    - Implement BulkResolveDialog for multi-select same-category resolution
    - Implement Row_10 balance display with real-time update after resolution
    - Implement edit counter showing remaining edits (10 max)
    - Display write-off threshold warning when WOF exceeds limit
    - _Requirements: 6.1, 6.2, 6.3, 6.5, 6.7, 6.9, 6.10_

  - [x] 23.2 Build approval workflow UI
    - Implement PendingApprovalsPage for managers listing cases awaiting approval
    - Implement ApprovalDialog with approve/reject/request-changes options and comment field
    - Implement DelegationDialog for authority transfer
    - Display Row_10 validation status and difference amount on submission
    - Implement rejection comments display for reconciliation users
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.9_

  - [ ]* 23.3 Write frontend tests for exception and approval UI
    - Test resolution dialog form validation
    - Test bulk resolve selection and submission
    - Test approval/rejection flow rendering
    - _Requirements: 6.2, 7.4_

- [ ] 24. Frontend - Reports, Notifications, and Settings
  - [x] 24.1 Build Reports and MIS pages
    - Create `frontend/src/features/reports/` module
    - Implement ReportsPage with tabs for each report type
    - Implement interactive charts (PrimeReact Chart) for monthly MIS (volumes, match rates, exception trends)
    - Implement DataTable display for tabular report data with filters
    - Implement export buttons (PDF, Excel) per report
    - Gate report access behind vlr.reports.read permission
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.9, 9.10_

  - [x] 24.2 Build Notifications history page
    - Create `frontend/src/features/notifications/` module
    - Implement NotificationHistoryPage displaying sent notifications per case (type, recipient, timestamp, status)
    - Implement manual reminder trigger button
    - _Requirements: 10.7, 10.10_

  - [x] 24.3 Build Settings and Configuration pages
    - Create `frontend/src/features/vlr-settings/` module
    - Implement settings forms: tolerance configuration, matching preferences (enable/disable passes), notification intervals, approval thresholds, TDS/GST defaults
    - Implement SAP connection settings page with masked credentials, test connection button, and field mapping editor
    - Implement automation rules management page (create, enable/disable, execution history)
    - Gate behind vlr.settings.write (IT_Admin only)
    - _Requirements: 13.1, 13.2, 13.3, 13.4, 13.5, 13.8, 13.10, 19.6, 19.7, 20.1, 20.3, 20.5_

- [ ] 25. Frontend - Vendor Portal
  - [x] 25.1 Build Vendor Portal frontend
    - Create separate route tree at `/portal` with token-based authentication
    - Implement PortalAuthPage that reads token from URL and authenticates
    - Implement PortalUploadPage with file upload (CSV/Excel, max 10MB), upload counter display, and validation feedback
    - Implement PortalStatementPage showing reconciliation statement after matching
    - Implement PortalSignOffPage with digital sign-off confirmation
    - Display expiration message for expired tokens with instructions to contact reconciliation team
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.8, 4.9, 4.10_

  - [ ]* 25.2 Write frontend tests for Vendor Portal
    - Test token authentication flow
    - Test file upload with validation errors
    - Test expired token display
    - Test sign-off confirmation
    - _Requirements: 4.2, 4.4, 4.9, 4.10_

- [ ] 26. Frontend - Navigation, Routing, and Error Handling
  - [x] 26.1 Wire VLR routes and navigation
    - Add VLR routes to AppRouter: /vlr/vendors, /vlr/requests, /vlr/direct, /vlr/track, /vlr/reports, /vlr/notifications, /vlr/settings, /portal/:token
    - Add VLR sidebar navigation items gated by vlr.menu.* permissions using useMenuPermissions hook
    - Implement global error handling: toast notifications for API failures, loading indicators for >5s requests, request cancellation support
    - Implement automatic JWT token refresh when within 60 seconds of expiry
    - Implement request deduplication for rapid interactions
    - Implement query cache invalidation on successful mutations
    - Configure TanStack Query stale time (5 minutes for page cache preservation)
    - _Requirements: 11.7, 14.1, 14.3, 14.4, 14.5, 14.6, 14.8, 14.9, 14.10_

- [ ] 27. Date Validation and Performance
  - [x] 27.1 Implement date range validation across all endpoints
    - Add Pydantic validators ensuring start_date < end_date and dates not in the future for ledger extraction
    - Apply to request creation, direct reconciliation, SAP pull, and report generation endpoints
    - _Requirements: 17.9_

  - [ ]* 27.2 Write property test for date range validation
    - **Property 36: Date Range Validation**
    - **Validates: Requirements 17.9**

  - [x] 27.3 Implement rate limiting and response compression
    - Configure rate limiting at 100 requests/minute/user on all VLR endpoints
    - Implement response compression for payloads > 1KB
    - _Requirements: 16.10, 17.7_

- [ ] 28. Pipeline Count Invariant Integration Test
  - [ ]* 28.1 Write property test for pipeline count invariant
    - **Property 29: Pipeline Count Invariant**
    - **Validates: Requirements 8.7**

- [x] 29. Final Checkpoint - Full system integration verification
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation at key milestones
- Property tests validate universal correctness properties from the design document (42 properties total)
- Unit tests validate specific examples and edge cases
- Backend uses Python 3.12 with FastAPI, pytest + Hypothesis for property-based testing
- Frontend uses TypeScript with React 19, Vitest + React Testing Library for component tests
- All Celery tasks prevent API blocking for long-running operations (SAP pulls, reconciliation engine)
- Existing RBAC and audit systems are extended, not reimplemented
- TanStack Query handles server-state caching; Redux Toolkit handles client-state only

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.3"] },
    { "id": 1, "tasks": ["1.2", "1.4", "1.5"] },
    { "id": 2, "tasks": ["1.6", "3.1", "4.1", "4.3"] },
    { "id": 3, "tasks": ["3.2", "3.3", "4.2", "4.4", "4.5", "4.6"] },
    { "id": 4, "tasks": ["3.4", "6.1"] },
    { "id": 5, "tasks": ["6.2", "6.3", "7.1"] },
    { "id": 6, "tasks": ["6.4", "7.2", "7.3", "7.4", "7.5", "7.6"] },
    { "id": 7, "tasks": ["7.7", "9.1"] },
    { "id": 8, "tasks": ["9.2", "9.3", "10.1"] },
    { "id": 9, "tasks": ["9.4", "10.2", "10.3", "11.1"] },
    { "id": 10, "tasks": ["10.4", "11.2", "11.3", "13.1"] },
    { "id": 11, "tasks": ["13.2", "13.3", "14.1", "14.2"] },
    { "id": 12, "tasks": ["14.3", "14.4", "15.1"] },
    { "id": 13, "tasks": ["15.2", "16.1", "17.1"] },
    { "id": 14, "tasks": ["16.2", "17.2", "17.3"] },
    { "id": 15, "tasks": ["17.4", "19.1", "20.1", "21.1"] },
    { "id": 16, "tasks": ["19.2", "20.2", "21.2", "22.1"] },
    { "id": 17, "tasks": ["19.3", "20.3", "21.3", "23.1"] },
    { "id": 18, "tasks": ["23.2", "24.1", "24.2", "24.3"] },
    { "id": 19, "tasks": ["23.3", "25.1"] },
    { "id": 20, "tasks": ["25.2", "26.1", "27.1"] },
    { "id": 21, "tasks": ["27.2", "27.3", "28.1"] }
  ]
}
```
