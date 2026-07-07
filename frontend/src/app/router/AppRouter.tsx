/**
 * Application router.
 * Defines all routes for Vendor Ledger Reconciliation application.
 */

import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { LoginPage } from '@features/authentication/pages/LoginPage';
import { MicrosoftCallbackPage } from '@features/authentication/pages/MicrosoftCallbackPage';
import { ManagePartyPage } from '@features/vendor-management/pages/ManagePartyPage';
import { EditPartyPage } from '@features/vendor-management/pages/EditPartyPage';
import { RequestStatementPage } from '@features/request-statement/pages/RequestStatementPage';
import { DirectReconciliationPage } from '@features/direct-reconciliation/pages/DirectReconciliationPage';
import { TrackReconciliationPage } from '@features/track-reconciliation/pages/TrackReconciliationPage';
import { ReconciliationDetailPage } from '@features/track-reconciliation/pages/ReconciliationDetailPage';
import { RolesPage } from '@features/rbac-admin/pages/RolesPage';
import { AuditLogsPage } from '@features/rbac-admin/pages/AuditLogsPage';
import { ExceptionListPage } from '@features/exceptions/ExceptionListPage';
import { ReportsPage } from '@features/reports/pages/ReportsPage';
import { NotificationHistoryPage } from '@features/notifications/pages/NotificationHistoryPage';
import { SettingsPage } from '@features/vlr-settings/SettingsPage';
import { PortalAuthPage } from '@features/vendor-portal/PortalAuthPage';
import { PortalUploadPage } from '@features/vendor-portal/PortalUploadPage';
import { PortalStatementPage } from '@features/vendor-portal/PortalStatementPage';
import { PortalSignOffPage } from '@features/vendor-portal/PortalSignOffPage';
import { MainLayout } from '@app/layouts/MainLayout';
import { PrivateRoute } from './PrivateRoute';

export const AppRouter = () => {
  return (
    <BrowserRouter>
      <Routes>
        {/* Public routes */}
        <Route path="/login" element={<LoginPage />} />
        <Route path="/auth/microsoft/callback" element={<MicrosoftCallbackPage />} />

        {/* Vendor Portal — public routes (token-based auth) */}
        <Route path="/portal/auth" element={<PortalAuthPage />} />
        <Route path="/portal/upload" element={<PortalUploadPage />} />
        <Route path="/portal/statement" element={<PortalStatementPage />} />
        <Route path="/portal/sign-off" element={<PortalSignOffPage />} />

        {/* Protected routes with layout */}
        <Route
          path="/"
          element={
            <PrivateRoute>
              <MainLayout />
            </PrivateRoute>
          }
        >
          <Route index element={<Navigate to="/manage-party" replace />} />

          {/* Core reconciliation pages */}
          <Route path="manage-party" element={<ManagePartyPage />} />
          <Route path="manage-party/:id" element={<EditPartyPage />} />
          <Route path="request-statement" element={<RequestStatementPage />} />
          <Route path="direct-reconciliation" element={<DirectReconciliationPage />} />
          <Route path="track-reconciliation" element={<TrackReconciliationPage />} />
          <Route path="track-reconciliation/:requestId" element={<ReconciliationDetailPage />} />

          {/* Exception Management */}
          <Route path="exceptions" element={<ExceptionListPage />} />

          {/* Reports & MIS */}
          <Route path="reports" element={<ReportsPage />} />

          {/* Notifications */}
          <Route path="notifications" element={<NotificationHistoryPage />} />

          {/* Access Management */}
          <Route path="access-management" element={<Navigate to="/access-management/roles" replace />} />
          <Route path="access-management/roles" element={<RolesPage />} />
          <Route path="access-management/audit-logs" element={<AuditLogsPage />} />

          {/* Settings */}
          <Route path="settings" element={<SettingsPage />} />

          {/* Automation */}
          <Route
            path="automation"
            element={<div className="p-4"><h2>Automation</h2><p>Automation module coming soon.</p></div>}
          />

          {/* ERP Integration */}
          <Route
            path="erp-integration"
            element={<div className="p-4"><h2>ERP Integration</h2><p>ERP Integration module coming soon.</p></div>}
          />
        </Route>

        {/* Unauthorized */}
        <Route
          path="/unauthorized"
          element={
            <div className="flex align-items-center justify-content-center min-h-screen">
              <div className="text-center">
                <h1 className="text-4xl" style={{ color: 'var(--color-error)' }}>403</h1>
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
