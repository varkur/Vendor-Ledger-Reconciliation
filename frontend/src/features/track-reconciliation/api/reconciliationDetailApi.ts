/**
 * Reconciliation Detail API functions.
 * Communicates with backend VLR endpoints for batch case management and bulk actions.
 *
 * Requirements: 1, 2, 4, 25
 */

import { apiClient } from '@shared/services/apiClient';

// ─────────────────────────────────────────────────────────────────────────────
// Types
// ─────────────────────────────────────────────────────────────────────────────

/** A single case row within a reconciliation batch. */
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

/** Paginated response for batch cases including summary counts. */
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

/** Parameters for fetching batch cases. */
export interface BatchCasesParams {
  company_code: string;
  stage?: string;
  page?: number;
  page_size?: number;
}

/** Request body for sending reminders. */
export interface SendReminderRequest {
  company_code: string;
  case_ids: string[];
  request_id: string;
}

/** Request body for bulk review action. */
export interface BulkReviewRequest {
  company_code: string;
  case_ids: string[];
}

/** Request body for bulk review done action. */
export interface BulkReviewDoneRequest {
  company_code: string;
  case_ids: string[];
}

/** Request body for bulk signoff request action. */
export interface BulkSignoffRequestBody {
  company_code: string;
  case_ids: string[];
}

/** Generic bulk action response. */
export interface BulkActionResponse {
  success: boolean;
  processed: number;
  failed: number;
  results?: Array<{ case_id: string; success: boolean; message?: string }>;
}

// ─────────────────────────────────────────────────────────────────────────────
// Statistics Types
// ─────────────────────────────────────────────────────────────────────────────

/** Amount and entry count for a difference or action row. */
export interface AmountEntry {
  amount: number;
  entry_count: number;
}

/** Amount statistics row for a specific category. */
export interface AmountCategoryRow {
  category: string;
  total_company_amount: number;
  company_amount_responded: number;
  party_amount_responded: number;
  net_difference: number;
}

/** Statement status counts. */
export interface StatementStatusCounts {
  total: number;
  responded: number;
  not_responded: number;
  rejected: number;
  failed: number;
}

/** Reconciliation status counts per sub-status. */
export interface ReconciliationStatusCounts {
  in_progress: number;
  statement_received: number;
  mapping_pending: number;
  statement_mapped: number;
  auto_completed: number;
  review_pending: number;
  reviewed: number;
  signoff_requested: number;
  signoff_completed: number;
  reco_rejected: number;
}

/** Reminder info. */
export interface ReminderInfo {
  reminders_sent: number;
  max_reminders: number;
  last_reminder_date: string | null;
}

/** Full statistics response from the backend. */
export interface RequestStatisticsResponse {
  request_id: string;
  total_cases: number;
  cases_by_status: Record<string, number>;
  statement_status: StatementStatusCounts;
  reconciliation_status: ReconciliationStatusCounts;
  amount_statistics: AmountCategoryRow[];
  reason_for_difference: Record<string, AmountEntry>;
  action_summary: Record<string, AmountEntry>;
  reminder_info: ReminderInfo;
}

// ─────────────────────────────────────────────────────────────────────────────
// API Functions
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Fetch cases for a reconciliation request with optional stage filtering and pagination.
 * GET /api/v1/vlr/reconciliation-requests/{request_id}/cases
 */
export async function getBatchCases(
  requestId: string,
  params: BatchCasesParams
): Promise<BatchCasesResponse> {
  const response = await apiClient.get<BatchCasesResponse>(
    `/vlr/reconciliation-requests/${requestId}/cases`,
    { params }
  );
  return response.data;
}

/**
 * Send reminder emails to selected cases.
 * POST /api/v1/vlr/reminders/send
 */
export async function sendReminder(data: SendReminderRequest): Promise<BulkActionResponse> {
  const response = await apiClient.post<BulkActionResponse>('/vlr/reminders/send', data);
  return response.data;
}

/**
 * Bulk move cases to review stage.
 * POST /api/v1/vlr/cases/bulk-review
 */
export async function bulkReview(data: BulkReviewRequest): Promise<BulkActionResponse> {
  const response = await apiClient.post<BulkActionResponse>('/vlr/cases/bulk-review', data);
  return response.data;
}

/**
 * Bulk mark review as done for selected cases.
 * POST /api/v1/vlr/cases/bulk-review-done
 */
export async function bulkReviewDone(data: BulkReviewDoneRequest): Promise<BulkActionResponse> {
  const response = await apiClient.post<BulkActionResponse>(
    '/vlr/cases/bulk-review-done',
    data
  );
  return response.data;
}

/**
 * Bulk trigger signoff request for selected cases.
 * POST /api/v1/vlr/cases/bulk-signoff-request
 */
export async function bulkSignoffRequest(
  data: BulkSignoffRequestBody
): Promise<BulkActionResponse> {
  const response = await apiClient.post<BulkActionResponse>(
    '/vlr/cases/bulk-signoff-request',
    data
  );
  return response.data;
}


/**
 * Fetch statistics for a reconciliation request.
 * GET /api/v1/vlr/requests/{request_id}/statistics
 */
export async function getRequestStatistics(
  requestId: string,
  companyCode: string
): Promise<RequestStatisticsResponse> {
  const response = await apiClient.get<RequestStatisticsResponse>(
    `/vlr/requests/${requestId}/statistics`,
    { params: { company_code: companyCode } }
  );
  return response.data;
}
