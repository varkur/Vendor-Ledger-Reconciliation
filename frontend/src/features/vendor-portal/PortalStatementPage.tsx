/**
 * Vendor Portal Statement page — Shows reconciliation statement to the vendor.
 * Displays matched/unmatched items for vendor review.
 */

import { useState } from 'react';
import { DataTable } from 'primereact/datatable';
import { Column } from 'primereact/column';
import { Tag } from 'primereact/tag';
import { Button } from 'primereact/button';
import { useNavigate } from 'react-router-dom';

interface StatementLine {
  id: string;
  date: string;
  reference: string;
  description: string;
  companyAmount: number;
  vendorAmount: number;
  difference: number;
  matchStatus: 'Matched' | 'Mismatch' | 'Missing in Company' | 'Missing in Vendor';
}

const sampleStatement: StatementLine[] = [
  { id: '1', date: '05-Apr-25', reference: 'INV-10001', description: 'Supply of raw materials - Batch A', companyAmount: 125000, vendorAmount: 125000, difference: 0, matchStatus: 'Matched' },
  { id: '2', date: '12-Apr-25', reference: 'INV-10025', description: 'Packaging materials Q1', companyAmount: 85000, vendorAmount: 87500, difference: -2500, matchStatus: 'Mismatch' },
  { id: '3', date: '20-May-25', reference: 'INV-10048', description: 'Chemical solvents delivery', companyAmount: 210000, vendorAmount: 210000, difference: 0, matchStatus: 'Matched' },
  { id: '4', date: '03-Jun-25', reference: 'INV-10062', description: 'Lab equipment maintenance', companyAmount: 45000, vendorAmount: 0, difference: 45000, matchStatus: 'Missing in Vendor' },
  { id: '5', date: '15-Jul-25', reference: 'INV-10089', description: 'API intermediates supply', companyAmount: 380000, vendorAmount: 380000, difference: 0, matchStatus: 'Matched' },
  { id: '6', date: '22-Aug-25', reference: 'CN-2001', description: 'Credit note - quality return', companyAmount: -15000, vendorAmount: -15000, difference: 0, matchStatus: 'Matched' },
  { id: '7', date: '10-Sep-25', reference: 'INV-10110', description: 'Tablet coating materials', companyAmount: 0, vendorAmount: 92000, difference: -92000, matchStatus: 'Missing in Company' },
  { id: '8', date: '28-Oct-25', reference: 'INV-10135', description: 'Warehousing charges Q3', companyAmount: 67500, vendorAmount: 67500, difference: 0, matchStatus: 'Matched' },
  { id: '9', date: '15-Dec-25', reference: 'INV-10160', description: 'Year-end supply batch', companyAmount: 195000, vendorAmount: 198500, difference: -3500, matchStatus: 'Mismatch' },
  { id: '10', date: '20-Feb-26', reference: 'INV-10190', description: 'Capsule materials shipment', companyAmount: 142000, vendorAmount: 142000, difference: 0, matchStatus: 'Matched' },
];

export const PortalStatementPage = () => {
  const [statement] = useState<StatementLine[]>(sampleStatement);
  const navigate = useNavigate();

  const matchStatusTemplate = (rowData: StatementLine) => {
    const severityMap: Record<string, 'success' | 'danger' | 'warning' | 'info'> = {
      Matched: 'success',
      Mismatch: 'danger',
      'Missing in Company': 'warning',
      'Missing in Vendor': 'info',
    };
    return <Tag value={rowData.matchStatus} severity={severityMap[rowData.matchStatus]} />;
  };

  const amountTemplate = (field: string) => (rowData: Record<string, unknown>) => {
    const value = rowData[field] as number;
    if (value === 0 && (rowData.matchStatus === 'Missing in Company' || rowData.matchStatus === 'Missing in Vendor')) {
      return <span style={{ color: 'var(--color-text-muted)' }}>—</span>;
    }
    return <span style={{ color: value < 0 ? 'var(--color-error)' : 'inherit' }}>₹{value.toLocaleString('en-IN')}</span>;
  };

  const differenceTemplate = (rowData: StatementLine) => {
    if (rowData.difference === 0) return <span style={{ color: 'var(--color-success)' }}>₹0</span>;
    return (
      <span style={{ color: 'var(--color-error)', fontWeight: 500 }}>
        ₹{rowData.difference.toLocaleString('en-IN')}
      </span>
    );
  };

  const totalCompany = statement.reduce((sum, s) => sum + s.companyAmount, 0);
  const totalVendor = statement.reduce((sum, s) => sum + s.vendorAmount, 0);
  const matchedCount = statement.filter((s) => s.matchStatus === 'Matched').length;

  return (
    <div style={{ maxWidth: 1100, margin: '0 auto', padding: '24px' }}>
      {/* Header */}
      <div className="flex align-items-center justify-content-between mb-3">
        <div>
          <h2 style={{ margin: 0 }}>Reconciliation Statement</h2>
          <p style={{ color: 'var(--color-text-muted)', margin: '4px 0 0' }}>
            Period: April 2025 – March 2026 | Request: EPL-00087
          </p>
        </div>
        <Button label="Proceed to Sign-Off" icon="pi pi-check" onClick={() => navigate('/portal/sign-off')} />
      </div>

      {/* Summary */}
      <div className="flex gap-3 mb-3">
        <div className="em-card flex-1 text-center">
          <div style={{ fontSize: '1.25rem', fontWeight: 600 }}>₹{totalCompany.toLocaleString('en-IN')}</div>
          <div style={{ fontSize: '0.8rem', color: 'var(--color-text-muted)' }}>Company Balance</div>
        </div>
        <div className="em-card flex-1 text-center">
          <div style={{ fontSize: '1.25rem', fontWeight: 600 }}>₹{totalVendor.toLocaleString('en-IN')}</div>
          <div style={{ fontSize: '0.8rem', color: 'var(--color-text-muted)' }}>Vendor Balance</div>
        </div>
        <div className="em-card flex-1 text-center">
          <div style={{ fontSize: '1.25rem', fontWeight: 600, color: 'var(--color-success)' }}>{matchedCount}/{statement.length}</div>
          <div style={{ fontSize: '0.8rem', color: 'var(--color-text-muted)' }}>Matched Items</div>
        </div>
        <div className="em-card flex-1 text-center">
          <div style={{ fontSize: '1.25rem', fontWeight: 600, color: 'var(--color-error)' }}>₹{Math.abs(totalCompany - totalVendor).toLocaleString('en-IN')}</div>
          <div style={{ fontSize: '0.8rem', color: 'var(--color-text-muted)' }}>Net Difference</div>
        </div>
      </div>

      {/* Statement Table */}
      <div className="em-card" style={{ padding: 0 }}>
        <DataTable
          value={statement}
          paginator
          rows={10}
          rowsPerPageOptions={[10, 25, 50]}
          sortMode="multiple"
          emptyMessage="No statement data available."
        >
          <Column field="date" header="Date" sortable style={{ width: '9%' }} />
          <Column field="reference" header="Reference" sortable style={{ width: '10%' }} />
          <Column field="description" header="Description" sortable style={{ width: '24%' }} />
          <Column header="Company Amt." body={amountTemplate('companyAmount')} sortable sortField="companyAmount" style={{ width: '13%' }} />
          <Column header="Vendor Amt." body={amountTemplate('vendorAmount')} sortable sortField="vendorAmount" style={{ width: '13%' }} />
          <Column header="Difference" body={differenceTemplate} sortable sortField="difference" style={{ width: '12%' }} />
          <Column header="Status" body={matchStatusTemplate} sortable sortField="matchStatus" style={{ width: '14%' }} />
        </DataTable>
      </div>
    </div>
  );
};
