/**
 * Request Statement API functions.
 * Communicates with backend VLR request endpoints via Axios.
 *
 * The Request Statement page creates reconciliation requests (same endpoint as Direct Reconciliation)
 * but focuses on the vendor statement request workflow — selecting vendors and configuring
 * reconciliation parameters for sending statement requests.
 *
 * Requirements: 11, 23.3, 25.1, 25.2
 */

import { apiClient } from '@shared/services/apiClient';
import { AxiosProgressEvent } from 'axios';

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
 * Extracts backend error messages for user-friendly display.
 */
export async function createStatementRequest(
  data: CreateStatementRequest
): Promise<StatementRequestResponse> {
  try {
    const response = await apiClient.post<StatementRequestResponse>(REQUESTS_BASE, data);
    return response.data;
  } catch (error: any) {
    // Extract the backend detail message for user-friendly errors
    const detail = error.response?.data?.detail;
    if (detail) {
      throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail));
    }
    throw new Error(error.message || 'Failed to create statement request. Please try again.');
  }
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

// ─────────────────────────────────────────────────────────────────────────────
// Company Ledger Upload
// ─────────────────────────────────────────────────────────────────────────────

/** Response from POST /reconciliation-requests/{request_id}/upload-company-ledger */
export interface UploadCompanyLedgerResponse {
  id: string;
  request_id: string;
  file_name: string;
  file_size: number;
  status: string;
  entries_parsed?: number;
  message: string;
}

/**
 * Upload a company ledger file for a reconciliation request.
 * Supports progress tracking via onProgress callback.
 */
export async function uploadCompanyLedger(
  requestId: string,
  file: File,
  companyCode: string,
  onProgress?: (progress: number) => void
): Promise<UploadCompanyLedgerResponse> {
  const formData = new FormData();
  formData.append('file', file);

  const response = await apiClient.post<UploadCompanyLedgerResponse>(
    `/vlr/reconciliation-requests/${requestId}/upload-company-ledger`,
    formData,
    {
      params: { company_code: companyCode },
      headers: {
        'Content-Type': 'multipart/form-data',
      },
      timeout: 120000, // 2 minutes for large file uploads
      onUploadProgress: (event: AxiosProgressEvent) => {
        if (onProgress && event.total) {
          const percent = Math.round((event.loaded * 100) / event.total);
          onProgress(percent);
        }
      },
    }
  );
  return response.data;
}
