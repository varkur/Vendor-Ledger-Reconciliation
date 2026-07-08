/**
 * React Query hooks for Track Reconciliation page.
 * Provides data fetching with lazy pagination, filtering, and search.
 *
 * Requirements: 23.2, 25.3, 25.4
 */

import { useQuery, keepPreviousData } from '@tanstack/react-query';

import {
  listCases,
  getCaseById,
  type CaseListParams,
  type PaginatedCaseResponse,
  type ReconciliationCase,
} from '../api/trackReconciliationApi';

/**
 * Hook to list reconciliation cases with server-side pagination and filtering.
 * Uses keepPreviousData for smooth pagination UX (no flicker on page change).
 */
export function useCaseList(params: CaseListParams) {
  return useQuery<PaginatedCaseResponse, Error>({
    queryKey: ['vlr', 'cases', params],
    queryFn: () => listCases(params),
    enabled: !!params.company_code,
    placeholderData: keepPreviousData,
    retry: 2,
    retryDelay: (attempt) => Math.min(1000 * 2 ** attempt, 10000),
  });
}

/**
 * Hook to get a single reconciliation case by ID.
 */
export function useCaseDetail(caseId: string, companyCode: string) {
  return useQuery<ReconciliationCase, Error>({
    queryKey: ['vlr', 'cases', caseId],
    queryFn: () => getCaseById(caseId, companyCode),
    enabled: !!caseId && !!companyCode,
    retry: 2,
    retryDelay: (attempt) => Math.min(1000 * 2 ** attempt, 10000),
  });
}
