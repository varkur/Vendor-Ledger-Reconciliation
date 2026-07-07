/**
 * Reconciliation Detail Page — Tabbed view with Statistics, All Parties, Reco Stage,
 * Review Stage, Sign Off Stage, and Action Tracker tabs.
 */

import { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Button } from 'primereact/button';
import { DataTable } from 'primereact/datatable';
import { Column } from 'primereact/column';
import { InputText } from 'primereact/inputtext';
import { StatisticsTab } from '../components/StatisticsTab';

type TabKey = 'statistics' | 'allParties' | 'recoStage' | 'reviewStage' | 'signOffStage' | 'actionTracker';

interface PartyRow {
  id: string;
  partyCode: string;
  partyName: string;
  status: string;
  lastUpdateDate: string;
  noOfDays: number;
  companyAmount: string;
  differenceAmount: string;
}

const allPartiesData: PartyRow[] = [
  { id: '1', partyCode: 'AAACR2346K', partyName: 'BRUKER INDIA SCIENTIFIC PVT LTD', status: 'Delivered', lastUpdateDate: '26-May-2026', noOfDays: 36, companyAmount: '-18,18,810', differenceAmount: '18,18,810' },
  { id: '2', partyCode: 'AAFCA6387P', partyName: 'AMI POLYMER PVT. LTD.', status: 'Delivered', lastUpdateDate: '26-May-2026', noOfDays: 36, companyAmount: '-49,82,158', differenceAmount: '49,82,158' },
  { id: '3', partyCode: 'DFLPP8600R', partyName: 'SAUMYA ENGINEERING', status: 'Read', lastUpdateDate: '26-May-2026', noOfDays: 36, companyAmount: '-7,01,424', differenceAmount: '7,01,424' },
  { id: '4', partyCode: 'AADCR2458M', partyName: 'SRSG BROADCAST INDIA PVT LTD', status: 'Delivered', lastUpdateDate: '26-May-2026', noOfDays: 36, companyAmount: '84,03,380', differenceAmount: '84,03,380' },
  { id: '5', partyCode: 'AAFCE2555C', partyName: 'EUROFINS ADVINUS BIOPHARMA SERVICES', status: 'Delivered', lastUpdateDate: '25-May-2026', noOfDays: 36, companyAmount: '0', differenceAmount: '0' },
  { id: '6', partyCode: 'ADKPG9872H', partyName: 'ENGINEERING WORKS', status: 'Delivered', lastUpdateDate: '26-May-2026', noOfDays: 36, companyAmount: '-5,17,919', differenceAmount: '5,17,919' },
  { id: '7', partyCode: 'AOPPP4338H', partyName: 'OM EXIM', status: 'Reviewed', lastUpdateDate: '12-Jun-2025', noOfDays: 19, companyAmount: '-8,22,040', differenceAmount: '0' },
  { id: '8', partyCode: 'AABCT5040M', partyName: 'T.G.DEVELOPERS PVT.LTD.', status: 'Delivered', lastUpdateDate: '26-May-2026', noOfDays: 36, companyAmount: '0', differenceAmount: '0' },
];

interface RecoStageRow {
  id: string;
  partyCode: string;
  partyName: string;
  status: string;
  fileExtension: string;
  owner: string;
  noOfDays: number;
  noOfLines: number;
  companyAmount: string;
  differenceAmount: string;
}

const recoStageData: RecoStageRow[] = [
  { id: '1', partyCode: 'AAUCS4616H', partyName: 'NOVENTIQ SERVICES INDIA PRIVATE LIM', status: 'Mapping_Pending', fileExtension: 'xlsx', owner: '', noOfDays: 15, noOfLines: 0, companyAmount: '-2,81,596', differenceAmount: '2,52,353' },
  { id: '2', partyCode: 'AAZCS7760H', partyName: 'SECURITYHQ INDIA PRIVATE LIMITED', status: 'In_Progress', fileExtension: 'xlsx', owner: '', noOfDays: 2, noOfLines: 11, companyAmount: '-69,81,956', differenceAmount: '6,46,478' },
  { id: '3', partyCode: 'AAACL0820G', partyName: 'LYKA LABORATORIES LTD.', status: 'Auto_Completed', fileExtension: 'xlsx', owner: '', noOfDays: 12, noOfLines: 71, companyAmount: '-87,12,726', differenceAmount: '1,49,54,779' },
  { id: '4', partyCode: 'ATKPP5981G', partyName: 'CITRINE TRADE SOLUTION', status: 'Auto_Completed', fileExtension: 'xlsx', owner: '', noOfDays: 19, noOfLines: 71, companyAmount: '-16,500', differenceAmount: '2,83,200' },
  { id: '5', partyCode: 'AA8FC7908E', partyName: 'C.ABHAYKUMAR & CO.', status: 'Mapping_Pending', fileExtension: 'xls', owner: '', noOfDays: 25, noOfLines: 2, companyAmount: '-90,85,974', differenceAmount: '1,82,30,860' },
];

interface ReviewStageRow {
  id: string;
  partyCode: string;
  partyName: string;
  status: string;
  owner: string;
  reviewer: string;
  noOfDays: number;
  noOfLines: number;
  unmatchedEntries: string;
  companyAmount: string;
  differenceAmount: string;
}

const reviewStageData: ReviewStageRow[] = [
  { id: '1', partyCode: 'AOPPP4338H', partyName: 'OM EXIM', status: 'Reviewed', owner: '', reviewer: '', noOfDays: 19, noOfLines: 104, unmatchedEntries: '', companyAmount: '-8,22,040', differenceAmount: '0' },
  { id: '2', partyCode: 'AACCK3065G', partyName: 'KITTEN ENTERPRISES PRIVATE LIMITED', status: 'Reviewed', owner: '', reviewer: '', noOfDays: 22, noOfLines: 67, unmatchedEntries: '', companyAmount: '-8,34,995', differenceAmount: '0' },
  { id: '3', partyCode: 'AAVCS4034Q', partyName: 'SEVEN SFAS HUMAN RESOURCE', status: 'Review_Pending', owner: '', reviewer: '', noOfDays: 19, noOfLines: 264, unmatchedEntries: '', companyAmount: '-25,47,437', differenceAmount: '21,29,649' },
  { id: '4', partyCode: 'AAECK5757H', partyName: 'KHC HEALTHCARE INDIA PRIVATE LIMITE', status: 'Reviewed', owner: '', reviewer: '', noOfDays: 35, noOfLines: 121, unmatchedEntries: '', companyAmount: '-33,97,071', differenceAmount: '6,97,894' },
];

interface SignOffRow {
  id: string;
  partyCode: string;
  partyName: string;
  status: string;
  noOfDays: number;
  reminderCount: number;
  owner: string;
  contactNumber: string;
}

const signOffData: SignOffRow[] = [
  { id: '1', partyCode: 'ANYPS8834M', partyName: 'AUTOPACK INDUSTRIES', status: 'Signoff_Requested', noOfDays: 33, reminderCount: 0, owner: 'Sir/Madam', contactNumber: '' },
  { id: '2', partyCode: 'AAGHB3657N', partyName: 'PATEL ELECTRIC & TRADING COMPANY', status: 'Signoff_Completed', noOfDays: 15, reminderCount: 0, owner: 'Sir/Madam', contactNumber: '' },
  { id: '3', partyCode: 'AALCP5737F', partyName: 'PGP GLASS PRIVATE LIMITED - KOSAMBA', status: 'Signoff_Requested', noOfDays: 19, reminderCount: 0, owner: '', contactNumber: '' },
  { id: '4', partyCode: 'AAHCA9685M', partyName: 'ADVANCED EXPERTISE TECHNOLOGY', status: 'Signoff_Completed', noOfDays: 11, reminderCount: 0, owner: '', contactNumber: '' },
  { id: '5', partyCode: 'AADCC4876C', partyName: 'CHARLES RIVER LABORATORIES', status: 'Signoff_Completed', noOfDays: 7, reminderCount: 0, owner: 'Blossom Pathare', contactNumber: '' },
];

interface ActionTrackerRow {
  id: string;
  actionTakenStatus: string;
  numberOfRecords: number;
  percentage: string;
  amountInLakhs: string;
}

const actionTrackerData: ActionTrackerRow[] = [
  { id: '1', actionTakenStatus: 'No Action Required', numberOfRecords: 2, percentage: '1%', amountInLakhs: '0' },
  { id: '2', actionTakenStatus: 'Pending with Company', numberOfRecords: 95, percentage: '60%', amountInLakhs: '-22' },
  { id: '3', actionTakenStatus: 'Pending with Party', numberOfRecords: 62, percentage: '39%', amountInLakhs: '37' },
  { id: '4', actionTakenStatus: 'Total', numberOfRecords: 159, percentage: '100%', amountInLakhs: '' },
];

export const ReconciliationDetailPage = () => {
  const { requestId } = useParams<{ requestId: string }>();
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState<TabKey>('statistics');
  const [searchQuery, setSearchQuery] = useState('');

  const tabs: { key: TabKey; label: string; badge?: number }[] = [
    { key: 'statistics', label: 'Statistics' },
    { key: 'allParties', label: 'All Parties' },
    { key: 'recoStage', label: 'Reco Stage', badge: 99 },
    { key: 'reviewStage', label: 'Review Stage', badge: 13 },
    { key: 'signOffStage', label: 'Sign Off Stage', badge: 17 },
    { key: 'actionTracker', label: 'Action Tracker' },
  ];

  const actionTemplate = () => (
    <div className="flex align-items-center gap-2">
      <span className="link-view">View</span>
      <i className="pi pi-ellipsis-h" style={{ cursor: 'pointer', color: 'var(--color-text-muted)' }} />
    </div>
  );

  const actionTrackerActionTemplate = () => (
    <span className="link-view">View</span>
  );

  return (
    <div>
      {/* Breadcrumb */}
      <div className="flex align-items-center gap-2 mb-3" style={{ fontSize: 12, color: 'var(--color-text-secondary)' }}>
        <span className="cursor-pointer" onClick={() => navigate('/track-reconciliation')} style={{ color: 'var(--color-primary)' }}>
          Track Reconciliation
        </span>
        <span>&gt;</span>
        <span>{requestId || 'MAY-2026-ROLEOUT DATA'}</span>
        <span>&gt;</span>
        <span>{tabs.find(t => t.key === activeTab)?.label}</span>
      </div>

      {/* Header Info */}
      <div className="flex align-items-center justify-content-between mb-4 p-3" style={{ background: 'var(--color-surface)', borderRadius: 'var(--radius-md)', border: '1px solid var(--color-surface-border)' }}>
        <div className="flex align-items-center gap-4">
          <Button icon="pi pi-arrow-left" className="p-button-text p-button-sm" onClick={() => navigate('/track-reconciliation')} />
          <div>
            <span className="text-sm" style={{ color: 'var(--color-text-muted)' }}>Reco Type</span>
            <span className="ml-3 font-semibold">bulkreco</span>
          </div>
          <div>
            <span className="text-sm" style={{ color: 'var(--color-text-muted)' }}>Reco Period</span>
            <span className="ml-3 font-semibold">01-Apr-2025 to 31-Mar-2026</span>
          </div>
        </div>
        <Button label="More Actions" icon="pi pi-chevron-down" iconPos="right" className="p-button-outlined p-button-sm" />
      </div>

      {/* Pipeline Tabs */}
      <div className="em-pipeline-tabs">
        {tabs.map((tab) => (
          <button
            key={tab.key}
            className={`em-pipeline-tab ${activeTab === tab.key ? 'active' : ''}`}
            onClick={() => setActiveTab(tab.key)}
          >
            {tab.label}
            {tab.badge !== undefined && (
              <span className="badge">{tab.badge > 99 ? '99+' : tab.badge}</span>
            )}
          </button>
        ))}
      </div>

      {/* Tab Content */}
      {activeTab === 'statistics' && <StatisticsTab />}

      {activeTab === 'allParties' && (
        <div>
          <div className="em-action-bar">
            <Button label="Send Reminder" icon="pi pi-send" className="p-button-outlined p-button-sm" />
            <Button label="Bulk Actions" icon="pi pi-ellipsis-h" className="p-button-outlined p-button-sm" />
            <div className="flex-1" />
            <div className="em-search-bar">
              <InputText
                placeholder="Type and press enter to Search"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                style={{ border: 'none', boxShadow: 'none', width: 180 }}
              />
              <i className="pi pi-search" />
            </div>
          </div>
          <div className="em-card" style={{ padding: 0 }}>
            <DataTable value={allPartiesData} paginator rows={10} sortMode="multiple" emptyMessage="No parties found.">
              <Column selectionMode="multiple" headerStyle={{ width: '3rem' }} />
              <Column field="partyCode" header="Party Code" sortable style={{ width: '12%' }} />
              <Column field="partyName" header="Party Name" sortable style={{ width: '25%' }} />
              <Column field="status" header="Status" sortable style={{ width: '10%' }} />
              <Column field="lastUpdateDate" header="Last Update Date" sortable style={{ width: '12%' }} />
              <Column field="noOfDays" header="No. of Days" sortable style={{ width: '8%', textAlign: 'center' }} />
              <Column field="companyAmount" header="Company Amount" sortable style={{ width: '12%', textAlign: 'right' }} />
              <Column field="differenceAmount" header="Difference Amount" sortable style={{ width: '12%', textAlign: 'right' }} />
              <Column header="Action" body={actionTemplate} style={{ width: '8%' }} />
            </DataTable>
          </div>
        </div>
      )}

      {activeTab === 'recoStage' && (
        <div>
          <div className="em-action-bar">
            <Button label="Send For Review" icon="pi pi-send" className="p-button-outlined p-button-sm" />
            <Button label="Bulk Actions" icon="pi pi-ellipsis-h" className="p-button-outlined p-button-sm" />
            <div className="flex-1" />
            <div className="em-search-bar">
              <InputText
                placeholder="Type and press enter to Search"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                style={{ border: 'none', boxShadow: 'none', width: 180 }}
              />
              <i className="pi pi-search" />
            </div>
          </div>
          <div className="em-card" style={{ padding: 0 }}>
            <DataTable value={recoStageData} paginator rows={10} sortMode="multiple" emptyMessage="No records found.">
              <Column selectionMode="multiple" headerStyle={{ width: '3rem' }} />
              <Column field="partyCode" header="Party Code" sortable style={{ width: '10%' }} />
              <Column field="partyName" header="Party Name" sortable style={{ width: '22%' }} />
              <Column field="status" header="Status" sortable style={{ width: '12%' }} />
              <Column field="fileExtension" header="File Extension" sortable style={{ width: '8%' }} />
              <Column field="owner" header="Owner" sortable style={{ width: '8%' }} />
              <Column field="noOfDays" header="No.of Days" sortable style={{ width: '7%', textAlign: 'center' }} />
              <Column field="noOfLines" header="No.of Lines" sortable style={{ width: '7%', textAlign: 'center' }} />
              <Column field="companyAmount" header="Company Amount" sortable style={{ width: '12%', textAlign: 'right' }} />
              <Column field="differenceAmount" header="Difference Amount" sortable style={{ width: '12%', textAlign: 'right' }} />
              <Column header="Action" body={actionTemplate} style={{ width: '8%' }} />
            </DataTable>
          </div>
        </div>
      )}

      {activeTab === 'reviewStage' && (
        <div>
          <div className="em-action-bar">
            <Button label="Review Done" icon="pi pi-check" className="p-button-outlined p-button-sm" />
            <Button label="Request SignOff" icon="pi pi-verified" className="p-button-outlined p-button-sm" />
            <Button label="Bulk Actions" icon="pi pi-ellipsis-h" className="p-button-outlined p-button-sm" />
            <div className="flex-1" />
            <div className="em-search-bar">
              <InputText
                placeholder="Type and press enter to Search"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                style={{ border: 'none', boxShadow: 'none', width: 180 }}
              />
              <i className="pi pi-search" />
            </div>
          </div>
          <div className="em-card" style={{ padding: 0 }}>
            <DataTable value={reviewStageData} paginator rows={10} sortMode="multiple" emptyMessage="No records found.">
              <Column selectionMode="multiple" headerStyle={{ width: '3rem' }} />
              <Column field="partyCode" header="Party Code" sortable style={{ width: '10%' }} />
              <Column field="partyName" header="Party Name" sortable style={{ width: '20%' }} />
              <Column field="status" header="Status" sortable style={{ width: '10%' }} />
              <Column field="owner" header="Owner" sortable style={{ width: '8%' }} />
              <Column field="reviewer" header="Reviewer" sortable style={{ width: '8%' }} />
              <Column field="noOfDays" header="No. of Days" sortable style={{ width: '7%', textAlign: 'center' }} />
              <Column field="noOfLines" header="No. of Lines" sortable style={{ width: '7%', textAlign: 'center' }} />
              <Column field="unmatchedEntries" header="Unmatched Entries" sortable style={{ width: '10%' }} />
              <Column field="companyAmount" header="Company Amount" sortable style={{ width: '10%', textAlign: 'right' }} />
              <Column field="differenceAmount" header="Difference Amount" sortable style={{ width: '10%', textAlign: 'right' }} />
              <Column header="Action" body={actionTemplate} style={{ width: '8%' }} />
            </DataTable>
          </div>
        </div>
      )}

      {activeTab === 'signOffStage' && (
        <div>
          <div className="em-action-bar">
            <Button label="Send Reminder" icon="pi pi-send" className="p-button-outlined p-button-sm" />
            <Button label="Bulk Actions" icon="pi pi-ellipsis-h" className="p-button-outlined p-button-sm" />
            <div className="flex-1" />
            <div className="em-search-bar">
              <InputText
                placeholder="Type and press enter to Search"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                style={{ border: 'none', boxShadow: 'none', width: 180 }}
              />
              <i className="pi pi-search" />
            </div>
          </div>
          <div className="em-card" style={{ padding: 0 }}>
            <DataTable value={signOffData} paginator rows={10} sortMode="multiple" emptyMessage="No records found.">
              <Column selectionMode="multiple" headerStyle={{ width: '3rem' }} />
              <Column field="partyCode" header="Party Code" sortable style={{ width: '12%' }} />
              <Column field="partyName" header="Party Name" sortable style={{ width: '25%' }} />
              <Column field="status" header="Status" sortable style={{ width: '14%' }} />
              <Column field="noOfDays" header="No. of Days" sortable style={{ width: '8%', textAlign: 'center' }} />
              <Column field="reminderCount" header="Reminder Count" sortable style={{ width: '10%', textAlign: 'center' }} />
              <Column field="owner" header="Owner" sortable style={{ width: '12%' }} />
              <Column field="contactNumber" header="Contact Number" sortable style={{ width: '12%' }} />
              <Column header="Action" body={actionTemplate} style={{ width: '8%' }} />
            </DataTable>
          </div>
        </div>
      )}

      {activeTab === 'actionTracker' && (
        <div>
          <div className="em-card" style={{ padding: 0 }}>
            <DataTable value={actionTrackerData} emptyMessage="No records found."
              rowClassName={(data) => data.actionTakenStatus === 'Total' ? 'font-bold' : ''}
            >
              <Column field="actionTakenStatus" header="Action Taken Status" sortable style={{ width: '25%' }} />
              <Column field="numberOfRecords" header="Number of Records" sortable style={{ width: '15%', textAlign: 'center' }} />
              <Column field="percentage" header="Percentage" sortable style={{ width: '15%', textAlign: 'center' }} />
              <Column field="amountInLakhs" header="Amount(In Lakhs)" sortable style={{ width: '20%', textAlign: 'right' }} />
              <Column header="Action" body={actionTrackerActionTemplate} style={{ width: '10%' }} />
            </DataTable>
          </div>
        </div>
      )}
    </div>
  );
};
