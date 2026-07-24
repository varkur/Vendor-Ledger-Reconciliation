/**
 * Storage service for auth tokens.
 *
 * Tokens are persisted in localStorage so the session survives a full page
 * refresh (previously they were in-memory only, which logged the user out on
 * every refresh). An in-memory cache mirrors them to avoid repeated reads.
 */

const ACCESS_TOKEN_KEY = 'vlr_access_token';
const REFRESH_TOKEN_KEY = 'vlr_refresh_token';

let accessToken: string | null = null;
let refreshToken: string | null = null;

// Hydrate the in-memory cache from localStorage on module load (page refresh).
try {
  accessToken = localStorage.getItem(ACCESS_TOKEN_KEY);
  refreshToken = localStorage.getItem(REFRESH_TOKEN_KEY);
} catch {
  // localStorage may be unavailable (e.g. privacy mode); fall back to memory.
}

export const storageService = {
  getAccessToken: (): string | null => accessToken,

  setAccessToken: (token: string): void => {
    accessToken = token;
    try {
      localStorage.setItem(ACCESS_TOKEN_KEY, token);
    } catch {
      /* ignore storage errors */
    }
  },

  getRefreshToken: (): string | null => refreshToken,

  setRefreshToken: (token: string): void => {
    refreshToken = token;
    try {
      localStorage.setItem(REFRESH_TOKEN_KEY, token);
    } catch {
      /* ignore storage errors */
    }
  },

  clearTokens: (): void => {
    accessToken = null;
    refreshToken = null;
    try {
      localStorage.removeItem(ACCESS_TOKEN_KEY);
      localStorage.removeItem(REFRESH_TOKEN_KEY);
    } catch {
      /* ignore storage errors */
    }
  },

  isAuthenticated: (): boolean => accessToken !== null,
};
