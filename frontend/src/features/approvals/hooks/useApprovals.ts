/**
 * React Query hooks for the Approvals page.
 * Provides data fetching for pending approvals and mutation hooks for approval actions.
 *
 * Requirements: 17
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useSelectedEntity } from '@shared/hooks/useSelectedEntity';

import {
  getPendingApprovals,
  approveCase,
  rejectCase,
  delegateApproval,
  type PendingApprovalsResponse,
  type ApproveRequestBody,
  type RejectRequestBody,
  type DelegateRequestBody,
  type ApprovalActionResponse,
  type DelegationActionResponse,
} from '../api/approvalsApi';

/** Query key prefix for pending approvals. */
export const APPROVALS_QUERY_KEY = 'vlr-approvals-pending';

/**
 * Hook to fetch pending approvals for the current user.
 * Includes entity scoping via companyCode.
 */
export function usePendingApprovals() {
  const { companyCode } = useSelectedEntity();

  return useQuery<PendingApprovalsResponse, Error>({
    queryKey: [APPROVALS_QUERY_KEY, companyCode],
    queryFn: () => getPendingApprovals(companyCode),
    enabled: !!companyCode,
    retry: 2,
    retryDelay: (attempt) => Math.min(1000 * 2 ** attempt, 10000),
  });
}

/**
 * Mutation hook to approve a case.
 * Invalidates the pending approvals query on success.
 */
export function useApproveCase() {
  const queryClient = useQueryClient();
  const { companyCode } = useSelectedEntity();

  return useMutation<
    ApprovalActionResponse,
    Error,
    { caseId: string; data: ApproveRequestBody }
  >({
    mutationFn: ({ caseId, data }) => approveCase(caseId, data, companyCode),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: [APPROVALS_QUERY_KEY] });
    },
  });
}

/**
 * Mutation hook to reject a case.
 * Invalidates the pending approvals query on success.
 */
export function useRejectCase() {
  const queryClient = useQueryClient();
  const { companyCode } = useSelectedEntity();

  return useMutation<
    ApprovalActionResponse,
    Error,
    { caseId: string; data: RejectRequestBody }
  >({
    mutationFn: ({ caseId, data }) => rejectCase(caseId, data, companyCode),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: [APPROVALS_QUERY_KEY] });
    },
  });
}

/**
 * Mutation hook to delegate approval authority.
 * Invalidates the pending approvals query on success.
 */
export function useDelegateApproval() {
  const queryClient = useQueryClient();
  const { companyCode } = useSelectedEntity();

  return useMutation<
    DelegationActionResponse,
    Error,
    { caseId: string; data: DelegateRequestBody }
  >({
    mutationFn: ({ caseId, data }) => delegateApproval(caseId, data, companyCode),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: [APPROVALS_QUERY_KEY] });
    },
  });
}
