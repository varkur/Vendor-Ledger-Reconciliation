/**
 * React Query hooks for Reports & MIS page.
 * Provides data fetching with loading/error/retry patterns for:
 * - Reconciliation summary report
 * - Exception report
 * - Vendor status report
 * - Monthly MIS report
 * - Report generation and download
 *
 * Requirements: 23.6, 25.1, 25.2
 */

import { useMutation, useQuery, keepPreviousData } from '@tanstack/react-query';

import {
  getReconciliationSummary,
  getExceptionReport,
  getVendorStatusReport,
  getMonthlyMISReport,
  generateReport,
  downloadReport,
  type ReportParams,
  type ReportType,
  type ExportFormat,
  type PaginatedReportResponse,
  type RecoStatementRow,
  type ExceptionReportRow,
  type VendorStatusRow,
  type MonthlyMISRow,
  type GenerateReportResponse,
} from '../api/reportsApi';

/** Query key prefix for reports. */
export const REPORTS_QUERY_KEY = 'vlr-reports';

/**
 * Hook to fetch reconciliation summary report.
 */
export function useReconciliationSummary(params: ReportParams, enabled = true) {
  return useQuery<PaginatedReportResponse<RecoStatementRow>, Error>({
    queryKey: [REPORTS_QUERY_KEY, 'reconciliation-summary', params],
    queryFn: () => getReconciliationSummary(params),
    enabled,
    placeholderData: keepPreviousData,
    retry: 2,
    retryDelay: (attempt) => Math.min(1000 * 2 ** attempt, 10000),
  });
}

/**
 * Hook to fetch exception report.
 */
export function useExceptionReport(params: ReportParams, enabled = true) {
  return useQuery<PaginatedReportResponse<ExceptionReportRow>, Error>({
    queryKey: [REPORTS_QUERY_KEY, 'exceptions', params],
    queryFn: () => getExceptionReport(params),
    enabled,
    placeholderData: keepPreviousData,
    retry: 2,
    retryDelay: (attempt) => Math.min(1000 * 2 ** attempt, 10000),
  });
}

/**
 * Hook to fetch vendor status report.
 */
export function useVendorStatusReport(params: ReportParams, enabled = true) {
  return useQuery<PaginatedReportResponse<VendorStatusRow>, Error>({
    queryKey: [REPORTS_QUERY_KEY, 'vendor-status', params],
    queryFn: () => getVendorStatusReport(params),
    enabled,
    placeholderData: keepPreviousData,
    retry: 2,
    retryDelay: (attempt) => Math.min(1000 * 2 ** attempt, 10000),
  });
}

/**
 * Hook to fetch monthly MIS report.
 */
export function useMonthlyMISReport(params: ReportParams, enabled = true) {
  return useQuery<PaginatedReportResponse<MonthlyMISRow>, Error>({
    queryKey: [REPORTS_QUERY_KEY, 'mis', params],
    queryFn: () => getMonthlyMISReport(params),
    enabled,
    placeholderData: keepPreviousData,
    retry: 2,
    retryDelay: (attempt) => Math.min(1000 * 2 ** attempt, 10000),
  });
}

/**
 * Mutation hook to generate a report for export (PDF/Excel).
 */
export function useGenerateReport() {
  return useMutation<
    GenerateReportResponse,
    Error,
    { reportType: ReportType; format: ExportFormat; params?: ReportParams }
  >({
    mutationFn: ({ reportType, format, params }) => generateReport(reportType, format, params),
  });
}

/**
 * Mutation hook to download an exported report by ID.
 * Returns a Blob that the caller can save as a file.
 */
export function useDownloadReport() {
  return useMutation<Blob, Error, string>({
    mutationFn: (reportId: string) => downloadReport(reportId),
  });
}
