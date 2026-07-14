/**
 * Reconciliation Output API functions.
 * Communicates with the backend reconciliation output endpoints via Axios.
 *
 * Requirements: 18.1-18.4, 19.1-19.4, 20.1-20.3, 21.1-21.3, 22.1-22.4
 */

import { apiClient } from '@shared/services/apiClient';

const BASE = '/vlr/reconciliation';

// ─────────────────────────────────────────────────────────────────────────────
// Types
// ─────────────────────────────────────────────────────────────────────────────

/** Match type from the multi-pass reconciliation engine. */
export type MatchType =
  | 'Exact'
  | 'Tolerance'
  | 'Fuzzy'
  | 'One-to-Many'
  | 'Many-to-One'
  | 'Date-proximity';

/** Confirmation action type. */
export type ConfirmAction = 'accept' | 'reject' | 'clarify';

/** Unmatched company action type. */
export type UnmatchedCompanyAction = 'accept' | 'dispute' | 'request';

/** Unmatched vendor action type. */
export type UnmatchedVendorAction = 'accept' | 'reject' | 'clarify';

/** Paginated response wrapper. */
export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

/** Pagination and filter parameters for list endpoints. */
export interface ListParams {
  page?: number;
  page_size?: number;
  sort_by?: string;
  sort_order?: 'asc' | 'desc';
  search?: string;
  match_type?: MatchType;
}

/** A single matched item entry (Tab 1). */
export interface MatchedItem {
  id: string;
  company_reference: string;
  vendor_reference: string;
  company_amount: number;
  vendor_amount: number;
  match_type: MatchType;
  confidence_score: number;
  posting_date: string;
  document_type: string;
  currency: string;
}

/** A single confirmation item entry (Tab 2). */
export interface ConfirmationItem {
  id: string;
  company_reference: string;
  vendor_reference: string;
  company_amount: number;
  vendor_amount: number;
  match_type: MatchType;
  confidence_score: number;
  posting_date: string;
  document_type: string;
  difference: number;
  reason: string;
}

/** A single unmatched company entry (Tab 3). */
export interface UnmatchedCompanyItem {
  id: string;
  reference: string;
  document_type: string;
  amount: number;
  posting_date: string;
  description: string;
  currency: string;
}

/** A single unmatched vendor entry (Tab 4). */
export interface UnmatchedVendorItem {
  id: string;
  reference: string;
  transaction_type: string;
  amount: number;
  date: string;
  description: string;
  currency: string;
}

/** Balance comparison entry for differences summary (Tab 5). */
export interface BalanceComparison {
  company_opening_balance: number;
  vendor_opening_balance: number;
  opening_difference: number;
  company_closing_balance: number;
  vendor_closing_balance: number;
  closing_difference: number;
}

/** Totals by transaction type for differences summary (Tab 5). */
export interface TypeTotal {
  transaction_type: string;
  company_total: number;
  vendor_total: number;
  difference: number;
}

/** Full differences summary (Tab 5). */
export interface DifferencesSummary {
  balance_comparison: BalanceComparison;
  type_totals: TypeTotal[];
  net_difference: number;
  currency: string;
}

/** Request body for POST /confirm action. */
export interface ConfirmMatchRequest {
  item_id: string;
  action: ConfirmAction | UnmatchedCompanyAction | UnmatchedVendorAction;
  notes?: string;
  tab: 'confirmation' | 'unmatched_company' | 'unmatched_vendor';
}

/** Response from POST /confirm. */
export interface ConfirmMatchResponse {
  success: boolean;
  message: string;
  item_id: string;
}

/** Request body for POST /approvals/submit. */
export interface SubmitForApprovalRequest {
  case_id: string;
  comments?: string;
}

/** Response from POST /approvals/submit. */
export interface SubmitForApprovalResponse {
  approval_id: string;
  case_id: string;
  status: string;
  message: string;
}

// ─────────────────────────────────────────────────────────────────────────────
// API Functions
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Get matched items for a reconciliation case (Tab 1).
 */
export async function getMatchedItems(
  caseId: string,
  params?: ListParams
): Promise<PaginatedResponse<MatchedItem>> {
  const response = await apiClient.get<PaginatedResponse<MatchedItem>>(
    `${BASE}/${caseId}/matched`,
    { params }
  );
  return response.data;
}

/**
 * Get items requiring finance confirmation (Tab 2).
 */
export async function getConfirmationItems(
  caseId: string,
  params?: ListParams
): Promise<PaginatedResponse<ConfirmationItem>> {
  const response = await apiClient.get<PaginatedResponse<ConfirmationItem>>(
    `${BASE}/${caseId}/confirmation`,
    { params }
  );
  return response.data;
}

/**
 * Get unmatched company ledger entries (Tab 3).
 */
export async function getUnmatchedCompany(
  caseId: string,
  params?: ListParams
): Promise<PaginatedResponse<UnmatchedCompanyItem>> {
  const response = await apiClient.get<PaginatedResponse<UnmatchedCompanyItem>>(
    `${BASE}/${caseId}/unmatched-company`,
    { params }
  );
  return response.data;
}

/**
 * Get unmatched vendor ledger entries (Tab 4).
 */
export async function getUnmatchedVendor(
  caseId: string,
  params?: ListParams
): Promise<PaginatedResponse<UnmatchedVendorItem>> {
  const response = await apiClient.get<PaginatedResponse<UnmatchedVendorItem>>(
    `${BASE}/${caseId}/unmatched-vendor`,
    { params }
  );
  return response.data;
}

/**
 * Get differences summary for a reconciliation case (Tab 5).
 */
export async function getDifferencesSummary(
  caseId: string
): Promise<DifferencesSummary> {
  const response = await apiClient.get<DifferencesSummary>(
    `${BASE}/${caseId}/summary`
  );
  return response.data;
}

/**
 * Submit a confirmation action (accept/reject/clarify/dispute/request).
 */
export async function confirmMatch(
  caseId: string,
  request: ConfirmMatchRequest
): Promise<ConfirmMatchResponse> {
  const response = await apiClient.post<ConfirmMatchResponse>(
    `${BASE}/${caseId}/confirm`,
    request
  );
  return response.data;
}

/**
 * Submit a reconciliation case for approval.
 * POST /api/v1/vlr/approvals/submit
 */
export async function submitForApproval(
  request: SubmitForApprovalRequest,
  companyCode: string
): Promise<SubmitForApprovalResponse> {
  const response = await apiClient.post<SubmitForApprovalResponse>(
    '/vlr/approvals/submit',
    request,
    { params: { company_code: companyCode } }
  );
  return response.data;
}
