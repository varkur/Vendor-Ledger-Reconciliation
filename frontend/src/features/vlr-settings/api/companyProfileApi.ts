/**
 * Company Profile API functions.
 * Communicates with backend company profile endpoints via Axios.
 */

import { apiClient } from '@shared/services/apiClient';

const BASE = '/vlr/settings/company-profile';

// ─────────────────────────────────────────────────────────────────────────────
// Types
// ─────────────────────────────────────────────────────────────────────────────

export interface CompanyProfile {
  entity_name: string;
  entity_type: string;
  pan_card: string;
  email: string;
  website: string;
  telephone: string;
  registered_address: string;
  company_code: string;
  letterhead_header: string;
  letterhead_footer: string;
  logo: string;
  verified: boolean;
}

export interface CompanyProfileUpdateRequest {
  entity_name?: string;
  entity_type?: string;
  pan_card?: string;
  email?: string;
  website?: string;
  telephone?: string;
  registered_address?: string;
  company_code?: string;
  letterhead_header?: string;
  letterhead_footer?: string;
  logo?: string;
}

// ─────────────────────────────────────────────────────────────────────────────
// API Functions
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Get company profile for a specific entity.
 * GET /api/v1/vlr/settings/company-profile?company_code=...
 */
export async function getCompanyProfile(companyCode?: string): Promise<CompanyProfile> {
  const response = await apiClient.get<CompanyProfile>(BASE, {
    params: companyCode ? { company_code: companyCode } : undefined,
  });
  return response.data;
}

/**
 * Update company profile.
 * PUT /api/v1/vlr/settings/company-profile
 */
export async function updateCompanyProfile(
  data: CompanyProfileUpdateRequest,
  companyCode?: string
): Promise<CompanyProfile> {
  const response = await apiClient.put<CompanyProfile>(BASE, data, {
    params: companyCode ? { company_code: companyCode } : undefined,
  });
  return response.data;
}
