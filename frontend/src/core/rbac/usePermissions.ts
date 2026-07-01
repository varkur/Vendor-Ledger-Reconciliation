/**
 * Permission hooks for components.
 * Provides declarative access to RBAC checks throughout the app.
 */

import { useCallback, useEffect } from 'react';
import { useAppDispatch, useAppSelector } from '@app/store';
import { fetchFieldPermissions, fetchMenuPermissions } from './rbacSlice';
import type { PermissionAction } from './types';

/**
 * Hook to check if the current user has access to a specific menu item.
 *
 * @example
 * const { canAccess } = useMenuPermission('users');
 * if (canAccess) { ... }
 */
export const useMenuPermission = (menuKey: string) => {
  const { menuKeys, isLoaded } = useAppSelector((state) => state.rbac);

  return {
    canAccess: isLoaded && menuKeys.includes(menuKey),
    isLoaded,
  };
};

/**
 * Hook to get all menu keys the user can access.
 * Used by navigation components to filter visible items.
 *
 * @example
 * const { menuKeys, isLoaded } = useMenuPermissions();
 */
export const useMenuPermissions = () => {
  const dispatch = useAppDispatch();
  const { menuKeys, isLoaded, isLoading } = useAppSelector((state) => state.rbac);

  useEffect(() => {
    if (!isLoaded && !isLoading) {
      dispatch(fetchMenuPermissions());
    }
  }, [dispatch, isLoaded, isLoading]);

  return { menuKeys, isLoaded, isLoading };
};

/**
 * Hook to check field-level permissions for a resource.
 * Lazy-loads field permissions on first access.
 *
 * @example
 * const { canReadField, canWriteField } = useFieldPermissions('users');
 * const showSalary = canReadField('salary');
 * const canEditEmail = canWriteField('email');
 */
export const useFieldPermissions = (resource: string) => {
  const dispatch = useAppDispatch();
  const fieldPermissions = useAppSelector(
    (state) => state.rbac.fieldPermissions[resource]
  );

  useEffect(() => {
    if (!fieldPermissions) {
      dispatch(fetchFieldPermissions(resource));
    }
  }, [dispatch, resource, fieldPermissions]);

  const canReadField = useCallback(
    (fieldName: string): boolean => {
      if (!fieldPermissions) return false;
      const actions = fieldPermissions[fieldName];
      return actions ? actions.includes('READ') : false;
    },
    [fieldPermissions]
  );

  const canWriteField = useCallback(
    (fieldName: string): boolean => {
      if (!fieldPermissions) return false;
      const actions = fieldPermissions[fieldName];
      return actions ? actions.includes('UPDATE') : false;
    },
    [fieldPermissions]
  );

  const getFieldActions = useCallback(
    (fieldName: string): PermissionAction[] => {
      if (!fieldPermissions) return [];
      return fieldPermissions[fieldName] || [];
    },
    [fieldPermissions]
  );

  return { canReadField, canWriteField, getFieldActions, isLoaded: !!fieldPermissions };
};

/**
 * Hook to check a specific permission code.
 *
 * @example
 * const hasPermission = useHasPermission('reports.export');
 */
export const useHasPermission = (permissionCode: string): boolean => {
  const { menuPermissions, isLoaded } = useAppSelector((state) => state.rbac);
  if (!isLoaded) return false;
  return menuPermissions.some((p) => p.code === permissionCode);
};
