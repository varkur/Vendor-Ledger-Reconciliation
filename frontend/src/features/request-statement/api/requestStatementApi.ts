/**
 * Request Statement API functions.
 * Communicates with backend VLR request endpoints via Axios.
 *
 * The Request Statement page creates reconciliation requests (same endpoint as Direct Reconciliation)
 * but focuses on the vendor statement request workflow — selecting vendors and configuring
 * reconciliation parameters for sending statement requests.
 *
 * Requirements: 23.3, 25.1, 25.2
 */

import { apiClient } from '@shared/services/apiClient';

const REQUESTS_BASE = '/vlr/requests';
const VENDORS_BASE = '/vlr/vendors';

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

/** Request body for creating a new statement request. */
export interface CreateStatementRequest {
  company_code: string;
  fiscal_year: string;
  period_start: string; // ISO date string (YYYY-MM-DD)
  period_end: string; // ISO date string (YYYY-MM-DD)
  vendor_ids: string[];
  tolerance_amount?: number;
  tds_percentage?: number;
  gst_percentage?: number;
  matching_preferences?: MatchingPreferences;
  assigned_manager_id?: string;
}

/** A single reconciliation request response from the backend. */
export interface StatementRequestResponse {
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

/** Vendor item for selection dropdown. */
export interface VendorOption {
  id: string;
  vendor_code: string;
  name: string;
  status: string;
}

/** Paginated vendor list response. */
export interface VendorListResponse {
  items: VendorOption[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

// ─────────────────────────────────────────────────────────────────────────────
// API Functions
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Create a new statement request (reconciliation request).
 */
export async function createStatementRequest(
  data: CreateStatementRequest
): Promise<StatementRequestResponse> {
  const response = await apiClient.post<StatementRequestResponse>(REQUESTS_BASE, data);
  return response.data;
}

/**
 * Fetch vendors for selection.
 * Only returns active vendors for the given company code.
 */
export async function fetchVendorsForSelection(
  companyCode: string,
  search?: string,
  page = 1,
  pageSize = 50
): Promise<VendorListResponse> {
  const response = await apiClient.get<VendorListResponse>(VENDORS_BASE, {
    params: {
      company_code: companyCode,
      status: 'active',
      search: search || undefined,
      page,
      page_size: pageSize,
    },
  });
  return response.data;
}
