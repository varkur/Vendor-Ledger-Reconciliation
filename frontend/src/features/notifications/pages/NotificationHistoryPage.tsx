/**
 * Notification History page — Shows sent notifications per case with status tracking.
 * Includes Send Reminder functionality.
 */

import { useState } from 'react';
import { DataTable } from 'primereact/datatable';
import { Column } from 'primereact/column';
import { Button } from 'primereact/button';
import { InputText } from 'primereact/inputtext';
import { Tag } from 'primereact/tag';
import { Toast } from 'primereact/toast';
import { useRef } from 'react';

interface NotificationEntry {
  id: string;
  notificationId: string;
  caseId: string;
  type: 'Email' | 'SMS' | 'In-App' | 'WhatsApp';
  recipient: string;
  subject: string;
  timestamp: string;
  status: 'Sent' | 'Delivered' | 'Read' | 'Failed' | 'Pending';
  vendorName: string;
}

const sampleNotifications: NotificationEntry[] = [
  { id: '1', notificationId: 'NTF-001', caseId: 'EPL-00087', type: 'Email', recipient: 'accounts@arlifesciences.com', subject: 'Reconciliation Statement Request - Apr 2025 to Mar 2026', timestamp: '01-Jul-26 09:30 AM', status: 'Delivered', vendorName: 'A R LIFE SCIENCES PVT LTD' },
  { id: '2', notificationId: 'NTF-002', caseId: 'EPL-00087', type: 'Email', recipient: 'RHEA@ACPHARMS.COM', subject: 'Reconciliation Statement Request - Apr 2025 to Mar 2026', timestamp: '01-Jul-26 09:30 AM', status: 'Read', vendorName: 'A S C PHARMASPECIALITIES LLP' },
  { id: '3', notificationId: 'NTF-003', caseId: 'EPL-00087', type: 'SMS', recipient: '+91-98765XXXXX', subject: 'Statement reminder sent', timestamp: '01-Jul-26 09:31 AM', status: 'Sent', vendorName: 'AAF INDIA PVT LTD' },
  { id: '4', notificationId: 'NTF-004', caseId: 'EPL-00090', type: 'Email', recipient: 'accounts@aadtech.in', subject: 'Reminder: Pending Reconciliation', timestamp: '28-Jun-26 02:15 PM', status: 'Failed', vendorName: 'AAD TECH INDIA PVT LTD' },
  { id: '5', notificationId: 'NTF-005', caseId: 'EPL-00089', type: 'Email', recipient: 'amit.suryawanshi@aafindia.net', subject: 'Reconciliation Statement Request', timestamp: '27-Jun-26 11:00 AM', status: 'Read', vendorName: 'AAF INDIA PVT LTD' },
  { id: '6', notificationId: 'NTF-006', caseId: 'EPL-00087', type: 'In-App', recipient: 'System', subject: 'Reconciliation batch initiated for 366 vendors', timestamp: '26-May-26 10:00 AM', status: 'Delivered', vendorName: 'Multiple Vendors' },
  { id: '7', notificationId: 'NTF-007', caseId: 'EPL-00092', type: 'WhatsApp', recipient: '+91-87654XXXXX', subject: 'Statement upload confirmation', timestamp: '22-Jun-26 03:45 PM', status: 'Delivered', vendorName: 'Vaishal Enterprise' },
  { id: '8', notificationId: 'NTF-008', caseId: 'EPL-00087', type: 'Email', recipient: 'DAIRYFRESH1992@GMAIL.COM', subject: '2nd Reminder: Reconciliation Pending', timestamp: '15-Jun-26 09:00 AM', status: 'Sent', vendorName: 'A.V.C PACKERS' },
];

export const NotificationHistoryPage = () => {
  const [searchQuery, setSearchQuery] = useState('');
  const [notifications] = useState<NotificationEntry[]>(sampleNotifications);
  const [selectedNotifications, setSelectedNotifications] = useState<NotificationEntry[]>([]);
  const toast = useRef<Toast>(null);

  const typeTemplate = (rowData: NotificationEntry) => {
    const iconMap: Record<string, string> = {
      Email: 'pi pi-envelope',
      SMS: 'pi pi-mobile',
      'In-App': 'pi pi-bell',
      WhatsApp: 'pi pi-comments',
    };
    return (
      <div className="flex align-items-center gap-2">
        <i className={iconMap[rowData.type]} style={{ fontSize: '0.9rem' }} />
        <span>{rowData.type}</span>
      </div>
    );
  };

  const statusTemplate = (rowData: NotificationEntry) => {
    const severityMap: Record<string, 'success' | 'info' | 'warning' | 'danger' | undefined> = {
      Sent: 'info',
      Delivered: 'success',
      Read: 'success',
      Failed: 'danger',
      Pending: 'warning',
    };
    return <Tag value={rowData.status} severity={severityMap[rowData.status]} />;
  };

  const handleSendReminder = () => {
    if (selectedNotifications.length === 0) {
      toast.current?.show({ severity: 'warn', summary: 'No Selection', detail: 'Please select notifications to resend reminders.' });
      return;
    }
    toast.current?.show({
      severity: 'success',
      summary: 'Reminders Sent',
      detail: `Sent ${selectedNotifications.length} reminder(s) successfully.`,
    });
    setSelectedNotifications([]);
  };

  const filteredNotifications = notifications.filter(
    (n) =>
      n.recipient.toLowerCase().includes(searchQuery.toLowerCase()) ||
      n.vendorName.toLowerCase().includes(searchQuery.toLowerCase()) ||
      n.caseId.toLowerCase().includes(searchQuery.toLowerCase()) ||
      n.notificationId.toLowerCase().includes(searchQuery.toLowerCase())
  );

  return (
    <div>
      <Toast ref={toast} />

      {/* Page Header */}
      <div className="em-page-header">
        <h2>Notification History</h2>
        <div className="em-page-header-actions">
          <div className="em-search-bar">
            <InputText
              placeholder="Search notifications..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              style={{ border: 'none', boxShadow: 'none', width: 200 }}
            />
            <i className="pi pi-search" />
          </div>
          <Button
            label="Send Reminder"
            icon="pi pi-send"
            onClick={handleSendReminder}
            disabled={selectedNotifications.length === 0}
          />
        </div>
      </div>

      {/* Summary */}
      <div className="flex gap-3 mb-3">
        <div className="em-card flex-1 text-center">
          <div style={{ fontSize: '1.5rem', fontWeight: 600 }}>{notifications.length}</div>
          <div style={{ fontSize: '0.85rem', color: 'var(--color-text-muted)' }}>Total Sent</div>
        </div>
        <div className="em-card flex-1 text-center">
          <div style={{ fontSize: '1.5rem', fontWeight: 600, color: 'var(--color-success)' }}>
            {notifications.filter((n) => n.status === 'Delivered' || n.status === 'Read').length}
          </div>
          <div style={{ fontSize: '0.85rem', color: 'var(--color-text-muted)' }}>Delivered</div>
        </div>
        <div className="em-card flex-1 text-center">
          <div style={{ fontSize: '1.5rem', fontWeight: 600, color: 'var(--color-error)' }}>
            {notifications.filter((n) => n.status === 'Failed').length}
          </div>
          <div style={{ fontSize: '0.85rem', color: 'var(--color-text-muted)' }}>Failed</div>
        </div>
      </div>

      {/* Data Table */}
      <div className="em-card" style={{ padding: 0 }}>
        <DataTable
          value={filteredNotifications}
          paginator
          rows={10}
          rowsPerPageOptions={[10, 25, 50]}
          sortMode="multiple"
          emptyMessage="No notifications found."
          selection={selectedNotifications}
          onSelectionChange={(e) => setSelectedNotifications(e.value as NotificationEntry[])}
          selectionMode="checkbox"
        >
          <Column selectionMode="multiple" style={{ width: '3%' }} />
          <Column field="notificationId" header="ID" sortable style={{ width: '8%' }} />
          <Column field="caseId" header="Case ID" sortable style={{ width: '9%' }} />
          <Column header="Type" body={typeTemplate} sortable sortField="type" style={{ width: '9%' }} />
          <Column field="vendorName" header="Vendor" sortable style={{ width: '18%' }} />
          <Column field="recipient" header="Recipient" sortable style={{ width: '18%' }} />
          <Column field="subject" header="Subject" sortable style={{ width: '18%' }} />
          <Column field="timestamp" header="Timestamp" sortable style={{ width: '12%' }} />
          <Column header="Status" body={statusTemplate} sortable sortField="status" style={{ width: '8%' }} />
        </DataTable>
      </div>
    </div>
  );
};
