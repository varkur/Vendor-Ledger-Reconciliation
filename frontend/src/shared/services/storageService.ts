/**
 * Secure storage service.
 * Access tokens are stored in memory only (never localStorage).
 * Refresh tokens are stored in memory for this implementation.
 */

let accessToken: string | null = null;
let refreshToken: string | null = null;

export const storageService = {
  getAccessToken: (): string | null => accessToken,

  setAccessToken: (token: string): void => {
    accessToken = token;
  },

  getRefreshToken: (): string | null => refreshToken,

  setRefreshToken: (token: string): void => {
    refreshToken = token;
  },

  clearTokens: (): void => {
    accessToken = null;
    refreshToken = null;
  },

  isAuthenticated: (): boolean => accessToken !== null,
};
