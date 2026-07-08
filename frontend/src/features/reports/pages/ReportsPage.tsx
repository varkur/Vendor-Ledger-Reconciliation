/**
 * Reports & MIS page — Tabbed interface for reconciliation reports.
 * Wired to backend report APIs with server-side pagination and export.
 * Tabs: Reconciliation Statement, Exception Report, Vendor Status, Monthly MIS
 *
 * Requirements: 23.6, 25.1, 25.2
 */

import { useState, useRef, useCallback } from 'react';
import { TabView, TabPanel } from 'primereact/tabview';
import { DataTable } from 'primereact/datatable';
import { Column } from 'primereact/column';
import { Button } from 'primereact/button';
import { Dropdown } from 'primereact/dropdown';
import { ProgressSpinner } from 'primereact/progressspinner';
import { Message } from 'primereact/message';
import { Toast } from 'primereact/toast';

import {
  useReconciliationSummary,
  useExceptionReport,
  useVendorStatusReport,
  useMonthlyMISReport,
  useGenerateReport,
  useDownloadReport,
} from '../hooks/useReports';
import type { ExportFormat, ReportType } from '../api/reportsApi';

// ─────────────────────────────────────────────────────────────────────────────
// Constants
// ─────────────────────────────────────────────────────────────────────────────

const DEFAULT_PAGE_SIZE = 10;

const EXPORT_FORMATS = [
  { label: 'PDF', value: 'pdf' },
  { label: 'Excel', value: 'excel' },
];

const TAB_TO_REPORT_TYPE: Record<number, ReportType> = {
  0: 'reconciliation-summary',
  1: 'exceptions',
  2: 'vendor-status',
  3: 'mis',
};

// ─────────────────────────────────────────────────────────────────────────────
// Component
// ─────────────────────────────────────────────────────────────────────────────

export const ReportsPage = () => {
  const toast = useRef<Toast>(null);
  const [activeTab, setActiveTab] = useState(0);
  const [exportFormat, setExportFormat] = useState<ExportFormat>('excel');

  // Page state per tab
  const [recoPage, setRecoPage] = useState(1);
  const [exceptionPage, setExceptionPage] = useState(1);
  const [vendorPage, setVendorPage] = useState(1);
  const [misPage, setMisPage] = useState(1);

  // Data hooks
  const recoQuery = useReconciliationSummary(
    { page: recoPage, page_size: DEFAULT_PAGE_SIZE },
    activeTab === 0
  );
  const exceptionQuery = useExceptionReport(
    { page: exceptionPage, page_size: DEFAULT_PAGE_SIZE },
    activeTab === 1
  );
  const vendorQuery = useVendorStatusReport(
    { page: vendorPage, page_size: DEFAULT_PAGE_SIZE },
    activeTab === 2
  );
  const misQuery = useMonthlyMISReport(
    { page: misPage, page_size: DEFAULT_PAGE_SIZE },
    activeTab === 3
  );

  // Export mutations
  const generateMutation = useGenerateReport();
  const downloadMutation = useDownloadReport();

  // Export handler
  const handleExport = useCallback(() => {
    const reportType = TAB_TO_REPORT_TYPE[activeTab];
    generateMutation.mutate(
      { reportType, format: exportFormat },
      {
        onSuccess: (response) => {
          // Trigger download
          downloadMutation.mutate(response.report_id, {
            onSuccess: (blob) => {
              const url = window.URL.createObjectURL(blob);
              const link = document.createElement('a');
              link.href = url;
              const ext = exportFormat === 'pdf' ? 'pdf' : 'xlsx';
              link.download = `${reportType}-report.${ext}`;
              document.body.appendChild(link);
              link.click();
              document.body.removeChild(link);
              window.URL.revokeObjectURL(url);

              toast.current?.show({
                severity: 'success',
                summary: 'Export Complete',
                detail: `Report downloaded as ${exportFormat.toUpperCase()}.`,
              });
            },
            onError: (err) => {
              toast.current?.show({
                severity: 'error',
                summary: 'Download Failed',
                detail: err.message || 'Failed to download report.',
              });
            },
          });
        },
        onError: (err) => {
          toast.current?.show({
            severity: 'error',
            summary: 'Export Failed',
            detail: err.message || 'Failed to generate report.',
          });
        },
      }
    );
  }, [activeTab, exportFormat, generateMutation, downloadMutation]);

  // Column templates
  const amountTemplate = (field: string) => (rowData: Record<string, unknown>) => (
    <span>₹{(rowData[field] as number).toLocaleString('en-IN')}</span>
  );

  const statusTemplate = (rowData: { status: string }) => (
    <span className={`status-badge ${rowData.status.toLowerCase().replace(/\s+/g, '-')}`}>
      {rowData.status}
    </span>
  );

  // Loading / Error state helpers
  const renderLoading = () => (
    <div className="flex justify-content-center align-items-center" style={{ minHeight: 200 }}>
      <ProgressSpinner style={{ width: '40px', height: '40px' }} />
    </div>
  );

  const renderError = (errorMsg: string | undefined, retryFn: () => void) => (
    <div className="flex flex-column align-items-center gap-3" style={{ padding: '2rem' }}>
      <Message severity="error" text={errorMsg || 'Failed to load report data.'} />
      <Button label="Retry" icon="pi pi-refresh" onClick={retryFn} />
    </div>
  );

  const renderEmpty = (message: string) => (
    <div className="flex flex-column align-items-center gap-2" style={{ padding: '3rem' }}>
      <i className="pi pi-file" style={{ fontSize: '2rem', color: 'var(--color-text-muted)' }} />
      <p style={{ color: 'var(--color-text-muted)' }}>{message}</p>
    </div>
  );

  return (
    <div>
      <Toast ref={toast} />

      {/* Page Header */}
      <div className="em-page-header">
        <h2>Reports & MIS</h2>
        <div className="em-page-header-actions">
          <Dropdown
            value={exportFormat}
            options={EXPORT_FORMATS}
            onChange={(e) => setExportFormat(e.value)}
            placeholder="Format"
            style={{ width: 120 }}
          />
          <Button
            label="Export"
            icon="pi pi-download"
            onClick={handleExport}
            loading={generateMutation.isPending || downloadMutation.isPending}
          />
        </div>
      </div>

      {/* Tabbed Reports */}
      <div className="em-card" style={{ padding: 0 }}>
        <TabView activeIndex={activeTab} onTabChange={(e) => setActiveTab(e.index)}>
          {/* Reconciliation Statement Tab */}
          <TabPanel header="Reconciliation Statement">
            {recoQuery.isLoading && !recoQuery.data ? (
              renderLoading()
            ) : recoQuery.isError ? (
              renderError(recoQuery.error?.message, () => recoQuery.refetch())
            ) : !recoQuery.data?.items.length ? (
              renderEmpty('No reconciliation data found.')
            ) : (
              <DataTable
                value={recoQuery.data.items}
                paginator
                rows={DEFAULT_PAGE_SIZE}
                totalRecords={recoQuery.data.total}
                first={(recoPage - 1) * DEFAULT_PAGE_SIZE}
                onPage={(e) => setRecoPage((e.page ?? 0) + 1)}
                rowsPerPageOptions={[10, 25, 50]}
                lazy
                loading={recoQuery.isLoading}
                sortMode="multiple"
                emptyMessage="No data found."
              >
                <Column field="vendor_name" header="Vendor Name" sortable style={{ width: '22%' }} />
                <Column header="Opening Bal." body={amountTemplate('opening_balance')} sortable sortField="opening_balance" style={{ width: '12%' }} />
                <Column header="Invoices" body={amountTemplate('invoices')} sortable sortField="invoices" style={{ width: '11%' }} />
                <Column header="Payments" body={amountTemplate('payments')} sortable sortField="payments" style={{ width: '11%' }} />
                <Column header="Adjustments" body={amountTemplate('adjustments')} sortable sortField="adjustments" style={{ width: '11%' }} />
                <Column header="Closing Bal." body={amountTemplate('closing_balance')} sortable sortField="closing_balance" style={{ width: '12%' }} />
                <Column header="Difference" body={amountTemplate('difference')} sortable sortField="difference" style={{ width: '11%' }} />
                <Column header="Status" body={statusTemplate} sortable sortField="status" style={{ width: '10%' }} />
              </DataTable>
            )}
          </TabPanel>

          {/* Exception Report Tab */}
          <TabPanel header="Exception Report">
            {exceptionQuery.isLoading && !exceptionQuery.data ? (
              renderLoading()
            ) : exceptionQuery.isError ? (
              renderError(exceptionQuery.error?.message, () => exceptionQuery.refetch())
            ) : !exceptionQuery.data?.items.length ? (
              renderEmpty('No exceptions found.')
            ) : (
              <DataTable
                value={exceptionQuery.data.items}
                paginator
                rows={DEFAULT_PAGE_SIZE}
                totalRecords={exceptionQuery.data.total}
                first={(exceptionPage - 1) * DEFAULT_PAGE_SIZE}
                onPage={(e) => setExceptionPage((e.page ?? 0) + 1)}
                rowsPerPageOptions={[10, 25, 50]}
                lazy
                loading={exceptionQuery.isLoading}
                sortMode="multiple"
                emptyMessage="No exceptions found."
              >
                <Column field="exception_id" header="Exception ID" sortable style={{ width: '10%' }} />
                <Column field="vendor_name" header="Vendor" sortable style={{ width: '22%' }} />
                <Column field="category" header="Category" sortable style={{ width: '14%' }} />
                <Column header="Amount" body={amountTemplate('amount')} sortable sortField="amount" style={{ width: '12%' }} />
                <Column field="age_days" header="Age (Days)" sortable style={{ width: '10%' }} />
                <Column header="Status" body={statusTemplate} sortable sortField="status" style={{ width: '12%' }} />
                <Column field="assigned_to" header="Assigned To" sortable style={{ width: '12%' }} />
              </DataTable>
            )}
          </TabPanel>

          {/* Vendor Status Tab */}
          <TabPanel header="Vendor Status">
            {vendorQuery.isLoading && !vendorQuery.data ? (
              renderLoading()
            ) : vendorQuery.isError ? (
              renderError(vendorQuery.error?.message, () => vendorQuery.refetch())
            ) : !vendorQuery.data?.items.length ? (
              renderEmpty('No vendors found.')
            ) : (
              <DataTable
                value={vendorQuery.data.items}
                paginator
                rows={DEFAULT_PAGE_SIZE}
                totalRecords={vendorQuery.data.total}
                first={(vendorPage - 1) * DEFAULT_PAGE_SIZE}
                onPage={(e) => setVendorPage((e.page ?? 0) + 1)}
                rowsPerPageOptions={[10, 25, 50]}
                lazy
                loading={vendorQuery.isLoading}
                sortMode="multiple"
                emptyMessage="No vendors found."
              >
                <Column field="vendor_code" header="Vendor Code" sortable style={{ width: '10%' }} />
                <Column field="vendor_name" header="Vendor Name" sortable style={{ width: '22%' }} />
                <Column field="total_invoices" header="Total Invoices" sortable style={{ width: '10%', textAlign: 'center' }} />
                <Column field="matched" header="Matched" sortable style={{ width: '9%', textAlign: 'center' }} />
                <Column field="unmatched" header="Unmatched" sortable style={{ width: '9%', textAlign: 'center' }} />
                <Column field="response_rate" header="Response Rate" sortable style={{ width: '10%' }} />
                <Column field="last_reco_date" header="Last Reco Date" sortable style={{ width: '12%' }} />
                <Column header="Status" body={statusTemplate} sortable sortField="status" style={{ width: '10%' }} />
              </DataTable>
            )}
          </TabPanel>

          {/* Monthly MIS Tab */}
          <TabPanel header="Monthly MIS">
            {misQuery.isLoading && !misQuery.data ? (
              renderLoading()
            ) : misQuery.isError ? (
              renderError(misQuery.error?.message, () => misQuery.refetch())
            ) : !misQuery.data?.items.length ? (
              renderEmpty('No MIS data found.')
            ) : (
              <DataTable
                value={misQuery.data.items}
                paginator
                rows={DEFAULT_PAGE_SIZE}
                totalRecords={misQuery.data.total}
                first={(misPage - 1) * DEFAULT_PAGE_SIZE}
                onPage={(e) => setMisPage((e.page ?? 0) + 1)}
                rowsPerPageOptions={[10, 25, 50]}
                lazy
                loading={misQuery.isLoading}
                sortMode="multiple"
                emptyMessage="No data found."
              >
                <Column field="month" header="Month" sortable style={{ width: '14%' }} />
                <Column field="total_vendors" header="Total Vendors" sortable style={{ width: '12%', textAlign: 'center' }} />
                <Column field="reco_completed" header="Reco Completed" sortable style={{ width: '12%', textAlign: 'center' }} />
                <Column field="exceptions_raised" header="Exceptions Raised" sortable style={{ width: '13%', textAlign: 'center' }} />
                <Column field="exceptions_resolved" header="Resolved" sortable style={{ width: '11%', textAlign: 'center' }} />
                <Column field="avg_resolution_days" header="Avg Resolution (Days)" sortable style={{ width: '14%', textAlign: 'center' }} />
                <Column field="match_rate" header="Match Rate" sortable style={{ width: '10%' }} />
              </DataTable>
            )}
          </TabPanel>
        </TabView>
      </div>
    </div>
  );
};
