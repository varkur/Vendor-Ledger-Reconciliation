/**
 * Action Tracker API functions.
 * Communicates with backend GET/PATCH /api/v1/vlr/action-tracker endpoints.
 */

import { apiClient } from '@shared/services/apiClient';

const BASE = '/vlr/action-tracker';

// ─────────────────────────────────────────────────────────────────────────────
// Types
// ─────────────────────────────────────────────────────────────────────────────

export const ACTION_TAKEN_STATUSES = [
  'Pending with Party',
  'Pending with Company',
  'No Action Required',
] as const;

export type ActionTakenStatus = (typeof ACTION_TAKEN_STATUSES)[number];

/** One row of the Action Tracker Summary screen. */
export interface ActionTrackerSummaryRow {
  action_taken_status: string;
  number_of_records: number;
  percentage: number;
  amount: number;
}

/** Full Action Tracker summary response. */
export interface ActionTrackerSummaryResponse {
  request_id: string;
  rows: ActionTrackerSummaryRow[];
  total_records: number;
  total_amount: number;
}

/** One detail row of the Action Tracker grid. */
export interface ActionTrackerItem {
  row_key: string;
  case_id: string;
  vendor_code: string;
  vendor_name: string;
  company_id?: string;
  party_id?: string;
  match_id?: string;
  status: string;
  classification: string;
  action_taken_status: string;
  action_owner: string;
  company_invoice_date?: string;
  company_invoice_number?: string;
  company_doctype?: string;
  company_original_doctype?: string;
  company_narration?: string;
  company_amount?: string;
  party_invoice_date?: string;
  party_invoice_number?: string;
  party_doctype?: string;
  party_original_doctype?: string;
  party_narration?: string;
  party_amount?: string;
  difference: number;
  remarks?: string;
  request_closed: boolean;
  action_taken_reference?: string;
  action_taken_remark?: string;
  reco_datetime?: string;
  posting_date?: string;
  clearing_date?: string;
  clearing_document_number?: string;
  tds_amount?: string;
}

/** Paginated Action Tracker detail list. */
export interface ActionTrackerItemListResponse {
  items: ActionTrackerItem[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

/** Parameters for fetching Action Tracker detail items. */
export interface ActionTrackerItemsParams {
  company_code: string;
  action_taken_status?: string;
  status?: string;
  action_owner?: string;
  search?: string;
  page?: number;
  page_size?: number;
}

/** One row payload for updating workflow fields. */
export interface UpdateActionTakenItem {
  case_id: string;
  row_key: string;
  action_owner?: string | null;
  action_taken_reference?: string | null;
  action_taken_remark?: string | null;
  request_closed?: boolean | null;
}

export interface BulkUpdateActionTakenResponse {
  updated: number;
}

// ─────────────────────────────────────────────────────────────────────────────
// API Functions
// ─────────────────────────────────────────────────────────────────────────────

/** GET /api/v1/vlr/action-tracker/requests/{request_id}/summary */
export async function getActionTrackerSummary(
  requestId: string,
  companyCode: string
): Promise<ActionTrackerSummaryResponse> {
  const response = await apiClient.get<ActionTrackerSummaryResponse>(
    `${BASE}/requests/${requestId}/summary`,
    { params: { company_code: companyCode } }
  );
  return response.data;
}

/** GET /api/v1/vlr/action-tracker/requests/{request_id}/items */
export async function getActionTrackerItems(
  requestId: string,
  params: ActionTrackerItemsParams
): Promise<ActionTrackerItemListResponse> {
  const response = await apiClient.get<ActionTrackerItemListResponse>(
    `${BASE}/requests/${requestId}/items`,
    { params }
  );
  return response.data;
}

/** GET /api/v1/vlr/action-tracker/requests/{request_id}/export (blob download) */
export async function exportActionTracker(requestId: string, companyCode: string) {
  return apiClient.get(`${BASE}/requests/${requestId}/export`, {
    params: { company_code: companyCode },
    responseType: 'blob',
  });
}

/** PATCH /api/v1/vlr/action-tracker/items?request_id=... */
export async function updateActionTakenItem(
  requestId: string,
  item: UpdateActionTakenItem
): Promise<BulkUpdateActionTakenResponse> {
  const response = await apiClient.patch<BulkUpdateActionTakenResponse>(
    `${BASE}/items`,
    item,
    { params: { request_id: requestId } }
  );
  return response.data;
}

/** POST /api/v1/vlr/action-tracker/items/bulk-update?request_id=... */
export async function bulkUpdateActionTakenItems(
  requestId: string,
  items: UpdateActionTakenItem[]
): Promise<BulkUpdateActionTakenResponse> {
  const response = await apiClient.post<BulkUpdateActionTakenResponse>(
    `${BASE}/items/bulk-update`,
    { items },
    { params: { request_id: requestId } }
  );
  return response.data;
}
