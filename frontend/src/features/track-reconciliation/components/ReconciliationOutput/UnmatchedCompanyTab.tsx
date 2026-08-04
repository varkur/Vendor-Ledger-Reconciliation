/**
 * UnmatchedCompanyTab — Tab 3: Unmatched Company Ledger entries.
 * Displays company entries with no vendor match, with Accept/Dispute/Request actions.
 *
 * Requirements: 20.1, 20.2, 20.3
 */

import { useState } from 'react';
import { Button } from 'primereact/button';
import { Column } from 'primereact/column';
import { DataTable, type DataTablePageEvent, type DataTableSortEvent } from 'primereact/datatable';
import { InputText } from 'primereact/inputtext';
import { Message } from 'primereact/message';
import { ProgressSpinner } from 'primereact/progressspinner';

import { useUnmatchedCompany, useConfirmMatch } from './useReconciliationOutput';
import { LEDGER_COLUMN_DEFS } from './reconciliationOutputApi';
import type { ListParams, UnmatchedCompanyAction, UnmatchedCompanyItem } from './reconciliationOutputApi';

// ─────────────────────────────────────────────────────────────────────────────
// Types
// ─────────────────────────────────────────────────────────────────────────────

interface UnmatchedCompanyTabProps {
  caseId: string;
}

// ─────────────────────────────────────────────────────────────────────────────
// Component
// ─────────────────────────────────────────────────────────────────────────────

export const UnmatchedCompanyTab = ({ caseId }: UnmatchedCompanyTabProps) => {
  const [params, setParams] = useState<ListParams>({
    page: 1,
    page_size: 10,
    sort_by: 'posting_date',
    sort_order: 'desc',
  });
  const [searchInput, setSearchInput] = useState('');

  const { data, isLoading, error, refetch } = useUnmatchedCompany(caseId, {
    ...params,
    search: searchInput || undefined,
  });

  const confirmMutation = useConfirmMatch(caseId);

  // ─── Event Handlers ──────────────────────────────────────────────────────────

  const onPage = (event: DataTablePageEvent) => {
    setParams((prev) => ({
      ...prev,
      page: (event.page ?? 0) + 1,
      page_size: event.rows,
    }));
  };

  const onSort = (event: DataTableSortEvent) => {
    setParams((prev) => ({
      ...prev,
      sort_by: event.sortField as string,
      sort_order: event.sortOrder === 1 ? 'asc' : 'desc',
    }));
  };

  const onSearchKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      setParams((prev) => ({ ...prev, page: 1 }));
    }
  };

  const handleAction = (itemId: string, action: UnmatchedCompanyAction) => {
    confirmMutation.mutate({
      item_id: itemId,
      action,
      tab: 'unmatched_company',
    });
  };

  // ─── Column Templates ────────────────────────────────────────────────────────

  const amountTemplate = (rowData: UnmatchedCompanyItem) => {
    const value = Number(rowData.amount ?? 0);
    return (
      <span className={value < 0 ? 'text-red-500' : ''}>
        {rowData.currency ?? 'INR'} {value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
      </span>
    );
  };

  const actionsTemplate = (rowData: UnmatchedCompanyItem) => (
    <div className="flex align-items-center gap-2">
      <Button
        icon="pi pi-check"
        severity="success"
        size="small"
        tooltip="Accept"
        tooltipOptions={{ position: 'top' }}
        onClick={() => handleAction(rowData.id, 'accept')}
        loading={confirmMutation.isPending && confirmMutation.variables?.item_id === rowData.id && confirmMutation.variables?.action === 'accept'}
        disabled={confirmMutation.isPending}
        aria-label={`Accept entry ${rowData.reference}`}
      />
      <Button
        icon="pi pi-exclamation-triangle"
        severity="warning"
        size="small"
        tooltip="Dispute"
        tooltipOptions={{ position: 'top' }}
        onClick={() => handleAction(rowData.id, 'dispute')}
        loading={confirmMutation.isPending && confirmMutation.variables?.item_id === rowData.id && confirmMutation.variables?.action === 'dispute'}
        disabled={confirmMutation.isPending}
        aria-label={`Dispute entry ${rowData.reference}`}
      />
      <Button
        icon="pi pi-envelope"
        severity="info"
        size="small"
        tooltip="Request info"
        tooltipOptions={{ position: 'top' }}
        onClick={() => handleAction(rowData.id, 'request')}
        loading={confirmMutation.isPending && confirmMutation.variables?.item_id === rowData.id && confirmMutation.variables?.action === 'request'}
        disabled={confirmMutation.isPending}
        aria-label={`Request info for entry ${rowData.reference}`}
      />
    </div>
  );

  // ─── Render ──────────────────────────────────────────────────────────────────

  if (isLoading) {
    return (
      <div className="flex align-items-center justify-content-center p-5">
        <ProgressSpinner style={{ width: '40px', height: '40px' }} aria-label="Loading unmatched company items" />
        <span className="ml-2">Loading unmatched company entries...</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-3">
        <Message
          severity="error"
          text={error.message || 'Failed to load unmatched company entries.'}
          className="w-full mb-3"
        />
        <button className="p-button p-button-outlined p-button-sm" onClick={() => refetch()}>
          <i className="pi pi-refresh mr-2" />
          Retry
        </button>
      </div>
    );
  }

  if (!data || data.items.length === 0) {
    return (
      <div className="p-4 text-center">
        <Message severity="info" text="No unmatched company ledger entries found." className="w-full" />
      </div>
    );
  }

  return (
    <div>
      {/* Mutation feedback */}
      {confirmMutation.isError && (
        <Message
          severity="error"
          text={confirmMutation.error?.message || 'Action failed. Please try again.'}
          className="w-full mb-3"
        />
      )}
      {confirmMutation.isSuccess && (
        <Message
          severity="success"
          text={confirmMutation.data?.message || 'Action completed successfully.'}
          className="w-full mb-3"
        />
      )}

      {/* Search Bar */}
      <div className="flex align-items-center gap-3 mb-3">
        <div className="em-search-bar">
          <InputText
            placeholder="Search by reference..."
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            onKeyDown={onSearchKeyDown}
            style={{ border: 'none', boxShadow: 'none', width: 200 }}
            aria-label="Search unmatched company entries"
          />
          <i className="pi pi-search" />
        </div>
      </div>

      {/* DataTable */}
      <div className="em-card" style={{ padding: 0 }}>
        <DataTable
          value={data.items}
          paginator
          rows={params.page_size}
          totalRecords={data.total}
          first={(data.page - 1) * data.page_size}
          onPage={onPage}
          onSort={onSort}
          sortField={params.sort_by}
          sortOrder={params.sort_order === 'asc' ? 1 : -1}
          lazy
          scrollable
          rowsPerPageOptions={[10, 25, 50]}
          emptyMessage="No unmatched company entries found."
          aria-label="Unmatched company ledger entries table"
        >
          {LEDGER_COLUMN_DEFS.map((c) => (
            <Column
              key={c.field}
              header={c.header}
              body={(row: UnmatchedCompanyItem) => {
                const v = row.columns ? (row.columns as any)[c.field] : undefined;
                return v === undefined || v === null || v === '' ? '—' : String(v);
              }}
              style={{ minWidth: '9rem', whiteSpace: 'nowrap' }}
            />
          ))}
        </DataTable>
      </div>
    </div>
  );
};
