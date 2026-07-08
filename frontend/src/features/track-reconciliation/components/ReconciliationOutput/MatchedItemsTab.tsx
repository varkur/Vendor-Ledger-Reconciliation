/**
 * MatchedItemsTab — Tab 1: Displays all matched entry pairs with match type
 * and confidence score. Supports sorting, filtering, and pagination.
 *
 * Requirements: 18.1, 18.2, 18.3, 18.4
 */

import { useState } from 'react';
import { Column } from 'primereact/column';
import { DataTable, type DataTablePageEvent, type DataTableSortEvent } from 'primereact/datatable';
import { Dropdown } from 'primereact/dropdown';
import { InputText } from 'primereact/inputtext';
import { Message } from 'primereact/message';
import { ProgressSpinner } from 'primereact/progressspinner';
import { Tag } from 'primereact/tag';

import { useMatchedItems } from './useReconciliationOutput';
import type { ListParams, MatchedItem, MatchType } from './reconciliationOutputApi';

// ─────────────────────────────────────────────────────────────────────────────
// Types & Helpers
// ─────────────────────────────────────────────────────────────────────────────

interface MatchedItemsTabProps {
  caseId: string;
}

const MATCH_TYPE_OPTIONS = [
  { label: 'All Types', value: '' },
  { label: 'Exact', value: 'Exact' },
  { label: 'Tolerance', value: 'Tolerance' },
  { label: 'Fuzzy', value: 'Fuzzy' },
  { label: 'One-to-Many', value: 'One-to-Many' },
  { label: 'Many-to-One', value: 'Many-to-One' },
  { label: 'Date-proximity', value: 'Date-proximity' },
];

/** Map match type to PrimeReact Tag severity for visual distinction. */
function getMatchTypeSeverity(
  matchType: MatchType
): 'success' | 'info' | 'warning' | 'danger' | 'secondary' | null {
  switch (matchType) {
    case 'Exact':
      return 'success';
    case 'Tolerance':
      return 'info';
    case 'Fuzzy':
      return 'warning';
    case 'One-to-Many':
      return 'secondary';
    case 'Many-to-One':
      return 'secondary';
    case 'Date-proximity':
      return 'warning';
    default:
      return null;
  }
}

/** Map confidence score (0.0-1.0) to a color-coded severity. */
function getConfidenceSeverity(score: number): 'success' | 'warning' | 'danger' {
  if (score >= 0.8) return 'success';
  if (score >= 0.5) return 'warning';
  return 'danger';
}

// ─────────────────────────────────────────────────────────────────────────────
// Component
// ─────────────────────────────────────────────────────────────────────────────

export const MatchedItemsTab = ({ caseId }: MatchedItemsTabProps) => {
  const [params, setParams] = useState<ListParams>({
    page: 1,
    page_size: 10,
    sort_by: 'posting_date',
    sort_order: 'desc',
  });
  const [searchInput, setSearchInput] = useState('');
  const [matchTypeFilter, setMatchTypeFilter] = useState<string>('');

  const { data, isLoading, error, refetch } = useMatchedItems(caseId, {
    ...params,
    search: searchInput || undefined,
    match_type: (matchTypeFilter as MatchType) || undefined,
  });

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

  // ─── Column Templates ────────────────────────────────────────────────────────

  const matchTypeTemplate = (rowData: MatchedItem) => (
    <Tag value={rowData.match_type} severity={getMatchTypeSeverity(rowData.match_type)} />
  );

  const confidenceTemplate = (rowData: MatchedItem) => {
    const percentage = Math.round(rowData.confidence_score * 100);
    return (
      <Tag
        value={`${percentage}%`}
        severity={getConfidenceSeverity(rowData.confidence_score)}
      />
    );
  };

  const amountTemplate = (field: 'company_amount' | 'vendor_amount') => (rowData: MatchedItem) => {
    const value = rowData[field];
    return (
      <span className={value < 0 ? 'text-red-500' : ''}>
        {rowData.currency} {value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
      </span>
    );
  };

  // ─── Render ──────────────────────────────────────────────────────────────────

  if (isLoading) {
    return (
      <div className="flex align-items-center justify-content-center p-5">
        <ProgressSpinner style={{ width: '40px', height: '40px' }} aria-label="Loading matched items" />
        <span className="ml-2">Loading matched items...</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-3">
        <Message
          severity="error"
          text={error.message || 'Failed to load matched items.'}
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
        <Message severity="info" text="No matched items found for this reconciliation case." className="w-full" />
      </div>
    );
  }

  return (
    <div>
      {/* Filter Bar */}
      <div className="flex align-items-center gap-3 mb-3">
        <div className="em-search-bar">
          <InputText
            placeholder="Search by reference..."
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            onKeyDown={onSearchKeyDown}
            style={{ border: 'none', boxShadow: 'none', width: 200 }}
            aria-label="Search matched items"
          />
          <i className="pi pi-search" />
        </div>
        <Dropdown
          value={matchTypeFilter}
          options={MATCH_TYPE_OPTIONS}
          onChange={(e) => {
            setMatchTypeFilter(e.value);
            setParams((prev) => ({ ...prev, page: 1 }));
          }}
          placeholder="Filter by match type"
          className="w-12rem"
          aria-label="Filter by match type"
        />
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
          emptyMessage="No matched items found."
          aria-label="Matched items table"
        >
          <Column field="company_reference" header="Company Ref" sortable style={{ width: '14%' }} />
          <Column field="vendor_reference" header="Vendor Ref" sortable style={{ width: '14%' }} />
          <Column field="company_amount" header="Company Amount" sortable body={amountTemplate('company_amount')} style={{ width: '13%', textAlign: 'right' }} />
          <Column field="vendor_amount" header="Vendor Amount" sortable body={amountTemplate('vendor_amount')} style={{ width: '13%', textAlign: 'right' }} />
          <Column field="match_type" header="Match Type" sortable body={matchTypeTemplate} style={{ width: '12%' }} />
          <Column field="confidence_score" header="Confidence" sortable body={confidenceTemplate} style={{ width: '10%', textAlign: 'center' }} />
          <Column field="posting_date" header="Posting Date" sortable style={{ width: '12%' }} />
          <Column field="document_type" header="Doc Type" sortable style={{ width: '10%' }} />
        </DataTable>
      </div>
    </div>
  );
};
