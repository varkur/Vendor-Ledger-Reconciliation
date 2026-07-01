/**
 * Authentication API calls.
 * Maps to backend: POST /api/v1/auth/login, /refresh, GET /auth/me
 */

import { apiClient } from '@shared/services/apiClient';
import { storageService } from '@shared/services/storageService';
import type {
  CurrentUser,
  LoginRequest,
  TokenResponse,
} from '../models/auth.types';

export const authApi = {
  login: async (credentials: LoginRequest): Promise<TokenResponse> => {
    const { data } = await apiClient.post<TokenResponse>(
      '/auth/login',
      credentials
    );
    // Store tokens
    storageService.setAccessToken(data.access_token);
    storageService.setRefreshToken(data.refresh_token);
    return data;
  },

  refresh: async (refreshToken: string): Promise<TokenResponse> => {
    const { data } = await apiClient.post<TokenResponse>('/auth/refresh', {
      refresh_token: refreshToken,
    });
    storageService.setAccessToken(data.access_token);
    return data;
  },

  getCurrentUser: async (): Promise<CurrentUser> => {
    const { data } = await apiClient.get<CurrentUser>('/auth/me');
    return data;
  },

  logout: (): void => {
    storageService.clearTokens();
  },
};
