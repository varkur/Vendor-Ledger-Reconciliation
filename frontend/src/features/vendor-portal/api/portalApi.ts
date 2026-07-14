/**
 * Vendor Portal API functions.
 * Communicates with backend portal endpoints via Axios.
 *
 * The Vendor Portal does NOT use the standard Bearer token auth (apiClient).
 * Instead it uses a portal-specific token passed via X-Portal-Token header.
 * We create a separate axios instance for portal calls.
 *
 * Requirements: 24.1, 24.2, 24.3, 24.4
 */

import axios, { AxiosProgressEvent } from 'axios';

const API_BASE_URL = '/api/v1';

/**
 * Axios instance for vendor portal — no Bearer token, uses X-Portal-Token header.
 */
const portalClient = axios.create({
  baseURL: `${API_BASE_URL}/vlr/portal`,
  timeout: 60000,
  headers: {
    Accept: 'application/json',
  },
});

// ─────────────────────────────────────────────────────────────────────────────
// Types
// ─────────────────────────────────────────────────────────────────────────────

/** Request body for POST /validate-token */
export interface ValidateTokenRequest {
  token: string;
}

/** Response from POST /validate-token */
export interface ValidateTokenResponse {
  case_id: string;
  vendor_name: string;
  period_start: string | null;
  period_end: string | null;
  status: string;
  upload_count: number;
  max_uploads: number;
  token_valid_until: string | null;
}

/** Response from POST /upload */
export interface PortalUploadResponse {
  case_id: string;
  status: string;
  upload_count: number;
  entries_parsed: number;
  message: string;
  task_id: string | null;
}

/** Response from GET /statement/{case_id} */
export interface PortalStatementResultResponse {
  case_id: string;
  status: string;
  vendor_name: string;
  period_start: string | null;
  period_end: string | null;
  total_matched_entries: number;
  total_unmatched_vendor: number;
  vendor_opening_balance: number | null;
  vendor_closing_balance: number | null;
  net_difference: number | null;
  match_summary: MatchSummaryItem[];
  statement_version: string;
}

/** Match summary item in the statement response */
export interface MatchSummaryItem {
  match_type: string;
  count: number;
  total_amount: string;
}

/** Response from GET /reconciliation-status/{case_id} */
export interface PortalReconciliationStatusResponse {
  status: 'processing' | 'completed' | 'error';
  message?: string;
}

/** Request body for POST /sign-off/{case_id} */
export interface PortalSignOffRequest {
  confirmation_text: string;
  statement_version: string;
}

/** Response from POST /sign-off/{case_id} */
export interface PortalCaseSignOffResponse {
  case_id: string;
  signed_at: string;
  ip_address: string;
  confirmation_text: string;
  statement_version: string;
  status: string;
  message: string;
}

/** API error response shape */
export interface PortalApiError {
  detail: string;
  status_code?: number;
}

/** Request body for POST /request-new-link */
export interface RequestNewLinkRequest {
  email: string;
}

/** Response from POST /request-new-link */
export interface RequestNewLinkResponse {
  message: string;
}

/** Request body for POST /dispute/{case_id} */
export interface PortalDisputeRequest {
  reason: string;
  attachment?: File;
}

/** Response from POST /dispute/{case_id} */
export interface PortalDisputeResponse {
  case_id: string;
  status: string;
  message: string;
}

// ─────────────────────────────────────────────────────────────────────────────
// API Functions
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Validate a portal access token. Returns case summary if valid.
 * Returns 410 if expired, 404 if not found.
 */
export async function validateToken(
  data: ValidateTokenRequest
): Promise<ValidateTokenResponse> {
  const response = await portalClient.post<ValidateTokenResponse>(
    '/validate-token',
    data
  );
  return response.data;
}

/**
 * Upload a vendor statement file with progress tracking.
 * Uses X-Portal-Token header for authentication.
 */
export async function uploadStatement(
  file: File,
  portalToken: string,
  onProgress?: (progress: number) => void
): Promise<PortalUploadResponse> {
  const formData = new FormData();
  formData.append('file', file);

  const response = await portalClient.post<PortalUploadResponse>(
    '/upload',
    formData,
    {
      headers: {
        'Content-Type': 'multipart/form-data',
        'X-Portal-Token': portalToken,
      },
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

/**
 * Retrieve vendor-facing reconciliation results for a specific case.
 * Uses X-Portal-Token header for authentication.
 */
export async function getStatement(
  caseId: string,
  portalToken: string
): Promise<PortalStatementResultResponse> {
  const response = await portalClient.get<PortalStatementResultResponse>(
    `/statement/${caseId}`,
    {
      headers: {
        'X-Portal-Token': portalToken,
      },
    }
  );
  return response.data;
}

/**
 * Record vendor sign-off/approval for a specific case.
 * Uses X-Portal-Token header for authentication.
 */
export async function signOffCase(
  caseId: string,
  data: PortalSignOffRequest,
  portalToken: string
): Promise<PortalCaseSignOffResponse> {
  const response = await portalClient.post<PortalCaseSignOffResponse>(
    `/sign-off/${caseId}`,
    data,
    {
      headers: {
        'X-Portal-Token': portalToken,
      },
    }
  );
  return response.data;
}

/**
 * Poll reconciliation processing status for a case.
 * Used after upload to check when reconciliation is complete.
 * Uses X-Portal-Token header for authentication.
 */
export async function getReconciliationStatus(
  caseId: string,
  portalToken: string
): Promise<PortalReconciliationStatusResponse> {
  const response = await portalClient.get<PortalReconciliationStatusResponse>(
    `/reconciliation-status/${caseId}`,
    {
      headers: {
        'X-Portal-Token': portalToken,
      },
    }
  );
  return response.data;
}


/**
 * Request a new portal access link. Does NOT require auth (vendor is unauthenticated).
 * Calls POST /api/v1/vlr/portal/request-new-link with the vendor's email.
 */
export async function requestNewLink(
  data: RequestNewLinkRequest
): Promise<RequestNewLinkResponse> {
  const response = await portalClient.post<RequestNewLinkResponse>(
    '/request-new-link',
    data
  );
  return response.data;
}

/**
 * Raise a dispute on reconciliation results for a specific case.
 * Uses X-Portal-Token header for authentication.
 * Sends multipart/form-data if an attachment is included.
 */
export async function raiseDispute(
  caseId: string,
  data: PortalDisputeRequest,
  portalToken: string
): Promise<PortalDisputeResponse> {
  const formData = new FormData();
  formData.append('reason', data.reason);
  if (data.attachment) {
    formData.append('attachment', data.attachment);
  }

  const response = await portalClient.post<PortalDisputeResponse>(
    `/dispute/${caseId}`,
    formData,
    {
      headers: {
        'Content-Type': 'multipart/form-data',
        'X-Portal-Token': portalToken,
      },
    }
  );
  return response.data;
}
