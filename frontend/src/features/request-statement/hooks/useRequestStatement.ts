/**
 * React Query hooks for Request Statement page.
 *
 * Provides data fetching with loading/error/retry patterns for:
 * - Creating statement requests (mutation)
 * - Fetching vendor list for selection (query)
 *
 * Requirements: 23.3, 25.1, 25.2
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import {
  createStatementRequest,
  fetchVendorsForSelection,
  type CreateStatementRequest,
  type StatementRequestResponse,
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
  pageSize = 50
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
