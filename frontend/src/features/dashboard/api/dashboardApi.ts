/**
 * Dashboard API functions.
 * Communicates with the backend dashboard endpoints via Axios.
 *
 * Requirements: 26.1, 26.2, 26.3, 26.4, 26.5, 26.6, 26.7, 26.8
 */

import { apiClient } from '@shared/services/apiClient';

const BASE = '/vlr/dashboard';

// ─────────────────────────────────────────────────────────────────────────────
// Types
// ─────────────────────────────────────────────────────────────────────────────

/** KPI widget data returned by the widgets endpoint. */
export interface DashboardWidgets {
  open_cases: number;
  pending_vendor_upload: number;
  pending_finance_review: number;
  overdue_cases: number;
  closed_this_month: number;
  avg_cycle_time_days: number;
  auto_match_rate: number;
}

/** A single recent confirmation entry. */
export interface RecentConfirmation {
  id: string;
  vendor_name: string;
  case_id: string;
  sign_off_date: string;
  status: string;
}

/** Response from the recent-confirmations endpoint. */
export interface RecentConfirmationsResponse {
  items: RecentConfirmation[];
}

// ─────────────────────────────────────────────────────────────────────────────
// API Functions
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Get all dashboard KPI widget data.
 * GET /api/v1/vlr/dashboard/widgets
 */
export async function getDashboardWidgets(): Promise<DashboardWidgets> {
  const response = await apiClient.get<DashboardWidgets>(`${BASE}/widgets`);
  return response.data;
}

/**
 * Get recent vendor confirmations (last 10 sign-offs).
 * GET /api/v1/vlr/dashboard/recent-confirmations
 */
export async function getRecentConfirmations(): Promise<RecentConfirmationsResponse> {
  const response = await apiClient.get<RecentConfirmationsResponse>(
    `${BASE}/recent-confirmations`
  );
  return response.data;
}
