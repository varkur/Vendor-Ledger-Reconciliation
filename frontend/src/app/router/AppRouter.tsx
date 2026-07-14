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
import { ReconciliationOutputPage } from '@features/track-reconciliation/pages/ReconciliationOutputPage';
import { RolesPage } from '@features/rbac-admin/pages/RolesPage';
import { AuditLogsPage } from '@features/rbac-admin/pages/AuditLogsPage';
import { ExceptionListPage } from '@features/exceptions/ExceptionListPage';
import { ApprovalsPage } from '@features/approvals/pages/ApprovalsPage';
import { ReportsPage } from '@features/reports/pages/ReportsPage';
import { NotificationHistoryPage } from '@features/notifications/pages/NotificationHistoryPage';
import { SettingsPage } from '@features/vlr-settings/SettingsPage';
import { CompanyProfilePage } from '@features/vlr-settings/pages/CompanyProfilePage';
import { AddEntityPage } from '@features/vlr-settings/pages/AddEntityPage';
import { EmailConfigPage } from '@features/vlr-settings/pages/EmailConfigPage';
import { RemindersPage } from '@features/vlr-settings/pages/RemindersPage';
import { EmailTemplatesPage } from '@features/vlr-settings/pages/EmailTemplatesPage';
import { DocumentTypesPage } from '@features/vlr-settings/pages/DocumentTypesPage';
import { PortalAuthPage } from '@features/vendor-portal/PortalAuthPage';
import { PortalUploadPage } from '@features/vendor-portal/PortalUploadPage';
import { PortalStatementPage } from '@features/vendor-portal/PortalStatementPage';
import { PortalSignOffPage } from '@features/vendor-portal/PortalSignOffPage';
import { PortalProvider } from '@features/vendor-portal/context/PortalContext';
import { DashboardPage } from '@features/dashboard/pages/DashboardPage';
import { WorkflowDefinitionsPage } from '@features/workflow-admin/pages/WorkflowDefinitionsPage';
import { ApprovalMatrixPage } from '@features/workflow-admin/pages/ApprovalMatrixPage';
import { WorkflowBuilderPage } from '@features/workflow-admin/pages/WorkflowBuilderPage';
import { MainLayout } from '@app/layouts/MainLayout';
import { PrivateRoute } from './PrivateRoute';

export const AppRouter = () => {
  return (
    <BrowserRouter>
      <Routes>
        {/* Public routes */}
        <Route path="/login" element={<LoginPage />} />
        <Route path="/auth/microsoft/callback" element={<MicrosoftCallbackPage />} />

        {/* Vendor Portal — public routes (token-based auth, wrapped in PortalProvider) */}
        <Route path="/portal/auth" element={<PortalProvider><PortalAuthPage /></PortalProvider>} />
        <Route path="/portal/upload" element={<PortalProvider><PortalUploadPage /></PortalProvider>} />
        <Route path="/portal/statement" element={<PortalProvider><PortalStatementPage /></PortalProvider>} />
        <Route path="/portal/sign-off" element={<PortalProvider><PortalSignOffPage /></PortalProvider>} />

        {/* Protected routes with layout */}
        <Route
          path="/"
          element={
            <PrivateRoute>
              <MainLayout />
            </PrivateRoute>
          }
        >
          <Route index element={<DashboardPage />} />
          <Route path="dashboard" element={<DashboardPage />} />

          {/* Core reconciliation pages */}
          <Route path="manage-party" element={<ManagePartyPage />} />
          <Route path="manage-party/:id" element={<EditPartyPage />} />
          <Route path="request-statement" element={<RequestStatementPage />} />
          <Route path="direct-reconciliation" element={<DirectReconciliationPage />} />
          <Route path="track-reconciliation" element={<TrackReconciliationPage />} />
          <Route path="track-reconciliation/:requestId" element={<ReconciliationDetailPage />} />
          <Route path="track-reconciliation/:requestId/case/:caseId" element={<ReconciliationOutputPage />} />

          {/* Exception Management */}
          <Route path="exceptions" element={<ExceptionListPage />} />

          {/* Approvals */}
          <Route path="approvals" element={<ApprovalsPage />} />

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
          <Route path="settings/company-profile" element={<CompanyProfilePage />} />
          <Route path="settings/add-entity" element={<AddEntityPage />} />
          <Route path="settings/email-config" element={<EmailConfigPage />} />
          <Route path="settings/reminders" element={<RemindersPage />} />
          <Route path="settings/email-templates" element={<EmailTemplatesPage />} />
          <Route path="settings/document-types" element={<DocumentTypesPage />} />
          <Route path="settings/workflow-definitions" element={<WorkflowDefinitionsPage />} />
          <Route path="settings/approval-matrix" element={<ApprovalMatrixPage />} />

          {/* Workflow Builder (accessed from Workflow Definitions) */}
          <Route path="workflow-builder/:definitionId" element={<WorkflowBuilderPage />} />

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
