/**
 * Track Reconciliation page — List of reconciliation cases with status tracking.
 * Wired to backend GET /api/v1/vlr/cases with server-side pagination, filtering, and search.
 *
 * Requirements: 23.2, 25.3, 25.4
 */

import { useState, useCallback } from 'react';
import { DataTable, DataTablePageEvent, DataTableSortEvent } from 'primereact/datatable';
import { Column } from 'primereact/column';
import { Button } from 'primereact/button';
import { InputText } from 'primereact/inputtext';
import { Dropdown } from 'primereact/dropdown';
import { ProgressSpinner } from 'primereact/progressspinner';
import { Message } from 'primereact/message';
import { useNavigate } from 'react-router-dom';

import { useCaseList } from '../hooks/useTrackReconciliation';
import type { ReconciliationCase } from '../api/trackReconciliationApi';
import { useSelectedEntity } from '@shared/hooks/useSelectedEntity';

/** Available status options for the filter dropdown. */
const STATUS_OPTIONS = [
  { label: 'All Statuses', value: '' },
  { label: 'Open', value: 'open' },
  { label: 'Draft', value: 'draft' },
  { label: 'Active', value: 'active' },
  { label: 'Data Received', value: 'data_received' },
  { label: 'Matching', value: 'matching' },
  { label: 'Matched', value: 'matched' },
  { label: 'Review', value: 'review' },
  { label: 'Pending Approval', value: 'pending_approval' },
  { label: 'Approved', value: 'approved' },
  { label: 'Closed', value: 'closed' },
];

/** Page size options for the paginator. */
const PAGE_SIZE_OPTIONS = [10, 25, 50, 100];

export const TrackReconciliationPage = () => {
  const navigate = useNavigate();
  const { companyCode } = useSelectedEntity();

  // Pagination state
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);

  // Filter state
  const [statusFilter, setStatusFilter] = useState('');
  const [searchQuery, setSearchQuery] = useState('');
  const [appliedSearch, setAppliedSearch] = useState('');

  // Sort state
  const [sortBy, setSortBy] = useState<string | undefined>(undefined);
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('desc');

  // Query hook — lazy server-side pagination
  const { data, isLoading, isError, error, refetch } = useCaseList({
    company_code: companyCode,
    page,
    page_size: pageSize,
    status: statusFilter || undefined,
    search: appliedSearch || undefined,
    sort_by: sortBy,
    sort_order: sortOrder,
  });

  // Handlers
  const handlePageChange = useCallback((event: DataTablePageEvent) => {
    setPage((event.page ?? 0) + 1); // PrimeReact is 0-indexed, our API is 1-indexed
    setPageSize(event.rows);
  }, []);

  const handleSort = useCallback((event: DataTableSortEvent) => {
    if (event.sortField) {
      setSortBy(event.sortField as string);
      setSortOrder(event.sortOrder === 1 ? 'asc' : 'desc');
    }
  }, []);

  const handleSearch = useCallback(() => {
    setAppliedSearch(searchQuery);
    setPage(1); // Reset to first page on new search
  }, [searchQuery]);

  const handleSearchKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === 'Enter') {
        handleSearch();
      }
    },
    [handleSearch]
  );

  const handleStatusFilterChange = useCallback((value: string) => {
    setStatusFilter(value);
    setPage(1); // Reset to first page on filter change
  }, []);

  // Column templates
  const statusTemplate = (rowData: ReconciliationCase) => {
    const statusClass = rowData.status === 'closed' ? 'closed' : rowData.status === 'open' || rowData.status === 'active' ? 'open' : 'in-progress';
    return (
      <span className={`status-badge ${statusClass}`}>
        {rowData.status.replace(/_/g, ' ')}
      </span>
    );
  };

  const caseTypeTemplate = (rowData: ReconciliationCase) => (
    <span style={{ textTransform: 'capitalize' }}>
      {rowData.case_type || 'batch'}
    </span>
  );

  const dateTemplate = (rowData: ReconciliationCase) => {
    if (!rowData.created_date) return '—';
    try {
      return new Date(rowData.created_date).toLocaleDateString('en-IN', {
        day: '2-digit',
        month: 'short',
        year: 'numeric',
      });
    } catch {
      return rowData.created_date;
    }
  };

  const actionTemplate = (rowData: ReconciliationCase) => (
    <div className="flex align-items-center gap-2">
      <span
        className="link-view"
        onClick={() => navigate(`/track-reconciliation/${rowData.id}`)}
        style={{ cursor: 'pointer' }}
      >
        View
      </span>
      <i className="pi pi-ellipsis-h" style={{ cursor: 'pointer', color: 'var(--color-text-muted)' }} />
    </div>
  );

  // Loading state
  if (isLoading && !data) {
    return (
      <div>
        <div className="em-page-header">
          <h2>Track Reconciliation</h2>
        </div>
        <div className="flex justify-content-center align-items-center" style={{ minHeight: 300 }}>
          <ProgressSpinner style={{ width: '50px', height: '50px' }} />
        </div>
      </div>
    );
  }

  // Error state
  if (isError) {
    return (
      <div>
        <div className="em-page-header">
          <h2>Track Reconciliation</h2>
        </div>
        <div className="flex flex-column align-items-center gap-3" style={{ minHeight: 300, paddingTop: 80 }}>
          <Message
            severity="error"
            text={error?.message || 'Failed to load reconciliation cases. Please try again.'}
          />
          <Button label="Retry" icon="pi pi-refresh" onClick={() => refetch()} className="p-button-outlined" />
        </div>
      </div>
    );
  }

  const cases = data?.items ?? [];
  const totalRecords = data?.total ?? 0;

  return (
    <div>
      {/* Page Header */}
      <div className="em-page-header">
        <h2>Track Reconciliation</h2>
        <div className="em-page-header-actions">
          <Dropdown
            value={statusFilter}
            options={STATUS_OPTIONS}
            onChange={(e) => handleStatusFilterChange(e.value)}
            placeholder="All Statuses"
            style={{ width: 160 }}
          />
          <div className="em-search-bar">
            <InputText
              placeholder="Type and press enter to Search"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              onKeyDown={handleSearchKeyDown}
              style={{ border: 'none', boxShadow: 'none', width: 200 }}
            />
            <i className="pi pi-search" style={{ cursor: 'pointer' }} onClick={handleSearch} />
          </div>
          <Button label="Add New Request" icon="pi pi-plus" />
        </div>
      </div>

      {/* Data Table with lazy pagination */}
      <div className="em-card" style={{ padding: 0 }}>
        {cases.length === 0 && !isLoading ? (
          <div className="flex flex-column align-items-center gap-3 p-5">
            <i className="pi pi-inbox" style={{ fontSize: '2rem', color: 'var(--color-text-muted)' }} />
            <p style={{ color: 'var(--color-text-muted)' }}>
              No reconciliation cases found.
              {appliedSearch && ' Try adjusting your search or filters.'}
            </p>
          </div>
        ) : (
          <DataTable
            value={cases}
            lazy
            paginator
            first={(page - 1) * pageSize}
            rows={pageSize}
            totalRecords={totalRecords}
            rowsPerPageOptions={PAGE_SIZE_OPTIONS}
            onPage={handlePageChange}
            onSort={handleSort}
            sortField={sortBy}
            sortOrder={sortOrder === 'asc' ? 1 : -1}
            loading={isLoading}
            emptyMessage="No cases found."
            dataKey="id"
          >
            <Column field="id" header="Case ID" sortable style={{ width: '18%' }}
              body={(row: ReconciliationCase) => row.id.substring(0, 8) + '...'}
            />
            <Column field="case_type" header="Type" sortable style={{ width: '10%' }} body={caseTypeTemplate} />
            <Column field="vendor_id" header="Vendor ID" sortable style={{ width: '18%' }}
              body={(row: ReconciliationCase) => row.vendor_id.substring(0, 8) + '...'}
            />
            <Column field="upload_count" header="Uploads" sortable style={{ width: '8%', textAlign: 'center' }} />
            <Column field="created_date" header="Created" sortable style={{ width: '14%' }} body={dateTemplate} />
            <Column field="status" header="Status" sortable style={{ width: '14%' }} body={statusTemplate} />
            <Column header="Action" body={actionTemplate} style={{ width: '10%' }} />
          </DataTable>
        )}
      </div>
    </div>
  );
};
