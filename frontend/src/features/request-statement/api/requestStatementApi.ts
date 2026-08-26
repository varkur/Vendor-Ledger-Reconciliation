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
  title?: string;
  period_start: string; // ISO date string (YYYY-MM-DD)
  period_end: string; // ISO date string (YYYY-MM-DD)
  vendor_ids: string[];
  tolerance_amount?: number;
  tds_percentage?: number;
  tds_percentage_min?: number;
  gst_percentage?: number;
  date_tolerance_days_min?: number;
  date_tolerance_days_max?: number;
  matching_preferences?: MatchingPreferences;
  assigned_manager_id?: string;
  email_template_id?: string;
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
  tds_percentage_min: number | null;
  gst_percentage: number | null;
  date_tolerance_days_min: number | null;
  date_tolerance_days_max: number | null;
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
  /** True when this was a multi-vendor request and the consolidated ledger was split by PAN/vendor code. */
  split_by_vendor?: boolean;
  /** Header of the column used to identify the vendor per row (e.g. "pan"). */
  identifier_column?: string | null;
  /** Number of vendors (cases) that received at least one entry from this upload. */
  matched_vendor_count?: number;
  /** Number of rows whose PAN/vendor code didn't match any vendor on this request. */
  unmatched_entry_count?: number;
  /** Sample of unmatched PAN/vendor code values, for surfacing to the user. */
  unmatched_identifiers?: string[];
  /** Number of vendor invite emails auto-sent (only when auto_notify_vendors=true was passed). */
  invites_sent?: number;
}

// ─────────────────────────────────────────────────────────────────────────────
// Consolidated Multi-Vendor Ledger Upload (auto-detect vendors from PAN)
// ─────────────────────────────────────────────────────────────────────────────

/** Config sent alongside the file for preview — everything CreateStatementRequest
 * needs except vendor_ids, since those are derived from the file. */
export interface LedgerUploadRequestConfig {
  company_code: string;
  fiscal_year: string;
  title?: string;
  period_start: string;
  period_end: string;
  tolerance_amount?: number;
  tds_percentage?: number;
  gst_percentage?: number;
  matching_preferences?: MatchingPreferences;
  assigned_manager_id?: string;
}

export interface MatchedVendorInfo {
  vendor_id: string;
  vendor_code: string;
  vendor_name: string;
  identifier_value: string;
  entry_count: number;
  is_active: boolean;
}

export interface MissingVendorInfo {
  identifier_value: string;
  entry_count: number;
}

export interface PreviewLedgerUploadResponse {
  staging_id: string;
  filename: string;
  identifier_column: string | null;
  total_entries: number;
  matched_vendors: MatchedVendorInfo[];
  missing_vendors: MissingVendorInfo[];
  blank_identifier_entry_count: number;
  expires_at: string;
}

export interface ConfirmLedgerUploadResponse {
  request_id: string;
  request_number: string | null;
  matched_vendor_count: number;
  entries_stored: number;
  skipped_missing_vendor_count: number;
  invites_sent: number;
}

/**
 * Upload a consolidated ledger for PREVIEW ONLY. Parses the file and matches
 * PAN/vendor-code values against the vendor master — no request or cases are
 * created yet. Follow up with confirmLedgerUpload() or discardLedgerUpload().
 */
export async function previewLedgerUpload(
  file: File,
  config: LedgerUploadRequestConfig
): Promise<PreviewLedgerUploadResponse> {
  const formData = new FormData();
  formData.append('file', file);
  formData.append('config', JSON.stringify(config));

  const response = await apiClient.post<PreviewLedgerUploadResponse>(
    '/vlr/reconciliation-requests/preview-ledger-upload',
    formData,
    {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 120000,
    }
  );
  return response.data;
}

/**
 * Confirm a staged consolidated upload — creates the request + one case per
 * matched vendor. If the preview reported missing vendors, `proceedWithMissing`
 * must be true or this call is rejected with 409.
 */
export async function confirmLedgerUpload(
  stagingId: string,
  proceedWithMissing: boolean,
  autoNotifyVendors = false
): Promise<ConfirmLedgerUploadResponse> {
  const response = await apiClient.post<ConfirmLedgerUploadResponse>(
    '/vlr/reconciliation-requests/confirm-ledger-upload',
    {
      staging_id: stagingId,
      proceed_with_missing: proceedWithMissing,
      auto_notify_vendors: autoNotifyVendors,
    }
  );
  return response.data;
}

/**
 * Discard a staged consolidated upload without creating anything — used when
 * the user chooses to fix the vendor master before proceeding.
 */
export async function discardLedgerUpload(stagingId: string): Promise<void> {
  await apiClient.delete(`/vlr/reconciliation-requests/discard-ledger-upload/${stagingId}`);
}

/**
 * Upload a company ledger file for a reconciliation request.
 * Supports progress tracking via onProgress callback.
 */
export async function uploadCompanyLedger(
  requestId: string,
  file: File,
  companyCode: string,
  onProgress?: (progress: number) => void,
  autoNotifyVendors?: boolean
): Promise<UploadCompanyLedgerResponse> {
  const formData = new FormData();
  formData.append('file', file);

  const response = await apiClient.post<UploadCompanyLedgerResponse>(
    `/vlr/reconciliation-requests/${requestId}/upload-company-ledger`,
    formData,
    {
      params: {
        company_code: companyCode,
        ...(autoNotifyVendors ? { auto_notify_vendors: true } : {}),
      },
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
