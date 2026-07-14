/**
 * Entity/Company Redux slice.
 * Manages which company entity is currently selected.
 * When the selected entity changes, data-dependent queries should refetch.
 */

import { createSlice, createAsyncThunk, PayloadAction } from '@reduxjs/toolkit';
import { apiClient } from '@shared/services/apiClient';

// ─────────────────────────────────────────────────────────────────────────────
// Types
// ─────────────────────────────────────────────────────────────────────────────

export interface CompanyEntity {
  id: string;
  company_code: string;
  name: string;
  entity_type: string;
  pan_card: string;
  is_active: boolean;
}

interface EntityState {
  entities: CompanyEntity[];
  selectedEntity: CompanyEntity | null;
  isLoading: boolean;
  error: string | null;
}

// ─────────────────────────────────────────────────────────────────────────────
// Initial state
// ─────────────────────────────────────────────────────────────────────────────

const initialState: EntityState = {
  entities: [],
  selectedEntity: null,
  isLoading: false,
  error: null,
};

// ─────────────────────────────────────────────────────────────────────────────
// Async thunks
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Fetch list of entities the current user has access to.
 */
export const fetchEntities = createAsyncThunk(
  'entity/fetchEntities',
  async (_, { rejectWithValue }) => {
    try {
      const { data } = await apiClient.get<CompanyEntity[]>('/vlr/settings/entities');
      return data;
    } catch (error: any) {
      return rejectWithValue(error.response?.data?.detail || 'Failed to load entities');
    }
  }
);

// ─────────────────────────────────────────────────────────────────────────────
// Slice
// ─────────────────────────────────────────────────────────────────────────────

const entitySlice = createSlice({
  name: 'entity',
  initialState,
  reducers: {
    selectEntity: (state, action: PayloadAction<CompanyEntity>) => {
      state.selectedEntity = action.payload;
      // Persist selection in sessionStorage for page refreshes
      sessionStorage.setItem('selectedEntityId', action.payload.id);
    },
    clearEntities: (state) => {
      state.entities = [];
      state.selectedEntity = null;
      sessionStorage.removeItem('selectedEntityId');
    },
  },
  extraReducers: (builder) => {
    builder
      .addCase(fetchEntities.pending, (state) => {
        state.isLoading = true;
        state.error = null;
      })
      .addCase(fetchEntities.fulfilled, (state, action: PayloadAction<CompanyEntity[]>) => {
        state.isLoading = false;
        state.entities = action.payload;

        // Restore previous selection or default to first entity
        const savedId = sessionStorage.getItem('selectedEntityId');
        const savedEntity = action.payload.find((e) => e.id === savedId);

        if (savedEntity) {
          state.selectedEntity = savedEntity;
        } else if (action.payload.length > 0) {
          state.selectedEntity = action.payload[0];
          sessionStorage.setItem('selectedEntityId', action.payload[0].id);
        }
      })
      .addCase(fetchEntities.rejected, (state, action) => {
        state.isLoading = false;
        state.error = action.payload as string;
      });
  },
});

export const { selectEntity, clearEntities } = entitySlice.actions;
export default entitySlice.reducer;
