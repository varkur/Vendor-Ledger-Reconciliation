/** Authentication domain models */

export interface LoginRequest {
  username: string;
  password: string;
}

export interface RefreshRequest {
  refresh_token: string;
}

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
}

export interface CurrentUser {
  id: string;
  username: string;
  email?: string;
  is_active: boolean;
}

export interface AuthState {
  user: CurrentUser | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  /** True while restoring the session from stored tokens on app startup. */
  isInitializing: boolean;
  error: string | null;
}
