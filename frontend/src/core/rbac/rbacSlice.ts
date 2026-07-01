/**
 * RBAC Redux slice.
 * Manages the user's permissions state fetched from the backend.
 * Loaded after authentication and used throughout the app.
 */

import { createAsyncThunk, createSlice, PayloadAction } from '@reduxjs/toolkit';
import { rbacApi } from './rbacApi';
import type { FieldPermissionsResponse, MenuPermissionsResponse, Permission, PermissionAction } from './types';

interface RbacState {
  /** Menu keys the user can access */
  menuKeys: string[];
  /** All menu permissions for detailed checks */
  menuPermissions: Permission[];
  /** Field-level permissions by resource */
  fieldPermissions: Record<string, Record<string, PermissionAction[]>>;
  /** Whether RBAC data has been loaded */
  isLoaded: boolean;
  isLoading: boolean;
  error: string | null;
}

const initialState: RbacState = {
  menuKeys: [],
  menuPermissions: [],
  fieldPermissions: {},
  isLoaded: false,
  isLoading: false,
  error: null,
};

/**
 * Fetch menu permissions after login.
 */
export const fetchMenuPermissions = createAsyncThunk(
  'rbac/fetchMenuPermissions',
  async (_, { rejectWithValue }) => {
    try {
      return await rbacApi.getMenuPermissions();
    } catch (error: any) {
      return rejectWithValue(error.response?.data?.detail || 'Failed to load permissions');
    }
  }
);

/**
 * Fetch field-level permissions for a specific resource (lazy-loaded).
 */
export const fetchFieldPermissions = createAsyncThunk(
  'rbac/fetchFieldPermissions',
  async (resource: string, { rejectWithValue }) => {
    try {
      return await rbacApi.getFieldPermissions(resource);
    } catch (error: any) {
      return rejectWithValue(error.response?.data?.detail || 'Failed to load field permissions');
    }
  }
);

const rbacSlice = createSlice({
  name: 'rbac',
  initialState,
  reducers: {
    clearRbac: () => initialState,
  },
  extraReducers: (builder) => {
    builder
      // Menu permissions
      .addCase(fetchMenuPermissions.pending, (state) => {
        state.isLoading = true;
        state.error = null;
      })
      .addCase(fetchMenuPermissions.fulfilled, (state, action: PayloadAction<MenuPermissionsResponse>) => {
        state.isLoading = false;
        state.isLoaded = true;
        state.menuKeys = action.payload.menu_keys;
        state.menuPermissions = action.payload.permissions;
      })
      .addCase(fetchMenuPermissions.rejected, (state, action) => {
        state.isLoading = false;
        state.error = action.payload as string;
      })
      // Field permissions
      .addCase(fetchFieldPermissions.fulfilled, (state, action: PayloadAction<FieldPermissionsResponse>) => {
        state.fieldPermissions[action.payload.resource] = action.payload.fields;
      });
  },
});

export const { clearRbac } = rbacSlice.actions;
export default rbacSlice.reducer;
