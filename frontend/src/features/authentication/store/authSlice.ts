/**
 * Authentication Redux slice.
 * Manages global auth state: user, tokens, loading, errors.
 * Automatically loads RBAC permissions on successful authentication.
 */

import { createSlice, createAsyncThunk, PayloadAction } from '@reduxjs/toolkit';
import { authApi } from '../api/authApi';
import { storageService } from '@shared/services/storageService';
import { fetchMenuPermissions } from '@core/rbac';
import type { AuthState, CurrentUser, LoginRequest } from '../models/auth.types';

const initialState: AuthState = {
  user: null,
  isAuthenticated: false,
  isLoading: false,
  // Start in "initializing" only if there's a stored token to restore.
  // This prevents PrivateRoute from redirecting to /login before we've had a
  // chance to rehydrate the session after a page refresh.
  isInitializing: storageService.isAuthenticated(),
  error: null,
};

export const loginThunk = createAsyncThunk(
  'auth/login',
  async (credentials: LoginRequest, { dispatch, rejectWithValue }) => {
    try {
      await authApi.login(credentials);
      const user = await authApi.getCurrentUser();
      // Load RBAC permissions immediately after authentication
      dispatch(fetchMenuPermissions());
      return user;
    } catch (error: any) {
      const message =
        error.response?.data?.detail || 'Login failed. Please try again.';
      return rejectWithValue(message);
    }
  }
);

export const fetchCurrentUser = createAsyncThunk(
  'auth/fetchCurrentUser',
  async (_, { dispatch, rejectWithValue }) => {
    try {
      const user = await authApi.getCurrentUser();
      // Load RBAC permissions on session restoration
      dispatch(fetchMenuPermissions());
      return user;
    } catch {
      return rejectWithValue('Session expired');
    }
  }
);

/**
 * Restore the session on app startup after a page refresh.
 * If a token is present in storage, re-fetch the current user (and RBAC).
 * If not, resolve immediately so the app leaves the "initializing" state.
 */
export const restoreSession = createAsyncThunk(
  'auth/restoreSession',
  async (_, { dispatch, rejectWithValue }) => {
    if (!storageService.isAuthenticated()) {
      return rejectWithValue('No stored session');
    }
    try {
      const user = await authApi.getCurrentUser();
      dispatch(fetchMenuPermissions());
      return user;
    } catch {
      // Token invalid/expired — clear it so we don't loop.
      authApi.logout();
      return rejectWithValue('Session expired');
    }
  }
);

const authSlice = createSlice({
  name: 'auth',
  initialState,
  reducers: {
    logout: (state) => {
      authApi.logout();
      state.user = null;
      state.isAuthenticated = false;
      state.error = null;
      // Note: RBAC state is cleared via clearRbac dispatch in component
    },
    clearError: (state) => {
      state.error = null;
    },
  },
  extraReducers: (builder) => {
    builder
      // Login
      .addCase(loginThunk.pending, (state) => {
        state.isLoading = true;
        state.error = null;
      })
      .addCase(loginThunk.fulfilled, (state, action: PayloadAction<CurrentUser>) => {
        state.isLoading = false;
        state.isAuthenticated = true;
        state.user = action.payload;
      })
      .addCase(loginThunk.rejected, (state, action) => {
        state.isLoading = false;
        state.error = action.payload as string;
      })
      // Fetch current user
      .addCase(fetchCurrentUser.pending, (state) => {
        state.isLoading = true;
      })
      .addCase(fetchCurrentUser.fulfilled, (state, action) => {
        state.isLoading = false;
        state.isAuthenticated = true;
        state.user = action.payload;
      })
      .addCase(fetchCurrentUser.rejected, (state) => {
        state.isLoading = false;
        state.isAuthenticated = false;
        state.user = null;
      })
      // Restore session on startup / refresh
      .addCase(restoreSession.pending, (state) => {
        state.isInitializing = true;
      })
      .addCase(restoreSession.fulfilled, (state, action: PayloadAction<CurrentUser>) => {
        state.isInitializing = false;
        state.isAuthenticated = true;
        state.user = action.payload;
      })
      .addCase(restoreSession.rejected, (state) => {
        state.isInitializing = false;
        state.isAuthenticated = false;
        state.user = null;
      });
  },
});

export const { logout, clearError } = authSlice.actions;
export default authSlice.reducer;
