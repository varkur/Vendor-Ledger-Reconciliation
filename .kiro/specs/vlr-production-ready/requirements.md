# Requirements Document

## Introduction

This feature completes the Vendor Ledger Reconciliation (VLR) application by wiring all remaining dead buttons, replacing mock data with live API calls, adding missing pages (Approvals, Document Types), connecting portal flows end-to-end, and ensuring the full reconciliation lifecycle (Request → Reconcile → Review → Sign Off → Approve) operates without gaps. Work is organized as vertical slices spanning both the React frontend and FastAPI backend.

## Glossary

- **System**: The VLR web application consisting of the React frontend and FastAPI backend
- **ReconciliationDetailPage**: The frontend page at `/track-reconciliation/:requestId` displaying cases, lifecycle tabs, and bulk actions
- **ReconciliationOutputPanel**: The frontend panel/page at `/track-reconciliation/:requestId/case/:caseId` showing matched/unmatched items for a single case
- **VendorPortal**: The public-facing portal (token-based auth) where vendors upload statements and sign off on reconciliations
- **RequestStatementPage**: The frontend page for composing and sending statement request emails to vendors
- **DirectReconciliationPage**: The frontend page for uploading statements directly and triggering reconciliation
- **ApprovalsPage**: A new frontend page listing pending approval items with approve/reject/delegate actions
- **DocumentTypesPage**: A new frontend page for managing document type classifications
- **Sidebar**: The main navigation menu rendered inside MainLayout
- **apiClient**: The axios-based HTTP client used by the frontend for authenticated API requests
- **portalClient**: The axios-based HTTP client used by the VendorPortal for token-based API requests
- **TanStack_Query**: The data-fetching library (React Query) used for server state management
- **Toast**: A PrimeReact toast notification shown temporarily to communicate success or error messages
- **Entity_Scope**: The organizational entity context applied to all data queries for multi-tenant isolation

## Requirements

### Requirement 1: Reconciliation Detail Page — Live Data

**User Story:** As a reconciliation analyst, I want the Reconciliation Detail Page to display real data from the API, so that I can review actual case statuses and take action.

#### Acceptance Criteria

1. WHEN the ReconciliationDetailPage mounts, THE System SHALL fetch case data from `GET /api/v1/vlr/reconciliation-requests/{request_id}/cases` using TanStack_Query with Entity_Scope applied.
2. WHEN the API returns case data, THE System SHALL render the cases table with status, party name, and contextual action button.
3. WHILE the case data is loading, THE System SHALL display a loading skeleton in the cases table area.
4. IF the API returns an error, THEN THE System SHALL display an inline error message with a retry option.
5. IF the API returns an empty case list, THEN THE System SHALL display an empty state message indicating no cases exist for this request.

### Requirement 2: Reconciliation Detail Page — Tab Navigation

**User Story:** As a reconciliation analyst, I want lifecycle stage tabs (Statistics, All Parties, Reco Stage, Review Stage, Sign Off Stage, Action Tracker) to filter and display relevant data, so that I can focus on cases at each stage.

#### Acceptance Criteria

1. WHEN the user selects a lifecycle tab, THE System SHALL filter the displayed cases to match the selected stage.
2. THE System SHALL preserve the selected tab state in the URL query parameters so that browser back/forward navigation works correctly.
3. WHEN the Statistics tab is active, THE System SHALL fetch and display summary counts from the reconciliation request metadata.

### Requirement 3: Reconciliation Detail Page — View Button Navigation

**User Story:** As a reconciliation analyst, I want the View button on each case row to navigate me to the reconciliation output for that case, so that I can review matched and unmatched items.

#### Acceptance Criteria

1. WHEN the user clicks the View button on a case row, THE System SHALL navigate to `/track-reconciliation/:requestId/case/:caseId`.
2. THE System SHALL render a contextual button label based on case status (e.g., "View" for completed, "Reconcile" for pending, "Review" for in-review).
3. WHEN the ReconciliationOutputPanel route is accessed, THE System SHALL fetch output data from `GET /api/v1/vlr/reconciliation-output/{case_id}`.

### Requirement 4: Reconciliation Detail Page — Bulk Actions

**User Story:** As a reconciliation analyst, I want to perform bulk actions (Send Reminder, Send For Review, Review Done, Request SignOff) on selected cases, so that I can progress multiple cases efficiently.

#### Acceptance Criteria

1. WHEN the user selects one or more cases and clicks "Send Reminder", THE System SHALL call `POST /api/v1/vlr/reminders/send` with the selected case IDs and display a loading spinner until a 200 OK response is received.
2. WHEN a bulk action API call succeeds, THE System SHALL invalidate the relevant TanStack_Query cache, refresh the cases table, and display a success Toast.
3. IF a bulk action API call fails, THEN THE System SHALL display an error Toast with the failure reason and keep the selection intact.
4. WHEN the user clicks "Send For Review", THE System SHALL call `POST /api/v1/vlr/cases/bulk-review` with the selected case IDs.
5. WHEN the user clicks "Review Done", THE System SHALL call `POST /api/v1/vlr/cases/bulk-review-done` with the selected case IDs.
6. WHEN the user clicks "Request SignOff", THE System SHALL call `POST /api/v1/vlr/cases/bulk-signoff-request` with the selected case IDs.

### Requirement 5: Vendor Portal — Request New Link

**User Story:** As a vendor, I want to request a new portal access link when my current link is expired or lost, so that I can still upload my statement.

#### Acceptance Criteria

1. WHEN the vendor clicks "Request New Link" on the PortalAuthPage, THE System SHALL call `POST /api/v1/vlr/portal/request-new-link` with the vendor's email address.
2. WHEN the API returns a success response, THE System SHALL display a confirmation message indicating a new link has been sent.
3. IF the API returns an error, THEN THE System SHALL display an error message describing the failure reason.

### Requirement 6: Vendor Portal — Upload Processing State

**User Story:** As a vendor, I want to see the processing status after uploading my statement, so that I know when reconciliation is complete and I can proceed.

#### Acceptance Criteria

1. WHEN the vendor submits a file upload on PortalUploadPage, THE System SHALL display a processing state with a progress indicator.
2. WHILE the reconciliation is processing, THE System SHALL poll `GET /api/v1/vlr/portal/reconciliation-status/{case_id}` at a configurable interval using the portalClient.
3. WHEN the polling response indicates completion, THE System SHALL navigate the vendor to the PortalStatementPage.
4. IF the polling response indicates an error, THEN THE System SHALL display an error message with instructions to contact support.

### Requirement 7: Vendor Portal — Sign-Off Navigation

**User Story:** As a vendor, I want the "Proceed to Sign-Off" button to navigate me to the sign-off page, so that I can confirm reconciliation results.

#### Acceptance Criteria

1. WHEN the vendor clicks "Proceed to Sign-Off" on PortalStatementPage, THE System SHALL navigate to the PortalSignOffPage with the current case context preserved.
2. THE System SHALL validate that the case status allows sign-off before enabling the "Proceed to Sign-Off" button.

### Requirement 8: Vendor Portal — Raise Dispute

**User Story:** As a vendor, I want to raise a dispute on reconciliation results I disagree with, so that discrepancies can be reviewed by the reconciliation team.

#### Acceptance Criteria

1. WHEN the vendor clicks "Raise Dispute" on PortalStatementPage, THE System SHALL display a dispute form requesting a reason and optional attachments.
2. WHEN the vendor submits the dispute form, THE System SHALL call `POST /api/v1/vlr/portal/dispute/{case_id}` with the dispute details using the portalClient.
3. WHEN the API returns a success response, THE System SHALL display a confirmation Toast and update the case status indicator to "Disputed".
4. IF the API returns a validation error, THEN THE System SHALL display inline field-level error messages.

### Requirement 9: Request Statement Page — Email Preview

**User Story:** As a reconciliation analyst, I want to preview the email template before sending statement requests, so that I can verify the content is correct.

#### Acceptance Criteria

1. WHEN the user clicks "Preview" on the RequestStatementPage, THE System SHALL call `GET /api/v1/vlr/email-templates/{id}/preview` and display the rendered email in a modal dialog.
2. WHILE the preview is loading, THE System SHALL display a loading indicator inside the modal.
3. IF the preview API call fails, THEN THE System SHALL display an error message in the modal.

### Requirement 10: Request Statement Page — Dropdown Population

**User Story:** As a reconciliation analyst, I want the email configuration, attachment, and contact person dropdowns to be populated with real data, so that I can compose statement requests correctly.

#### Acceptance Criteria

1. WHEN the RequestStatementPage mounts, THE System SHALL fetch email sender options from `GET /api/v1/vlr/settings/email-config` and populate the "Send Email from" dropdown.
2. WHEN the RequestStatementPage mounts, THE System SHALL fetch available attachments from `GET /api/v1/vlr/email-templates/{id}/attachments` and populate the "Email Attachment" dropdown.
3. WHEN the RequestStatementPage mounts, THE System SHALL fetch vendor contact persons from `GET /api/v1/vlr/vendors/{vendor_id}/contacts` and populate the "Contact Person" dropdown.
4. IF any dropdown data fetch fails, THEN THE System SHALL display the dropdown in a disabled state with an error tooltip.

### Requirement 11: Request Statement Page — File Upload

**User Story:** As a reconciliation analyst, I want to upload vendor statements directly in Step 2, so that I can proceed with reconciliation when statements are received offline.

#### Acceptance Criteria

1. WHEN the user selects a file in the "Upload Statement" step, THE System SHALL validate the file type and size before uploading.
2. WHEN the user confirms the upload, THE System SHALL call the file upload API endpoint and display upload progress.
3. WHEN the upload completes successfully, THE System SHALL display a success Toast and advance to the next step.
4. IF the upload fails, THEN THE System SHALL display an error Toast with the failure reason and allow retry.

### Requirement 12: Direct Reconciliation Page — View Navigation

**User Story:** As a reconciliation analyst, I want the View link on each direct reconciliation row to navigate to the reconciliation output, so that I can review results.

#### Acceptance Criteria

1. WHEN the user clicks the "View" link on a DirectReconciliationPage row, THE System SHALL navigate to `/track-reconciliation/:requestId/case/:caseId` for the corresponding reconciliation.
2. THE System SHALL use react-router-dom navigation so that browser back/forward buttons work correctly.

### Requirement 13: Direct Reconciliation Page — Quick Create Dialog

**User Story:** As a reconciliation analyst, I want the Quick Create dialog to have functional form inputs and submit action, so that I can create direct reconciliations without navigating away.

#### Acceptance Criteria

1. WHEN the user clicks "Quick Create", THE System SHALL display a dialog with form fields for vendor selection, period, and statement upload.
2. THE System SHALL validate all required fields using react-hook-form with zod schema before allowing submission.
3. WHEN the user submits the Quick Create form, THE System SHALL call the direct reconciliation creation API endpoint and display a loading state on the submit button.
4. WHEN the API returns success, THE System SHALL close the dialog, invalidate the list query, and display a success Toast.
5. IF the API returns a validation error, THEN THE System SHALL display inline field-level error messages in the dialog.

### Requirement 14: Reminders Page — Create Group

**User Story:** As a reconciliation analyst, I want to create reminder groups to organize automated reminders by category, so that I can manage reminder schedules efficiently.

#### Acceptance Criteria

1. WHEN the user clicks "Create Group" on the RemindersPage, THE System SHALL display a dialog form with group name and configuration fields.
2. WHEN the user submits the form, THE System SHALL call `POST /api/v1/vlr/reminder-configs` with the group data and display a loading state.
3. WHEN the API returns success, THE System SHALL close the dialog, invalidate the reminder groups query, and display a success Toast.
4. IF the API returns a validation error, THEN THE System SHALL display inline field-level error messages.

### Requirement 15: Exceptions Page — Resolve Feedback

**User Story:** As a reconciliation analyst, I want resolving an exception to provide clear feedback and link me back to the related case, so that I can continue working efficiently.

#### Acceptance Criteria

1. WHEN the user resolves an exception, THE System SHALL invalidate the exceptions list TanStack_Query cache and refresh the table.
2. WHEN an exception is resolved successfully, THE System SHALL display a success Toast containing a clickable link to the related reconciliation case.
3. IF the resolve API call fails, THEN THE System SHALL display an error Toast with the failure reason.

### Requirement 16: Reports Page — Reconciliation Summary

**User Story:** As a manager, I want to view a reconciliation summary report with filterable data, so that I can monitor overall reconciliation progress.

#### Acceptance Criteria

1. WHEN the user navigates to the Reconciliation Summary tab on ReportsPage, THE System SHALL fetch data from `GET /api/v1/vlr/reports/reconciliation-summary` with Entity_Scope applied.
2. THE System SHALL display the summary data in a tabular format with pagination support.
3. WHILE the report data is loading, THE System SHALL display a loading skeleton.
4. IF the API returns an error, THEN THE System SHALL display an inline error message with a retry option.

### Requirement 17: Approvals Page — Full Stack Build

**User Story:** As an approver, I want a dedicated approvals page listing all pending approval items, so that I can review and act on approvals from one place.

#### Acceptance Criteria

1. WHEN the user navigates to the ApprovalsPage, THE System SHALL fetch pending approvals from `GET /api/v1/vlr/approvals/pending` with Entity_Scope applied.
2. THE System SHALL display each approval item with request details, requester name, submission date, and action buttons.
3. WHEN the user clicks "Approve" on an item, THE System SHALL call `POST /api/v1/vlr/approvals/{id}/approve`, display a loading spinner, wait for 200 OK, refresh the table, and display a success Toast.
4. WHEN the user clicks "Reject" on an item, THE System SHALL display a reason input dialog, then call `POST /api/v1/vlr/approvals/{id}/reject` with the reason, wait for 200 OK, refresh the table, and display a success Toast.
5. WHEN the user clicks "Delegate" on an item, THE System SHALL display a user selection dialog, then call `POST /api/v1/vlr/approvals/{id}/delegate` with the selected user, wait for 200 OK, refresh the table, and display a success Toast.
6. IF any approval action API call fails, THEN THE System SHALL display an error Toast with the failure reason.
7. THE System SHALL be accessible via a new route `/approvals` registered in the AppRouter with MainLayout wrapping.

### Requirement 18: Sidebar — Exceptions Link

**User Story:** As a user, I want to access the Exceptions page from the sidebar navigation, so that I can quickly navigate to exception management.

#### Acceptance Criteria

1. THE System SHALL display an "Exceptions" menu item in the Sidebar navigation under the appropriate section.
2. WHEN the user clicks the "Exceptions" menu item, THE System SHALL navigate to `/exceptions`.
3. THE System SHALL highlight the "Exceptions" menu item when the current route matches `/exceptions`.

### Requirement 19: Document Types Page

**User Story:** As an administrator, I want a dedicated page for managing document type classifications, so that I can define what document types are available in the system.

#### Acceptance Criteria

1. THE System SHALL provide a DocumentTypesPage accessible via a new route `/settings/document-types`.
2. WHEN the DocumentTypesPage loads, THE System SHALL fetch document types from the backend API with Entity_Scope applied.
3. THE System SHALL allow creating, editing, and deleting document types through the page interface.
4. WHEN any create/edit/delete operation succeeds, THE System SHALL invalidate the document types query and display a success Toast.
5. IF any operation fails, THEN THE System SHALL display an error Toast with the failure reason.

### Requirement 20: Workflow Admin Routes

**User Story:** As an administrator, I want to access existing workflow admin pages through proper routes, so that I can configure workflow rules and stages.

#### Acceptance Criteria

1. THE System SHALL register routes for existing workflow admin pages in the AppRouter under a `/workflow-admin` path prefix.
2. WHEN the user navigates to a workflow admin route, THE System SHALL render the corresponding existing workflow admin page component within the MainLayout.
3. THE System SHALL add workflow admin links to the Sidebar navigation under an administration section.

### Requirement 21: End-to-End Flow — Submit for Approval

**User Story:** As a reconciliation analyst, I want to submit completed reconciliations for approval, so that the approval workflow is triggered and the case progresses.

#### Acceptance Criteria

1. WHEN the user clicks "Submit for Approval" on a reconciliation case, THE System SHALL call `POST /api/v1/vlr/approvals/submit` with the case ID and display a loading spinner.
2. WHEN the API returns success, THE System SHALL update the case status indicator to "Pending Approval" and display a success Toast.
3. IF the case is not in a submittable state, THEN THE System SHALL disable the "Submit for Approval" button and display a tooltip explaining the prerequisite.

### Requirement 22: End-to-End Flow — Auto-Trigger Sign-Off

**User Story:** As a reconciliation analyst, I want the system to automatically progress cases to sign-off after review is completed, so that the workflow continues without manual intervention.

#### Acceptance Criteria

1. WHEN a case review is marked as done, THE System SHALL automatically trigger the sign-off request to the vendor portal.
2. WHEN the auto-trigger succeeds, THE System SHALL update the case status to "Awaiting Sign-Off" and log the event.
3. IF the auto-trigger fails, THEN THE System SHALL display a warning Toast and allow manual retry.

### Requirement 23: End-to-End Flow — Status Progression Indicators

**User Story:** As a reconciliation analyst, I want to see clear visual indicators of where each case stands in the workflow, so that I can quickly assess progress.

#### Acceptance Criteria

1. THE System SHALL display a status badge on each case row reflecting the current lifecycle stage (Requested, Received, Reconciling, In Review, Awaiting Sign-Off, Signed Off, Pending Approval, Approved, Closed).
2. THE System SHALL use consistent color coding from existing CSS variables for each status.
3. WHEN a case status changes due to a user action, THE System SHALL immediately update the status badge without requiring a full page refresh.

### Requirement 24: Cross-Cutting — Loading, Error, and Empty States

**User Story:** As a user, I want consistent feedback when data is loading, when errors occur, or when no data exists, so that I always understand the current state of the application.

#### Acceptance Criteria

1. WHILE any API data is being fetched, THE System SHALL display a loading skeleton or spinner appropriate to the component size.
2. IF any API call returns an error, THEN THE System SHALL display an inline error state with a descriptive message and retry action.
3. IF any list API returns zero results, THEN THE System SHALL display an appropriate empty state message.
4. THE System SHALL use existing PrimeReact components and em-card CSS class for all loading, error, and empty state presentations.

### Requirement 25: Cross-Cutting — Entity Scoping and Cache Invalidation

**User Story:** As a user in a multi-entity organization, I want all data queries to be scoped to my current entity, so that I only see relevant data.

#### Acceptance Criteria

1. THE System SHALL include the active Entity_Scope identifier in all TanStack_Query cache keys.
2. WHEN the user switches entities, THE System SHALL invalidate all entity-scoped query caches and refetch visible data.
3. THE System SHALL pass the entity identifier as a query parameter or header on all API requests via the apiClient.
