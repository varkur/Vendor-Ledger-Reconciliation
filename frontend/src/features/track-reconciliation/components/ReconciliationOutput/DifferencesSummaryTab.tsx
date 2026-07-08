/**
 * DifferencesSummaryTab — Tab 5: Differences Summary.
 * Shows opening/closing balance comparison, totals by transaction type,
 * and net difference between company and vendor ledgers.
 *
 * Requirements: 22.1, 22.2, 22.3, 22.4
 */

import { Column } from 'primereact/column';
import { DataTable } from 'primereact/datatable';
import { Message } from 'primereact/message';
import { ProgressSpinner } from 'primereact/progressspinner';
import { Tag } from 'primereact/tag';

import { useSummary } from './useReconciliationOutput';
import type { TypeTotal } from './reconciliationOutputApi';

// ─────────────────────────────────────────────────────────────────────────────
// Types
// ─────────────────────────────────────────────────────────────────────────────

interface DifferencesSummaryTabProps {
  caseId: string;
}

// ─────────────────────────────────────────────────────────────────────────────
// Helpers
// ─────────────────────────────────────────────────────────────────────────────

function formatAmount(value: number, currency?: string): string {
  const formatted = value.toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
  return currency ? `${currency} ${formatted}` : formatted;
}

// ─────────────────────────────────────────────────────────────────────────────
// Component
// ─────────────────────────────────────────────────────────────────────────────

export const DifferencesSummaryTab = ({ caseId }: DifferencesSummaryTabProps) => {
  const { data, isLoading, error, refetch } = useSummary(caseId);

  // ─── Render ──────────────────────────────────────────────────────────────────

  if (isLoading) {
    return (
      <div className="flex align-items-center justify-content-center p-5">
        <ProgressSpinner style={{ width: '40px', height: '40px' }} aria-label="Loading differences summary" />
        <span className="ml-2">Loading differences summary...</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-3">
        <Message
          severity="error"
          text={error.message || 'Failed to load differences summary.'}
          className="w-full mb-3"
        />
        <button className="p-button p-button-outlined p-button-sm" onClick={() => refetch()}>
          <i className="pi pi-refresh mr-2" />
          Retry
        </button>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="p-4 text-center">
        <Message severity="info" text="No summary data available for this reconciliation case." className="w-full" />
      </div>
    );
  }

  const { balance_comparison, type_totals, net_difference, currency } = data;

  // ─── Column Templates for Type Totals ────────────────────────────────────────

  const companyTotalTemplate = (rowData: TypeTotal) => (
    <span className={rowData.company_total < 0 ? 'text-red-500' : ''}>
      {formatAmount(rowData.company_total, currency)}
    </span>
  );

  const vendorTotalTemplate = (rowData: TypeTotal) => (
    <span className={rowData.vendor_total < 0 ? 'text-red-500' : ''}>
      {formatAmount(rowData.vendor_total, currency)}
    </span>
  );

  const differenceTemplate = (rowData: TypeTotal) => (
    <span className={rowData.difference !== 0 ? 'text-orange-500 font-semibold' : 'text-green-600'}>
      {formatAmount(rowData.difference, currency)}
    </span>
  );

  return (
    <div className="flex flex-column gap-4">
      {/* Balance Comparison Cards */}
      <div className="grid">
        {/* Opening Balance Card */}
        <div className="col-12 md:col-6">
          <div className="em-card">
            <h4 className="mt-0 mb-3">Opening Balance Comparison</h4>
            <div className="flex flex-column gap-2">
              <div className="flex justify-content-between align-items-center">
                <span className="text-color-secondary">Company Opening Balance</span>
                <span className="font-semibold">
                  {formatAmount(balance_comparison.company_opening_balance, currency)}
                </span>
              </div>
              <div className="flex justify-content-between align-items-center">
                <span className="text-color-secondary">Vendor Opening Balance</span>
                <span className="font-semibold">
                  {formatAmount(balance_comparison.vendor_opening_balance, currency)}
                </span>
              </div>
              <hr className="my-2" style={{ borderColor: 'var(--color-surface-border)' }} />
              <div className="flex justify-content-between align-items-center">
                <span className="font-semibold">Opening Difference</span>
                <span className={`font-bold ${balance_comparison.opening_difference !== 0 ? 'text-orange-500' : 'text-green-600'}`}>
                  {formatAmount(balance_comparison.opening_difference, currency)}
                </span>
              </div>
            </div>
          </div>
        </div>

        {/* Closing Balance Card */}
        <div className="col-12 md:col-6">
          <div className="em-card">
            <h4 className="mt-0 mb-3">Closing Balance Comparison</h4>
            <div className="flex flex-column gap-2">
              <div className="flex justify-content-between align-items-center">
                <span className="text-color-secondary">Company Closing Balance</span>
                <span className="font-semibold">
                  {formatAmount(balance_comparison.company_closing_balance, currency)}
                </span>
              </div>
              <div className="flex justify-content-between align-items-center">
                <span className="text-color-secondary">Vendor Closing Balance</span>
                <span className="font-semibold">
                  {formatAmount(balance_comparison.vendor_closing_balance, currency)}
                </span>
              </div>
              <hr className="my-2" style={{ borderColor: 'var(--color-surface-border)' }} />
              <div className="flex justify-content-between align-items-center">
                <span className="font-semibold">Closing Difference</span>
                <span className={`font-bold ${balance_comparison.closing_difference !== 0 ? 'text-orange-500' : 'text-green-600'}`}>
                  {formatAmount(balance_comparison.closing_difference, currency)}
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Net Difference Banner */}
      <div className="em-card">
        <div className="flex align-items-center justify-content-between">
          <div className="flex align-items-center gap-3">
            <i className="pi pi-chart-bar text-2xl" style={{ color: 'var(--color-primary)' }} />
            <div>
              <h4 className="m-0">Net Difference</h4>
              <span className="text-sm text-color-secondary">
                Company Ledger vs Vendor Ledger
              </span>
            </div>
          </div>
          <div className="flex align-items-center gap-2">
            <span className={`text-2xl font-bold ${net_difference === 0 ? 'text-green-600' : 'text-orange-500'}`}>
              {formatAmount(net_difference, currency)}
            </span>
            {net_difference === 0 ? (
              <Tag value="Reconciled" severity="success" />
            ) : (
              <Tag value="Unreconciled" severity="warning" />
            )}
          </div>
        </div>
      </div>

      {/* Totals by Transaction Type */}
      <div className="em-card" style={{ padding: 0 }}>
        <div className="p-3 pb-0">
          <h4 className="m-0 mb-3">Totals by Transaction Type</h4>
        </div>
        <DataTable
          value={type_totals}
          emptyMessage="No transaction type totals available."
          aria-label="Totals by transaction type table"
        >
          <Column field="transaction_type" header="Transaction Type" style={{ width: '25%' }} />
          <Column
            field="company_total"
            header="Company Total"
            body={companyTotalTemplate}
            style={{ width: '25%', textAlign: 'right' }}
          />
          <Column
            field="vendor_total"
            header="Vendor Total"
            body={vendorTotalTemplate}
            style={{ width: '25%', textAlign: 'right' }}
          />
          <Column
            field="difference"
            header="Difference"
            body={differenceTemplate}
            style={{ width: '25%', textAlign: 'right' }}
          />
        </DataTable>
      </div>
    </div>
  );
};
