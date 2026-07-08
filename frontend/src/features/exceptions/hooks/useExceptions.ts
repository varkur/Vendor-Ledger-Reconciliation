/**
 * React Query hooks for Exceptions page.
 * Provides data fetching with lazy pagination, filtering, and mutation for resolution.
 *
 * Requirements: 23.4, 25.3, 25.4
 */

import { useMutation, useQuery, useQueryClient, keepPreviousData } from '@tanstack/react-query';

import {
  listExceptions,
  resolveException,
  bulkResolveExceptions,
  type ExceptionListParams,
  type PaginatedExceptionResponse,
  type ResolveExceptionRequest,
  type ResolutionResponse,
  type BulkResolveRequest,
  type BulkResolveResponse,
} from '../api/exceptionsApi';

/** Query key prefix for exceptions. */
export const EXCEPTIONS_QUERY_KEY = 'vlr-exceptions';

/**
 * Hook to list exceptions with server-side pagination and filtering.
 * Uses keepPreviousData for smooth pagination UX (no flicker on page change).
 */
export function useExceptionList(params: ExceptionListParams) {
  return useQuery<PaginatedExceptionResponse, Error>({
    queryKey: [EXCEPTIONS_QUERY_KEY, params],
    queryFn: () => listExceptions(params),
    enabled: !!params.company_code,
    placeholderData: keepPreviousData,
    retry: 2,
    retryDelay: (attempt) => Math.min(1000 * 2 ** attempt, 10000),
  });
}

/**
 * Mutation hook to resolve a single exception.
 * Invalidates the exception list query on success so the table refreshes automatically.
 */
export function useResolveException(companyCode: string) {
  const queryClient = useQueryClient();

  return useMutation<
    ResolutionResponse,
    Error,
    { exceptionId: string; data: ResolveExceptionRequest }
  >({
    mutationFn: ({ exceptionId, data }) =>
      resolveException(exceptionId, data, companyCode),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: [EXCEPTIONS_QUERY_KEY] });
    },
  });
}

/**
 * Mutation hook to bulk resolve multiple exceptions.
 * Invalidates the exception list query on success.
 */
export function useBulkResolveExceptions(companyCode: string) {
  const queryClient = useQueryClient();

  return useMutation<BulkResolveResponse, Error, BulkResolveRequest>({
    mutationFn: (data) => bulkResolveExceptions(data, companyCode),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: [EXCEPTIONS_QUERY_KEY] });
    },
  });
}
