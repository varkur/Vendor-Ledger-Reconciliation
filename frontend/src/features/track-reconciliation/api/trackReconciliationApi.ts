/**
 * Track Reconciliation API functions.
 * Communicates with the backend case listing/filtering endpoints via Axios.
 *
 * Requirements: 23.2, 25.3, 25.4
 */

import { apiClient } from '@shared/services/apiClient';

const BASE = '/vlr/cases';

// ─────────────────────────────────────────────────────────────────────────────
// Types
// ─────────────────────────────────────────────────────────────────────────────

/** Paginated response wrapper for cases. */
export interface PaginatedCaseResponse {
  items: ReconciliationCase[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

/** A single reconciliation case from the listing endpoint. */
export interface ReconciliationCase {
  id: string;
  request_id: string;
  vendor_id: string;
  case_type: string;
  status: string;
  upload_count: number;
  edit_count: number;
  row_10_balance: number | null;
  match_statistics: Record<string, unknown> | null;
  created_date: string | null;
}

/** Query parameters for listing/filtering cases. */
export interface CaseListParams {
  company_code: string;
  page?: number;
  page_size?: number;
  status?: string;
  vendor_id?: string;
  request_id?: string;
  case_type?: string;
  search?: string;
  sort_by?: string;
  sort_order?: 'asc' | 'desc';
}

// ─────────────────────────────────────────────────────────────────────────────
// API Functions
// ─────────────────────────────────────────────────────────────────────────────

/**
 * List reconciliation cases with filtering and pagination.
 * GET /api/v1/vlr/cases
 */
export async function listCases(params: CaseListParams): Promise<PaginatedCaseResponse> {
  const response = await apiClient.get<PaginatedCaseResponse>(BASE, { params });
  return response.data;
}

/**
 * Get a single reconciliation case by ID.
 * GET /api/v1/vlr/cases/{id}
 */
export async function getCaseById(
  caseId: string,
  companyCode: string
): Promise<ReconciliationCase> {
  const response = await apiClient.get<ReconciliationCase>(`${BASE}/${caseId}`, {
    params: { company_code: companyCode },
  });
  return response.data;
}
