/**
 * VLR Settings API functions.
 * Communicates with backend VLR configuration endpoints via Axios.
 *
 * Requirements: 23.7, 25.1, 25.2
 */

import { apiClient } from '@shared/services/apiClient';

const BASE = '/vlr/settings';

// ─────────────────────────────────────────────────────────────────────────────
// Types
// ─────────────────────────────────────────────────────────────────────────────

/** Tolerance configuration section. */
export interface ToleranceConfig {
  amount_tolerance: number;
  percent_tolerance: number;
  date_tolerance: number;
}

/** Matching preferences section. */
export interface MatchingConfig {
  matching_method: 'auto' | 'rules' | 'manual';
  auto_match_threshold: number;
  enable_fuzzy_match: boolean;
}

/** Notification interval configuration. */
export interface NotificationConfig {
  reminder_interval_days: number;
  max_reminders: number;
  escalation_days: number;
}

/** Approval thresholds configuration. */
export interface ApprovalConfig {
  auto_approve_limit: number;
  manager_approve_limit: number;
  require_dual_approval: boolean;
}

/** TDS/GST defaults configuration. */
export interface TaxConfig {
  default_tds_rate: number;
  default_gst_rate: number;
  tds_threshold: number;
}

/** SAP connection configuration. */
export interface SAPConnectionConfig {
  sap_host: string;
  sap_client: string;
  sap_username: string;
  sap_password?: string;
  sap_system_number: string;
}

/** Complete settings object. */
export interface VLRSettings {
  tolerance: ToleranceConfig;
  matching: MatchingConfig;
  notifications: NotificationConfig;
  approvals: ApprovalConfig;
  tax: TaxConfig;
  sap_connection: SAPConnectionConfig;
}

/** Response from test connection endpoint. */
export interface TestConnectionResponse {
  success: boolean;
  message: string;
  latency_ms?: number;
}

// ─────────────────────────────────────────────────────────────────────────────
// API Functions
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Get current VLR settings.
 * GET /api/v1/vlr/settings
 */
export async function getSettings(): Promise<VLRSettings> {
  const response = await apiClient.get<VLRSettings>(BASE);
  return response.data;
}

/**
 * Update VLR settings (full or partial).
 * PUT /api/v1/vlr/settings
 */
export async function updateSettings(settings: Partial<VLRSettings>): Promise<VLRSettings> {
  const response = await apiClient.put<VLRSettings>(BASE, settings);
  return response.data;
}

/**
 * Test SAP connection with provided configuration.
 * POST /api/v1/vlr/settings/test-connection
 */
export async function testSAPConnection(
  config: SAPConnectionConfig
): Promise<TestConnectionResponse> {
  const response = await apiClient.post<TestConnectionResponse>(
    `${BASE}/test-connection`,
    config
  );
  return response.data;
}
