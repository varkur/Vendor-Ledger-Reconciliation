/**
 * Direct Reconciliation API functions.
 * Communicates with backend VLR request endpoints via Axios.
 *
 * Requirements: 23.1, 25.1, 25.2
 */

import { apiClient } from '@shared/services/apiClient';

const BASE = '/vlr/requests';

// ─────────────────────────────────────────────────────────────────────────────
// Types
// ─────────────────────────────────────────────────────────────────────────────

/** Matching preferences configuration for a reconciliation request. */
export interface MatchingPreferences {
  exact_match_enabled: boolean;
  tolerance_match_enabled: boolean;
  fuzzy_reference_enabled: boolean;
  one_to_many_enabled: boolean;
  many_to_one_enabled: boolean;
}

/** Request body for creating a new reconciliation request. */
export interface CreateReconciliationRequest {
  company_code: string;
  fiscal_year: string;
  period_start: string; // ISO date string
  period_end: string; // ISO date string
  vendor_ids: string[];
  tolerance_amount?: number;
  tds_percentage?: number;
  gst_percentage?: number;
  matching_preferences?: MatchingPreferences;
  assigned_manager_id?: string;
}

/** A single reconciliation request response from the backend. */
export interface ReconciliationRequestResponse {
  id: string;
  company_code: string;
  fiscal_year: string;
  period_start: string;
  period_end: string;
  status: string;
  tolerance_amount: number | null;
  tds_percentage: number | null;
  gst_percentage: number | null;
  matching_preferences: Record<string, boolean> | null;
  assigned_manager_id: string | null;
  created_by: string | null;
  created_date: string | null;
}

/** Paginated list response for reconciliation requests. */
export interface ReconciliationRequestListResponse {
  items: ReconciliationRequestResponse[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

/** Parameters for listing reconciliation requests. */
export interface ListRequestsParams {
  company_code: string;
  status?: string;
  fiscal_year?: string;
  reco_type?: string;
  date_from?: string;
  date_to?: string;
  assigned_manager_id?: string;
  page?: number;
  page_size?: number;
}

// ─────────────────────────────────────────────────────────────────────────────
// API Functions
// ─────────────────────────────────────────────────────────────────────────────

/**
 * List reconciliation requests with filtering and pagination.
 */
export async function listReconciliationRequests(
  params: ListRequestsParams
): Promise<ReconciliationRequestListResponse> {
  const response = await apiClient.get<ReconciliationRequestListResponse>(BASE, {
    params,
  });
  return response.data;
}

/**
 * Create a new reconciliation request.
 */
export async function createReconciliationRequest(
  data: CreateReconciliationRequest
): Promise<ReconciliationRequestResponse> {
  const response = await apiClient.post<ReconciliationRequestResponse>(BASE, data);
  return response.data;
}

/**
 * Get a single reconciliation request by ID.
 */
export async function getReconciliationRequest(
  requestId: string,
  companyCode: string
): Promise<ReconciliationRequestResponse> {
  const response = await apiClient.get<ReconciliationRequestResponse>(
    `${BASE}/${requestId}`,
    { params: { company_code: companyCode } }
  );
  return response.data;
}
