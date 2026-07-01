/**
 * RBAC module public API.
 */

// Components
export { FieldGate, MenuGate, PermissionGate } from './PermissionGate';

// Hooks
export {
  useFieldPermissions,
  useHasPermission,
  useMenuPermission,
  useMenuPermissions,
} from './usePermissions';

// Redux
export { clearRbac, fetchFieldPermissions, fetchMenuPermissions } from './rbacSlice';
export { default as rbacReducer } from './rbacSlice';

// Types
export type {
  AuditLogEntry,
  AuditLogListResponse,
  FieldPermissionsResponse,
  MenuPermissionsResponse,
  Permission,
  PermissionAction,
  PermissionScope,
  Role,
  RoleAssignment,
} from './types';

// API
export { rbacApi } from './rbacApi';
