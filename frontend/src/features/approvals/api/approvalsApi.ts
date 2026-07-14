/**
 * Approvals API functions.
 * Communicates with backend approval workflow endpoints via Axios.
 *
 * Requirements: 17
 */

import { apiClient } from '@shared/services/apiClient';

const BASE = '/vlr/approvals';

// ─────────────────────────────────────────────────────────────────────────────
// Types
// ─────────────────────────────────────────────────────────────────────────────

/** A single pending approval item from the listing endpoint. */
export interface PendingApprovalItem {
  id: string;
  request_id: string | null;
  vendor_id: string | null;
  case_type: string | null;
  status: string;
  row_10_balance: number | null;
  created_date: string | null;
  /** Extended fields populated by the frontend display */
  vendor_name?: string;
  submitted_by?: string;
}

/** Response wrapper for pending approvals list. */
export interface PendingApprovalsResponse {
  items: PendingApprovalItem[];
  total: number;
}

/** Request body for approving a case. */
export interface ApproveRequestBody {
  comments?: string;
}

/** Request body for rejecting a case. */
export interface RejectRequestBody {
  comments: string;
}

/** Request body for delegating approval authority. */
export interface DelegateRequestBody {
  to_user_id: string;
  duration_days?: number;
}

/** Response from an approval action (approve/reject). */
export interface ApprovalActionResponse {
  approval_id: string;
  case_id: string;
  decision: string;
  comments: string | null;
  approver_id: string;
  approval_level: string;
  decision_date: string;
}

/** Response from a delegation action. */
export interface DelegationActionResponse {
  id: string;
  from_user_id: string;
  to_user_id: string;
  start_date: string;
  end_date: string;
  is_active: boolean;
}

// ─────────────────────────────────────────────────────────────────────────────
// API Functions
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Fetch pending approvals for the current user.
 * GET /api/v1/vlr/approvals/pending
 */
export async function getPendingApprovals(companyCode: string): Promise<PendingApprovalsResponse> {
  const response = await apiClient.get<PendingApprovalsResponse>(`${BASE}/pending`, {
    params: { company_code: companyCode },
  });
  return response.data;
}

/**
 * Approve a reconciliation case.
 * POST /api/v1/vlr/approvals/{case_id}/approve
 */
export async function approveCase(
  caseId: string,
  data: ApproveRequestBody,
  companyCode: string
): Promise<ApprovalActionResponse> {
  const response = await apiClient.post<ApprovalActionResponse>(
    `${BASE}/${caseId}/approve`,
    data,
    { params: { company_code: companyCode } }
  );
  return response.data;
}

/**
 * Reject a reconciliation case.
 * POST /api/v1/vlr/approvals/{case_id}/reject
 */
export async function rejectCase(
  caseId: string,
  data: RejectRequestBody,
  companyCode: string
): Promise<ApprovalActionResponse> {
  const response = await apiClient.post<ApprovalActionResponse>(
    `${BASE}/${caseId}/reject`,
    data,
    { params: { company_code: companyCode } }
  );
  return response.data;
}

/**
 * Delegate approval authority for a case.
 * POST /api/v1/vlr/approvals/{case_id}/delegate
 */
export async function delegateApproval(
  caseId: string,
  data: DelegateRequestBody,
  companyCode: string
): Promise<DelegationActionResponse> {
  const response = await apiClient.post<DelegationActionResponse>(
    `${BASE}/${caseId}/delegate`,
    data,
    { params: { company_code: companyCode } }
  );
  return response.data;
}
