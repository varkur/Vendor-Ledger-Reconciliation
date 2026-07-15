/**
 * React Query hooks for the Reconciliation Detail Page.
 * Provides data fetching for batch cases and mutation hooks for bulk actions.
 *
 * Requirements: 1, 2, 4, 25
 */

import {
  useMutation,
  useQuery,
  useQueryClient,
  keepPreviousData,
} from '@tanstack/react-query';
import { useSelectedEntity } from '@shared/hooks/useSelectedEntity';

import {
  getBatchCases,
  getRequestStatistics,
  sendReminder,
  bulkReview,
  bulkReviewDone,
  bulkSignoffRequest,
  type BatchCasesParams,
  type BatchCasesResponse,
  type BulkActionResponse,
  type SendReminderRequest,
  type BulkReviewRequest,
  type BulkReviewDoneRequest,
  type BulkSignoffRequestBody,
  type RequestStatisticsResponse,
} from '../api/reconciliationDetailApi';

/** Query key prefix for reconciliation detail (batch cases). */
export const RECO_DETAIL_QUERY_KEY = 'vlr-reconciliation-detail';

/**
 * Hook to fetch batch cases for a reconciliation request.
 * Supports stage filtering and pagination with smooth page transitions.
 */
export function useBatchCases(
  requestId: string,
  params: { stage?: string; page?: number; page_size?: number }
) {
  const { companyCode } = useSelectedEntity();

  const queryParams: BatchCasesParams = {
    company_code: companyCode,
    ...params,
  };

  return useQuery<BatchCasesResponse, Error>({
    queryKey: [RECO_DETAIL_QUERY_KEY, companyCode, requestId, params],
    queryFn: () => getBatchCases(requestId, queryParams),
    enabled: !!companyCode && !!requestId,
    placeholderData: keepPreviousData,
    retry: 2,
    retryDelay: (attempt) => Math.min(1000 * 2 ** attempt, 10000),
  });
}

/**
 * Mutation hook to send reminders to selected cases.
 * Invalidates the batch cases query on success.
 */
export function useSendReminder(requestId: string) {
  const queryClient = useQueryClient();
  const { companyCode } = useSelectedEntity();

  return useMutation<BulkActionResponse, Error, { case_ids: string[] }>({
    mutationFn: (data) =>
      sendReminder({
        company_code: companyCode,
        case_ids: data.case_ids,
        request_id: requestId,
      } satisfies SendReminderRequest),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: [RECO_DETAIL_QUERY_KEY, companyCode, requestId] });
    },
  });
}

/**
 * Mutation hook to bulk move cases to review stage.
 * Invalidates the batch cases query on success.
 */
export function useBulkReview(requestId: string) {
  const queryClient = useQueryClient();
  const { companyCode } = useSelectedEntity();

  return useMutation<BulkActionResponse, Error, { case_ids: string[] }>({
    mutationFn: (data) =>
      bulkReview({
        company_code: companyCode,
        case_ids: data.case_ids,
      } satisfies BulkReviewRequest),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: [RECO_DETAIL_QUERY_KEY, companyCode, requestId] });
    },
  });
}

/**
 * Mutation hook to bulk mark review as done.
 * Invalidates the batch cases query on success.
 */
export function useBulkReviewDone(requestId: string) {
  const queryClient = useQueryClient();
  const { companyCode } = useSelectedEntity();

  return useMutation<BulkActionResponse, Error, { case_ids: string[] }>({
    mutationFn: (data) =>
      bulkReviewDone({
        company_code: companyCode,
        case_ids: data.case_ids,
      } satisfies BulkReviewDoneRequest),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: [RECO_DETAIL_QUERY_KEY, companyCode, requestId] });
    },
  });
}

/**
 * Mutation hook to bulk trigger signoff request.
 * Invalidates the batch cases query on success.
 */
export function useBulkSignoffRequest(requestId: string) {
  const queryClient = useQueryClient();
  const { companyCode } = useSelectedEntity();

  return useMutation<BulkActionResponse, Error, { case_ids: string[] }>({
    mutationFn: (data) =>
      bulkSignoffRequest({
        company_code: companyCode,
        case_ids: data.case_ids,
      } satisfies BulkSignoffRequestBody),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: [RECO_DETAIL_QUERY_KEY, companyCode, requestId] });
    },
  });
}


/** Query key prefix for request statistics. */
export const RECO_STATISTICS_QUERY_KEY = 'vlr-request-statistics';

/**
 * Hook to fetch enriched statistics for a reconciliation request.
 * Uses TanStack Query with automatic refetch and retry.
 */
export function useRequestStatistics(requestId: string) {
  const { companyCode } = useSelectedEntity();

  return useQuery<RequestStatisticsResponse, Error>({
    queryKey: [RECO_STATISTICS_QUERY_KEY, companyCode, requestId],
    queryFn: () => getRequestStatistics(requestId, companyCode),
    enabled: !!companyCode && !!requestId,
    retry: 2,
    retryDelay: (attempt) => Math.min(1000 * 2 ** attempt, 10000),
    staleTime: 30_000, // 30 seconds
  });
}
