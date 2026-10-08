/**
 * React Query hooks for the Action Tracker tab.
 * Provides summary/detail data fetching and workflow-field mutation hooks.
 */

import { useMutation, useQuery, useQueryClient, keepPreviousData } from '@tanstack/react-query';
import { useSelectedEntity } from '@shared/hooks/useSelectedEntity';

import {
  getActionTrackerSummary,
  getActionTrackerItems,
  updateActionTakenItem,
  bulkUpdateActionTakenItems,
  type ActionTrackerSummaryResponse,
  type ActionTrackerItemListResponse,
  type ActionTrackerItemsParams,
  type UpdateActionTakenItem,
  type BulkUpdateActionTakenResponse,
} from '../api/actionTrackerApi';

export const ACTION_TRACKER_QUERY_KEY = 'vlr-action-tracker';

/** Hook to fetch the Action Tracker summary (grouped by Action Taken Status). */
export function useActionTrackerSummary(requestId: string) {
  const { companyCode } = useSelectedEntity();

  return useQuery<ActionTrackerSummaryResponse, Error>({
    queryKey: [ACTION_TRACKER_QUERY_KEY, 'summary', companyCode, requestId],
    queryFn: () => getActionTrackerSummary(requestId, companyCode),
    enabled: !!companyCode && !!requestId,
    retry: 2,
    retryDelay: (attempt) => Math.min(1000 * 2 ** attempt, 10000),
  });
}

/** Hook to fetch paginated/filterable Action Tracker detail rows. */
export function useActionTrackerItems(
  requestId: string,
  params: Omit<ActionTrackerItemsParams, 'company_code'>
) {
  const { companyCode } = useSelectedEntity();

  return useQuery<ActionTrackerItemListResponse, Error>({
    queryKey: [ACTION_TRACKER_QUERY_KEY, 'items', companyCode, requestId, params],
    queryFn: () => getActionTrackerItems(requestId, { company_code: companyCode, ...params }),
    enabled: !!companyCode && !!requestId,
    placeholderData: keepPreviousData,
    retry: 2,
    retryDelay: (attempt) => Math.min(1000 * 2 ** attempt, 10000),
  });
}

/** Mutation hook to update one Action Tracker row's workflow fields. */
export function useUpdateActionTakenItem(requestId: string) {
  const queryClient = useQueryClient();
  const { companyCode } = useSelectedEntity();

  return useMutation<BulkUpdateActionTakenResponse, Error, UpdateActionTakenItem>({
    mutationFn: (item) => updateActionTakenItem(requestId, item),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: [ACTION_TRACKER_QUERY_KEY, 'items', companyCode, requestId] });
      queryClient.invalidateQueries({ queryKey: [ACTION_TRACKER_QUERY_KEY, 'summary', companyCode, requestId] });
    },
  });
}

/** Mutation hook to update many Action Tracker rows' workflow fields at once. */
export function useBulkUpdateActionTakenItems(requestId: string) {
  const queryClient = useQueryClient();
  const { companyCode } = useSelectedEntity();

  return useMutation<BulkUpdateActionTakenResponse, Error, UpdateActionTakenItem[]>({
    mutationFn: (items) => bulkUpdateActionTakenItems(requestId, items),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: [ACTION_TRACKER_QUERY_KEY, 'items', companyCode, requestId] });
      queryClient.invalidateQueries({ queryKey: [ACTION_TRACKER_QUERY_KEY, 'summary', companyCode, requestId] });
    },
  });
}
