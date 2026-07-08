/**
 * Exception Management page — List of reconciliation exceptions with severity, status, and resolution actions.
 * Wired to backend GET /api/v1/vlr/exceptions with server-side pagination, filtering, and search.
 *
 * Requirements: 23.4, 25.3, 25.4
 */

import { useState, useCallback } from 'react';
import { DataTable, DataTablePageEvent } from 'primereact/datatable';
import { Column } from 'primereact/column';
import { Button } from 'primereact/button';
import { InputText } from 'primereact/inputtext';
import { Tag } from 'primereact/tag';
import { Dropdown } from 'primereact/dropdown';
import { ProgressSpinner } from 'primereact/progressspinner';
import { Message } from 'primereact/message';
import { ResolutionDialog } from './ResolutionDialog';
import { useExceptionList, useResolveException } from './hooks/useExceptions';
import type { ExceptionItem } from './api/exceptionsApi';

/** Available severity filter options. */
const SEVERITY_OPTIONS = [
  { label: 'All Severities', value: '' },
  { label: 'High', value: 'high' },
  { label: 'Medium', value: 'medium' },
  { label: 'Low', value: 'low' },
];

/** Available category filter options. */
const CATEGORY_OPTIONS = [
  { label: 'All Categories', value: '' },
  { label: 'Amount Mismatch', value: 'amount_mismatch' },
  { label: 'Missing Invoice', value: 'missing_invoice' },
  { label: 'Duplicate Entry', value: 'duplicate_entry' },
  { label: 'TDS Difference', value: 'tds_difference' },
  { label: 'Credit Note Pending', value: 'credit_note_pending' },
  { label: 'GST Mismatch', value: 'gst_mismatch' },
];

/** Available status filter options. */
const STATUS_OPTIONS = [
  { label: 'All Statuses', value: '' },
  { label: 'Open', value: 'open' },
  { label: 'In Progress', value: 'in_progress' },
  { label: 'Resolved', value: 'resolved' },
  { label: 'Escalated', value: 'escalated' },
];

/** Page size options for the paginator. */
const PAGE_SIZE_OPTIONS = [10, 25, 50];

/** Default company code — in a real app this comes from user context/session. */
const DEFAULT_COMPANY_CODE = 'EPL';

/** Map backend resolution action codes to the format expected by the API. */
const RESOLUTION_ACTION_MAP: Record<string, string> = {
  ACM: 'accept_company_match',
  RDV: 'request_document_vendor',
  MTD: 'mark_tds_difference',
  MAA: 'mark_agreed_adjustment',
  WOF: 'write_off',
  ESC: 'escalate',
};

export const ExceptionListPage = () => {
  // Pagination state
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);

  // Filter state
  const [severityFilter, setSeverityFilter] = useState('');
  const [categoryFilter, setCategoryFilter] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [searchQuery, setSearchQuery] = useState('');

  // Resolution dialog state
  const [resolutionDialogVisible, setResolutionDialogVisible] = useState(false);
  const [selectedExceptionForResolution, setSelectedExceptionForResolution] = useState<ExceptionItem | null>(null);

  // Query hook — lazy server-side pagination
  const { data, isLoading, isError, error, refetch } = useExceptionList({
    company_code: DEFAULT_COMPANY_CODE,
    page,
    page_size: pageSize,
    severity: severityFilter || undefined,
    category: categoryFilter || undefined,
    status: statusFilter || undefined,
  });

  // Mutation hook for resolving exceptions
  const resolveExceptionMutation = useResolveException(DEFAULT_COMPANY_CODE);

  // Handlers
  const handlePageChange = useCallback((event: DataTablePageEvent) => {
    setPage((event.page ?? 0) + 1); // PrimeReact is 0-indexed, our API is 1-indexed
    setPageSize(event.rows);
  }, []);

  const handleSeverityFilterChange = useCallback((value: string) => {
    setSeverityFilter(value);
    setPage(1);
  }, []);

  const handleCategoryFilterChange = useCallback((value: string) => {
    setCategoryFilter(value);
    setPage(1);
  }, []);

  const handleStatusFilterChange = useCallback((value: string) => {
    setStatusFilter(value);
    setPage(1);
  }, []);

  const handleResolutionConfirm = useCallback(
    (action: string, comments: string) => {
      if (!selectedExceptionForResolution) return;

      const backendAction = RESOLUTION_ACTION_MAP[action] || action;

      resolveExceptionMutation.mutate(
        {
          exceptionId: selectedExceptionForResolution.id,
          data: {
            action: backendAction,
            comment: comments || undefined,
          },
        },
        {
          onSettled: () => {
            setResolutionDialogVisible(false);
            setSelectedExceptionForResolution(null);
          },
        }
      );
    },
    [selectedExceptionForResolution, resolveExceptionMutation]
  );

  // Column templates
  const severityTemplate = (rowData: ExceptionItem) => {
    const severityMap: Record<string, 'danger' | 'warning' | 'info'> = {
      high: 'danger',
      High: 'danger',
      medium: 'warning',
      Medium: 'warning',
      low: 'info',
      Low: 'info',
    };
    return <Tag value={rowData.severity} severity={severityMap[rowData.severity]} />;
  };

  const statusTemplate = (rowData: ExceptionItem) => {
    const statusClass: Record<string, string> = {
      open: 'open',
      Open: 'open',
      in_progress: 'in-progress',
      'In Progress': 'in-progress',
      resolved: 'resolved',
      Resolved: 'resolved',
      escalated: 'escalated',
      Escalated: 'escalated',
    };
    const displayStatus = rowData.status.replace(/_/g, ' ');
    return (
      <span className={`status-badge ${statusClass[rowData.status] || ''}`}>
        {displayStatus}
      </span>
    );
  };

  const amountTemplate = (rowData: ExceptionItem) => {
    if (rowData.amount == null) return '—';
    return <span>₹{Number(rowData.amount).toLocaleString('en-IN', { minimumFractionDigits: 2 })}</span>;
  };

  const dateTemplate = (rowData: ExceptionItem) => {
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

  const actionTemplate = (rowData: ExceptionItem) => (
    <div className="flex align-items-center gap-2">
      <Button
        icon="pi pi-check-circle"
        className="p-button-text p-button-sm"
        tooltip="Resolve"
        disabled={rowData.status === 'resolved'}
        onClick={() => {
          setSelectedExceptionForResolution(rowData);
          setResolutionDialogVisible(true);
        }}
      />
      <Button icon="pi pi-eye" className="p-button-text p-button-sm" tooltip="View Details" />
    </div>
  );

  // Client-side search filtering (applied on top of server-side results)
  const exceptions = data?.items ?? [];
  const filteredExceptions = searchQuery
    ? exceptions.filter(
        (e) =>
          e.category.toLowerCase().includes(searchQuery.toLowerCase()) ||
          e.id.toLowerCase().includes(searchQuery.toLowerCase()) ||
          (e.severity && e.severity.toLowerCase().includes(searchQuery.toLowerCase()))
      )
    : exceptions;

  const totalRecords = searchQuery ? filteredExceptions.length : (data?.total ?? 0);

  // Summary counts from data
  const openCount = exceptions.filter((e) => e.status === 'open' || e.status === 'Open').length;
  const inProgressCount = exceptions.filter((e) => e.status === 'in_progress' || e.status === 'In Progress').length;
  const resolvedCount = exceptions.filter((e) => e.status === 'resolved' || e.status === 'Resolved').length;
  const escalatedCount = exceptions.filter((e) => e.status === 'escalated' || e.status === 'Escalated').length;

  // Loading state
  if (isLoading && !data) {
    return (
      <div>
        <div className="em-page-header">
          <h2>Exception Management</h2>
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
          <h2>Exception Management</h2>
        </div>
        <div className="flex flex-column align-items-center gap-3" style={{ minHeight: 300, paddingTop: 80 }}>
          <Message
            severity="error"
            text={error?.message || 'Failed to load exceptions. Please try again.'}
          />
          <Button label="Retry" icon="pi pi-refresh" onClick={() => refetch()} className="p-button-outlined" />
        </div>
      </div>
    );
  }

  return (
    <div>
      {/* Page Header */}
      <div className="em-page-header">
        <h2>Exception Management</h2>
        <div className="em-page-header-actions">
          <Dropdown
            value={categoryFilter}
            options={CATEGORY_OPTIONS}
            onChange={(e) => handleCategoryFilterChange(e.value)}
            placeholder="All Categories"
            style={{ width: 160 }}
          />
          <Dropdown
            value={severityFilter}
            options={SEVERITY_OPTIONS}
            onChange={(e) => handleSeverityFilterChange(e.value)}
            placeholder="All Severities"
            style={{ width: 150 }}
          />
          <Dropdown
            value={statusFilter}
            options={STATUS_OPTIONS}
            onChange={(e) => handleStatusFilterChange(e.value)}
            placeholder="All Statuses"
            style={{ width: 140 }}
          />
          <div className="em-search-bar">
            <InputText
              placeholder="Search exceptions..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              style={{ border: 'none', boxShadow: 'none', width: 200 }}
            />
            <i className="pi pi-search" />
          </div>
          <Button label="Export" icon="pi pi-download" className="p-button-outlined" />
        </div>
      </div>

      {/* Summary Cards */}
      <div className="flex gap-3 mb-3">
        <div className="em-card flex-1 text-center">
          <div style={{ fontSize: '1.5rem', fontWeight: 600, color: 'var(--color-error)' }}>
            {openCount}
          </div>
          <div style={{ fontSize: '0.85rem', color: 'var(--color-text-muted)' }}>Open</div>
        </div>
        <div className="em-card flex-1 text-center">
          <div style={{ fontSize: '1.5rem', fontWeight: 600, color: 'var(--color-warning)' }}>
            {inProgressCount}
          </div>
          <div style={{ fontSize: '0.85rem', color: 'var(--color-text-muted)' }}>In Progress</div>
        </div>
        <div className="em-card flex-1 text-center">
          <div style={{ fontSize: '1.5rem', fontWeight: 600, color: 'var(--color-success)' }}>
            {resolvedCount}
          </div>
          <div style={{ fontSize: '0.85rem', color: 'var(--color-text-muted)' }}>Resolved</div>
        </div>
        <div className="em-card flex-1 text-center">
          <div style={{ fontSize: '1.5rem', fontWeight: 600, color: 'var(--color-primary)' }}>
            {escalatedCount}
          </div>
          <div style={{ fontSize: '0.85rem', color: 'var(--color-text-muted)' }}>Escalated</div>
        </div>
      </div>

      {/* Data Table with lazy pagination */}
      <div className="em-card" style={{ padding: 0 }}>
        {filteredExceptions.length === 0 && !isLoading ? (
          <div className="flex flex-column align-items-center gap-3 p-5">
            <i className="pi pi-inbox" style={{ fontSize: '2rem', color: 'var(--color-text-muted)' }} />
            <p style={{ color: 'var(--color-text-muted)' }}>
              No exceptions found.
              {(searchQuery || severityFilter || categoryFilter || statusFilter) &&
                ' Try adjusting your search or filters.'}
            </p>
          </div>
        ) : (
          <DataTable
            value={filteredExceptions}
            lazy={!searchQuery}
            paginator
            first={searchQuery ? 0 : (page - 1) * pageSize}
            rows={pageSize}
            totalRecords={totalRecords}
            rowsPerPageOptions={PAGE_SIZE_OPTIONS}
            onPage={searchQuery ? undefined : handlePageChange}
            loading={isLoading}
            emptyMessage="No exceptions found."
            dataKey="id"
          >
            <Column
              field="id"
              header="Exception ID"
              style={{ width: '12%' }}
              body={(row: ExceptionItem) => row.id.substring(0, 8) + '...'}
            />
            <Column field="category" header="Category" style={{ width: '15%' }}
              body={(row: ExceptionItem) => row.category.replace(/_/g, ' ')}
            />
            <Column header="Severity" body={severityTemplate} style={{ width: '10%' }} />
            <Column header="Amount" body={amountTemplate} style={{ width: '12%' }} />
            <Column header="Created" body={dateTemplate} style={{ width: '12%' }} />
            <Column header="Status" body={statusTemplate} style={{ width: '12%' }} />
            <Column header="Action" body={actionTemplate} style={{ width: '10%' }} />
          </DataTable>
        )}
      </div>

      {/* Resolution Dialog */}
      <ResolutionDialog
        visible={resolutionDialogVisible}
        onHide={() => {
          setResolutionDialogVisible(false);
          setSelectedExceptionForResolution(null);
        }}
        exception={
          selectedExceptionForResolution
            ? {
                exceptionId: selectedExceptionForResolution.id.substring(0, 8),
                vendorName: selectedExceptionForResolution.category.replace(/_/g, ' '),
                description: `Severity: ${selectedExceptionForResolution.severity} | Amount: ₹${
                  selectedExceptionForResolution.amount != null
                    ? Number(selectedExceptionForResolution.amount).toLocaleString('en-IN', { minimumFractionDigits: 2 })
                    : '—'
                }`,
              }
            : null
        }
        onConfirm={handleResolutionConfirm}
      />
    </div>
  );
};
