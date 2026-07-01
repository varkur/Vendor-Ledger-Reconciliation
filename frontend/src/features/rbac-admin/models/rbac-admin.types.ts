/**
 * RBAC Admin feature types.
 */

export interface Permission {
  id: string;
  code: string;
  name: string;
  description: string;
  scope: 'MENU' | 'API' | 'FIELD';
  resource: string;
  action: string;
  is_active: boolean;
  created_date: string;
}

export interface Role {
  id: string;
  code: string;
  name: string;
  description: string;
  is_system: boolean;
  is_active: boolean;
  tenant_id: string | null;
  parent_role_id: string | null;
  permissions: Permission[];
  created_date: string;
  modified_date: string;
}

export interface RoleListResponse {
  roles: Role[];
  total: number;
}

export interface CreateRoleRequest {
  code: string;
  name: string;
  description?: string;
  tenant_id?: string;
  parent_role_id?: string;
}

export interface UpdateRoleRequest {
  name?: string;
  description?: string;
  is_active?: boolean;
  parent_role_id?: string;
}

export interface RoleAssignRequest {
  user_id: string;
  role_id: string;
  tenant_id?: string;
}

export interface PermissionGrantRequest {
  role_id: string;
  permission_id: string;
}

export interface AuditLogEntry {
  id: string;
  actor_id: string | null;
  actor_username: string;
  action: string;
  resource_type: string;
  resource_id: string;
  tenant_id: string | null;
  old_value: string | null;
  new_value: string | null;
  ip_address: string;
  user_agent: string;
  extra_data: string | null;
  created_at: string;
}

export interface AuditLogListResponse {
  logs: AuditLogEntry[];
  total: number;
  skip: number;
  limit: number;
}
