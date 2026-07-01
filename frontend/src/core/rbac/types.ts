/**
 * RBAC type definitions.
 * Mirrors the backend permission model for frontend consumption.
 */

export type PermissionScope = 'MENU' | 'API' | 'FIELD';
export type PermissionAction = 'CREATE' | 'READ' | 'UPDATE' | 'DELETE' | 'EXECUTE' | 'EXPORT' | 'IMPORT' | 'APPROVE';

export interface Permission {
  id: string;
  code: string;
  name: string;
  description: string;
  scope: PermissionScope;
  resource: string;
  action: PermissionAction;
  is_active: boolean;
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
}

export interface MenuPermissionsResponse {
  menu_keys: string[];
  permissions: Permission[];
}

export interface FieldPermissionsResponse {
  resource: string;
  fields: Record<string, PermissionAction[]>;
}

export interface RoleAssignment {
  id: string;
  user_id: string;
  role_id: string;
  tenant_id: string | null;
  is_active: boolean;
  created_date: string;
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
  metadata: string | null;
  created_at: string;
}

export interface AuditLogListResponse {
  logs: AuditLogEntry[];
  total: number;
  skip: number;
  limit: number;
}
