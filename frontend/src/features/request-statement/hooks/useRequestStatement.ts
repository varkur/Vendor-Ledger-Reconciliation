/**
 * React Query hooks for Request Statement page.
 *
 * Provides data fetching with loading/error/retry patterns for:
 * - Creating statement requests (mutation)
 * - Fetching vendor list for selection (query)
 * - Uploading company ledger with progress tracking (mutation)
 *
 * Requirements: 11, 23.3, 25.1, 25.2
 */

import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { AxiosError } from 'axios';

import {
  createStatementRequest,
  fetchVendorsForSelection,
  uploadCompanyLedger,
  type CreateStatementRequest,
  type StatementRequestResponse,
  type UploadCompanyLedgerResponse,
  type VendorListResponse,
} from '../api/requestStatementApi';

/** Query key prefix for request statement operations. */
export const REQUEST_STATEMENT_QUERY_KEY = 'vlr-request-statement';
export const VENDOR_SELECTION_QUERY_KEY = 'vlr-vendor-selection';

/**
 * Query hook to fetch vendors for the vendor selection multi-select.
 * Returns active vendors with search support.
 * Implements retry (2 attempts) with exponential backoff per design spec.
 */
export function useVendorSelection(
  companyCode: string,
  search?: string,
  page = 1,
  pageSize = 200
) {
  return useQuery<VendorListResponse, Error>({
    queryKey: [VENDOR_SELECTION_QUERY_KEY, companyCode, search, page, pageSize],
    queryFn: () => fetchVendorsForSelection(companyCode, search, page, pageSize),
    enabled: !!companyCode,
    retry: 2,
    retryDelay: (attempt) => Math.min(1000 * 2 ** attempt, 10000),
  });
}

/**
 * Mutation hook to create a new statement request.
 * Invalidates related queries on success.
 */
export function useCreateStatementRequest() {
  const queryClient = useQueryClient();

  return useMutation<StatementRequestResponse, Error, CreateStatementRequest>({
    mutationFn: (data: CreateStatementRequest) => createStatementRequest(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: [REQUEST_STATEMENT_QUERY_KEY] });
    },
  });
}

// ─────────────────────────────────────────────────────────────────────────────
// Company Ledger Upload
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Hook for uploading a company ledger file with progress tracking.
 * Returns upload mutation + progress state.
 */
export function useUploadCompanyLedger(requestId: string, companyCode: string) {
  const [uploadProgress, setUploadProgress] = useState<number>(0);

  const mutation = useMutation<
    UploadCompanyLedgerResponse,
    AxiosError<{ detail?: string }>,
    File
  >({
    mutationFn: (file: File) =>
      uploadCompanyLedger(requestId, file, companyCode, (progress) => {
        setUploadProgress(progress);
      }),
    onSettled: () => {
      // Reset progress after a short delay so user sees 100%
      setTimeout(() => setUploadProgress(0), 1500);
    },
  });

  return {
    ...mutation,
    uploadProgress,
  };
}
