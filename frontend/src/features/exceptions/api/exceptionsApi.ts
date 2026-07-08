/**
 * Exceptions API functions.
 * Communicates with backend exception management endpoints via Axios.
 *
 * Requirements: 23.4, 25.3, 25.4
 */

import { apiClient } from '@shared/services/apiClient';

const BASE = '/vlr/exceptions';

// ─────────────────────────────────────────────────────────────────────────────
// Types
// ─────────────────────────────────────────────────────────────────────────────

/** A single exception item from the listing endpoint. */
export interface ExceptionItem {
  id: string;
  case_id: string;
  ledger_entry_id: string | null;
  category: string;
  severity: string;
  amount: number | null;
  first_flagged_date: string | null;
  status: string;
  created_date: string | null;
}

/** Paginated response wrapper for exceptions. */
export interface PaginatedExceptionResponse {
  items: ExceptionItem[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

/** Query parameters for listing/filtering exceptions. */
export interface ExceptionListParams {
  company_code: string;
  case_id?: string;
  severity?: string;
  category?: string;
  status?: string;
  page?: number;
  page_size?: number;
}

/** Request body for resolving a single exception. */
export interface ResolveExceptionRequest {
  action: string;
  comment?: string;
}

/** Response from resolving an exception. */
export interface ResolutionResponse {
  exception_id: string;
  action: string;
  status: string;
  resolved_by: string;
  resolved_date: string;
  comments: string | null;
}

/** Request body for bulk resolving exceptions. */
export interface BulkResolveRequest {
  exception_ids: string[];
  action: string;
  comment?: string;
}

/** Response from bulk resolving exceptions. */
export interface BulkResolveResponse {
  total: number;
  resolved: number;
  failed: number;
  results: ResolutionResponse[];
  errors: string[];
}

// ─────────────────────────────────────────────────────────────────────────────
// API Functions
// ─────────────────────────────────────────────────────────────────────────────

/**
 * List exceptions with filtering and pagination.
 * GET /api/v1/vlr/exceptions
 */
export async function listExceptions(params: ExceptionListParams): Promise<PaginatedExceptionResponse> {
  const response = await apiClient.get<PaginatedExceptionResponse>(BASE, { params });
  return response.data;
}

/**
 * Resolve a single exception.
 * POST /api/v1/vlr/exceptions/{id}/resolve
 */
export async function resolveException(
  exceptionId: string,
  data: ResolveExceptionRequest,
  companyCode: string
): Promise<ResolutionResponse> {
  const response = await apiClient.post<ResolutionResponse>(
    `${BASE}/${exceptionId}/resolve`,
    data,
    { params: { company_code: companyCode } }
  );
  return response.data;
}

/**
 * Bulk resolve multiple exceptions.
 * POST /api/v1/vlr/exceptions/bulk-resolve
 */
export async function bulkResolveExceptions(
  data: BulkResolveRequest,
  companyCode: string
): Promise<BulkResolveResponse> {
  const response = await apiClient.post<BulkResolveResponse>(
    `${BASE}/bulk-resolve`,
    data,
    { params: { company_code: companyCode } }
  );
  return response.data;
}
