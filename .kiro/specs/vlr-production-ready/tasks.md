# Implementation Plan: VLR Production Ready

## Overview

Fix all dead buttons, broken flows, and missing pages in the VLR application to make it production-ready. Work is organized as vertical slices: each task wires a frontend component to real backend APIs, adds missing routes, or creates new pages. Backend endpoints are added only where they don't already exist.

## Tasks

- [x] 1. ReconciliationDetailPage — Live Data & Bulk Actions (P0)
  - [x] 1.1 Create API layer and hooks for ReconciliationDetailPage
    - Create `frontend/src/features/track-reconciliation/api/reconciliationDetailApi.ts` with types and API functions for: getBatchCases (GET /api/v1/vlr/reconciliation-requests/{request_id}/cases), sendReminder (POST /api/v1/vlr/reminders/send), bulkReview, bulkReviewDone, bulkSignoffRequest
    - Create `frontend/src/features/track-reconciliation/hooks/useReconciliationDetail.ts` with TanStack Query hooks wrapping each API function
    - Include Entity_Scope (companyCode) in all query keys and API params
    - _Requirements: 1, 2, 4, 25_

  - [x] 1.2 Create backend bulk action endpoints
    - Add `POST /api/v1/vlr/reminders/send` endpoint in notification_controller accepting case_ids array, triggering reminder emails
    - Add `POST /api/v1/vlr/cases/bulk-review` in case_controller accepting case_ids, advancing each case workflow to review step
    - Add `POST /api/v1/vlr/cases/bulk-review-done` in case_controller accepting case_ids, marking review complete
    - Add `POST /api/v1/vlr/cases/bulk-signoff-request` in case_controller accepting case_ids, triggering portal sign-off invite
    - All endpoints validate permissions and return success/failure per case_id
    - _Requirements: 4_

  - [x] 1.3 Rewrite ReconciliationDetailPage to use live data
    - Remove all hardcoded mock arrays (allPartiesData, recoStageData, reviewStageData, signOffData, actionTrackerData)
    - Replace with useBatchCases hook fetching from API with stage filter per tab
    - Add loading skeleton state while data loads
    - Add error state with retry button
    - Add empty state when no cases exist
    - Preserve tab state in URL query parameter for back/forward navigation
    - _Requirements: 1, 2, 24_

  - [x] 1.4 Wire all action buttons on ReconciliationDetailPage
    - "Send Reminder" → calls useSendReminder with selected case_ids, shows loading spinner, success Toast on completion, invalidates query
    - "Send For Review" → calls useBulkReview with selected case_ids, same UX pattern
    - "Review Done" → calls useBulkReviewDone with selected case_ids
    - "Request SignOff" → calls useBulkSignoffRequest with selected case_ids
    - "Bulk Actions" → dropdown menu with all bulk operations
    - "More Actions" header button → dropdown with Export batch, Close batch options
    - All buttons disabled when no rows selected, show count badge
    - _Requirements: 4_

  - [x] 1.5 Wire "View" button navigation to ReconciliationOutputPanel
    - Change the actionTemplate "View" span to a clickable element that navigates to `/track-reconciliation/${requestId}/case/${row.case_id}`
    - Display contextual label: "View" for completed, "Reconcile" for pending mapping, "Review" for in-review cases
    - _Requirements: 3_

- [x] 2. ReconciliationOutput Route & Page (P0)
  - [x] 2.1 Create ReconciliationOutputPage and register route
    - Create `frontend/src/features/track-reconciliation/pages/ReconciliationOutputPage.tsx` that reads caseId from useParams and renders ReconciliationOutputPanel
    - Add breadcrumb navigation: Track Reconciliation > {requestId} > {vendorName}
    - Add back button to return to ReconciliationDetailPage
    - Register route in AppRouter.tsx: `<Route path="track-reconciliation/:requestId/case/:caseId" element={<ReconciliationOutputPage />} />`
    - _Requirements: 3_

  - [x] 2.2 Add "Submit for Approval" button to ReconciliationOutputPanel
    - After all Finance Confirmation items (Tab 2) are processed (tab shows 0 pending items), display a "Submit for Approval" button
    - Button calls `POST /api/v1/vlr/approvals/submit` with case_id
    - On success, show Toast and update case status badge to "Pending Approval"
    - Disable button if case is not in submittable state (show tooltip explaining prerequisite)
    - Create backend endpoint `POST /api/v1/vlr/approvals/submit` in approval_controller if not exists
    - _Requirements: 21_

- [x] 3. Direct Reconciliation Page Fixes (P0)
  - [x] 3.1 Wire View navigation on DirectReconciliationPage
    - Update actionTemplate to navigate to `/track-reconciliation/${rowData.id}/case/${rowData.case_id}` on click (or to the detail page if case_id not directly available, navigate to `/track-reconciliation/${rowData.id}`)
    - Use useNavigate hook from react-router-dom
    - _Requirements: 12_

  - [x] 3.2 Improve Quick Create dialog with proper form
    - Replace hardcoded fiscal year with a dropdown (auto-populated from current date: e.g., "2024-25", "2025-26")
    - Add Calendar date pickers for Period From and Period To
    - Add vendor selection Dropdown (single vendor, fetched from vendors API)
    - Add file upload field for company ledger (optional at creation time)
    - Validate all required fields before submission using form state
    - Pass all form values to the create mutation
    - _Requirements: 13_

- [x] 4. Request Statement Page Fixes (P0)
  - [x] 4.1 Wire Preview button and email dropdowns
    - "Preview" button onClick: fetch `GET /api/v1/vlr/email-templates/{emailTemplate}/preview` and display rendered HTML in a Dialog modal
    - "Send Email From" dropdown: fetch options from `GET /api/v1/vlr/settings/email-config` on page mount, map to dropdown options
    - "Contact Person" dropdown: when vendors are selected, fetch contacts from `GET /api/v1/vlr/vendors/{vendor_id}/contacts` for the first selected vendor and populate dropdown
    - "Email Attachment" dropdown: populate with "Company Ledger Extract" as default option plus any configured attachment types
    - Add loading states to dropdowns while data fetches
    - _Requirements: 9, 10_

  - [x] 4.2 Wire file upload in Step 2
    - Replace the static "Browse File" button with PrimeReact FileUpload component
    - Accept .xlsx, .xls, .csv files (max 50MB)
    - On file select + confirm, upload to `POST /api/v1/vlr/reconciliation-requests/{request_id}/upload-company-ledger` (create this backend endpoint if needed)
    - Show upload progress via ProgressBar
    - On success, show Toast and enable navigation to track reconciliation
    - _Requirements: 11_

  - [x] 4.3 Create backend preview and upload endpoints
    - Add `GET /api/v1/vlr/email-templates/{id}/preview` in email_template_controller: render Jinja2 template with sample data, return HTML string
    - Add `POST /api/v1/vlr/reconciliation-requests/{request_id}/upload-company-ledger` in request_controller: accept file upload, store file, trigger transformation pipeline
    - Add `GET /api/v1/vlr/vendors/{vendor_id}/contacts` in vendor_controller if not already implemented: return list of contacts for a vendor
    - _Requirements: 9, 10, 11_

- [x] 5. Vendor Portal Fixes (P1)
  - [x] 5.1 Fix "Request New Link" button on PortalAuthPage
    - Add onClick handler to the "Request New Link" button
    - Show a small form/dialog asking for the vendor's email address
    - On submit, call `POST /api/v1/vlr/portal/request-new-link` with { email }
    - Show success message "A new link has been sent to your email" or error message
    - Create backend endpoint: generate new token, invalidate old one, trigger send_vendor_invite Celery task
    - _Requirements: 5_

  - [x] 5.2 Add processing state and polling to PortalUploadPage
    - After successful upload, if task_id is returned, start polling `GET /api/v1/vlr/portal/reconciliation-status/{case_id}` every 5 seconds using portalClient
    - Show "Processing your statement..." with ProgressSpinner and step indicator
    - When polling returns status "completed", auto-navigate to /portal/statement
    - When polling returns status "error", show error message with support contact
    - After 2 minutes of polling with no completion, show "Taking longer than expected" message with option to check back later
    - Create backend endpoint `GET /api/v1/vlr/portal/reconciliation-status/{case_id}` that returns { status: 'processing' | 'completed' | 'error', message?: string }
    - _Requirements: 6_

  - [x] 5.3 Add "Raise Dispute" flow to PortalStatementPage
    - Add "Raise Dispute" button next to "Proceed to Sign-Off"
    - On click, open Dialog with: reason textarea (required), optional file attachment
    - On submit, call `POST /api/v1/vlr/portal/dispute/{case_id}` with { reason, attachment? } using portalClient
    - On success, show Toast, update status badge to "Disputed", disable "Proceed to Sign-Off"
    - Create backend endpoint: update case status to disputed, create audit event, notify finance team
    - _Requirements: 8_

  - [x] 5.4 Verify PortalStatementPage sign-off navigation
    - Confirm "Proceed to Sign-Off" button navigates to /portal/sign-off correctly
    - Add validation: disable button if case status doesn't allow sign-off (not in 'matched' or 'review_complete' state)
    - Show tooltip on disabled button explaining prerequisite
    - _Requirements: 7_

- [x] 6. Reminders Create Group (P1)
  - [x] 6.1 Add Create Group dialog to RemindersPage
    - Add onClick handler to "Create Group" button that opens a Dialog
    - Dialog form fields: Group Name (InputText, required), Interval Days (InputNumber, required), Number of Reminders (InputNumber, required, default 3)
    - On submit, call `POST /api/v1/vlr/reminder-configs` with form data using apiClient
    - On success, close dialog, invalidate reminder-groups query, show success Toast
    - On error, show inline error messages in dialog
    - Add loading state to submit button during API call
    - _Requirements: 14_

- [x] 7. Approvals Page (P1)
  - [x] 7.1 Create ApprovalsPage frontend
    - Create `frontend/src/features/approvals/pages/ApprovalsPage.tsx`
    - Fetch pending approvals from `GET /api/v1/vlr/approvals/pending` with TanStack Query
    - Render DataTable with columns: Vendor Name, Case ID (truncated), Amount, Submitted By, Submission Date, Actions
    - Action buttons per row: Approve (green), Reject (red, opens reason dialog), Delegate (blue, opens user picker dialog)
    - Approve calls `POST /api/v1/vlr/approvals/{id}/approve`, invalidates query, shows Toast
    - Reject calls `POST /api/v1/vlr/approvals/{id}/reject` with { reason }, same pattern
    - Delegate calls `POST /api/v1/vlr/approvals/{id}/delegate` with { user_id }, same pattern
    - Add loading, error, and empty states following established patterns
    - _Requirements: 17_

  - [x] 7.2 Register Approvals route and sidebar link
    - Add route in AppRouter.tsx: `<Route path="approvals" element={<ApprovalsPage />} />`
    - Add "Approvals" to navItems under "Account Reco" in MainLayout.tsx, positioned after Track Reconciliation
    - _Requirements: 17, 18_

- [x] 8. Sidebar & Navigation Fixes (P1)
  - [x] 8.1 Add Exceptions and Approvals to sidebar, fix Document Types link
    - In MainLayout.tsx navItems, add `{ label: 'Exceptions', path: '/exceptions' }` to Account Reco children, after Track Reconciliation
    - Add `{ label: 'Approvals', path: '/approvals' }` to Account Reco children, after Exceptions
    - Fix "Document Types" path: change from `/settings` to `/settings/document-types`
    - _Requirements: 18, 19_

- [x] 9. Exception Resolve Feedback (P2)
  - [x] 9.1 Improve resolution feedback on ExceptionListPage
    - After resolveExceptionMutation succeeds: invalidate exceptions list query (queryClient.invalidateQueries), show success Toast with message and clickable link to the related reconciliation case
    - After resolveExceptionMutation fails: show error Toast with failure reason from API
    - Keep selection intact on error so user can retry
    - _Requirements: 15_

- [x] 10. Reports Reconciliation Summary Fix (P2)
  - [x] 10.1 Create aggregate reconciliation summary endpoint and fix frontend
    - Create backend endpoint `GET /api/v1/vlr/reports/reconciliation-summary` (without case_id) in report_controller that returns paginated aggregate data across all cases: vendor_name, opening_balance, invoices, payments, adjustments, closing_balance, difference, status
    - Ensure the existing `useReconciliationSummary` hook calls this endpoint correctly (verify it doesn't require case_id)
    - Add date range filter support (query params: date_from, date_to)
    - _Requirements: 16_

- [x] 11. Document Types Page (P2)
  - [x] 11.1 Create DocumentTypesPage with CRUD
    - Create `frontend/src/features/vlr-settings/pages/DocumentTypesPage.tsx`
    - Fetch document types from `GET /api/v1/vlr/settings/document-types` with TanStack Query
    - Render DataTable with columns: Code, Category (Invoice/Payment/Credit Note/Debit Note/TDS/Other), Is TDS (boolean badge), Active (toggle)
    - Add "Create" button → Dialog with: Code (InputText), Category (Dropdown), Is TDS (Checkbox), Active (Checkbox)
    - Add inline Edit and Delete actions per row
    - Create calls POST, Edit calls PUT, Delete calls DELETE on the same endpoint path
    - Add loading, error, empty states
    - _Requirements: 19_

  - [x] 11.2 Create backend document types CRUD endpoints
    - Add `GET /api/v1/vlr/settings/document-types` to settings_controller: list all document type mappings with pagination
    - Add `POST /api/v1/vlr/settings/document-types`: create new mapping (validate unique code)
    - Add `PUT /api/v1/vlr/settings/document-types/{id}`: update mapping
    - Add `DELETE /api/v1/vlr/settings/document-types/{id}`: soft-delete (set is_active=false) or hard-delete
    - Register route in AppRouter.tsx: `<Route path="settings/document-types" element={<DocumentTypesPage />} />`
    - _Requirements: 19_

- [x] 12. Workflow Admin Routes (P2)
  - [x] 12.1 Register existing workflow admin pages in router
    - Check if WorkflowDefinitionsPage and ApprovalMatrixPage components exist in the codebase
    - If they exist, add routes: `/settings/workflow-definitions` and `/settings/approval-matrix` in AppRouter.tsx
    - If they don't exist, create placeholder pages with descriptive "coming soon" content
    - Add "Workflow Config" link to Settings section in sidebar navItems
    - _Requirements: 20_

- [x] 13. End-to-End Flow — Status Indicators (P0)
  - [x] 13.1 Add status progression badges and auto-trigger sign-off
    - Create a StatusBadge component using PrimeReact Tag with consistent color mapping from CSS variables for all lifecycle stages: Requested, Received, Reconciling, In Review, Awaiting Sign-Off, Signed Off, Pending Approval, Approved, Closed
    - Apply StatusBadge to case rows in ReconciliationDetailPage and DirectReconciliationPage
    - After approval is granted (detected via status change in the approvals flow), the backend should auto-trigger the portal sign-off email (add logic to approval_controller's approve endpoint to call notification_service.send_portal_signoff)
    - _Requirements: 22, 23_

## Notes

- All frontend work uses the existing design system: PrimeReact components, em-card CSS class, existing color variables
- All API calls go through apiClient (authenticated) or portalClient (portal token-based)
- TanStack Query is used for all server state with proper cache invalidation on mutations
- Entity scoping is enforced on all queries via companyCode from useSelectedEntity hook
- All pages support browser back/forward navigation (react-router-dom, no hash routing)
- Loading states use ProgressSpinner or Skeleton; errors use Message with retry; empty states use descriptive text with action CTA
- Toast notifications (PrimeReact Toast) for all mutation success/failure feedback

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2"] },
    { "id": 1, "tasks": ["1.3", "1.4", "1.5", "2.1"] },
    { "id": 2, "tasks": ["2.2", "3.1", "3.2", "4.1", "4.3"] },
    { "id": 3, "tasks": ["4.2", "5.1", "5.2", "13.1"] },
    { "id": 4, "tasks": ["5.3", "5.4", "6.1", "7.1"] },
    { "id": 5, "tasks": ["7.2", "8.1"] },
    { "id": 6, "tasks": ["9.1", "10.1", "11.1", "11.2"] },
    { "id": 7, "tasks": ["12.1"] }
  ]
}
```
