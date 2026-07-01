/**
 * RBAC Admin API client.
 * Provides CRUD operations for roles, permissions, and audit logs.
 */

import { apiClient } from '@shared/services/apiClient';
import type {
  AuditLogListResponse,
  CreateRoleRequest,
  Permission,
  PermissionGrantRequest,
  RoleAssignRequest,
  RoleListResponse,
  UpdateRoleRequest,
} from '../models/rbac-admin.types';

const BASE = '/rbac';

export const rbacAdminApi = {
  // ─── Roles ───

  async listRoles(tenantId?: string): Promise<RoleListResponse> {
    const params = tenantId ? { tenant_id: tenantId } : {};
    const response = await apiClient.get<RoleListResponse>(`${BASE}/roles`, { params });
    return response.data;
  },

  async createRole(data: CreateRoleRequest): Promise<any> {
    const response = await apiClient.post(`${BASE}/roles`, data);
    return response.data;
  },

  async updateRole(roleId: string, data: UpdateRoleRequest): Promise<any> {
    const response = await apiClient.patch(`${BASE}/roles/${roleId}`, data);
    return response.data;
  },

  // ─── Permissions ───

  async listPermissions(scope?: string): Promise<Permission[]> {
    const params = scope ? { scope } : {};
    const response = await apiClient.get<Permission[]>(`${BASE}/permissions`, { params });
    return response.data;
  },

  async grantPermission(data: PermissionGrantRequest): Promise<any> {
    const response = await apiClient.post(`${BASE}/roles/grant-permission`, data);
    return response.data;
  },

  async revokePermission(data: PermissionGrantRequest): Promise<any> {
    const response = await apiClient.post(`${BASE}/roles/revoke-permission`, data);
    return response.data;
  },

  // ─── Role Assignments ───

  async assignRole(data: RoleAssignRequest): Promise<any> {
    const response = await apiClient.post(`${BASE}/assignments`, data);
    return response.data;
  },

  async revokeRole(data: RoleAssignRequest): Promise<any> {
    const response = await apiClient.post(`${BASE}/assignments/revoke`, data);
    return response.data;
  },

  // ─── Audit Logs ───

  async listAuditLogs(params?: {
    action?: string;
    actor_username?: string;
    resource_type?: string;
    skip?: number;
    limit?: number;
  }): Promise<AuditLogListResponse> {
    const response = await apiClient.get<AuditLogListResponse>(`${BASE}/audit-logs`, { params });
    return response.data;
  },
};
