/**
 * Dashboard page — real-time KPI widgets and recent confirmations table.
 * Uses React Query with auto-refresh (30s) for live dashboard updates.
 *
 * Requirements: 26.1, 26.2, 26.3, 26.4, 26.5, 26.6, 26.7, 26.8
 */

import { DataTable, DataTableSortEvent } from 'primereact/datatable';
import { Column } from 'primereact/column';
import { ProgressSpinner } from 'primereact/progressspinner';
import { Message } from 'primereact/message';
import { Button } from 'primereact/button';
import { useState, useCallback } from 'react';

import { useDashboardWidgets, useRecentConfirmations } from '../hooks/useDashboard';
import type { RecentConfirmation } from '../api/dashboardApi';

// ─────────────────────────────────────────────────────────────────────────────
// Widget Card Component
// ─────────────────────────────────────────────────────────────────────────────

interface WidgetCardProps {
  icon: string;
  iconColor: string;
  iconBg: string;
  label: string;
  value: string | number;
  trend?: 'up' | 'down' | 'neutral';
}

const WidgetCard = ({ icon, iconColor, iconBg, label, value, trend }: WidgetCardProps) => (
  <div className="em-card" style={{ padding: '1.25rem', display: 'flex', alignItems: 'center', gap: '1rem' }}>
    <div
      style={{
        width: 48,
        height: 48,
        borderRadius: '50%',
        backgroundColor: iconBg,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        flexShrink: 0,
      }}
    >
      <i className={icon} style={{ fontSize: '1.25rem', color: iconColor }} />
    </div>
    <div style={{ flex: 1 }}>
      <div style={{ fontSize: '1.5rem', fontWeight: 700, lineHeight: 1.2 }}>{value}</div>
      <div style={{ fontSize: '0.85rem', color: 'var(--color-text-muted)', marginTop: '0.25rem' }}>
        {label}
        {trend && trend !== 'neutral' && (
          <i
            className={trend === 'up' ? 'pi pi-arrow-up' : 'pi pi-arrow-down'}
            style={{
              fontSize: '0.75rem',
              marginLeft: '0.5rem',
              color: trend === 'up' ? 'var(--green-500)' : 'var(--red-500)',
            }}
          />
        )}
      </div>
    </div>
  </div>
);

// ─────────────────────────────────────────────────────────────────────────────
// Dashboard Page
// ─────────────────────────────────────────────────────────────────────────────

export const DashboardPage = () => {
  const {
    data: widgets,
    isLoading: widgetsLoading,
    isError: widgetsError,
    error: widgetsErr,
    refetch: refetchWidgets,
  } = useDashboardWidgets();

  const {
    data: confirmationsData,
    isLoading: confirmationsLoading,
    isError: confirmationsError,
    error: confirmationsErr,
    refetch: refetchConfirmations,
  } = useRecentConfirmations();

  // Sort state for confirmations table
  const [sortField, setSortField] = useState<string | undefined>(undefined);
  const [sortOrder, setSortOrder] = useState<1 | -1>(1);

  const handleSort = useCallback((event: DataTableSortEvent) => {
    setSortField(event.sortField as string);
    setSortOrder(event.sortOrder as 1 | -1);
  }, []);

  // Date formatting for sign-off date column
  const dateTemplate = (rowData: RecentConfirmation) => {
    if (!rowData.sign_off_date) return '—';
    try {
      return new Date(rowData.sign_off_date).toLocaleDateString('en-IN', {
        day: '2-digit',
        month: 'short',
        year: 'numeric',
      });
    } catch {
      return rowData.sign_off_date;
    }
  };

  // Status badge template
  const statusTemplate = (rowData: RecentConfirmation) => {
    const statusClass =
      rowData.status === 'confirmed'
        ? 'closed'
        : rowData.status === 'pending'
          ? 'open'
          : 'in-progress';
    return (
      <span className={`status-badge ${statusClass}`}>
        {rowData.status.replace(/_/g, ' ')}
      </span>
    );
  };

  // Case ID short display
  const caseIdTemplate = (rowData: RecentConfirmation) => (
    <span title={rowData.case_id}>
      {rowData.case_id.length > 8 ? rowData.case_id.substring(0, 8) + '...' : rowData.case_id}
    </span>
  );

  // Loading state
  if (widgetsLoading && !widgets) {
    return (
      <div>
        <div className="em-page-header">
          <h2>Dashboard</h2>
        </div>
        <div className="flex justify-content-center align-items-center" style={{ minHeight: 300 }}>
          <ProgressSpinner style={{ width: '50px', height: '50px' }} />
        </div>
      </div>
    );
  }

  // Error state for widgets
  if (widgetsError) {
    return (
      <div>
        <div className="em-page-header">
          <h2>Dashboard</h2>
        </div>
        <div className="flex flex-column align-items-center gap-3" style={{ minHeight: 300, paddingTop: 80 }}>
          <Message
            severity="error"
            text={widgetsErr?.message || 'Failed to load dashboard data. Please try again.'}
          />
          <Button
            label="Retry"
            icon="pi pi-refresh"
            onClick={() => {
              refetchWidgets();
              refetchConfirmations();
            }}
            className="p-button-outlined"
          />
        </div>
      </div>
    );
  }

  const confirmations = confirmationsData?.items ?? [];

  return (
    <div>
      {/* Page Header */}
      <div className="em-page-header">
        <h2>Dashboard</h2>
      </div>

      {/* Top row: 4 metric cards */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
          gap: '1rem',
          marginBottom: '1rem',
        }}
      >
        <WidgetCard
          icon="pi pi-folder-open"
          iconColor="var(--blue-500)"
          iconBg="var(--blue-50)"
          label="Open Cases"
          value={widgets?.open_cases ?? 0}
        />
        <WidgetCard
          icon="pi pi-upload"
          iconColor="var(--orange-500)"
          iconBg="var(--orange-50)"
          label="Pending Vendor Upload"
          value={widgets?.pending_vendor_upload ?? 0}
        />
        <WidgetCard
          icon="pi pi-eye"
          iconColor="var(--purple-500)"
          iconBg="var(--purple-50)"
          label="Pending Finance Review"
          value={widgets?.pending_finance_review ?? 0}
        />
        <WidgetCard
          icon="pi pi-exclamation-triangle"
          iconColor="var(--red-500)"
          iconBg="var(--red-50)"
          label="Overdue Cases"
          value={widgets?.overdue_cases ?? 0}
        />
      </div>

      {/* Second row: 3 metric cards */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
          gap: '1rem',
          marginBottom: '1.5rem',
        }}
      >
        <WidgetCard
          icon="pi pi-check-circle"
          iconColor="var(--green-500)"
          iconBg="var(--green-50)"
          label="Closed This Month"
          value={widgets?.closed_this_month ?? 0}
        />
        <WidgetCard
          icon="pi pi-clock"
          iconColor="var(--teal-500)"
          iconBg="var(--teal-50)"
          label="Avg Cycle Time (days)"
          value={widgets?.avg_cycle_time_days != null ? widgets.avg_cycle_time_days.toFixed(1) : '—'}
        />
        <WidgetCard
          icon="pi pi-percentage"
          iconColor="var(--indigo-500)"
          iconBg="var(--indigo-50)"
          label="Auto-Match Rate"
          value={
            widgets?.auto_match_rate != null
              ? `${(widgets.auto_match_rate * 100).toFixed(1)}%`
              : '—'
          }
        />
      </div>

      {/* Recent Confirmations Table */}
      <div className="em-card" style={{ padding: 0 }}>
        <div style={{ padding: '1rem 1.25rem', borderBottom: '1px solid var(--surface-border)' }}>
          <h3 style={{ margin: 0, fontSize: '1rem', fontWeight: 600 }}>Recent Confirmations</h3>
        </div>

        {confirmationsLoading && !confirmationsData ? (
          <div className="flex justify-content-center align-items-center" style={{ minHeight: 150 }}>
            <ProgressSpinner style={{ width: '36px', height: '36px' }} />
          </div>
        ) : confirmationsError ? (
          <div className="flex flex-column align-items-center gap-3 p-4">
            <Message
              severity="error"
              text={confirmationsErr?.message || 'Failed to load recent confirmations.'}
            />
            <Button
              label="Retry"
              icon="pi pi-refresh"
              onClick={() => refetchConfirmations()}
              className="p-button-outlined p-button-sm"
            />
          </div>
        ) : confirmations.length === 0 ? (
          <div className="flex flex-column align-items-center gap-3 p-5">
            <i className="pi pi-inbox" style={{ fontSize: '2rem', color: 'var(--color-text-muted)' }} />
            <p style={{ color: 'var(--color-text-muted)', margin: 0 }}>
              No recent confirmations found.
            </p>
          </div>
        ) : (
          <DataTable
            value={confirmations}
            sortField={sortField}
            sortOrder={sortOrder}
            onSort={handleSort}
            dataKey="id"
            emptyMessage="No recent confirmations."
            loading={confirmationsLoading}
          >
            <Column field="vendor_name" header="Vendor Name" sortable style={{ width: '30%' }} />
            <Column field="case_id" header="Case ID" sortable style={{ width: '25%' }} body={caseIdTemplate} />
            <Column field="sign_off_date" header="Sign-Off Date" sortable style={{ width: '25%' }} body={dateTemplate} />
            <Column field="status" header="Status" sortable style={{ width: '20%' }} body={statusTemplate} />
          </DataTable>
        )}
      </div>
    </div>
  );
};
