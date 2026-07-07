/**
 * Track Reconciliation page — List of reconciliation requests with status tracking.
 */

import { useState } from 'react';
import { DataTable } from 'primereact/datatable';
import { Column } from 'primereact/column';
import { Button } from 'primereact/button';
import { InputText } from 'primereact/inputtext';
import { useNavigate } from 'react-router-dom';

interface RecoRequest {
  id: string;
  requestId: string;
  recoType: string;
  requestTitle: string;
  numberOfParties: number;
  recoPeriod: string;
  sendDate: string;
  status: string;
}

const sampleData: RecoRequest[] = [
  { id: '1', requestId: 'EPL-00094', recoType: 'Ledger', requestTitle: '1222', numberOfParties: 0, recoPeriod: '13-Jul-26 to 15-Jul-26', sendDate: '01-Jul-26', status: 'Not Sent' },
  { id: '2', requestId: 'EPL-00093', recoType: 'Ledger', requestTitle: 'Emcure', numberOfParties: 0, recoPeriod: '01-Apr-25 to 31-Mar-26', sendDate: '29-Jun-26', status: 'Not Sent' },
  { id: '3', requestId: 'EPL-00092', recoType: 'Ledger', requestTitle: 'Vaishal Enterprise Internal Reconciliation', numberOfParties: 1, recoPeriod: '01-Apr-23 to 31-Mar-26', sendDate: '22-Jun-26', status: 'open' },
  { id: '4', requestId: 'EPL-00091', recoType: 'Ledger', requestTitle: 'Rajeev gupsta data', numberOfParties: 0, recoPeriod: '01-Apr-25 to 31-Mar-26', sendDate: '10-Jun-26', status: 'Not Sent' },
  { id: '5', requestId: 'EPL-00090', recoType: 'Ledger', requestTitle: 'Test 2', numberOfParties: 1, recoPeriod: '01-Apr-25 to 31-Mar-26', sendDate: '02-Jun-26', status: 'open' },
  { id: '6', requestId: 'EPL-00089', recoType: 'Ledger', requestTitle: 'Test', numberOfParties: 1, recoPeriod: '01-Apr-25 to 31-Mar-26', sendDate: '01-Jun-26', status: 'open' },
  { id: '7', requestId: 'EPL-00087', recoType: 'Ledger', requestTitle: 'MAY-2026-ROLEOUT DATA', numberOfParties: 366, recoPeriod: '01-Apr-25 to 31-Mar-26', sendDate: '26-May-26', status: 'open' },
  { id: '8', requestId: 'EPL-00086', recoType: 'Ledger', requestTitle: 'V-XPRESS(A DIVISION OF V-TRANS INDI', numberOfParties: 1, recoPeriod: '01-Apr-24 to 31-Mar-26', sendDate: '10-Apr-28', status: 'open' },
  { id: '9', requestId: 'EPL-00085', recoType: 'Ledger', requestTitle: 'GATI KINTETSU EXPRESS PVT LTD', numberOfParties: 1, recoPeriod: '01-Apr-24 to 31-Mar-26', sendDate: '07-Apr-26', status: 'open' },
];

export const TrackReconciliationPage = () => {
  const [searchQuery, setSearchQuery] = useState('');
  const [requests] = useState<RecoRequest[]>(sampleData);
  const navigate = useNavigate();

  const statusTemplate = (rowData: RecoRequest) => (
    <span className={`status-badge ${rowData.status === 'open' ? 'open' : 'not-sent'}`}>
      {rowData.status}
    </span>
  );

  const actionTemplate = (rowData: RecoRequest) => (
    <div className="flex align-items-center gap-2">
      <span
        className="link-view"
        onClick={() => navigate(`/track-reconciliation/${rowData.requestId}`)}
        style={{ cursor: 'pointer' }}
      >
        View
      </span>
      <i className="pi pi-ellipsis-h" style={{ cursor: 'pointer', color: 'var(--color-text-muted)' }} />
    </div>
  );

  const filteredRequests = requests.filter(
    (r) =>
      r.requestTitle.toLowerCase().includes(searchQuery.toLowerCase()) ||
      r.requestId.toLowerCase().includes(searchQuery.toLowerCase())
  );

  return (
    <div>
      {/* Page Header */}
      <div className="em-page-header">
        <h2>Track Reconciliation</h2>
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
          <Button label="Add New Request" icon="pi pi-plus" />
        </div>
      </div>

      {/* Data Table */}
      <div className="em-card" style={{ padding: 0 }}>
        <DataTable
          value={filteredRequests}
          paginator
          rows={10}
          rowsPerPageOptions={[10, 25, 50]}
          sortMode="multiple"
          emptyMessage="No requests found."
        >
          <Column field="requestId" header="Request ID" sortable style={{ width: '10%' }} />
          <Column field="recoType" header="Reco Type" sortable style={{ width: '8%' }} />
          <Column field="requestTitle" header="Request Title" sortable style={{ width: '25%' }} />
          <Column field="numberOfParties" header="Number of Parties" sortable style={{ width: '10%', textAlign: 'center' }} />
          <Column field="recoPeriod" header="Reco Period" sortable style={{ width: '18%' }} />
          <Column field="sendDate" header="Send Date" sortable style={{ width: '10%' }} />
          <Column header="Status" body={statusTemplate} sortable style={{ width: '10%' }} />
          <Column header="Action" body={actionTemplate} style={{ width: '9%' }} />
        </DataTable>
      </div>
    </div>
  );
};
