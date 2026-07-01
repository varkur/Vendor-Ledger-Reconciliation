/**
 * Declarative permission-based rendering components.
 * Use these to conditionally show/hide UI elements based on permissions.
 */

import React from 'react';
import { useMenuPermission, useHasPermission, useFieldPermissions } from './usePermissions';

interface PermissionGateProps {
  /** The permission code required to render children */
  permission: string;
  /** Content to render when permission is granted */
  children: React.ReactNode;
  /** Optional fallback when permission is denied */
  fallback?: React.ReactNode;
}

/**
 * Renders children only if the user has the specified permission.
 *
 * @example
 * <PermissionGate permission="users.create">
 *   <CreateUserButton />
 * </PermissionGate>
 */
export const PermissionGate: React.FC<PermissionGateProps> = ({
  permission,
  children,
  fallback = null,
}) => {
  const hasPermission = useHasPermission(permission);
  return <>{hasPermission ? children : fallback}</>;
};

interface MenuGateProps {
  /** The menu key required to render children */
  menuKey: string;
  children: React.ReactNode;
  fallback?: React.ReactNode;
}

/**
 * Renders children only if the user has access to the specified menu.
 *
 * @example
 * <MenuGate menuKey="users">
 *   <NavItem to="/users" label="Users" />
 * </MenuGate>
 */
export const MenuGate: React.FC<MenuGateProps> = ({
  menuKey,
  children,
  fallback = null,
}) => {
  const { canAccess, isLoaded } = useMenuPermission(menuKey);

  if (!isLoaded) return null; // Loading state
  return <>{canAccess ? children : fallback}</>;
};

interface FieldGateProps {
  /** Resource name (e.g., "users") */
  resource: string;
  /** Field name (e.g., "salary") */
  field: string;
  /** Required action for the field */
  action?: 'READ' | 'UPDATE';
  children: React.ReactNode;
  fallback?: React.ReactNode;
}

/**
 * Renders children only if the user has the specified field-level permission.
 *
 * @example
 * <FieldGate resource="employees" field="salary" action="READ">
 *   <SalaryDisplay value={employee.salary} />
 * </FieldGate>
 */
export const FieldGate: React.FC<FieldGateProps> = ({
  resource,
  field,
  action = 'READ',
  children,
  fallback = null,
}) => {
  const { canReadField, canWriteField, isLoaded } = useFieldPermissions(resource);

  if (!isLoaded) return null;

  const hasAccess = action === 'READ' ? canReadField(field) : canWriteField(field);
  return <>{hasAccess ? children : fallback}</>;
};
