/**
 * React Query hooks for Dashboard page.
 * Provides auto-refreshing data for KPI widgets and recent confirmations.
 * Data refreshes every 30 seconds for real-time updates.
 *
 * Requirements: 26.1, 26.2, 26.3, 26.4, 26.5, 26.6, 26.7, 26.8
 */

import { useQuery } from '@tanstack/react-query';

import {
  getDashboardWidgets,
  getRecentConfirmations,
  type DashboardWidgets,
  type RecentConfirmationsResponse,
} from '../api/dashboardApi';

/** Auto-refresh interval in milliseconds (30 seconds). */
const REFRESH_INTERVAL_MS = 30_000;

/**
 * Hook to fetch dashboard KPI widget data with auto-refresh.
 * Refreshes every 30 seconds for real-time dashboard updates.
 */
export function useDashboardWidgets() {
  return useQuery<DashboardWidgets, Error>({
    queryKey: ['vlr', 'dashboard', 'widgets'],
    queryFn: getDashboardWidgets,
    refetchInterval: REFRESH_INTERVAL_MS,
    retry: 2,
    retryDelay: (attempt) => Math.min(1000 * 2 ** attempt, 10000),
  });
}

/**
 * Hook to fetch recent confirmations table data with auto-refresh.
 * Refreshes every 30 seconds for real-time dashboard updates.
 */
export function useRecentConfirmations() {
  return useQuery<RecentConfirmationsResponse, Error>({
    queryKey: ['vlr', 'dashboard', 'recent-confirmations'],
    queryFn: getRecentConfirmations,
    refetchInterval: REFRESH_INTERVAL_MS,
    retry: 2,
    retryDelay: (attempt) => Math.min(1000 * 2 ** attempt, 10000),
  });
}
