/**
 * Direct Reconciliation page — List of direct reconciliation cases.
 */

import { useState } from 'react';
import { DataTable } from 'primereact/datatable';
import { Column } from 'primereact/column';
import { Button } from 'primereact/button';
import { InputText } from 'primereact/inputtext';

interface DirectRecoCase {
  id: string;
  partyCode: string;
  partyName: string;
  endDate: string;
  createdOn: string;
  recoStatus: string;
}

const sampleData: DirectRecoCase[] = [
  { id: '1', partyCode: 'AAFCS9777', partyName: 'SHREE PACK CONTAINERS PVT. LTD- Emcure', endDate: '31-Mar-25', createdOn: '10-Jul-25', recoStatus: 'Auto_Completed' },
  { id: '2', partyCode: 'ADXPS5053L', partyName: 'Emcure- Amity Prints', endDate: '31-Mar-25', createdOn: '28-Jun-25', recoStatus: 'Auto_Completed' },
  { id: '3', partyCode: 'Testing', partyName: 'Testing', endDate: '31-Mar-24', createdOn: '18-Dec-24', recoStatus: 'Auto_Completed' },
  { id: '4', partyCode: 'Testing', partyName: 'Testing', endDate: '31-Mar-24', createdOn: '12-Dec-24', recoStatus: 'Auto_Completed' },
  { id: '5', partyCode: 'Testing', partyName: 'Testing', endDate: '31-Mar-24', createdOn: '12-Dec-24', recoStatus: 'Auto_Completed' },
  { id: '6', partyCode: 'Testing', partyName: 'Testing', endDate: '31-Mar-24', createdOn: '15-Nov-24', recoStatus: 'Statement_Mapped' },
  { id: '7', partyCode: 'Testing', partyName: 'Testing', endDate: '31-Mar-24', createdOn: '07-Nov-24', recoStatus: 'Auto_Completed' },
  { id: '8', partyCode: 'Testing', partyName: 'Testing', endDate: '30-Oct-24', createdOn: '06-Nov-24', recoStatus: 'Auto_Completed' },
  { id: '9', partyCode: 'test individual', partyName: 'test', endDate: '30-Oct-24', createdOn: '30-Oct-24', recoStatus: 'Auto_Completed' },
  { id: '10', partyCode: 'Testing', partyName: 'Testing', endDate: '30-Oct-24', createdOn: '28-Oct-24', recoStatus: 'Auto_Completed' },
];

export const DirectReconciliationPage = () => {
  const [searchQuery, setSearchQuery] = useState('');
  const [cases] = useState<DirectRecoCase[]>(sampleData);

  const statusTemplate = (rowData: DirectRecoCase) => (
    <span className={`status-badge ${rowData.recoStatus === 'Auto_Completed' ? 'completed' : 'pending'}`}>
      {rowData.recoStatus}
    </span>
  );

  const actionTemplate = () => (
    <span className="link-view">View</span>
  );

  const filteredCases = cases.filter(
    (c) =>
      c.partyName.toLowerCase().includes(searchQuery.toLowerCase()) ||
      c.partyCode.toLowerCase().includes(searchQuery.toLowerCase())
  );

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
              style={{ border: 'none', boxShadow: 'none', width: 200 }}
            />
            <i className="pi pi-search" />
          </div>
          <Button label="New Reconciliation" icon="pi pi-plus" />
        </div>
      </div>

      {/* Data Table */}
      <div className="em-card" style={{ padding: 0 }}>
        <DataTable
          value={filteredCases}
          paginator
          rows={10}
          rowsPerPageOptions={[10, 25, 50]}
          sortMode="multiple"
          emptyMessage="No reconciliation cases found."
        >
          <Column field="partyCode" header="Party Code" sortable style={{ width: '15%' }} />
          <Column field="partyName" header="Party Name" sortable style={{ width: '30%' }} />
          <Column field="endDate" header="End Date" sortable style={{ width: '12%' }} />
          <Column field="createdOn" header="Created On" sortable style={{ width: '12%' }} />
          <Column header="Reco Status" body={statusTemplate} sortable style={{ width: '18%' }} />
          <Column header="Action" body={actionTemplate} style={{ width: '8%' }} />
        </DataTable>
      </div>
    </div>
  );
};
