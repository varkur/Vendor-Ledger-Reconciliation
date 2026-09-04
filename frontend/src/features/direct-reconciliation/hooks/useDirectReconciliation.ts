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
import { apiClient } from '@shared/services/apiClient';

import {
  listReconciliationRequests,
  type ListRequestsParams,
  type ReconciliationRequestListResponse,
} from '../api/directReconciliationApi';

/** Query key prefix for direct reconciliation requests. */
export const DIRECT_RECO_QUERY_KEY = 'vlr-direct-reconciliation';

/** Response shape for POST /vlr/cases/direct (dual ledger upload). */
export interface DirectCaseCreateResponse {
  case_id: string;
  request_id: string;
  vendor_id: string;
  case_type: string;
  status: string;
  company_entries_count: number;
  vendor_entries_count: number;
  reconciliation_triggered: boolean;
  task_id: string | null;
  message: string;
  created_date: string | null;
}

/**
 * Query hook to list reconciliation requests with pagination and filtering.
 * Implements retry (2 attempts) and exponential backoff per design spec.
 */
export function useReconciliationRequests(params: ListRequestsParams) {
  // Direct Reconciliation must only show direct-type reconciliations.
  const directParams: ListRequestsParams = { ...params, reco_type: 'direct' };
  return useQuery<ReconciliationRequestListResponse, Error>({
    queryKey: [DIRECT_RECO_QUERY_KEY, directParams],
    queryFn: () => listReconciliationRequests(directParams),
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

  return useMutation<DirectCaseCreateResponse, Error, FormData>({
    mutationFn: async (formData: FormData) => {
      const { data } = await apiClient.post<DirectCaseCreateResponse>('/vlr/cases/direct', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
        timeout: 120000, // 2 minutes — file parsing + DB inserts (no longer triggers reconciliation inline)
      });
      return data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: [DIRECT_RECO_QUERY_KEY] });
    },
  });
}
