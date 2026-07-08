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
  signOffCase,
  uploadStatement,
  validateToken,
  type PortalApiError,
  type PortalCaseSignOffResponse,
  type PortalSignOffRequest,
  type PortalStatementResultResponse,
  type PortalUploadResponse,
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
