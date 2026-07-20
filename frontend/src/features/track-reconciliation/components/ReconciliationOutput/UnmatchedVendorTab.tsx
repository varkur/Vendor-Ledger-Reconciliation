/**
 * UnmatchedVendorTab — Tab 4: Unmatched Vendor Ledger entries.
 * Displays vendor entries with no company match, with Accept/Reject/Clarify actions.
 *
 * Requirements: 21.1, 21.2, 21.3
 */

import { useState } from 'react';
import { Button } from 'primereact/button';
import { Column } from 'primereact/column';
import { DataTable, type DataTablePageEvent, type DataTableSortEvent } from 'primereact/datatable';
import { InputText } from 'primereact/inputtext';
import { Message } from 'primereact/message';
import { ProgressSpinner } from 'primereact/progressspinner';

import { useUnmatchedVendor, useConfirmMatch } from './useReconciliationOutput';
import type { ListParams, UnmatchedVendorAction, UnmatchedVendorItem } from './reconciliationOutputApi';

// ─────────────────────────────────────────────────────────────────────────────
// Types
// ─────────────────────────────────────────────────────────────────────────────

interface UnmatchedVendorTabProps {
  caseId: string;
}

// ─────────────────────────────────────────────────────────────────────────────
// Component
// ─────────────────────────────────────────────────────────────────────────────

export const UnmatchedVendorTab = ({ caseId }: UnmatchedVendorTabProps) => {
  const [params, setParams] = useState<ListParams>({
    page: 1,
    page_size: 10,
    sort_by: 'date',
    sort_order: 'desc',
  });
  const [searchInput, setSearchInput] = useState('');

  const { data, isLoading, error, refetch } = useUnmatchedVendor(caseId, {
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

  const handleAction = (itemId: string, action: UnmatchedVendorAction) => {
    confirmMutation.mutate({
      item_id: itemId,
      action,
      tab: 'unmatched_vendor',
    });
  };

  // ─── Column Templates ────────────────────────────────────────────────────────

  const amountTemplate = (rowData: UnmatchedVendorItem) => {
    const value = Number(rowData.amount ?? 0);
    return (
      <span className={value < 0 ? 'text-red-500' : ''}>
        {rowData.currency ?? 'INR'} {value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
      </span>
    );
  };

  const actionsTemplate = (rowData: UnmatchedVendorItem) => (
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
        icon="pi pi-times"
        severity="danger"
        size="small"
        tooltip="Reject"
        tooltipOptions={{ position: 'top' }}
        onClick={() => handleAction(rowData.id, 'reject')}
        loading={confirmMutation.isPending && confirmMutation.variables?.item_id === rowData.id && confirmMutation.variables?.action === 'reject'}
        disabled={confirmMutation.isPending}
        aria-label={`Reject entry ${rowData.reference}`}
      />
      <Button
        icon="pi pi-question-circle"
        severity="warning"
        size="small"
        tooltip="Request clarification"
        tooltipOptions={{ position: 'top' }}
        onClick={() => handleAction(rowData.id, 'clarify')}
        loading={confirmMutation.isPending && confirmMutation.variables?.item_id === rowData.id && confirmMutation.variables?.action === 'clarify'}
        disabled={confirmMutation.isPending}
        aria-label={`Clarify entry ${rowData.reference}`}
      />
    </div>
  );

  // ─── Render ──────────────────────────────────────────────────────────────────

  if (isLoading) {
    return (
      <div className="flex align-items-center justify-content-center p-5">
        <ProgressSpinner style={{ width: '40px', height: '40px' }} aria-label="Loading unmatched vendor items" />
        <span className="ml-2">Loading unmatched vendor entries...</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-3">
        <Message
          severity="error"
          text={error.message || 'Failed to load unmatched vendor entries.'}
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
        <Message severity="info" text="No unmatched vendor ledger entries found." className="w-full" />
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
            aria-label="Search unmatched vendor entries"
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
          rowsPerPageOptions={[10, 25, 50]}
          emptyMessage="No unmatched vendor entries found."
          aria-label="Unmatched vendor ledger entries table"
        >
          <Column field="reference" header="Reference" sortable style={{ width: '14%' }} />
          <Column field="transaction_type" header="Transaction Type" sortable style={{ width: '14%' }} />
          <Column field="amount" header="Amount" sortable body={amountTemplate} style={{ width: '14%', textAlign: 'right' }} />
          <Column field="date" header="Date" sortable style={{ width: '12%' }} />
          <Column field="description" header="Description" sortable style={{ width: '28%' }} />
          <Column header="Actions" body={actionsTemplate} style={{ width: '15%' }} />
        </DataTable>
      </div>
    </div>
  );
};
