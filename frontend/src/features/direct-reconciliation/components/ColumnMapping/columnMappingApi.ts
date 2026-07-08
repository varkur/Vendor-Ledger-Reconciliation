/**
 * Column Mapping API functions.
 * Communicates with the backend column-mapping endpoints via Axios.
 *
 * Requirements: 9.1, 9.2, 9.3, 10.1, 10.2, 10.3, 11.1, 11.2, 11.3, 11.4
 */

import { apiClient } from '@shared/services/apiClient';

const BASE = '/vlr/column-mapping';

// ─────────────────────────────────────────────────────────────────────────────
// Types
// ─────────────────────────────────────────────────────────────────────────────

/** Transaction type tags available for column assignment. */
export type TransactionTypeTag =
  | 'INVOICE'
  | 'PAYMENT'
  | 'TDS'
  | 'CREDIT_NOTE'
  | 'DEBIT_NOTE'
  | 'OPENING_BALANCE'
  | 'CLOSING_BALANCE'
  | 'DATE'
  | 'REFERENCE'
  | 'AMOUNT'
  | 'DESCRIPTION'
  | 'IGNORE';

export const TRANSACTION_TYPE_TAGS: TransactionTypeTag[] = [
  'INVOICE',
  'PAYMENT',
  'TDS',
  'CREDIT_NOTE',
  'DEBIT_NOTE',
  'OPENING_BALANCE',
  'CLOSING_BALANCE',
  'DATE',
  'REFERENCE',
  'AMOUNT',
  'DESCRIPTION',
  'IGNORE',
];

/** Confidence level for auto-mapping suggestions. */
export type ConfidenceLevel = 'High' | 'Medium' | 'Low';

/** Response from POST /preview — file upload with first 10 rows. */
export interface FilePreviewResponse {
  headers: string[];
  rows: string[][];
  total_row_count: number;
  filename: string;
}

/** A single auto-mapping suggestion. */
export interface ColumnSuggestion {
  column_index: number;
  header: string;
  suggested_tag: TransactionTypeTag | null;
  confidence: ConfidenceLevel | null;
  should_preselect: boolean;
}

/** Response from POST /auto-map. */
export interface AutoMapResponse {
  suggestions: ColumnSuggestion[];
}

/** A single column-to-tag mapping entry. */
export interface ColumnMappingEntry {
  column_index: number;
  header: string;
  tag: string;
}

/** Request body for POST /save-template. */
export interface SaveTemplateRequest {
  vendor_id: string;
  mappings: ColumnMappingEntry[];
}

/** Response from POST /save-template. */
export interface SaveTemplateResponse {
  vendor_id: string;
  message: string;
}

/** Response from GET /template/{vendor_id}. */
export interface TemplateResponse {
  vendor_id: string;
  mappings: ColumnMappingEntry[];
}

// ─────────────────────────────────────────────────────────────────────────────
// API Functions
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Upload a vendor statement file and receive a 10-row preview.
 */
export async function previewFile(file: File): Promise<FilePreviewResponse> {
  const formData = new FormData();
  formData.append('file', file);

  const response = await apiClient.post<FilePreviewResponse>(
    `${BASE}/preview`,
    formData,
    {
      headers: { 'Content-Type': 'multipart/form-data' },
    }
  );
  return response.data;
}

/**
 * Get auto-mapping suggestions for a set of column headers.
 */
export async function autoMapColumns(headers: string[]): Promise<AutoMapResponse> {
  const response = await apiClient.post<AutoMapResponse>(`${BASE}/auto-map`, {
    headers,
  });
  return response.data;
}

/**
 * Save a column mapping template for a vendor.
 */
export async function saveTemplate(
  request: SaveTemplateRequest
): Promise<SaveTemplateResponse> {
  const response = await apiClient.post<SaveTemplateResponse>(
    `${BASE}/save-template`,
    request
  );
  return response.data;
}

/**
 * Retrieve a saved column mapping template for a vendor.
 */
export async function getTemplate(vendorId: string): Promise<TemplateResponse> {
  const response = await apiClient.get<TemplateResponse>(
    `${BASE}/template/${vendorId}`
  );
  return response.data;
}
