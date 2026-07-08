/**
 * React Query hooks for direct reconciliation case management.
 *
 * Provides data fetching with loading/error/retry patterns for:
 * - Listing reconciliation requests (paginated)
 * - Creating new reconciliation requests
 *
 * Requirements: 23.1, 25.1, 25.2
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import {
  createReconciliationRequest,
  listReconciliationRequests,
  type CreateReconciliationRequest,
  type ListRequestsParams,
  type ReconciliationRequestListResponse,
  type ReconciliationRequestResponse,
} from '../api/directReconciliationApi';

/** Query key prefix for direct reconciliation requests. */
export const DIRECT_RECO_QUERY_KEY = 'vlr-direct-reconciliation';

/**
 * Query hook to list reconciliation requests with pagination and filtering.
 * Implements retry (2 attempts) and exponential backoff per design spec.
 */
export function useReconciliationRequests(params: ListRequestsParams) {
  return useQuery<ReconciliationRequestListResponse, Error>({
    queryKey: [DIRECT_RECO_QUERY_KEY, params],
    queryFn: () => listReconciliationRequests(params),
    enabled: !!params.company_code,
    retry: 2,
    retryDelay: (attempt) => Math.min(1000 * 2 ** attempt, 10000),
  });
}

/**
 * Mutation hook to create a new reconciliation request.
 * Invalidates the list query on success so the table refreshes automatically.
 */
export function useCreateReconciliationRequest() {
  const queryClient = useQueryClient();

  return useMutation<ReconciliationRequestResponse, Error, CreateReconciliationRequest>({
    mutationFn: (data: CreateReconciliationRequest) =>
      createReconciliationRequest(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: [DIRECT_RECO_QUERY_KEY] });
    },
  });
}
