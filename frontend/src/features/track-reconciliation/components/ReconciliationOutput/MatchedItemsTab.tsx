/**
 * MatchedItemsTab — Tab 1: Displays all matched entry pairs with match type
 * and confidence score. Supports sorting, filtering, and pagination.
 *
 * Requirements: 18.1, 18.2, 18.3, 18.4
 */

import { useState, useEffect } from 'react';
import { Column } from 'primereact/column';
import { DataTable, type DataTablePageEvent, type DataTableSortEvent } from 'primereact/datatable';
import { Dropdown } from 'primereact/dropdown';
import { InputText } from 'primereact/inputtext';
import { Message } from 'primereact/message';
import { ProgressSpinner } from 'primereact/progressspinner';
import { Tag } from 'primereact/tag';

import { useRef } from 'react';
import { Toast } from 'primereact/toast';
import { useQueryClient } from '@tanstack/react-query';
import { useDebouncedValue } from '@shared/hooks/useDebouncedValue';
import { useMatchedItems } from './useReconciliationOutput';
import { manualUnlink, LEDGER_COLUMN_DEFS } from './reconciliationOutputApi';
import type { ListParams, MatchedItem, MatchType } from './reconciliationOutputApi';

// ─────────────────────────────────────────────────────────────────────────────
// Types & Helpers
// ─────────────────────────────────────────────────────────────────────────────

interface MatchedItemsTabProps {
  caseId: string;
  editable?: boolean;
  /**
   * Pre-applied, non-editable filter to a single manual-link status_reason
   * (from the "Manually Mapped" Particulars drill-in). When set, the
   * match-type dropdown and search bar are hidden since the view is already
   * scoped to one reason.
   */
  statusReasonFilter?: string;
  /**
   * Show all manual links (pass 8) regardless of reason — used for the
   * group-level "View" on the "Manually Mapped" Particulars row.
   */
  manualOnly?: boolean;
  /**
   * Pre-applied, non-editable filter to a single computed Status/
   * Classification value (e.g. "TDS Booked by Company", "Write off /
   * Rounding off") — from the Particulars statement's matched-residual
   * drill-in. When set, the search bar and match-type dropdown are hidden
   * since the view is already scoped to one residual reason.
   */
  computedStatusFilter?: string;
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

export const MatchedItemsTab = ({ caseId, editable = false, statusReasonFilter, manualOnly = false, computedStatusFilter }: MatchedItemsTabProps) => {
  const [params, setParams] = useState<ListParams>({
    page: 1,
    page_size: 10,
    sort_by: 'posting_date',
    sort_order: 'desc',
  });
  const [searchInput, setSearchInput] = useState('');
  const [matchTypeFilter, setMatchTypeFilter] = useState<string>('');
  const toast = useRef<Toast>(null);
  const queryClient = useQueryClient();

  const handleUnlink = async (matchId: string) => {
    try {
      await manualUnlink(caseId, matchId);
      toast.current?.show({ severity: 'success', summary: 'Unlinked', detail: 'Match removed; entries returned to unmatched.', life: 4000 });
      queryClient.invalidateQueries({ queryKey: ['vlr', 'reconciliation', caseId] });
    } catch (err: any) {
      toast.current?.show({ severity: 'error', summary: 'Unlink Failed', detail: err.response?.data?.detail || 'Failed to unlink.', life: 6000 });
    }
  };

  // Debounce the search box so it only queries the server after the user
  // pauses typing, not on every keystroke — typing each letter previously
  // fired a brand-new request/query-key, which reset the loading state and
  // made the whole table flash/reload on every character.
  const debouncedSearch = useDebouncedValue(searchInput, 400);
  useEffect(() => {
    setParams((prev) => (prev.page === 1 ? prev : { ...prev, page: 1 }));
  }, [debouncedSearch]);

  const isReasonScoped = !!statusReasonFilter || manualOnly || !!computedStatusFilter;
  const { data, isLoading, isFetching, error, refetch } = useMatchedItems(caseId, {
    ...params,
    search: isReasonScoped ? undefined : (debouncedSearch || undefined),
    match_type: isReasonScoped ? undefined : ((matchTypeFilter as MatchType) || undefined),
    status_reason: statusReasonFilter || undefined,
    manual_only: manualOnly || undefined,
    computed_status_filter: computedStatusFilter || undefined,
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

  return (
    <div>
      <Toast ref={toast} />
      {/* Filter Bar */}
      {isReasonScoped ? (
        <div className="mb-3">
          <Tag
            value={
              computedStatusFilter
                ? `Status: ${computedStatusFilter}`
                : statusReasonFilter
                ? `Reason: ${statusReasonFilter}`
                : 'All Manually Mapped Entries'
            }
            severity="info"
          />
        </div>
      ) : (
        <div className="flex align-items-center gap-3 mb-3">
          <div className="em-search-bar">
            <InputText
              placeholder="Search by reference..."
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
              style={{ border: 'none', boxShadow: 'none', width: 200 }}
              aria-label="Search matched items"
            />
            <i className={isFetching ? 'pi pi-spin pi-spinner' : 'pi pi-search'} />
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
      )}

      {!data || data.items.length === 0 ? (
        <div className="p-4 text-center">
          <Message severity="info" text="No matched items found for this reconciliation case." className="w-full" />
        </div>
      ) : (
      <div className="em-card" style={{ padding: 0, opacity: isFetching ? 0.6 : 1, transition: 'opacity 150ms' }}>
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
          emptyMessage="No matched items found."
          aria-label="Matched items table"
        >
          {editable && (
            <Column
              header="Action"
              frozen
              style={{ width: '9rem', minWidth: '9rem', textAlign: 'center' }}
              body={(row: MatchedItem) => (
                <button
                  onClick={() => handleUnlink((row as any).id)}
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: 6,
                    padding: '5px 12px',
                    fontSize: '0.8rem',
                    fontWeight: 600,
                    color: '#dc2626',
                    background: '#fff',
                    border: '1px solid #dc2626',
                    borderRadius: 6,
                    cursor: 'pointer',
                  }}
                  onMouseOver={(e) => {
                    e.currentTarget.style.background = '#dc2626';
                    e.currentTarget.style.color = '#fff';
                  }}
                  onMouseOut={(e) => {
                    e.currentTarget.style.background = '#fff';
                    e.currentTarget.style.color = '#dc2626';
                  }}
                >
                  <i className="pi pi-times" style={{ fontSize: '0.7rem' }} />
                  Unlink
                </button>
              )}
            />
          )}
          <Column field="match_type" header="Match Type" sortable body={matchTypeTemplate} style={{ minWidth: '9rem' }} />
          <Column field="matched_rule" header="Matched Rule" style={{ minWidth: '10rem' }} body={(row: MatchedItem) => row.matched_rule || '—'} />
          {isReasonScoped && (
            <Column field="status_reason" header="Reason" style={{ minWidth: '12rem' }} body={(row: MatchedItem) => row.status_reason || '—'} />
          )}
          <Column field="confidence_score" header="Confidence" sortable body={confidenceTemplate} style={{ minWidth: '8rem', textAlign: 'center' }} />
          {LEDGER_COLUMN_DEFS.map((c) => (
            <Column
              key={`co_${c.field}`}
              header={`Company ${c.header}`}
              body={(row: MatchedItem) => {
                const v = row.company_columns ? (row.company_columns as any)[c.field] : undefined;
                return v === undefined || v === null || v === '' ? '—' : String(v);
              }}
              style={{ minWidth: '9rem', whiteSpace: 'nowrap' }}
            />
          ))}
          {LEDGER_COLUMN_DEFS.map((c) => (
            <Column
              key={`pa_${c.field}`}
              header={`Party ${c.header}`}
              body={(row: MatchedItem) => {
                const v = row.party_columns ? (row.party_columns as any)[c.field] : undefined;
                return v === undefined || v === null || v === '' ? '—' : String(v);
              }}
              style={{ minWidth: '9rem', whiteSpace: 'nowrap' }}
            />
          ))}
        </DataTable>
      </div>
      )}
    </div>
  );
};
