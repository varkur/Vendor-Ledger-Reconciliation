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
 * Fetches from GET /api/v1/vlr/settings/ (general settings) and
 * GET /api/v1/vlr/settings/sap-connection (SAP config, masked).
 * Maps backend field names to the frontend VLRSettings interface.
 */
export async function getSettings(): Promise<VLRSettings> {
  // Fetch general settings and SAP connection in parallel
  const [settingsRes, sapRes] = await Promise.all([
    apiClient.get(`${BASE}/`),
    apiClient.get(`${BASE}/sap-connection`).catch(() => ({ data: null })),
  ]);

  const s = settingsRes.data;
  const sap = sapRes.data;

  return {
    tolerance: {
      amount_tolerance: s.tolerance?.amount_tolerance_absolute ?? 0,
      percent_tolerance: s.tolerance?.amount_tolerance_percentage ?? 0,
      date_tolerance: s.tolerance?.date_tolerance_days ?? 0,
    },
    matching: {
      matching_method: s.matching?.strategy === 'fuzzy' ? 'auto'
        : s.matching?.strategy === 'rule_based' ? 'rules'
        : s.matching?.strategy ?? 'auto',
      auto_match_threshold: (s.matching?.auto_match_threshold ?? 0.8) * 100,
      enable_fuzzy_match: s.matching?.strategy === 'fuzzy' || s.matching?.require_document_number_match === false,
    },
    approvals: {
      auto_approve_limit: s.approval_thresholds?.auto_approve_below ?? 0,
      manager_approve_limit: s.approval_thresholds?.manager_approval_below ?? 0,
      require_dual_approval: (s.approval_thresholds?.require_dual_approval_above ?? 0) > 0,
    },
    tax: {
      default_tds_rate: 2,
      default_gst_rate: 18,
      tds_threshold: 30000,
    },
    sap_connection: {
      sap_host: sap?.host ?? '',
      sap_client: sap?.client ?? '',
      sap_username: sap?.username ?? '',
      sap_system_number: sap?.system_number ?? '',
    },
  };
}

/**
 * Update VLR settings by calling individual section endpoints.
 * The backend exposes separate PUT endpoints per section:
 *   PUT /api/v1/vlr/settings/tolerance
 *   PUT /api/v1/vlr/settings/matching
 *   PUT /api/v1/vlr/settings/approval-thresholds
 *   PUT /api/v1/vlr/settings/sap-connection
 */
export async function updateSettings(settings: Partial<VLRSettings>): Promise<VLRSettings> {
  const promises: Promise<unknown>[] = [];

  if (settings.tolerance) {
    promises.push(apiClient.put(`${BASE}/tolerance`, {
      amount_tolerance_percentage: settings.tolerance.percent_tolerance,
      amount_tolerance_absolute: settings.tolerance.amount_tolerance,
      date_tolerance_days: settings.tolerance.date_tolerance,
    }));
  }

  if (settings.matching) {
    promises.push(apiClient.put(`${BASE}/matching`, {
      strategy: settings.matching.matching_method,
      auto_match_threshold: (settings.matching.auto_match_threshold ?? 0) / 100,
      require_document_number_match: settings.matching.enable_fuzzy_match,
    }));
  }

  if (settings.approvals) {
    promises.push(apiClient.put(`${BASE}/approval-thresholds`, {
      auto_approve_below: settings.approvals.auto_approve_limit,
      manager_approval_below: settings.approvals.manager_approve_limit,
      require_dual_approval_above: settings.approvals.require_dual_approval
        ? settings.approvals.manager_approve_limit
        : undefined,
    }));
  }

  if (settings.sap_connection) {
    promises.push(apiClient.put(`${BASE}/sap-connection`, {
      host: settings.sap_connection.sap_host,
      client: settings.sap_connection.sap_client,
      username: settings.sap_connection.sap_username,
      password: settings.sap_connection.sap_password,
      system_number: settings.sap_connection.sap_system_number,
    }));
  }

  await Promise.all(promises);

  // Re-fetch all settings to return the updated state (mapped to frontend shape)
  return getSettings();
}

/**
 * Test SAP connection with provided configuration.
 * POST /api/v1/vlr/settings/sap-connection/test
 */
export async function testSAPConnection(
  config: SAPConnectionConfig
): Promise<TestConnectionResponse> {
  const response = await apiClient.post<TestConnectionResponse>(
    `${BASE}/sap-connection/test`,
    config
  );
  return response.data;
}
