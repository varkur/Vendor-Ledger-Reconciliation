/**
 * UnmatchedCompanyTab — Tab 3: Unmatched Company Ledger entries.
 * Displays company entries with no vendor match, with Accept/Dispute/Request actions.
 *
 * Requirements: 20.1, 20.2, 20.3
 */

import { useEffect, useState } from 'react';
import { Column } from 'primereact/column';
import { DataTable, type DataTablePageEvent, type DataTableSortEvent } from 'primereact/datatable';
import { InputText } from 'primereact/inputtext';
import { Message } from 'primereact/message';
import { ProgressSpinner } from 'primereact/progressspinner';
import { Tag } from 'primereact/tag';

import { useDebouncedValue } from '@shared/hooks/useDebouncedValue';
import { useUnmatchedCompany, useConfirmMatch } from './useReconciliationOutput';
import { LEDGER_COLUMN_DEFS } from './reconciliationOutputApi';
import type { ListParams, UnmatchedCompanyItem } from './reconciliationOutputApi';

// ─────────────────────────────────────────────────────────────────────────────
// Types
// ─────────────────────────────────────────────────────────────────────────────

interface UnmatchedCompanyTabProps {
  caseId: string;
  /**
   * Pre-applied, non-editable filter to a single Particulars-statement
   * difference group (from the reconciliation statement's "View" drill-in).
   * When set, the search bar is hidden since the view is already scoped to
   * one group.
   */
  groupFilter?: string;
}

// ─────────────────────────────────────────────────────────────────────────────
// Component
// ─────────────────────────────────────────────────────────────────────────────

export const UnmatchedCompanyTab = ({ caseId, groupFilter }: UnmatchedCompanyTabProps) => {
  const [params, setParams] = useState<ListParams>({
    page: 1,
    page_size: 10,
    sort_by: 'posting_date',
    sort_order: 'desc',
  });
  const [searchInput, setSearchInput] = useState('');

  // Debounce the search box so it only queries the server after the user
  // pauses typing, not on every keystroke — matches the pattern used by
  // MatchedItemsTab/ConfirmationTab.
  const debouncedSearch = useDebouncedValue(searchInput, 400);
  useEffect(() => {
    setParams((prev) => (prev.page === 1 ? prev : { ...prev, page: 1 }));
  }, [debouncedSearch]);

  const { data, isLoading, error, refetch } = useUnmatchedCompany(caseId, {
    ...params,
    search: groupFilter ? undefined : (debouncedSearch || undefined),
    group_filter: groupFilter || undefined,
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

      {/* Search Bar / Group Filter Indicator */}
      {groupFilter ? (
        <div className="mb-3">
          <Tag value={`Group: ${groupFilter}`} severity="info" />
        </div>
      ) : (
        <div className="flex align-items-center gap-3 mb-3">
          <div className="em-search-bar">
            <InputText
              placeholder="Search by reference..."
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
              style={{ border: 'none', boxShadow: 'none', width: 200 }}
              aria-label="Search unmatched company entries"
            />
            <i className="pi pi-search" />
          </div>
        </div>
      )}

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
