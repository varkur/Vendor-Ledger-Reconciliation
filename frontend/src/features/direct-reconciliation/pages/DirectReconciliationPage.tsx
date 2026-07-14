/**
 * Direct Reconciliation page — List of direct reconciliation cases.
 *
 * Wired to backend APIs:
 * - GET /api/v1/vlr/requests (list with pagination/filtering)
 * - POST /api/v1/vlr/requests (create new reconciliation request)
 *
 * Implements loading, error (with retry), and empty states using PrimeReact components.
 *
 * Requirements: 12, 13, 23.1, 25.1, 25.2
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button } from 'primereact/button';
import { Calendar } from 'primereact/calendar';
import { Column } from 'primereact/column';
import { DataTable } from 'primereact/datatable';
import { Dialog } from 'primereact/dialog';
import { Dropdown } from 'primereact/dropdown';
import { FileUpload, type FileUploadSelectEvent } from 'primereact/fileupload';
import { InputText } from 'primereact/inputtext';
import { Message } from 'primereact/message';
import { Paginator, type PaginatorPageChangeEvent } from 'primereact/paginator';
import { ProgressSpinner } from 'primereact/progressspinner';
import { Skeleton } from 'primereact/skeleton';
import { useForm, Controller } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';

import {
  useReconciliationRequests,
  useCreateReconciliationRequest,
} from '../hooks/useDirectReconciliation';
import type { ReconciliationRequestResponse } from '../api/directReconciliationApi';
import { useSelectedEntity } from '@shared/hooks/useSelectedEntity';
import { useVendors } from '@features/vendor-management/hooks/useVendors';
import { StatusBadge } from '@shared/components/StatusBadge';

// ─────────────────────────────────────────────────────────────────────────────
// Constants
// ─────────────────────────────────────────────────────────────────────────────

const DEFAULT_PAGE_SIZE = 10;
const PAGE_SIZE_OPTIONS = [10, 25, 50];

// ─────────────────────────────────────────────────────────────────────────────
// Quick Create Form Schema
// ─────────────────────────────────────────────────────────────────────────────

const quickCreateSchema = z.object({
  fiscal_year: z.string().min(1, 'Fiscal Year is required'),
  period_start: z.date({ required_error: 'Period From is required' }),
  period_end: z.date({ required_error: 'Period To is required' }),
  vendor_id: z.string().min(1, 'Vendor is required'),
});

type QuickCreateFormData = z.infer<typeof quickCreateSchema>;

// ─────────────────────────────────────────────────────────────────────────────
// Helpers
// ─────────────────────────────────────────────────────────────────────────────

/** Generate fiscal year options based on current date. */
function generateFiscalYearOptions(): { label: string; value: string }[] {
  const currentYear = new Date().getFullYear();
  const currentMonth = new Date().getMonth(); // 0-indexed
  // Indian fiscal year: April to March
  // If we're in Jan-Mar, the current FY started last year
  const startYear = currentMonth >= 3 ? currentYear : currentYear - 1;

  return [
    { label: `${startYear - 1}-${String(startYear).slice(2)}`, value: `${startYear - 1}-${String(startYear).slice(2)}` },
    { label: `${startYear}-${String(startYear + 1).slice(2)}`, value: `${startYear}-${String(startYear + 1).slice(2)}` },
    { label: `${startYear + 1}-${String(startYear + 2).slice(2)}`, value: `${startYear + 1}-${String(startYear + 2).slice(2)}` },
  ];
}

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

/** Format a Date object to ISO date string (YYYY-MM-DD). */
function toISODateString(date: Date): string {
  return date.toISOString().split('T')[0] ?? '';
}

// ─────────────────────────────────────────────────────────────────────────────
// Component
// ─────────────────────────────────────────────────────────────────────────────

export const DirectReconciliationPage = () => {
  const { companyCode } = useSelectedEntity();
  const navigate = useNavigate();

  // ─── State ───────────────────────────────────────────────────────────────────
  const [searchQuery, setSearchQuery] = useState('');
  const [activeSearch, setActiveSearch] = useState('');
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE);
  const [showNewDialog, setShowNewDialog] = useState(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const fileUploadRef = useRef<FileUpload>(null);

  // ─── API Hooks ───────────────────────────────────────────────────────────────
  const {
    data,
    isLoading,
    isError,
    error,
    refetch,
  } = useReconciliationRequests({
    company_code: companyCode,
    page,
    page_size: pageSize,
  });

  const createMutation = useCreateReconciliationRequest();

  // Fetch vendors for the dropdown
  const {
    data: vendorsData,
    isLoading: vendorsLoading,
  } = useVendors(companyCode, { status: 'Active' }, 1, 100);

  // ─── Form Setup ──────────────────────────────────────────────────────────────
  const fiscalYearOptions = useMemo(() => generateFiscalYearOptions(), []);

  const vendorOptions = useMemo(() => {
    if (!vendorsData?.items) return [];
    return vendorsData.items.map((v) => ({
      label: `${v.vendor_code} - ${v.name}`,
      value: v.id,
    }));
  }, [vendorsData]);

  const {
    control,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<QuickCreateFormData>({
    resolver: zodResolver(quickCreateSchema),
    defaultValues: {
      fiscal_year: '',
      period_start: undefined,
      period_end: undefined,
      vendor_id: '',
    },
  });

  // Reset form when dialog closes
  useEffect(() => {
    if (!showNewDialog) {
      reset();
      setSelectedFile(null);
    }
  }, [showNewDialog, reset]);

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

  const onFormSubmit = useCallback(
    (data: QuickCreateFormData) => {
      createMutation.mutate(
        {
          company_code: companyCode,
          fiscal_year: data.fiscal_year,
          period_start: toISODateString(data.period_start),
          period_end: toISODateString(data.period_end),
          vendor_ids: [data.vendor_id],
        },
        {
          onSuccess: () => {
            setShowNewDialog(false);
          },
        }
      );
    },
    [createMutation, companyCode]
  );

  const handleFileSelect = useCallback((e: FileUploadSelectEvent) => {
    if (e.files && e.files.length > 0) {
      const file = e.files[0];
      if (file) setSelectedFile(file as unknown as File);
    }
  }, []);

  const handleFileClear = useCallback(() => {
    setSelectedFile(null);
  }, []);

  // ─── Column Templates ───────────────────────────────────────────────────────

  const statusTemplate = (rowData: ReconciliationRequestResponse) => (
    <StatusBadge status={rowData.status} />
  );

  const periodTemplate = (rowData: ReconciliationRequestResponse) => (
    <span>
      {formatDate(rowData.period_start)} to {formatDate(rowData.period_end)}
    </span>
  );

  const createdDateTemplate = (rowData: ReconciliationRequestResponse) => (
    <span>{formatDate(rowData.created_date)}</span>
  );

  const actionTemplate = (rowData: ReconciliationRequestResponse) => (
    <span
      className="link-view"
      style={{ cursor: 'pointer' }}
      onClick={() => navigate(`/track-reconciliation/${rowData.id}`)}
      role="link"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          navigate(`/track-reconciliation/${rowData.id}`);
        }
      }}
    >
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
        header="Quick Create — New Reconciliation"
        visible={showNewDialog}
        onHide={() => setShowNewDialog(false)}
        style={{ width: '550px' }}
        modal
        aria-label="Create new reconciliation dialog"
      >
        <form onSubmit={handleSubmit(onFormSubmit)} className="p-fluid">
          <div className="flex flex-column gap-3">
            <p className="text-color-secondary m-0">
              Create a new direct reconciliation case. Fill in the required fields
              below to initiate the reconciliation workflow.
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

            {/* Fiscal Year */}
            <div className="field">
              <label htmlFor="fiscal_year">Fiscal Year *</label>
              <Controller
                name="fiscal_year"
                control={control}
                render={({ field }) => (
                  <Dropdown
                    id="fiscal_year"
                    {...field}
                    options={fiscalYearOptions}
                    placeholder="Select Fiscal Year"
                    className={errors.fiscal_year ? 'p-invalid' : ''}
                  />
                )}
              />
              {errors.fiscal_year && (
                <small className="p-error">{errors.fiscal_year.message}</small>
              )}
            </div>

            {/* Period From and To */}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
              <div className="field">
                <label htmlFor="period_start">Period From *</label>
                <Controller
                  name="period_start"
                  control={control}
                  render={({ field }) => (
                    <Calendar
                      id="period_start"
                      value={field.value}
                      onChange={(e) => field.onChange(e.value)}
                      dateFormat="dd-M-yy"
                      placeholder="Select start date"
                      showIcon
                      className={errors.period_start ? 'p-invalid' : ''}
                    />
                  )}
                />
                {errors.period_start && (
                  <small className="p-error">{errors.period_start.message}</small>
                )}
              </div>

              <div className="field">
                <label htmlFor="period_end">Period To *</label>
                <Controller
                  name="period_end"
                  control={control}
                  render={({ field }) => (
                    <Calendar
                      id="period_end"
                      value={field.value}
                      onChange={(e) => field.onChange(e.value)}
                      dateFormat="dd-M-yy"
                      placeholder="Select end date"
                      showIcon
                      className={errors.period_end ? 'p-invalid' : ''}
                    />
                  )}
                />
                {errors.period_end && (
                  <small className="p-error">{errors.period_end.message}</small>
                )}
              </div>
            </div>

            {/* Vendor Selection */}
            <div className="field">
              <label htmlFor="vendor_id">Vendor *</label>
              <Controller
                name="vendor_id"
                control={control}
                render={({ field }) => (
                  <Dropdown
                    id="vendor_id"
                    {...field}
                    options={vendorOptions}
                    placeholder={vendorsLoading ? 'Loading vendors...' : 'Select Vendor'}
                    filter
                    filterPlaceholder="Search vendors"
                    loading={vendorsLoading}
                    disabled={vendorsLoading}
                    className={errors.vendor_id ? 'p-invalid' : ''}
                    emptyMessage="No vendors found"
                  />
                )}
              />
              {errors.vendor_id && (
                <small className="p-error">{errors.vendor_id.message}</small>
              )}
            </div>

            {/* File Upload (Optional) */}
            <div className="field">
              <label htmlFor="company_ledger">Company Ledger (optional)</label>
              <FileUpload
                ref={fileUploadRef}
                mode="basic"
                accept=".xlsx,.xls,.csv"
                maxFileSize={52428800}
                chooseLabel={selectedFile ? selectedFile.name : 'Browse File'}
                auto={false}
                onSelect={handleFileSelect}
                onClear={handleFileClear}
              />
              {selectedFile && (
                <small className="text-color-secondary mt-1">
                  Selected: {selectedFile.name} ({(selectedFile.size / 1024).toFixed(1)} KB)
                </small>
              )}
            </div>

            {/* Actions */}
            <div className="flex justify-content-end gap-2 mt-3">
              <Button
                label="Cancel"
                type="button"
                severity="secondary"
                onClick={() => setShowNewDialog(false)}
                disabled={createMutation.isPending}
              />
              <Button
                label="Create"
                type="submit"
                icon="pi pi-check"
                loading={createMutation.isPending}
                disabled={createMutation.isPending}
              />
            </div>
          </div>
        </form>
      </Dialog>
    );
  }
};
