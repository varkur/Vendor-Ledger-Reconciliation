# Design Document

## Overview

This design addresses all dead buttons, missing pages, and broken flows in the VLR frontend and backend to achieve production readiness. Changes span route registration, sidebar navigation, page rewrites (replacing mock data with API calls), new pages (Approvals, Document Types), and end-to-end workflow wiring. All work follows existing patterns: TanStack Query for data fetching, apiClient/portalClient for HTTP, PrimeReact components, and the em-card design system.

## Architecture

The existing architecture remains unchanged. This work is purely a UI wiring and integration effort within the established layered architecture:

```
Frontend (React/PrimeReact/TanStack Query)
   ↓ apiClient / portalClient (Axios)
API Layer (FastAPI v1 — already has controllers for all domains)
   ↓
Domain Services + Infrastructure
```

All backend controllers already exist (approval_controller, case_controller, notification_controller, portal_controller, etc.). This spec primarily adds frontend pages and wires existing dead UI to those backend endpoints, with a few new backend endpoints where gaps exist.

## Components and Interfaces

### Frontend Changes

#### 1. ReconciliationDetailPage Rewrite (Requirement 1, 2, 3, 4)

**File**: `frontend/src/features/track-reconciliation/pages/ReconciliationDetailPage.tsx`

Replace all hardcoded arrays (`allPartiesData`, `recoStageData`, `reviewStageData`, `signOffData`, `actionTrackerData`) with TanStack Query hooks that fetch from:
- `GET /api/v1/vlr/reconciliation-requests/{request_id}/cases`

Create a new hook file: `frontend/src/features/track-reconciliation/hooks/useReconciliationDetail.ts`

```typescript
// Hooks to create:
export function useBatchCases(requestId: string, params: { stage?: string; page?: number; page_size?: number }) { ... }
export function useSendReminder(requestId: string) { ... }  // POST /api/v1/vlr/reminders/send
export function useBulkReview() { ... }  // POST /api/v1/vlr/cases/bulk-review
export function useBulkReviewDone() { ... }  // POST /api/v1/vlr/cases/bulk-review-done
export function useBulkSignoffRequest() { ... }  // POST /api/v1/vlr/cases/bulk-signoff-request
```

API layer: `frontend/src/features/track-reconciliation/api/reconciliationDetailApi.ts`

```typescript
export interface BatchCaseRow {
  id: string;
  case_id: string;
  vendor_code: string;
  vendor_name: string;
  status: string;
  workflow_step: string;
  last_update_date: string;
  days_elapsed: number;
  company_amount: number;
  difference_amount: number;
  file_extension?: string;
  owner?: string;
  reviewer?: string;
  no_of_lines?: number;
  unmatched_entries?: number;
  reminder_count?: number;
  contact_person?: string;
}

export interface BatchCasesResponse {
  items: BatchCaseRow[];
  total: number;
  page: number;
  page_size: number;
  summary: {
    total_parties: number;
    reco_stage_count: number;
    review_stage_count: number;
    signoff_stage_count: number;
  };
}
```

Tab filtering: Each tab passes a `stage` filter parameter to the API:
- All Parties: no filter (all cases)
- Reco Stage: `stage=reconciliation`
- Review Stage: `stage=review`
- Sign Off Stage: `stage=signoff`
- Action Tracker: `stage=action_tracker`

#### 2. ReconciliationOutputPanel Route (Requirement 3)

**New route**: `/track-reconciliation/:requestId/case/:caseId`

**File**: `frontend/src/app/router/AppRouter.tsx` — add route:
```tsx
<Route path="track-reconciliation/:requestId/case/:caseId" element={<ReconciliationOutputPage />} />
```

**New page**: `frontend/src/features/track-reconciliation/pages/ReconciliationOutputPage.tsx`
```typescript
// Reads caseId from useParams, renders ReconciliationOutputPanel
import { useParams } from 'react-router-dom';
import { ReconciliationOutputPanel } from '../components/ReconciliationOutput';

export const ReconciliationOutputPage = () => {
  const { caseId } = useParams<{ caseId: string; requestId: string }>();
  if (!caseId) return <div>Invalid case</div>;
  return <ReconciliationOutputPanel caseId={caseId} />;
};
```

#### 3. Vendor Portal Fixes (Requirement 5, 6, 7, 8)

**PortalAuthPage** — Add onClick to "Request New Link":
```typescript
const handleRequestNewLink = () => {
  // Show email input dialog, then call POST /api/v1/vlr/portal/request-new-link
};
```

**PortalUploadPage** — Add polling for reconciliation status after upload:
```typescript
// After successful upload, poll GET /api/v1/vlr/portal/reconciliation-status/{case_id}
// When status = 'completed', auto-navigate to /portal/statement
```

**PortalStatementPage** — Add "Raise Dispute" button:
```typescript
// Opens dialog with reason textarea + item selection
// Calls POST /api/v1/vlr/portal/dispute/{case_id}
```

#### 4. Request Statement Page Fixes (Requirement 9, 10, 11)

**Preview button**: Opens Dialog, calls `GET /api/v1/vlr/email-templates/{id}/preview`.

**Send Email From dropdown**: Populated from `GET /api/v1/vlr/settings/email-config` (existing endpoint).

**Contact Person dropdown**: Populated from `GET /api/v1/vlr/vendors/{vendor_id}/contacts` when vendors are selected.

**File Upload (Step 2)**: Wired to an upload API with progress tracking.

#### 5. Direct Reconciliation View Navigation (Requirement 12, 13)

Add `onClick={() => navigate(`/track-reconciliation/${row.id}/case/${row.case_id}`)}` to the View action template.

Quick Create dialog: Replace hardcoded values with proper form fields (vendor dropdown, date pickers, fiscal year selector).

#### 6. Reminders Create Group (Requirement 14)

Add onClick handler to "Create Group" button that opens a Dialog with form fields:
- Group Name, Interval (days), Number of Reminders
- On submit: `POST /api/v1/vlr/reminder-configs`

#### 7. Exceptions Resolve Feedback (Requirement 15)

After `resolveExceptionMutation` succeeds:
- Invalidate the exceptions query
- Show success Toast with link to related case

#### 8. Reports Reconciliation Summary (Requirement 16)

The `useReconciliationSummary` hook already calls `GET /api/v1/vlr/reports/reconciliation-summary` with pagination. If the backend requires a case_id, add a new aggregate endpoint:
- `GET /api/v1/vlr/reports/reconciliation-summary` (no case_id, returns aggregate across all cases)

#### 9. Approvals Page (Requirement 17)

**New page**: `frontend/src/features/approvals/pages/ApprovalsPage.tsx`

```typescript
// Fetches GET /api/v1/vlr/approvals/pending
// Renders DataTable with: Vendor Name, Case ID, Amount, Submitted By, Date, Actions
// Actions: Approve (POST .../approve), Reject (POST .../reject with dialog), Delegate (POST .../delegate with user picker)
```

**New route**: `/approvals` in AppRouter.tsx
**Sidebar**: Add to Account Reco section

#### 10. Sidebar Updates (Requirement 18, 20)

Add to the `navItems` array in MainLayout:
- Under "Account Reco": `{ label: 'Exceptions', path: '/exceptions' }` after Track Reconciliation
- Under "Account Reco": `{ label: 'Approvals', path: '/approvals' }` after Exceptions

Fix "Document Types" path: Change from `/settings` to `/settings/document-types`.

#### 11. Document Types Page (Requirement 19)

**New page**: `frontend/src/features/vlr-settings/pages/DocumentTypesPage.tsx`

CRUD for document type mappings using existing backend endpoint:
- `GET /api/v1/vlr/settings/document-types`
- `POST /api/v1/vlr/settings/document-types`
- `PUT /api/v1/vlr/settings/document-types/{id}`
- `DELETE /api/v1/vlr/settings/document-types/{id}`

**New route**: `/settings/document-types` in AppRouter.tsx

#### 12. Workflow Admin Routes (Requirement 20)

Check if WorkflowDefinitionsPage and ApprovalMatrixPage exist. If so, add routes:
- `/settings/workflow-definitions`
- `/settings/approval-matrix`

Add to Settings sidebar section.

#### 13. End-to-End Flow Wiring (Requirement 21, 22, 23)

**Submit for Approval**: On ReconciliationOutputPanel, after all Tab 2 items are confirmed, show "Submit for Approval" button → `POST /api/v1/vlr/approvals/submit`.

**Status badges**: Add lifecycle stage badges to case rows using consistent color coding.

### Backend Changes

#### New Endpoints Required

1. **POST /api/v1/vlr/portal/request-new-link** — Generate new portal token and resend invite email
2. **GET /api/v1/vlr/portal/reconciliation-status/{case_id}** — Return current reconciliation processing status for polling
3. **POST /api/v1/vlr/portal/dispute/{case_id}** — Record vendor dispute with comments
4. **POST /api/v1/vlr/reminders/send** — Send reminder to specific case IDs
5. **POST /api/v1/vlr/cases/bulk-review** — Bulk move cases to review stage
6. **POST /api/v1/vlr/cases/bulk-review-done** — Bulk mark review as done
7. **POST /api/v1/vlr/cases/bulk-signoff-request** — Bulk trigger signoff request
8. **GET /api/v1/vlr/reports/reconciliation-summary** (aggregate, no case_id) — Return summary across all cases with pagination
9. **POST /api/v1/vlr/approvals/submit** — Submit a case for approval
10. **GET /api/v1/vlr/settings/document-types** — List document type mappings (CRUD)
11. **POST /api/v1/vlr/settings/document-types** — Create document type mapping
12. **PUT /api/v1/vlr/settings/document-types/{id}** — Update document type mapping
13. **DELETE /api/v1/vlr/settings/document-types/{id}** — Delete document type mapping
14. **GET /api/v1/vlr/email-templates/{id}/preview** — Render email template preview
15. **GET /api/v1/vlr/vendors/{vendor_id}/contacts** — Get vendor contacts (may already exist)

All new endpoints follow the existing pattern: FastAPI router → service → repository.

## Data Models

No new database models are required. All data models already exist from the vlr-complete-rebuild spec. The new endpoints operate on existing models:
- `vlr_reconciliation_cases` (workflow_step, status fields)
- `vlr_document_type_mappings` (CRUD via settings)
- `vlr_portal_tokens` (for request-new-link)
- `vlr_audit_events` (for logging actions)

## Error Handling

All new frontend components follow the established pattern:
- Loading: `<ProgressSpinner />` or `<Skeleton />`
- Error: `<Message severity="error" />` with retry button
- Empty: Icon + descriptive text + action CTA
- Success: Toast notification

All backend endpoints follow existing error handling middleware with structured JSON responses and correlation IDs.

## Cross-Cutting Concerns

### Entity Scoping (Requirement 25)
All new TanStack Query hooks include `companyCode` in their query keys and pass it as a parameter to API calls via `apiClient`. Entity switching triggers `queryClient.invalidateQueries()` (already implemented in MainLayout).

### Cache Invalidation
- Bulk actions invalidate the batch cases query
- Resolve exception invalidates the exceptions list
- Create Group invalidates reminder groups query
- Approve/Reject invalidates pending approvals query

### Navigation
All navigation uses `react-router-dom`'s `useNavigate` for proper browser history support. URL state is preserved for tab selection via query parameters where appropriate.
