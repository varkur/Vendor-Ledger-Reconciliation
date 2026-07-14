/**
 * React Query hooks for the Vendor Portal.
 *
 * Provides data fetching with loading/error/retry patterns for:
 * - Token validation (authentication)
 * - File upload with progress tracking
 * - Statement retrieval
 * - Sign-off submission
 *
 * Requirements: 24.1, 24.2, 24.3, 24.4
 */

import { useMutation, useQuery } from '@tanstack/react-query';
import { AxiosError } from 'axios';
import { useState } from 'react';

import {
  getStatement,
  getReconciliationStatus,
  raiseDispute,
  requestNewLink,
  signOffCase,
  uploadStatement,
  validateToken,
  type PortalApiError,
  type PortalCaseSignOffResponse,
  type PortalDisputeRequest,
  type PortalDisputeResponse,
  type PortalReconciliationStatusResponse,
  type PortalSignOffRequest,
  type PortalStatementResultResponse,
  type PortalUploadResponse,
  type RequestNewLinkResponse,
  type ValidateTokenResponse,
} from '../api/portalApi';

/** Query key prefix for vendor portal queries. */
export const PORTAL_QUERY_KEY = 'vlr-vendor-portal';

// ─────────────────────────────────────────────────────────────────────────────
// Token Validation
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Mutation hook to validate a portal token.
 * Used on the auth page to authenticate and retrieve case summary.
 */
export function useValidateToken() {
  return useMutation<
    ValidateTokenResponse,
    AxiosError<PortalApiError>,
    string
  >({
    mutationFn: (token: string) => validateToken({ token }),
    retry: false,
  });
}

// ─────────────────────────────────────────────────────────────────────────────
// File Upload
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Hook for file upload with progress tracking.
 * Returns upload mutation + progress state.
 */
export function usePortalUpload(portalToken: string) {
  const [uploadProgress, setUploadProgress] = useState<number>(0);

  const mutation = useMutation<
    PortalUploadResponse,
    AxiosError<PortalApiError>,
    File
  >({
    mutationFn: (file: File) =>
      uploadStatement(file, portalToken, (progress) => {
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

// ─────────────────────────────────────────────────────────────────────────────
// Reconciliation Status Polling
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Query hook to poll reconciliation processing status after upload.
 * Polls every 5 seconds while enabled. Stops when status is 'completed' or 'error'.
 */
export function useReconciliationStatus(
  caseId: string | null,
  portalToken: string | null,
  enabled: boolean
) {
  return useQuery<
    PortalReconciliationStatusResponse,
    AxiosError<PortalApiError>
  >({
    queryKey: [PORTAL_QUERY_KEY, 'reconciliation-status', caseId],
    queryFn: () => getReconciliationStatus(caseId!, portalToken!),
    enabled: !!caseId && !!portalToken && enabled,
    refetchInterval: (query) => {
      // Stop polling once completed or error
      const status = query.state.data?.status;
      if (status === 'completed' || status === 'error') {
        return false;
      }
      return 5000; // Poll every 5 seconds
    },
    retry: 2,
    retryDelay: (attempt) => Math.min(1000 * 2 ** attempt, 5000),
  });
}

// ─────────────────────────────────────────────────────────────────────────────
// Statement Retrieval
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Query hook to fetch the vendor-facing reconciliation statement.
 * Implements retry (2 attempts) and exponential backoff.
 */
export function usePortalStatement(
  caseId: string | null,
  portalToken: string | null
) {
  return useQuery<
    PortalStatementResultResponse,
    AxiosError<PortalApiError>
  >({
    queryKey: [PORTAL_QUERY_KEY, 'statement', caseId],
    queryFn: () => getStatement(caseId!, portalToken!),
    enabled: !!caseId && !!portalToken,
    retry: 2,
    retryDelay: (attempt) => Math.min(1000 * 2 ** attempt, 10000),
  });
}

// ─────────────────────────────────────────────────────────────────────────────
// Sign-Off
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Mutation hook to submit vendor sign-off for a reconciliation case.
 */
export function usePortalSignOff(
  caseId: string | null,
  portalToken: string | null
) {
  return useMutation<
    PortalCaseSignOffResponse,
    AxiosError<PortalApiError>,
    PortalSignOffRequest
  >({
    mutationFn: (data: PortalSignOffRequest) =>
      signOffCase(caseId!, data, portalToken!),
  });
}


// ─────────────────────────────────────────────────────────────────────────────
// Request New Link
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Mutation hook to request a new portal access link.
 * Used on the auth page when the vendor's link is expired.
 */
export function useRequestNewLink() {
  return useMutation<
    RequestNewLinkResponse,
    AxiosError<PortalApiError>,
    string
  >({
    mutationFn: (email: string) => requestNewLink({ email }),
    retry: false,
  });
}

// ─────────────────────────────────────────────────────────────────────────────
// Raise Dispute
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Mutation hook to raise a dispute on reconciliation results.
 * Used on the statement page when the vendor disagrees with results.
 */
export function useRaiseDispute(
  caseId: string | null,
  portalToken: string | null
) {
  return useMutation<
    PortalDisputeResponse,
    AxiosError<PortalApiError>,
    PortalDisputeRequest
  >({
    mutationFn: (data: PortalDisputeRequest) =>
      raiseDispute(caseId!, data, portalToken!),
  });
}
