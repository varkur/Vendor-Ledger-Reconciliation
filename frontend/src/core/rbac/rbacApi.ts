/**
 * RBAC API client.
 * Fetches permissions from the backend for the current user.
 */

import { apiClient } from '@shared/services/apiClient';
import type { FieldPermissionsResponse, MenuPermissionsResponse } from './types';

const RBAC_BASE = '/rbac';

export const rbacApi = {
  /**
   * Get the current user's menu-level permissions.
   * Used to determine which navigation items to show/hide.
   */
  async getMenuPermissions(): Promise<MenuPermissionsResponse> {
    const response = await apiClient.get<MenuPermissionsResponse>(
      `${RBAC_BASE}/my-permissions/menu`
    );
    return response.data;
  },

  /**
   * Get field-level permissions for a specific resource.
   * Used to control field visibility/editability in forms.
   */
  async getFieldPermissions(resource: string): Promise<FieldPermissionsResponse> {
    const response = await apiClient.get<FieldPermissionsResponse>(
      `${RBAC_BASE}/my-permissions/fields/${resource}`
    );
    return response.data;
  },
};
