/**
 * React Query hooks for reconciliation output API operations.
 *
 * Requirements: 18.1-18.4, 19.1-19.4, 20.1-20.3, 21.1-21.3, 22.1-22.4
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import {
  confirmMatch,
  getConfirmationItems,
  getDifferencesSummary,
  getMatchedItems,
  getUnmatchedCompany,
  getUnmatchedVendor,
  type ConfirmMatchRequest,
  type ConfirmMatchResponse,
  type ConfirmationItem,
  type DifferencesSummary,
  type ListParams,
  type MatchedItem,
  type PaginatedResponse,
  type UnmatchedCompanyItem,
  type UnmatchedVendorItem,
} from './reconciliationOutputApi';

/**
 * Query hook for matched items (Tab 1).
 * Supports pagination, sorting, and filtering.
 */
export function useMatchedItems(caseId: string, params?: ListParams) {
  return useQuery<PaginatedResponse<MatchedItem>, Error>({
    queryKey: ['vlr', 'reconciliation', caseId, 'matched', params],
    queryFn: () => getMatchedItems(caseId, params),
    enabled: !!caseId,
    retry: 2,
    retryDelay: (attempt) => Math.min(1000 * 2 ** attempt, 10000),
  });
}

/**
 * Query hook for confirmation items (Tab 2).
 * Supports pagination, sorting, and filtering.
 */
export function useConfirmationItems(caseId: string, params?: ListParams) {
  return useQuery<PaginatedResponse<ConfirmationItem>, Error>({
    queryKey: ['vlr', 'reconciliation', caseId, 'confirmation', params],
    queryFn: () => getConfirmationItems(caseId, params),
    enabled: !!caseId,
    retry: 2,
    retryDelay: (attempt) => Math.min(1000 * 2 ** attempt, 10000),
  });
}

/**
 * Query hook for unmatched company items (Tab 3).
 * Supports pagination, sorting, and filtering.
 */
export function useUnmatchedCompany(caseId: string, params?: ListParams) {
  return useQuery<PaginatedResponse<UnmatchedCompanyItem>, Error>({
    queryKey: ['vlr', 'reconciliation', caseId, 'unmatched-company', params],
    queryFn: () => getUnmatchedCompany(caseId, params),
    enabled: !!caseId,
    retry: 2,
    retryDelay: (attempt) => Math.min(1000 * 2 ** attempt, 10000),
  });
}

/**
 * Query hook for unmatched vendor items (Tab 4).
 * Supports pagination, sorting, and filtering.
 */
export function useUnmatchedVendor(caseId: string, params?: ListParams) {
  return useQuery<PaginatedResponse<UnmatchedVendorItem>, Error>({
    queryKey: ['vlr', 'reconciliation', caseId, 'unmatched-vendor', params],
    queryFn: () => getUnmatchedVendor(caseId, params),
    enabled: !!caseId,
    retry: 2,
    retryDelay: (attempt) => Math.min(1000 * 2 ** attempt, 10000),
  });
}

/**
 * Query hook for differences summary (Tab 5).
 */
export function useSummary(caseId: string) {
  return useQuery<DifferencesSummary, Error>({
    queryKey: ['vlr', 'reconciliation', caseId, 'summary'],
    queryFn: () => getDifferencesSummary(caseId),
    enabled: !!caseId,
    retry: 2,
    retryDelay: (attempt) => Math.min(1000 * 2 ** attempt, 10000),
  });
}

/**
 * Mutation hook for confirming/rejecting/clarifying match entries.
 * Invalidates related queries on success.
 */
export function useConfirmMatch(caseId: string) {
  const queryClient = useQueryClient();

  return useMutation<ConfirmMatchResponse, Error, ConfirmMatchRequest>({
    mutationFn: (request: ConfirmMatchRequest) => confirmMatch(caseId, request),
    onSuccess: () => {
      // Invalidate all related queries to refresh data
      queryClient.invalidateQueries({
        queryKey: ['vlr', 'reconciliation', caseId],
      });
    },
  });
}
