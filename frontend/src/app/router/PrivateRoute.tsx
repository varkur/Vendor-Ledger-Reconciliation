/**
 * Protected route wrapper.
 * Redirects to /login if not authenticated.
 * Uses RBAC menu permissions for access control.
 *
 * DEV MODE: Set VITE_DEV_BYPASS_AUTH=true in .env to skip auth checks.
 */

import { Navigate, useLocation } from 'react-router-dom';
import { useAppSelector } from '@app/store';

interface PrivateRouteProps {
  children: React.ReactNode;
  menuKey?: string;
}

const DEV_BYPASS_AUTH = import.meta.env.VITE_DEV_BYPASS_AUTH === 'true';

export const PrivateRoute = ({ children, menuKey }: PrivateRouteProps) => {
  const { isAuthenticated } = useAppSelector((state) => state.auth);
  const { menuKeys, isLoaded: rbacLoaded } = useAppSelector((state) => state.rbac);
  const location = useLocation();

  // In dev mode, bypass auth entirely
  if (DEV_BYPASS_AUTH) {
    return <>{children}</>;
  }

  if (!isAuthenticated) {
    // Save intended destination
    sessionStorage.setItem('redirectAfterLogin', location.pathname);
    return <Navigate to="/login" replace />;
  }

  // If a menuKey is specified, check RBAC permissions
  if (menuKey) {
    if (!rbacLoaded) {
      // Still loading permissions — show nothing briefly
      return null;
    }
    if (!menuKeys.includes(menuKey)) {
      return <Navigate to="/unauthorized" replace />;
    }
  }

  return <>{children}</>;
};
