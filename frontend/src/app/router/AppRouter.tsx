/**
 * Application router.
 * Defines all routes with authentication and RBAC guards.
 */

import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { LoginPage } from '@features/authentication/pages/LoginPage';
import { MicrosoftCallbackPage } from '@features/authentication/pages/MicrosoftCallbackPage';
import { UserListPage } from '@features/user-management/pages/UserListPage';
import { EmployeeADServicePage } from '@features/service-menu/pages/EmployeeADServicePage';
import { RolesPage } from '@features/rbac-admin/pages/RolesPage';
import { AuditLogsPage } from '@features/rbac-admin/pages/AuditLogsPage';
import { WorkflowDefinitionsPage, WorkflowBuilderPage, ApprovalMatrixPage } from '@features/workflow-admin';
import { CommissionClaimsPage } from '@features/commission-claims';
import { MainLayout } from '@app/layouts/MainLayout';
import { PrivateRoute } from './PrivateRoute';

export const AppRouter = () => {
  return (
    <BrowserRouter>
      <Routes>
        {/* Public routes */}
        <Route path="/login" element={<LoginPage />} />
        <Route path="/auth/microsoft/callback" element={<MicrosoftCallbackPage />} />

        {/* Protected routes with layout */}
        <Route
          path="/"
          element={
            <PrivateRoute>
              <MainLayout />
            </PrivateRoute>
          }
        >
          <Route index element={<Navigate to="/dashboard" replace />} />
          <Route
            path="dashboard"
            element={<div className="p-4"><h2>Dashboard</h2><p>Welcome to the Enterprise App</p></div>}
          />
          <Route
            path="users"
            element={
              <PrivateRoute menuKey="users">
                <UserListPage />
              </PrivateRoute>
            }
          />
          <Route
            path="roles"
            element={
              <PrivateRoute menuKey="roles">
                <RolesPage />
              </PrivateRoute>
            }
          />
          <Route
            path="audit-logs"
            element={
              <PrivateRoute menuKey="audit_logs">
                <AuditLogsPage />
              </PrivateRoute>
            }
          />
          <Route
            path="services/employee-ad"
            element={
              <PrivateRoute menuKey="services">
                <EmployeeADServicePage />
              </PrivateRoute>
            }
          />
          <Route
            path="workflows"
            element={
              <PrivateRoute menuKey="workflows">
                <WorkflowDefinitionsPage />
              </PrivateRoute>
            }
          />
          <Route
            path="workflow-builder/:definitionId"
            element={
              <PrivateRoute menuKey="workflows">
                <WorkflowBuilderPage />
              </PrivateRoute>
            }
          />
          <Route
            path="approval-matrix"
            element={
              <PrivateRoute menuKey="workflows">
                <ApprovalMatrixPage />
              </PrivateRoute>
            }
          />
          <Route
            path="claims"
            element={
              <PrivateRoute menuKey="dashboard">
                <CommissionClaimsPage />
              </PrivateRoute>
            }
          />
        </Route>

        {/* Unauthorized */}
        <Route
          path="/unauthorized"
          element={
            <div className="flex align-items-center justify-content-center min-h-screen">
              <div className="text-center">
                <h1 className="text-4xl text-red-500">403</h1>
                <p className="text-600">You don't have permission to access this page.</p>
              </div>
            </div>
          }
        />

        {/* Catch-all */}
        <Route path="*" element={<Navigate to="/login" replace />} />
      </Routes>
    </BrowserRouter>
  );
};
