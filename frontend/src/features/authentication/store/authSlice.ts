/**
 * Authentication Redux slice.
 * Manages global auth state: user, tokens, loading, errors.
 * Automatically loads RBAC permissions on successful authentication.
 */

import { createSlice, createAsyncThunk, PayloadAction } from '@reduxjs/toolkit';
import { authApi } from '../api/authApi';
import { fetchMenuPermissions } from '@core/rbac';
import type { AuthState, CurrentUser, LoginRequest } from '../models/auth.types';

const initialState: AuthState = {
  user: null,
  isAuthenticated: false,
  isLoading: false,
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
      });
  },
});

export const { logout, clearError } = authSlice.actions;
export default authSlice.reducer;
