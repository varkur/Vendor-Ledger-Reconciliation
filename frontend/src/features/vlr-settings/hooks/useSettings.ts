/**
 * React Query hooks for VLR Settings page.
 * Provides data fetching with loading/error/retry patterns for:
 * - Loading current settings
 * - Saving settings
 * - Testing SAP connection
 *
 * Requirements: 23.7, 25.1, 25.2
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import {
  getSettings,
  updateSettings,
  testSAPConnection,
  type VLRSettings,
  type SAPConnectionConfig,
  type TestConnectionResponse,
} from '../api/settingsApi';

/** Query key for VLR settings. */
export const SETTINGS_QUERY_KEY = 'vlr-settings';

/**
 * Hook to load current VLR settings.
 */
export function useVLRSettings() {
  return useQuery<VLRSettings, Error>({
    queryKey: [SETTINGS_QUERY_KEY],
    queryFn: () => getSettings(),
    retry: 2,
    retryDelay: (attempt) => Math.min(1000 * 2 ** attempt, 10000),
    staleTime: 5 * 60 * 1000, // Settings are unlikely to change frequently
  });
}

/**
 * Mutation hook to save settings.
 * Invalidates settings query on success to refresh state.
 */
export function useUpdateSettings() {
  const queryClient = useQueryClient();

  return useMutation<VLRSettings, Error, Partial<VLRSettings>>({
    mutationFn: (settings: Partial<VLRSettings>) => updateSettings(settings),
    onSuccess: (data) => {
      queryClient.setQueryData([SETTINGS_QUERY_KEY], data);
    },
  });
}

/**
 * Mutation hook to test SAP connection.
 */
export function useTestSAPConnection() {
  return useMutation<TestConnectionResponse, Error, SAPConnectionConfig>({
    mutationFn: (config: SAPConnectionConfig) => testSAPConnection(config),
  });
}
