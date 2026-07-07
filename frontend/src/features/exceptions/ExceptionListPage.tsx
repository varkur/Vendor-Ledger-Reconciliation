/**
 * Exception Management page — List of reconciliation exceptions with severity, status, and resolution actions.
 */

import { useState } from 'react';
import { DataTable } from 'primereact/datatable';
import { Column } from 'primereact/column';
import { Button } from 'primereact/button';
import { InputText } from 'primereact/inputtext';
import { Tag } from 'primereact/tag';
import { ResolutionDialog } from './ResolutionDialog';

interface ExceptionItem {
  id: string;
  exceptionId: string;
  vendorName: string;
  category: string;
  severity: 'High' | 'Medium' | 'Low';
  amount: number;
  ageDays: number;
  status: 'Open' | 'In Progress' | 'Resolved' | 'Escalated';
  description: string;
  createdDate: string;
}

const sampleExceptions: ExceptionItem[] = [
  { id: '1', exceptionId: 'EXC-001', vendorName: 'A S C PHARMASPECIALITIES LLP', category: 'Amount Mismatch', severity: 'High', amount: 125000.50, ageDays: 45, status: 'Open', description: 'Invoice amount differs by ₹1,25,000', createdDate: '15-May-26' },
  { id: '2', exceptionId: 'EXC-002', vendorName: 'A R LIFE SCIENCES PVT LTD', category: 'Missing Invoice', severity: 'Medium', amount: 45000.00, ageDays: 30, status: 'In Progress', description: 'Invoice #INV-4523 not found in vendor ledger', createdDate: '01-Jun-26' },
  { id: '3', exceptionId: 'EXC-003', vendorName: 'AAF INDIA PVT LTD', category: 'Duplicate Entry', severity: 'Low', amount: 12500.00, ageDays: 12, status: 'Open', description: 'Duplicate payment entry detected', createdDate: '19-Jun-26' },
  { id: '4', exceptionId: 'EXC-004', vendorName: 'GATI KINTETSU EXPRESS PVT LTD', category: 'TDS Difference', severity: 'High', amount: 87500.00, ageDays: 60, status: 'Escalated', description: 'TDS deducted at wrong rate (2% vs 10%)', createdDate: '01-May-26' },
  { id: '5', exceptionId: 'EXC-005', vendorName: 'V-XPRESS LOGISTICS', category: 'Credit Note Pending', severity: 'Medium', amount: 32000.00, ageDays: 25, status: 'Open', description: 'Credit note CN-789 not reflected', createdDate: '06-Jun-26' },
  { id: '6', exceptionId: 'EXC-006', vendorName: 'AAD TECH INDIA PVT LTD', category: 'Amount Mismatch', severity: 'Low', amount: 5600.00, ageDays: 8, status: 'Resolved', description: 'Minor rounding difference', createdDate: '23-Jun-26' },
  { id: '7', exceptionId: 'EXC-007', vendorName: 'AAKRUTI HOSPITALITY PVT LTD', category: 'GST Mismatch', severity: 'High', amount: 67800.00, ageDays: 38, status: 'In Progress', description: 'GST rate mismatch on service invoice', createdDate: '24-May-26' },
  { id: '8', exceptionId: 'EXC-008', vendorName: 'A-1 ENTERPRISES', category: 'Missing Invoice', severity: 'Medium', amount: 28000.00, ageDays: 20, status: 'Open', description: 'Invoice not recorded in company books', createdDate: '11-Jun-26' },
];

export const ExceptionListPage = () => {
  const [searchQuery, setSearchQuery] = useState('');
  const [exceptions] = useState<ExceptionItem[]>(sampleExceptions);
  const [selectedExceptions, setSelectedExceptions] = useState<ExceptionItem[]>([]);
  const [resolutionDialogVisible, setResolutionDialogVisible] = useState(false);
  const [selectedExceptionForResolution, setSelectedExceptionForResolution] = useState<ExceptionItem | null>(null);

  const severityTemplate = (rowData: ExceptionItem) => {
    const severityMap: Record<string, 'danger' | 'warning' | 'info'> = {
      High: 'danger',
      Medium: 'warning',
      Low: 'info',
    };
    return <Tag value={rowData.severity} severity={severityMap[rowData.severity]} />;
  };

  const statusTemplate = (rowData: ExceptionItem) => {
    const statusClass: Record<string, string> = {
      Open: 'open',
      'In Progress': 'in-progress',
      Resolved: 'resolved',
      Escalated: 'escalated',
    };
    return (
      <span className={`status-badge ${statusClass[rowData.status] || ''}`}>
        {rowData.status}
      </span>
    );
  };

  const amountTemplate = (rowData: ExceptionItem) => (
    <span>₹{rowData.amount.toLocaleString('en-IN', { minimumFractionDigits: 2 })}</span>
  );

  const ageTemplate = (rowData: ExceptionItem) => (
    <span style={{ color: rowData.ageDays > 30 ? 'var(--color-error)' : 'inherit' }}>
      {rowData.ageDays} days
    </span>
  );

  const actionTemplate = (rowData: ExceptionItem) => (
    <div className="flex align-items-center gap-2">
      <Button
        icon="pi pi-check-circle"
        className="p-button-text p-button-sm"
        tooltip="Resolve"
        onClick={() => {
          setSelectedExceptionForResolution(rowData);
          setResolutionDialogVisible(true);
        }}
      />
      <Button icon="pi pi-eye" className="p-button-text p-button-sm" tooltip="View Details" />
    </div>
  );

  const filteredExceptions = exceptions.filter(
    (e) =>
      e.vendorName.toLowerCase().includes(searchQuery.toLowerCase()) ||
      e.exceptionId.toLowerCase().includes(searchQuery.toLowerCase()) ||
      e.category.toLowerCase().includes(searchQuery.toLowerCase())
  );

  return (
    <div>
      {/* Page Header */}
      <div className="em-page-header">
        <h2>Exception Management</h2>
        <div className="em-page-header-actions">
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
            {exceptions.filter((e) => e.status === 'Open').length}
          </div>
          <div style={{ fontSize: '0.85rem', color: 'var(--color-text-muted)' }}>Open</div>
        </div>
        <div className="em-card flex-1 text-center">
          <div style={{ fontSize: '1.5rem', fontWeight: 600, color: 'var(--color-warning)' }}>
            {exceptions.filter((e) => e.status === 'In Progress').length}
          </div>
          <div style={{ fontSize: '0.85rem', color: 'var(--color-text-muted)' }}>In Progress</div>
        </div>
        <div className="em-card flex-1 text-center">
          <div style={{ fontSize: '1.5rem', fontWeight: 600, color: 'var(--color-success)' }}>
            {exceptions.filter((e) => e.status === 'Resolved').length}
          </div>
          <div style={{ fontSize: '0.85rem', color: 'var(--color-text-muted)' }}>Resolved</div>
        </div>
        <div className="em-card flex-1 text-center">
          <div style={{ fontSize: '1.5rem', fontWeight: 600, color: 'var(--color-primary)' }}>
            {exceptions.filter((e) => e.status === 'Escalated').length}
          </div>
          <div style={{ fontSize: '0.85rem', color: 'var(--color-text-muted)' }}>Escalated</div>
        </div>
      </div>

      {/* Data Table */}
      <div className="em-card" style={{ padding: 0 }}>
        <DataTable
          value={filteredExceptions}
          paginator
          rows={10}
          rowsPerPageOptions={[10, 25, 50]}
          sortMode="multiple"
          emptyMessage="No exceptions found."
          selection={selectedExceptions}
          onSelectionChange={(e) => setSelectedExceptions(e.value as ExceptionItem[])}
          selectionMode="checkbox"
        >
          <Column selectionMode="multiple" style={{ width: '3%' }} />
          <Column field="exceptionId" header="Exception ID" sortable style={{ width: '10%' }} />
          <Column field="vendorName" header="Vendor" sortable style={{ width: '20%' }} />
          <Column field="category" header="Category" sortable style={{ width: '13%' }} />
          <Column header="Severity" body={severityTemplate} sortable sortField="severity" style={{ width: '9%' }} />
          <Column header="Amount" body={amountTemplate} sortable sortField="amount" style={{ width: '12%' }} />
          <Column header="Age" body={ageTemplate} sortable sortField="ageDays" style={{ width: '8%' }} />
          <Column header="Status" body={statusTemplate} sortable sortField="status" style={{ width: '10%' }} />
          <Column header="Action" body={actionTemplate} style={{ width: '10%' }} />
        </DataTable>
      </div>

      {/* Resolution Dialog */}
      <ResolutionDialog
        visible={resolutionDialogVisible}
        onHide={() => setResolutionDialogVisible(false)}
        exception={selectedExceptionForResolution}
        onConfirm={(action, comments) => {
          console.log('Resolution confirmed:', { exception: selectedExceptionForResolution, action, comments });
          setResolutionDialogVisible(false);
        }}
      />
    </div>
  );
};
