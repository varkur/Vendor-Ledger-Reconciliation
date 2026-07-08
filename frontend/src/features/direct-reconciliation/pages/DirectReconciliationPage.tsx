/**
 * Direct Reconciliation page — List of direct reconciliation cases.
 *
 * Wired to backend APIs:
 * - GET /api/v1/vlr/requests (list with pagination/filtering)
 * - POST /api/v1/vlr/requests (create new reconciliation request)
 *
 * Implements loading, error (with retry), and empty states using PrimeReact components.
 *
 * Requirements: 23.1, 25.1, 25.2
 */

import { useCallback, useState } from 'react';
import { Button } from 'primereact/button';
import { Column } from 'primereact/column';
import { DataTable } from 'primereact/datatable';
import { Dialog } from 'primereact/dialog';
import { InputText } from 'primereact/inputtext';
import { Message } from 'primereact/message';
import { Paginator, type PaginatorPageChangeEvent } from 'primereact/paginator';
import { ProgressSpinner } from 'primereact/progressspinner';
import { Skeleton } from 'primereact/skeleton';

import {
  useReconciliationRequests,
  useCreateReconciliationRequest,
} from '../hooks/useDirectReconciliation';
import type { ReconciliationRequestResponse } from '../api/directReconciliationApi';

// ─────────────────────────────────────────────────────────────────────────────
// Constants
// ─────────────────────────────────────────────────────────────────────────────

const DEFAULT_COMPANY_CODE = '1000';
const DEFAULT_PAGE_SIZE = 10;
const PAGE_SIZE_OPTIONS = [10, 25, 50];

// ─────────────────────────────────────────────────────────────────────────────
// Helpers
// ─────────────────────────────────────────────────────────────────────────────

/** Format an ISO date string to a readable format (DD-MMM-YY). */
function formatDate(isoDate: string | null): string {
  if (!isoDate) return '—';
  try {
    const d = new Date(isoDate);
    return d.toLocaleDateString('en-IN', {
      day: '2-digit',
      month: 'short',
      year: '2-digit',
    });
  } catch {
    return isoDate;
  }
}

/** Get CSS class for status badge styling. */
function getStatusClass(status: string): string {
  const normalized = status.toLowerCase();
  if (normalized.includes('completed') || normalized.includes('closed')) return 'completed';
  if (normalized.includes('open') || normalized.includes('active')) return 'open';
  if (normalized.includes('error') || normalized.includes('failed')) return 'error';
  return 'pending';
}

// ─────────────────────────────────────────────────────────────────────────────
// Component
// ─────────────────────────────────────────────────────────────────────────────

export const DirectReconciliationPage = () => {
  // ─── State ───────────────────────────────────────────────────────────────────
  const [searchQuery, setSearchQuery] = useState('');
  const [activeSearch, setActiveSearch] = useState('');
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE);
  const [showNewDialog, setShowNewDialog] = useState(false);

  // ─── API Hooks ───────────────────────────────────────────────────────────────
  const {
    data,
    isLoading,
    isError,
    error,
    refetch,
  } = useReconciliationRequests({
    company_code: DEFAULT_COMPANY_CODE,
    page,
    page_size: pageSize,
  });

  const createMutation = useCreateReconciliationRequest();

  // ─── Derived ─────────────────────────────────────────────────────────────────
  const requests = data?.items ?? [];
  const totalRecords = data?.total ?? 0;

  // Client-side search filter on the current page results
  const filteredRequests = activeSearch
    ? requests.filter(
        (r) =>
          r.fiscal_year.toLowerCase().includes(activeSearch.toLowerCase()) ||
          r.status.toLowerCase().includes(activeSearch.toLowerCase()) ||
          r.company_code.toLowerCase().includes(activeSearch.toLowerCase()) ||
          (r.created_by ?? '').toLowerCase().includes(activeSearch.toLowerCase())
      )
    : requests;

  // ─── Handlers ────────────────────────────────────────────────────────────────

  const handleSearch = useCallback(() => {
    setActiveSearch(searchQuery);
    setPage(1);
  }, [searchQuery]);

  const handleSearchKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === 'Enter') {
        handleSearch();
      }
    },
    [handleSearch]
  );

  const handlePageChange = useCallback((event: PaginatorPageChangeEvent) => {
    setPage(Math.floor(event.first / event.rows) + 1);
    setPageSize(event.rows);
  }, []);

  const handleNewReconciliation = useCallback(() => {
    setShowNewDialog(true);
  }, []);

  const handleCreateSubmit = useCallback(() => {
    // Create a minimal request — in a full implementation this would be a form
    createMutation.mutate(
      {
        company_code: DEFAULT_COMPANY_CODE,
        fiscal_year: '2024-25',
        period_start: '2024-04-01',
        period_end: '2025-03-31',
        vendor_ids: [],
      },
      {
        onSuccess: () => {
          setShowNewDialog(false);
        },
      }
    );
  }, [createMutation]);

  // ─── Column Templates ───────────────────────────────────────────────────────

  const statusTemplate = (rowData: ReconciliationRequestResponse) => (
    <span className={`status-badge ${getStatusClass(rowData.status)}`}>
      {rowData.status}
    </span>
  );

  const periodTemplate = (rowData: ReconciliationRequestResponse) => (
    <span>
      {formatDate(rowData.period_start)} to {formatDate(rowData.period_end)}
    </span>
  );

  const createdDateTemplate = (rowData: ReconciliationRequestResponse) => (
    <span>{formatDate(rowData.created_date)}</span>
  );

  const actionTemplate = () => (
    <span className="link-view" style={{ cursor: 'pointer' }}>
      View
    </span>
  );

  // ─── Loading State ──────────────────────────────────────────────────────────

  if (isLoading) {
    return (
      <div>
        <div className="em-page-header">
          <h2>Direct Reconciliation</h2>
        </div>
        <div className="em-card">
          <div className="flex align-items-center justify-content-center p-5">
            <ProgressSpinner
              style={{ width: '50px', height: '50px' }}
              aria-label="Loading reconciliation cases"
            />
            <span className="ml-3 text-color-secondary">
              Loading reconciliation cases...
            </span>
          </div>
          {/* Skeleton rows for visual placeholder */}
          <div className="p-3">
            {Array.from({ length: 5 }).map((_, i) => (
              <Skeleton key={i} height="2.5rem" className="mb-2" />
            ))}
          </div>
        </div>
      </div>
    );
  }

  // ─── Error State ────────────────────────────────────────────────────────────

  if (isError) {
    return (
      <div>
        <div className="em-page-header">
          <h2>Direct Reconciliation</h2>
        </div>
        <div className="em-card">
          <Message
            severity="error"
            text={
              error?.message ??
              'Failed to load reconciliation cases. Please try again.'
            }
            className="w-full mb-3"
          />
          <div className="flex justify-content-center">
            <Button
              label="Retry"
              icon="pi pi-refresh"
              severity="secondary"
              onClick={() => refetch()}
              aria-label="Retry loading reconciliation cases"
            />
          </div>
        </div>
      </div>
    );
  }

  // ─── Empty State ────────────────────────────────────────────────────────────

  if (requests.length === 0 && !activeSearch) {
    return (
      <div>
        <div className="em-page-header">
          <h2>Direct Reconciliation</h2>
          <div className="em-page-header-actions">
            <Button
              label="New Reconciliation"
              icon="pi pi-plus"
              onClick={handleNewReconciliation}
            />
          </div>
        </div>
        <div className="em-card">
          <div className="flex flex-column align-items-center justify-content-center p-5">
            <i
              className="pi pi-inbox text-color-secondary"
              style={{ fontSize: '3rem' }}
            />
            <h3 className="mt-3 mb-1">No Reconciliation Cases</h3>
            <p className="text-color-secondary text-center" style={{ maxWidth: '400px' }}>
              Get started by creating your first direct reconciliation. Click
              &quot;New Reconciliation&quot; to initiate a case for vendor ledger
              comparison.
            </p>
            <Button
              label="Create First Reconciliation"
              icon="pi pi-plus"
              className="mt-3"
              onClick={handleNewReconciliation}
            />
          </div>
        </div>
        {renderNewReconciliationDialog()}
      </div>
    );
  }

  // ─── Success State ──────────────────────────────────────────────────────────

  return (
    <div>
      {/* Page Header */}
      <div className="em-page-header">
        <h2>Direct Reconciliation</h2>
        <div className="em-page-header-actions">
          <div className="em-search-bar">
            <InputText
              placeholder="Type and press enter to Search"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              onKeyDown={handleSearchKeyDown}
              style={{ border: 'none', boxShadow: 'none', width: 200 }}
              aria-label="Search reconciliation cases"
            />
            <i
              className="pi pi-search"
              onClick={handleSearch}
              style={{ cursor: 'pointer' }}
            />
          </div>
          <Button
            label="New Reconciliation"
            icon="pi pi-plus"
            onClick={handleNewReconciliation}
          />
        </div>
      </div>

      {/* Data Table */}
      <div className="em-card" style={{ padding: 0 }}>
        <DataTable
          value={filteredRequests}
          sortMode="multiple"
          emptyMessage="No reconciliation cases match your search."
          aria-label="Reconciliation cases list"
        >
          <Column
            field="company_code"
            header="Company Code"
            sortable
            style={{ width: '12%' }}
          />
          <Column
            field="fiscal_year"
            header="Fiscal Year"
            sortable
            style={{ width: '12%' }}
          />
          <Column
            header="Reconciliation Period"
            body={periodTemplate}
            sortable
            sortField="period_start"
            style={{ width: '22%' }}
          />
          <Column
            header="Created On"
            body={createdDateTemplate}
            sortable
            sortField="created_date"
            style={{ width: '14%' }}
          />
          <Column
            header="Status"
            body={statusTemplate}
            sortable
            sortField="status"
            style={{ width: '18%' }}
          />
          <Column
            header="Action"
            body={actionTemplate}
            style={{ width: '8%' }}
          />
        </DataTable>

        {/* Paginator */}
        <Paginator
          first={(page - 1) * pageSize}
          rows={pageSize}
          totalRecords={totalRecords}
          rowsPerPageOptions={PAGE_SIZE_OPTIONS}
          onPageChange={handlePageChange}
          aria-label="Reconciliation cases pagination"
        />
      </div>

      {/* Create Reconciliation Dialog */}
      {renderNewReconciliationDialog()}
    </div>
  );

  // ─── Dialog Render ──────────────────────────────────────────────────────────

  function renderNewReconciliationDialog() {
    return (
      <Dialog
        header="New Reconciliation"
        visible={showNewDialog}
        onHide={() => setShowNewDialog(false)}
        style={{ width: '450px' }}
        modal
        aria-label="Create new reconciliation dialog"
      >
        <div className="flex flex-column gap-3">
          <p className="text-color-secondary m-0">
            Create a new direct reconciliation case. This will initiate the
            reconciliation workflow for the selected vendors and period.
          </p>

          {createMutation.isError && (
            <Message
              severity="error"
              text={
                createMutation.error?.message ??
                'Failed to create reconciliation. Please try again.'
              }
              className="w-full"
            />
          )}

          <div className="flex justify-content-end gap-2 mt-3">
            <Button
              label="Cancel"
              severity="secondary"
              onClick={() => setShowNewDialog(false)}
              disabled={createMutation.isPending}
            />
            <Button
              label="Create"
              icon="pi pi-check"
              onClick={handleCreateSubmit}
              loading={createMutation.isPending}
              disabled={createMutation.isPending}
            />
          </div>
        </div>
      </Dialog>
    );
  }
};
