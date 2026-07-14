/**
 * Reports API functions.
 * Communicates with backend VLR report generation and download endpoints via Axios.
 *
 * Requirements: 23.6, 25.1, 25.2
 */

import { apiClient } from '@shared/services/apiClient';

const BASE = '/vlr/reports';

// ─────────────────────────────────────────────────────────────────────────────
// Types
// ─────────────────────────────────────────────────────────────────────────────

/** Report type identifiers. */
export type ReportType =
  | 'reconciliation-summary'
  | 'aging-analysis'
  | 'exceptions'
  | 'vendor-status'
  | 'mis';

/** Export format for reports. */
export type ExportFormat = 'pdf' | 'excel';

/** Reconciliation statement row. */
export interface RecoStatementRow {
  id: string;
  vendor_name: string;
  opening_balance: number;
  invoices: number;
  payments: number;
  adjustments: number;
  closing_balance: number;
  difference: number;
  status: string;
}

/** Exception report row. */
export interface ExceptionReportRow {
  id: string;
  exception_id: string;
  vendor_name: string;
  category: string;
  amount: number;
  age_days: number;
  status: string;
  assigned_to: string;
}

/** Vendor status row. */
export interface VendorStatusRow {
  id: string;
  vendor_code: string;
  vendor_name: string;
  total_invoices: number;
  matched: number;
  unmatched: number;
  response_rate: string;
  last_reco_date: string;
  status: string;
}

/** Monthly MIS row. */
export interface MonthlyMISRow {
  id: string;
  month: string;
  total_vendors: number;
  reco_completed: number;
  exceptions_raised: number;
  exceptions_resolved: number;
  avg_resolution_days: number;
  match_rate: string;
}

/** Paginated report response. */
export interface PaginatedReportResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

/** Parameters for fetching report data. */
export interface ReportParams {
  company_code?: string;
  page?: number;
  page_size?: number;
  case_id?: string;
  vendor_id?: string;
  date_from?: string;
  date_to?: string;
}

/** Report generation response. */
export interface GenerateReportResponse {
  report_id: string;
  status: string;
  message: string;
}

// ─────────────────────────────────────────────────────────────────────────────
// API Functions
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Get reconciliation summary report data.
 * GET /api/v1/vlr/reports/reconciliation-summary
 */
export async function getReconciliationSummary(
  params: ReportParams
): Promise<PaginatedReportResponse<RecoStatementRow>> {
  const response = await apiClient.get<PaginatedReportResponse<RecoStatementRow>>(
    `${BASE}/reconciliation-summary`,
    { params }
  );
  return response.data;
}

/**
 * Get exception report data.
 * GET /api/v1/vlr/reports/exceptions
 */
export async function getExceptionReport(
  params: ReportParams
): Promise<PaginatedReportResponse<ExceptionReportRow>> {
  const response = await apiClient.get<PaginatedReportResponse<ExceptionReportRow>>(
    `${BASE}/exceptions`,
    { params }
  );
  return response.data;
}

/**
 * Get vendor status report data.
 * GET /api/v1/vlr/reports/vendor-status
 */
export async function getVendorStatusReport(
  params: ReportParams
): Promise<PaginatedReportResponse<VendorStatusRow>> {
  const response = await apiClient.get<PaginatedReportResponse<VendorStatusRow>>(
    `${BASE}/vendor-status`,
    { params }
  );
  return response.data;
}

/**
 * Get monthly MIS report data.
 * GET /api/v1/vlr/reports/mis
 */
export async function getMonthlyMISReport(
  params: ReportParams
): Promise<PaginatedReportResponse<MonthlyMISRow>> {
  const response = await apiClient.get<PaginatedReportResponse<MonthlyMISRow>>(
    `${BASE}/mis`,
    { params }
  );
  return response.data;
}

/**
 * Generate a report for export.
 * POST /api/v1/vlr/reports/generate
 */
export async function generateReport(
  reportType: ReportType,
  format: ExportFormat,
  params?: ReportParams
): Promise<GenerateReportResponse> {
  const response = await apiClient.post<GenerateReportResponse>(`${BASE}/generate`, {
    report_type: reportType,
    format,
    ...params,
  });
  return response.data;
}

/**
 * Download an exported report by report ID.
 * GET /api/v1/vlr/reports/export/{report_id}
 * Returns a Blob for file download.
 */
export async function downloadReport(reportId: string): Promise<Blob> {
  const response = await apiClient.get(`${BASE}/export/${reportId}`, {
    responseType: 'blob',
  });
  return response.data;
}
