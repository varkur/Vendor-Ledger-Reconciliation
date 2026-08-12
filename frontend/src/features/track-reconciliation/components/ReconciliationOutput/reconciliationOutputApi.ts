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

/**
 * Full ledger-entry column set (mirrors the Excel export). Returned by the
 * backend under `columns` (unmatched) or `company_columns`/`party_columns`
 * (matched). Keys are snake_case as sent by the API.
 */
export interface EntryColumns {
  statement_type: string;
  invoice_date: string;
  invoice_number: string;
  doctype: string;
  original_doctype: string;
  narration: string;
  amount: number;
  daybook_name: string;
  clearing_document_number: string;
  clearing_date: string;
  tds_amount: string;
  posting_date: string;
  company_code: string;
  supplier: string;
  document_number: string;
  business_area: string;
  assignment: string;
  document_header_text: string;
  tax_code: string;
  year_month: string;
  reference: string;
  profit_center: string;
  amount_in_doc_curr: number;
  document_currency: string;
  local_currency: string;
  entry_date: string;
  withhldg_tax_base_amount: string;
  payment_date: string;
}

/** Ordered column definitions for rendering the full ledger tables. */
export const LEDGER_COLUMN_DEFS: { field: keyof EntryColumns; header: string }[] = [
  { field: 'statement_type', header: 'Statement Type' },
  { field: 'invoice_date', header: 'Invoice Date' },
  { field: 'invoice_number', header: 'Invoice Number' },
  { field: 'doctype', header: 'DocType' },
  { field: 'original_doctype', header: 'Original DocType' },
  { field: 'narration', header: 'Narration' },
  { field: 'amount', header: 'Amount' },
  { field: 'daybook_name', header: 'Daybook Name' },
  { field: 'clearing_document_number', header: 'Clearing Document Number' },
  { field: 'clearing_date', header: 'Clearing Date' },
  { field: 'tds_amount', header: 'TDS Amount' },
  { field: 'posting_date', header: 'Posting Date' },
  { field: 'company_code', header: 'Company Code' },
  { field: 'supplier', header: 'Supplier' },
  { field: 'document_number', header: 'Document Number' },
  { field: 'business_area', header: 'Business Area' },
  { field: 'assignment', header: 'Assignment' },
  { field: 'document_header_text', header: 'Document Header Text' },
  { field: 'tax_code', header: 'Tax Code' },
  { field: 'year_month', header: 'Year/Month' },
  { field: 'reference', header: 'Reference' },
  { field: 'profit_center', header: 'Profit Center' },
  { field: 'amount_in_doc_curr', header: 'Amount in Doc. Curr.' },
  { field: 'document_currency', header: 'Document Currency' },
  { field: 'local_currency', header: 'Local Currency' },
  { field: 'entry_date', header: 'Entry Date' },
  { field: 'withhldg_tax_base_amount', header: 'Withhldg Tax Base Amount' },
  { field: 'payment_date', header: 'Payment Date' },
];

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
  /** Filter to manual links (pass 8) with this exact status_reason. */
  status_reason?: string;
  /** Filter to all manual links (pass 8), regardless of status_reason. */
  manual_only?: boolean;
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
  matched_rule?: string;
  status_reason?: string;
  company_columns?: EntryColumns;
  party_columns?: EntryColumns;
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
  columns?: EntryColumns;
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
  columns?: EntryColumns;
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
  unmatched_company_amount?: number;
  unmatched_vendor_amount?: number;
  residual_difference?: number;
  total_unmatched_company?: number;
  total_unmatched_vendor?: number;
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

/** Normalize backend pagination { pagination: {...} } into flat fields. */
function normalizePagination<T>(raw: any, items: T[]): PaginatedResponse<T> {
  const p = raw?.pagination ?? {};
  return {
    items,
    total: p.total_items ?? raw?.total ?? items.length,
    page: p.page ?? raw?.page ?? 1,
    page_size: p.page_size ?? raw?.page_size ?? items.length,
    total_pages: p.total_pages ?? raw?.total_pages ?? 1,
  };
}

/**
 * Get matched items for a reconciliation case (Tab 1).
 */
export async function getMatchedItems(
  caseId: string,
  params?: ListParams
): Promise<PaginatedResponse<MatchedItem>> {
  const { status_reason, manual_only, ...rest } = params ?? {};
  const response = await apiClient.get<any>(`${BASE}/${caseId}/matched`, {
    params: {
      ...rest,
      status_reason_filter: status_reason || undefined,
      manual_only: manual_only || undefined,
    },
  });
  const items: MatchedItem[] = (response.data.items ?? []).map((it: any) => ({
    id: it.match_id ?? it.id,
    company_reference: it.cl_reference ?? '',
    vendor_reference: it.vl_reference ?? '',
    company_amount: Number(it.cl_amount ?? 0),
    vendor_amount: Number(it.vl_amount ?? 0),
    match_type: it.match_type,
    confidence_score: it.match_score ?? it.confidence_score ?? 0,
    posting_date: it.posting_date ?? '',
    document_type: it.document_type ?? '',
    currency: it.currency ?? 'INR',
    matched_rule: it.matched_rule ?? '',
    status_reason: it.status_reason ?? '',
    company_columns: it.company_columns ?? undefined,
    party_columns: it.party_columns ?? undefined,
  }));
  return normalizePagination(response.data, items);
}

/**
 * Get items requiring finance confirmation (Tab 2).
 */
export async function getConfirmationItems(
  caseId: string,
  params?: ListParams
): Promise<PaginatedResponse<ConfirmationItem>> {
  const response = await apiClient.get<any>(`${BASE}/${caseId}/confirmation`, { params });
  const items: ConfirmationItem[] = (response.data.items ?? []).map((it: any) => ({
    id: it.match_id ?? it.id,
    company_reference: it.cl_reference ?? '',
    vendor_reference: it.vl_reference ?? '',
    company_amount: Number(it.cl_amount ?? 0),
    vendor_amount: Number(it.vl_amount ?? 0),
    match_type: it.match_type,
    confidence_score: it.match_score ?? it.confidence_score ?? 0,
    posting_date: it.posting_date ?? '',
    document_type: it.document_type ?? '',
    difference: Number(it.difference ?? 0),
    reason: it.reason ?? '',
  }));
  return normalizePagination(response.data, items);
}

/**
 * Get unmatched company ledger entries (Tab 3).
 */
export async function getUnmatchedCompany(
  caseId: string,
  params?: ListParams
): Promise<PaginatedResponse<UnmatchedCompanyItem>> {
  const response = await apiClient.get<any>(`${BASE}/${caseId}/unmatched-company`, { params });
  const items: UnmatchedCompanyItem[] = (response.data.items ?? []).map((it: any) => ({
    id: it.entry_id ?? it.id,
    document_number: it.document_number ?? '',
    reference: it.reference_number ?? it.document_number ?? '',
    amount: Number(it.amount ?? 0),
    posting_date: it.posting_date ?? '',
    document_type: it.document_category ?? it.document_type ?? '',
    currency: it.currency ?? 'INR',
    description: it.description ?? '',
    columns: it.columns ?? undefined,
  })) as any;
  return normalizePagination(response.data, items);
}

/**
 * Get unmatched vendor ledger entries (Tab 4).
 */
export async function getUnmatchedVendor(
  caseId: string,
  params?: ListParams
): Promise<PaginatedResponse<UnmatchedVendorItem>> {
  const response = await apiClient.get<any>(`${BASE}/${caseId}/unmatched-vendor`, { params });
  const items: UnmatchedVendorItem[] = (response.data.items ?? []).map((it: any) => ({
    id: it.entry_id ?? it.id,
    document_number: it.document_number ?? '',
    reference: it.reference_number ?? it.document_number ?? '',
    amount: Number(it.amount ?? 0),
    posting_date: it.posting_date ?? '',
    document_type: it.document_category ?? it.document_type ?? '',
    currency: it.currency ?? 'INR',
    description: it.description ?? '',
    columns: it.columns ?? undefined,
  })) as any;
  return normalizePagination(response.data, items);
}

/**
 * Get differences summary for a reconciliation case (Tab 5).
 * Normalizes the backend response shape to what the UI expects.
 */
export async function getDifferencesSummary(
  caseId: string
): Promise<DifferencesSummary> {
  const response = await apiClient.get<any>(`${BASE}/${caseId}/summary`);
  const d = response.data ?? {};
  const ob = d.opening_balance ?? {};
  const cb = d.closing_balance ?? {};

  return {
    balance_comparison: {
      company_opening_balance: Number(ob.company_balance ?? 0),
      vendor_opening_balance: Number(ob.vendor_balance ?? 0),
      opening_difference: Number(ob.difference ?? 0),
      company_closing_balance: Number(cb.company_balance ?? 0),
      vendor_closing_balance: Number(cb.vendor_balance ?? 0),
      closing_difference: Number(cb.difference ?? 0),
    },
    type_totals: (d.totals_by_type ?? []).map((t: any) => ({
      transaction_type: t.type_name ?? t.transaction_type ?? '',
      company_total: Number(t.company_total ?? 0),
      vendor_total: Number(t.vendor_total ?? 0),
      difference: Number(t.difference ?? 0),
    })),
    net_difference: Number(d.net_difference ?? 0),
    currency: d.currency ?? 'INR',
    total_matched: d.total_matched ?? 0,
    total_unmatched_company: d.total_unmatched_company ?? 0,
    total_unmatched_vendor: d.total_unmatched_vendor ?? 0,
    total_pending_confirmation: d.total_pending_confirmation ?? 0,
    unmatched_company_amount: Number(d.unmatched_company_amount ?? 0),
    unmatched_vendor_amount: Number(d.unmatched_vendor_amount ?? 0),
    residual_difference: Number(d.residual_difference ?? 0),
  } as DifferencesSummary;
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


// ─────────────────────────────────────────────────────────────────────────────
// Manual Link / Unlink
// ─────────────────────────────────────────────────────────────────────────────

export interface ManualLinkResponse {
  match_id: string;
  company_amount: number;
  vendor_amount: number;
  difference: number;
  status_reason: string;
  message: string;
}

export interface StatusReasonsResponse {
  reasons: string[];
}

/**
 * Fetch the fixed list of reasons a reviewer must choose from when manually
 * linking two unmatched entries (see docs/Update Status.xlsx). Not
 * case-scoped — the list is the same across all cases.
 */
export async function getStatusReasons(): Promise<string[]> {
  const { data } = await apiClient.get<StatusReasonsResponse>(
    `${BASE}/status-reasons`
  );
  return data.reasons;
}

/**
 * Manually link selected unmatched company + vendor entries.
 * statusReason is MANDATORY — the reviewer must select why these entries
 * are being linked (from getStatusReasons()).
 */
export async function manualLink(
  caseId: string,
  companyEntryIds: string[],
  vendorEntryIds: string[],
  statusReason: string,
  notes?: string
): Promise<ManualLinkResponse> {
  const { data } = await apiClient.post<ManualLinkResponse>(
    `${BASE}/${caseId}/link`,
    {
      company_entry_ids: companyEntryIds,
      vendor_entry_ids: vendorEntryIds,
      status_reason: statusReason,
      notes,
    }
  );
  return data;
}

/** Unlink a match, returning its entries to the unmatched pool. */
export async function manualUnlink(caseId: string, matchId: string): Promise<{ success: boolean; message: string }> {
  const { data } = await apiClient.post<{ success: boolean; message: string }>(
    `${BASE}/${caseId}/unlink`,
    { match_id: matchId }
  );
  return data;
}
