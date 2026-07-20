/**
 * ConfirmationTab — Tab 2: Finance Confirmation Required.
 * Lists matches needing manual review with Accept/Reject/Clarify actions.
 *
 * Requirements: 19.1, 19.2, 19.3, 19.4
 */

import { useState } from 'react';
import { Button } from 'primereact/button';
import { Column } from 'primereact/column';
import { DataTable, type DataTablePageEvent, type DataTableSortEvent } from 'primereact/datatable';
import { InputText } from 'primereact/inputtext';
import { Message } from 'primereact/message';
import { ProgressSpinner } from 'primereact/progressspinner';
import { Tag } from 'primereact/tag';

import { useConfirmationItems, useConfirmMatch } from './useReconciliationOutput';
import type { ConfirmAction, ConfirmationItem, ListParams } from './reconciliationOutputApi';

// ─────────────────────────────────────────────────────────────────────────────
// Types
// ─────────────────────────────────────────────────────────────────────────────

interface ConfirmationTabProps {
  caseId: string;
}

// ─────────────────────────────────────────────────────────────────────────────
// Component
// ─────────────────────────────────────────────────────────────────────────────

export const ConfirmationTab = ({ caseId }: ConfirmationTabProps) => {
  const [params, setParams] = useState<ListParams>({
    page: 1,
    page_size: 10,
    sort_by: 'confidence_score',
    sort_order: 'asc',
  });
  const [searchInput, setSearchInput] = useState('');

  const { data, isLoading, error, refetch } = useConfirmationItems(caseId, {
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

  const handleAction = (itemId: string, action: ConfirmAction) => {
    confirmMutation.mutate({
      item_id: itemId,
      action,
      tab: 'confirmation',
    });
  };

  // ─── Column Templates ────────────────────────────────────────────────────────

  const confidenceTemplate = (rowData: ConfirmationItem) => {
    const percentage = Math.round(rowData.confidence_score * 100);
    const severity = percentage >= 80 ? 'success' : percentage >= 50 ? 'warning' : 'danger';
    return <Tag value={`${percentage}%`} severity={severity} />;
  };

  const differenceTemplate = (rowData: ConfirmationItem) => {
    const value = Number(rowData.difference ?? 0);
    return (
      <span className={value !== 0 ? 'text-orange-500 font-semibold' : ''}>
        {value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
      </span>
    );
  };

  const actionsTemplate = (rowData: ConfirmationItem) => (
    <div className="flex align-items-center gap-2">
      <Button
        icon="pi pi-check"
        severity="success"
        size="small"
        tooltip="Accept match"
        tooltipOptions={{ position: 'top' }}
        onClick={() => handleAction(rowData.id, 'accept')}
        loading={confirmMutation.isPending && confirmMutation.variables?.item_id === rowData.id && confirmMutation.variables?.action === 'accept'}
        disabled={confirmMutation.isPending}
        aria-label={`Accept match for ${rowData.company_reference}`}
      />
      <Button
        icon="pi pi-times"
        severity="danger"
        size="small"
        tooltip="Reject match"
        tooltipOptions={{ position: 'top' }}
        onClick={() => handleAction(rowData.id, 'reject')}
        loading={confirmMutation.isPending && confirmMutation.variables?.item_id === rowData.id && confirmMutation.variables?.action === 'reject'}
        disabled={confirmMutation.isPending}
        aria-label={`Reject match for ${rowData.company_reference}`}
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
        aria-label={`Clarify match for ${rowData.company_reference}`}
      />
    </div>
  );

  // ─── Render ──────────────────────────────────────────────────────────────────

  if (isLoading) {
    return (
      <div className="flex align-items-center justify-content-center p-5">
        <ProgressSpinner style={{ width: '40px', height: '40px' }} aria-label="Loading confirmation items" />
        <span className="ml-2">Loading items requiring confirmation...</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-3">
        <Message
          severity="error"
          text={error.message || 'Failed to load confirmation items.'}
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
        <Message severity="info" text="No items require finance confirmation at this time." className="w-full" />
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
            aria-label="Search confirmation items"
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
          emptyMessage="No confirmation items found."
          aria-label="Finance confirmation items table"
        >
          <Column field="company_reference" header="Company Ref" sortable style={{ width: '12%' }} />
          <Column field="vendor_reference" header="Vendor Ref" sortable style={{ width: '12%' }} />
          <Column field="company_amount" header="Company Amt" sortable style={{ width: '11%', textAlign: 'right' }} />
          <Column field="vendor_amount" header="Vendor Amt" sortable style={{ width: '11%', textAlign: 'right' }} />
          <Column field="difference" header="Difference" sortable body={differenceTemplate} style={{ width: '10%', textAlign: 'right' }} />
          <Column field="match_type" header="Match Type" sortable style={{ width: '10%' }} />
          <Column field="confidence_score" header="Confidence" sortable body={confidenceTemplate} style={{ width: '9%', textAlign: 'center' }} />
          <Column field="reason" header="Reason" sortable style={{ width: '12%' }} />
          <Column header="Actions" body={actionsTemplate} style={{ width: '13%' }} />
        </DataTable>
      </div>
    </div>
  );
};
