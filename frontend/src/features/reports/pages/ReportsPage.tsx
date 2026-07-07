/**
 * Reports & MIS page — Tabbed interface for reconciliation reports.
 * Tabs: Reconciliation Statement, Exception Report, Vendor Status, Monthly MIS
 */

import { useState } from 'react';
import { TabView, TabPanel } from 'primereact/tabview';
import { DataTable } from 'primereact/datatable';
import { Column } from 'primereact/column';
import { Button } from 'primereact/button';
import { Dropdown } from 'primereact/dropdown';

// --- Sample data for each tab ---

interface RecoStatement {
  id: string;
  vendorName: string;
  openingBalance: number;
  invoices: number;
  payments: number;
  adjustments: number;
  closingBalance: number;
  difference: number;
  status: string;
}

const recoStatementData: RecoStatement[] = [
  { id: '1', vendorName: 'A S C PHARMASPECIALITIES LLP', openingBalance: 500000, invoices: 250000, payments: 200000, adjustments: -10000, closingBalance: 540000, difference: 0, status: 'Matched' },
  { id: '2', vendorName: 'A R LIFE SCIENCES PVT LTD', openingBalance: 320000, invoices: 180000, payments: 150000, adjustments: 0, closingBalance: 350000, difference: 45000, status: 'Mismatch' },
  { id: '3', vendorName: 'AAF INDIA PVT LTD', openingBalance: 120000, invoices: 95000, payments: 80000, adjustments: -5000, closingBalance: 130000, difference: 12500, status: 'Mismatch' },
  { id: '4', vendorName: 'GATI KINTETSU EXPRESS PVT LTD', openingBalance: 780000, invoices: 450000, payments: 420000, adjustments: -30000, closingBalance: 780000, difference: 0, status: 'Matched' },
  { id: '5', vendorName: 'V-XPRESS LOGISTICS', openingBalance: 210000, invoices: 130000, payments: 100000, adjustments: 0, closingBalance: 240000, difference: 32000, status: 'Mismatch' },
];

interface ExceptionReport {
  id: string;
  exceptionId: string;
  vendorName: string;
  category: string;
  amount: number;
  ageDays: number;
  status: string;
  assignedTo: string;
}

const exceptionReportData: ExceptionReport[] = [
  { id: '1', exceptionId: 'EXC-001', vendorName: 'A S C PHARMASPECIALITIES LLP', category: 'Amount Mismatch', amount: 125000, ageDays: 45, status: 'Open', assignedTo: 'Rahul S.' },
  { id: '2', exceptionId: 'EXC-002', vendorName: 'A R LIFE SCIENCES PVT LTD', category: 'Missing Invoice', amount: 45000, ageDays: 30, status: 'In Progress', assignedTo: 'Priya M.' },
  { id: '3', exceptionId: 'EXC-004', vendorName: 'GATI KINTETSU EXPRESS PVT LTD', category: 'TDS Difference', amount: 87500, ageDays: 60, status: 'Escalated', assignedTo: 'Suresh K.' },
  { id: '4', exceptionId: 'EXC-007', vendorName: 'AAKRUTI HOSPITALITY PVT LTD', category: 'GST Mismatch', amount: 67800, ageDays: 38, status: 'In Progress', assignedTo: 'Anita R.' },
];

interface VendorStatus {
  id: string;
  vendorCode: string;
  vendorName: string;
  totalInvoices: number;
  matched: number;
  unmatched: number;
  responseRate: string;
  lastRecoDate: string;
  status: string;
}

const vendorStatusData: VendorStatus[] = [
  { id: '1', vendorCode: 'ARTFA2233P', vendorName: 'A S C PHARMASPECIALITIES LLP', totalInvoices: 45, matched: 42, unmatched: 3, responseRate: '93%', lastRecoDate: '28-Jun-26', status: 'Active' },
  { id: '2', vendorCode: 'AAGCA5553K', vendorName: 'A R LIFE SCIENCES PVT LTD', totalInvoices: 32, matched: 28, unmatched: 4, responseRate: '87%', lastRecoDate: '25-Jun-26', status: 'Active' },
  { id: '3', vendorCode: 'AAFCA4502R', vendorName: 'AAF INDIA PVT LTD', totalInvoices: 18, matched: 18, unmatched: 0, responseRate: '100%', lastRecoDate: '30-Jun-26', status: 'Completed' },
  { id: '4', vendorCode: 'AJBPB0367K', vendorName: 'GATI KINTETSU EXPRESS PVT LTD', totalInvoices: 56, matched: 48, unmatched: 8, responseRate: '85%', lastRecoDate: '20-Jun-26', status: 'Active' },
  { id: '5', vendorCode: 'AAFCA5196D', vendorName: 'V-XPRESS LOGISTICS', totalInvoices: 23, matched: 20, unmatched: 3, responseRate: '78%', lastRecoDate: '22-Jun-26', status: 'Pending' },
];

interface MonthlyMIS {
  id: string;
  month: string;
  totalVendors: number;
  recoCompleted: number;
  exceptionsRaised: number;
  exceptionsResolved: number;
  avgResolutionDays: number;
  matchRate: string;
}

const monthlyMISData: MonthlyMIS[] = [
  { id: '1', month: 'June 2026', totalVendors: 366, recoCompleted: 320, exceptionsRaised: 45, exceptionsResolved: 38, avgResolutionDays: 12, matchRate: '87%' },
  { id: '2', month: 'May 2026', totalVendors: 366, recoCompleted: 350, exceptionsRaised: 52, exceptionsResolved: 50, avgResolutionDays: 10, matchRate: '90%' },
  { id: '3', month: 'April 2026', totalVendors: 360, recoCompleted: 340, exceptionsRaised: 38, exceptionsResolved: 38, avgResolutionDays: 8, matchRate: '92%' },
  { id: '4', month: 'March 2026', totalVendors: 355, recoCompleted: 330, exceptionsRaised: 60, exceptionsResolved: 55, avgResolutionDays: 14, matchRate: '85%' },
];

// --- Export format options ---
const exportFormats = [
  { label: 'PDF', value: 'pdf' },
  { label: 'Excel', value: 'excel' },
];

export const ReportsPage = () => {
  const [activeTab, setActiveTab] = useState(0);
  const [exportFormat, setExportFormat] = useState('excel');

  const handleExport = () => {
    const tabNames = ['Reconciliation Statement', 'Exception Report', 'Vendor Status', 'Monthly MIS'];
    console.log(`Exporting ${tabNames[activeTab]} as ${exportFormat}`);
    // TODO: Implement actual export logic
  };

  const amountTemplate = (field: string) => (rowData: Record<string, unknown>) => (
    <span>₹{(rowData[field] as number).toLocaleString('en-IN')}</span>
  );

  const statusTemplate = (rowData: { status: string }) => (
    <span className={`status-badge ${rowData.status.toLowerCase().replace(/\s+/g, '-')}`}>
      {rowData.status}
    </span>
  );

  return (
    <div>
      {/* Page Header */}
      <div className="em-page-header">
        <h2>Reports & MIS</h2>
        <div className="em-page-header-actions">
          <Dropdown
            value={exportFormat}
            options={exportFormats}
            onChange={(e) => setExportFormat(e.value)}
            placeholder="Format"
            style={{ width: 120 }}
          />
          <Button label="Export" icon="pi pi-download" onClick={handleExport} />
        </div>
      </div>

      {/* Tabbed Reports */}
      <div className="em-card" style={{ padding: 0 }}>
        <TabView activeIndex={activeTab} onTabChange={(e) => setActiveTab(e.index)}>
          {/* Reconciliation Statement Tab */}
          <TabPanel header="Reconciliation Statement">
            <DataTable
              value={recoStatementData}
              paginator
              rows={10}
              rowsPerPageOptions={[10, 25, 50]}
              sortMode="multiple"
              emptyMessage="No data found."
            >
              <Column field="vendorName" header="Vendor Name" sortable style={{ width: '22%' }} />
              <Column header="Opening Bal." body={amountTemplate('openingBalance')} sortable sortField="openingBalance" style={{ width: '12%' }} />
              <Column header="Invoices" body={amountTemplate('invoices')} sortable sortField="invoices" style={{ width: '11%' }} />
              <Column header="Payments" body={amountTemplate('payments')} sortable sortField="payments" style={{ width: '11%' }} />
              <Column header="Adjustments" body={amountTemplate('adjustments')} sortable sortField="adjustments" style={{ width: '11%' }} />
              <Column header="Closing Bal." body={amountTemplate('closingBalance')} sortable sortField="closingBalance" style={{ width: '12%' }} />
              <Column header="Difference" body={amountTemplate('difference')} sortable sortField="difference" style={{ width: '11%' }} />
              <Column header="Status" body={statusTemplate} sortable sortField="status" style={{ width: '10%' }} />
            </DataTable>
          </TabPanel>

          {/* Exception Report Tab */}
          <TabPanel header="Exception Report">
            <DataTable
              value={exceptionReportData}
              paginator
              rows={10}
              rowsPerPageOptions={[10, 25, 50]}
              sortMode="multiple"
              emptyMessage="No exceptions found."
            >
              <Column field="exceptionId" header="Exception ID" sortable style={{ width: '10%' }} />
              <Column field="vendorName" header="Vendor" sortable style={{ width: '22%' }} />
              <Column field="category" header="Category" sortable style={{ width: '14%' }} />
              <Column header="Amount" body={amountTemplate('amount')} sortable sortField="amount" style={{ width: '12%' }} />
              <Column field="ageDays" header="Age (Days)" sortable style={{ width: '10%' }} />
              <Column header="Status" body={statusTemplate} sortable sortField="status" style={{ width: '12%' }} />
              <Column field="assignedTo" header="Assigned To" sortable style={{ width: '12%' }} />
            </DataTable>
          </TabPanel>

          {/* Vendor Status Tab */}
          <TabPanel header="Vendor Status">
            <DataTable
              value={vendorStatusData}
              paginator
              rows={10}
              rowsPerPageOptions={[10, 25, 50]}
              sortMode="multiple"
              emptyMessage="No vendors found."
            >
              <Column field="vendorCode" header="Vendor Code" sortable style={{ width: '10%' }} />
              <Column field="vendorName" header="Vendor Name" sortable style={{ width: '22%' }} />
              <Column field="totalInvoices" header="Total Invoices" sortable style={{ width: '10%', textAlign: 'center' }} />
              <Column field="matched" header="Matched" sortable style={{ width: '9%', textAlign: 'center' }} />
              <Column field="unmatched" header="Unmatched" sortable style={{ width: '9%', textAlign: 'center' }} />
              <Column field="responseRate" header="Response Rate" sortable style={{ width: '10%' }} />
              <Column field="lastRecoDate" header="Last Reco Date" sortable style={{ width: '12%' }} />
              <Column header="Status" body={statusTemplate} sortable sortField="status" style={{ width: '10%' }} />
            </DataTable>
          </TabPanel>

          {/* Monthly MIS Tab */}
          <TabPanel header="Monthly MIS">
            <DataTable
              value={monthlyMISData}
              paginator
              rows={10}
              rowsPerPageOptions={[10, 25, 50]}
              sortMode="multiple"
              emptyMessage="No data found."
            >
              <Column field="month" header="Month" sortable style={{ width: '14%' }} />
              <Column field="totalVendors" header="Total Vendors" sortable style={{ width: '12%', textAlign: 'center' }} />
              <Column field="recoCompleted" header="Reco Completed" sortable style={{ width: '12%', textAlign: 'center' }} />
              <Column field="exceptionsRaised" header="Exceptions Raised" sortable style={{ width: '13%', textAlign: 'center' }} />
              <Column field="exceptionsResolved" header="Resolved" sortable style={{ width: '11%', textAlign: 'center' }} />
              <Column field="avgResolutionDays" header="Avg Resolution (Days)" sortable style={{ width: '14%', textAlign: 'center' }} />
              <Column field="matchRate" header="Match Rate" sortable style={{ width: '10%' }} />
            </DataTable>
          </TabPanel>
        </TabView>
      </div>
    </div>
  );
};
