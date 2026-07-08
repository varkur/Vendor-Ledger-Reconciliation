/**
 * Vendor Portal Statement page — Shows reconciliation results to the vendor.
 * Loads data from the backend API instead of using mock data.
 *
 * Connects to: GET /api/v1/vlr/portal/statement/{case_id} (with X-Portal-Token header)
 * Requirements: 24.3
 */

import { DataTable } from 'primereact/datatable';
import { Column } from 'primereact/column';
import { Tag } from 'primereact/tag';
import { Button } from 'primereact/button';
import { ProgressSpinner } from 'primereact/progressspinner';
import { Message } from 'primereact/message';
import { useNavigate } from 'react-router-dom';

import { usePortalStatement } from './hooks/usePortal';
import { usePortalContext } from './context/PortalContext';
import type { MatchSummaryItem } from './api/portalApi';

export const PortalStatementPage = () => {
  const navigate = useNavigate();
  const { portalToken, caseInfo, isAuthenticated } = usePortalContext();

  const caseId = caseInfo?.case_id || null;
  const { data: statement, isLoading, error, refetch } = usePortalStatement(
    caseId,
    portalToken
  );

  // Redirect to auth if not authenticated
  if (!isAuthenticated || !portalToken) {
    return (
      <div style={{ maxWidth: 600, margin: '0 auto', padding: '60px 24px', textAlign: 'center' }}>
        <div className="em-card" style={{ padding: 40 }}>
          <i
            className="pi pi-lock"
            style={{ fontSize: '3rem', color: 'var(--color-warning, #f59e0b)' }}
          />
          <h3 style={{ marginTop: 16 }}>Authentication Required</h3>
          <p style={{ color: 'var(--color-text-muted)' }}>
            Please use the link from your email to access the portal.
          </p>
        </div>
      </div>
    );
  }

  // Loading state
  if (isLoading) {
    return (
      <div style={{ maxWidth: 1100, margin: '0 auto', padding: '60px 24px', textAlign: 'center' }}>
        <ProgressSpinner style={{ width: 50, height: 50 }} />
        <p style={{ marginTop: 16, color: 'var(--color-text-muted)' }}>
          Loading reconciliation statement...
        </p>
      </div>
    );
  }

  // Error state
  if (error) {
    const errorMessage =
      error.response?.data?.detail || 'Failed to load reconciliation statement.';
    return (
      <div style={{ maxWidth: 600, margin: '0 auto', padding: '60px 24px', textAlign: 'center' }}>
        <div className="em-card" style={{ padding: 40 }}>
          <i
            className="pi pi-exclamation-triangle"
            style={{ fontSize: '3rem', color: 'var(--color-error, #ef4444)' }}
          />
          <h3 style={{ marginTop: 16 }}>Unable to Load Statement</h3>
          <Message severity="error" text={errorMessage} className="mb-3 w-full" />
          <Button label="Retry" icon="pi pi-refresh" onClick={() => refetch()} className="mt-2" />
        </div>
      </div>
    );
  }

  // No data state
  if (!statement) {
    return (
      <div style={{ maxWidth: 600, margin: '0 auto', padding: '60px 24px', textAlign: 'center' }}>
        <div className="em-card" style={{ padding: 40 }}>
          <i
            className="pi pi-info-circle"
            style={{ fontSize: '3rem', color: 'var(--color-text-muted)' }}
          />
          <h3 style={{ marginTop: 16 }}>No Statement Available</h3>
          <p style={{ color: 'var(--color-text-muted)' }}>
            The reconciliation has not produced results yet. Please check back later.
          </p>
        </div>
      </div>
    );
  }

  const formatCurrency = (value: number | null | undefined) => {
    if (value === null || value === undefined) return '—';
    return `₹${Number(value).toLocaleString('en-IN')}`;
  };

  const matchTypeTemplate = (rowData: MatchSummaryItem) => {
    const labels: Record<string, string> = {
      exact: 'Exact Match',
      tolerance: 'Tolerance Match',
      fuzzy_reference: 'Fuzzy Reference',
      one_to_many: 'One-to-Many',
      many_to_one: 'Many-to-One',
      date_proximity: 'Date Proximity',
    };
    return <span>{labels[rowData.match_type] || rowData.match_type}</span>;
  };

  const amountTemplate = (rowData: MatchSummaryItem) => {
    const amount = parseFloat(rowData.total_amount);
    return (
      <span style={{ color: amount < 0 ? 'var(--color-error)' : 'inherit' }}>
        ₹{amount.toLocaleString('en-IN')}
      </span>
    );
  };

  const periodDisplay =
    statement.period_start && statement.period_end
      ? `${statement.period_start} – ${statement.period_end}`
      : 'Not specified';

  const statusSeverity: Record<string, 'success' | 'warning' | 'info' | 'danger'> = {
    matched: 'success',
    signed_off: 'success',
    review: 'warning',
    pending_approval: 'warning',
    data_received: 'info',
    initiated: 'info',
  };

  return (
    <div style={{ maxWidth: 1100, margin: '0 auto', padding: '24px' }}>
      {/* Header */}
      <div className="flex align-items-center justify-content-between mb-3">
        <div>
          <h2 style={{ margin: 0 }}>Reconciliation Statement</h2>
          <p style={{ color: 'var(--color-text-muted)', margin: '4px 0 0' }}>
            Vendor: {statement.vendor_name} | Period: {periodDisplay}
          </p>
        </div>
        <div className="flex gap-2 align-items-center">
          <Tag
            value={statement.status.replace(/_/g, ' ').toUpperCase()}
            severity={statusSeverity[statement.status] || 'info'}
          />
          <Button
            label="Proceed to Sign-Off"
            icon="pi pi-check"
            onClick={() => navigate('/portal/sign-off')}
          />
        </div>
      </div>

      {/* Summary Cards */}
      <div className="flex gap-3 mb-3">
        <div className="em-card flex-1 text-center">
          <div style={{ fontSize: '1.25rem', fontWeight: 600 }}>
            {formatCurrency(statement.vendor_opening_balance)}
          </div>
          <div style={{ fontSize: '0.8rem', color: 'var(--color-text-muted)' }}>
            Vendor Opening Balance
          </div>
        </div>
        <div className="em-card flex-1 text-center">
          <div style={{ fontSize: '1.25rem', fontWeight: 600 }}>
            {formatCurrency(statement.vendor_closing_balance)}
          </div>
          <div style={{ fontSize: '0.8rem', color: 'var(--color-text-muted)' }}>
            Vendor Closing Balance
          </div>
        </div>
        <div className="em-card flex-1 text-center">
          <div
            style={{ fontSize: '1.25rem', fontWeight: 600, color: 'var(--color-success)' }}
          >
            {statement.total_matched_entries}
          </div>
          <div style={{ fontSize: '0.8rem', color: 'var(--color-text-muted)' }}>
            Matched Entries
          </div>
        </div>
        <div className="em-card flex-1 text-center">
          <div
            style={{ fontSize: '1.25rem', fontWeight: 600, color: 'var(--color-warning)' }}
          >
            {statement.total_unmatched_vendor}
          </div>
          <div style={{ fontSize: '0.8rem', color: 'var(--color-text-muted)' }}>
            Unmatched Vendor Items
          </div>
        </div>
        <div className="em-card flex-1 text-center">
          <div
            style={{
              fontSize: '1.25rem',
              fontWeight: 600,
              color:
                statement.net_difference && Number(statement.net_difference) !== 0
                  ? 'var(--color-error)'
                  : 'var(--color-success)',
            }}
          >
            {formatCurrency(statement.net_difference)}
          </div>
          <div style={{ fontSize: '0.8rem', color: 'var(--color-text-muted)' }}>
            Net Difference
          </div>
        </div>
      </div>

      {/* Match Summary Table */}
      {statement.match_summary.length > 0 && (
        <div className="em-card" style={{ padding: 0 }}>
          <div
            style={{
              padding: '12px 16px',
              borderBottom: '1px solid var(--color-border, #e5e7eb)',
            }}
          >
            <h3 style={{ margin: 0, fontSize: '1rem' }}>Match Summary by Type</h3>
          </div>
          <DataTable
            value={statement.match_summary}
            emptyMessage="No match results available."
          >
            <Column
              header="Match Type"
              body={matchTypeTemplate}
              style={{ width: '40%' }}
            />
            <Column field="count" header="Count" style={{ width: '20%' }} sortable />
            <Column
              header="Total Amount"
              body={amountTemplate}
              style={{ width: '40%' }}
              sortable
              sortField="total_amount"
            />
          </DataTable>
        </div>
      )}

      {/* Empty match summary */}
      {statement.match_summary.length === 0 && (
        <div className="em-card text-center" style={{ padding: 32 }}>
          <i
            className="pi pi-info-circle"
            style={{ fontSize: '2rem', color: 'var(--color-text-muted)' }}
          />
          <p style={{ marginTop: 12, color: 'var(--color-text-muted)' }}>
            Reconciliation matching has not been completed yet. Results will appear
            here once the auto-reconciliation process finishes.
          </p>
        </div>
      )}
    </div>
  );
};
