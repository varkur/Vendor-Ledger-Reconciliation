/**
 * Microsoft SSO API calls.
 * Maps to backend: GET /api/v1/auth/microsoft/login, POST /api/v1/auth/microsoft/callback
 */

import { apiClient } from '@shared/services/apiClient';
import type { TokenResponse } from '../models/auth.types';

export interface MicrosoftLoginUrlResponse {
  auth_url: string;
  redirect_uri: string;
}

export interface MicrosoftCallbackRequest {
  code: string;
}

export const microsoftApi = {
  /**
   * Get the Azure AD authorization URL from the backend.
   * Frontend should redirect the browser to the returned auth_url.
   */
  getLoginUrl: async (): Promise<MicrosoftLoginUrlResponse> => {
    const { data } = await apiClient.get<MicrosoftLoginUrlResponse>('/auth/microsoft/login');
    return data;
  },

  /**
   * Exchange the Microsoft authorization code for application JWT tokens.
   * Called after Azure AD redirects back with ?code=XXX.
   */
  exchangeCode: async (code: string): Promise<TokenResponse> => {
    const { data } = await apiClient.post<TokenResponse>('/auth/microsoft/callback', { code });
    return data;
  },
};
