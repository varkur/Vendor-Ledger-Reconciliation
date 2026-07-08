/**
 * Notification History page — Shows sent notifications per case with status tracking.
 * Wired to backend GET /api/v1/vlr/notifications with server-side pagination and search.
 * Includes Send Reminder and Mark as Read functionality.
 *
 * Requirements: 23.5, 25.1, 25.2
 */

import { useState, useRef, useCallback } from 'react';
import { DataTable } from 'primereact/datatable';
import { Column } from 'primereact/column';
import { Button } from 'primereact/button';
import { InputText } from 'primereact/inputtext';
import { Tag } from 'primereact/tag';
import { Toast } from 'primereact/toast';
import { ProgressSpinner } from 'primereact/progressspinner';
import { Message } from 'primereact/message';

import { useNotificationList, useMarkAsRead, useSendReminder } from '../hooks/useNotifications';
import type { NotificationEntry } from '../api/notificationsApi';

// ─────────────────────────────────────────────────────────────────────────────
// Constants
// ─────────────────────────────────────────────────────────────────────────────

const DEFAULT_PAGE_SIZE = 10;

// ─────────────────────────────────────────────────────────────────────────────
// Component
// ─────────────────────────────────────────────────────────────────────────────

export const NotificationHistoryPage = () => {
  const toast = useRef<Toast>(null);

  // State
  const [searchQuery, setSearchQuery] = useState('');
  const [appliedSearch, setAppliedSearch] = useState('');
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE);
  const [selectedNotifications, setSelectedNotifications] = useState<NotificationEntry[]>([]);

  // API hooks
  const { data, isLoading, isError, error, refetch } = useNotificationList({
    page,
    page_size: pageSize,
    search: appliedSearch || undefined,
  });

  const markAsReadMutation = useMarkAsRead();
  const sendReminderMutation = useSendReminder();

  // Handlers
  const handleSearch = useCallback(() => {
    setAppliedSearch(searchQuery);
    setPage(1);
  }, [searchQuery]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === 'Enter') handleSearch();
    },
    [handleSearch]
  );

  const handleSendReminder = useCallback(() => {
    if (selectedNotifications.length === 0) {
      toast.current?.show({
        severity: 'warn',
        summary: 'No Selection',
        detail: 'Please select notifications to resend reminders.',
      });
      return;
    }

    const ids = selectedNotifications.map((n) => n.id);
    sendReminderMutation.mutate(ids, {
      onSuccess: (response) => {
        toast.current?.show({
          severity: 'success',
          summary: 'Reminders Sent',
          detail: `Sent ${response.sent_count} reminder(s) successfully.`,
        });
        setSelectedNotifications([]);
      },
      onError: (err) => {
        toast.current?.show({
          severity: 'error',
          summary: 'Send Failed',
          detail: err.message || 'Failed to send reminders. Please try again.',
        });
      },
    });
  }, [selectedNotifications, sendReminderMutation]);

  const handleMarkAsRead = useCallback(() => {
    if (selectedNotifications.length === 0) return;

    const ids = selectedNotifications.map((n) => n.id);
    markAsReadMutation.mutate(ids, {
      onSuccess: (response) => {
        toast.current?.show({
          severity: 'info',
          summary: 'Marked as Read',
          detail: `${response.updated_count} notification(s) marked as read.`,
        });
        setSelectedNotifications([]);
      },
      onError: (err) => {
        toast.current?.show({
          severity: 'error',
          summary: 'Update Failed',
          detail: err.message || 'Failed to mark notifications. Please try again.',
        });
      },
    });
  }, [selectedNotifications, markAsReadMutation]);

  const handlePageChange = useCallback((event: { page: number; rows: number }) => {
    setPage(event.page + 1);
    setPageSize(event.rows);
  }, []);

  // Column templates
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

  // Derived values
  const notifications = data?.items ?? [];
  const totalRecords = data?.total ?? 0;
  const deliveredCount = notifications.filter(
    (n) => n.status === 'Delivered' || n.status === 'Read'
  ).length;
  const failedCount = notifications.filter((n) => n.status === 'Failed').length;

  // ─── Loading state ─────────────────────────────────────────────────────────
  if (isLoading && !data) {
    return (
      <div className="flex justify-content-center align-items-center" style={{ minHeight: 300 }}>
        <ProgressSpinner style={{ width: '50px', height: '50px' }} />
      </div>
    );
  }

  // ─── Error state ───────────────────────────────────────────────────────────
  if (isError) {
    return (
      <div className="flex flex-column align-items-center gap-3" style={{ padding: '2rem' }}>
        <Message
          severity="error"
          text={error?.message || 'Failed to load notifications. Please try again.'}
        />
        <Button label="Retry" icon="pi pi-refresh" onClick={() => refetch()} />
      </div>
    );
  }

  // ─── Render ────────────────────────────────────────────────────────────────
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
              onKeyDown={handleKeyDown}
              style={{ border: 'none', boxShadow: 'none', width: 200 }}
            />
            <i className="pi pi-search" style={{ cursor: 'pointer' }} onClick={handleSearch} />
          </div>
          <Button
            label="Mark as Read"
            icon="pi pi-check"
            className="p-button-outlined"
            onClick={handleMarkAsRead}
            disabled={selectedNotifications.length === 0}
            loading={markAsReadMutation.isPending}
          />
          <Button
            label="Send Reminder"
            icon="pi pi-send"
            onClick={handleSendReminder}
            disabled={selectedNotifications.length === 0}
            loading={sendReminderMutation.isPending}
          />
        </div>
      </div>

      {/* Summary */}
      <div className="flex gap-3 mb-3">
        <div className="em-card flex-1 text-center">
          <div style={{ fontSize: '1.5rem', fontWeight: 600 }}>{totalRecords}</div>
          <div style={{ fontSize: '0.85rem', color: 'var(--color-text-muted)' }}>Total Sent</div>
        </div>
        <div className="em-card flex-1 text-center">
          <div style={{ fontSize: '1.5rem', fontWeight: 600, color: 'var(--color-success)' }}>
            {deliveredCount}
          </div>
          <div style={{ fontSize: '0.85rem', color: 'var(--color-text-muted)' }}>Delivered</div>
        </div>
        <div className="em-card flex-1 text-center">
          <div style={{ fontSize: '1.5rem', fontWeight: 600, color: 'var(--color-error)' }}>
            {failedCount}
          </div>
          <div style={{ fontSize: '0.85rem', color: 'var(--color-text-muted)' }}>Failed</div>
        </div>
      </div>

      {/* Data Table */}
      <div className="em-card" style={{ padding: 0 }}>
        {notifications.length === 0 && !isLoading ? (
          <div className="flex flex-column align-items-center gap-2" style={{ padding: '3rem' }}>
            <i className="pi pi-bell" style={{ fontSize: '2rem', color: 'var(--color-text-muted)' }} />
            <p style={{ color: 'var(--color-text-muted)' }}>No notifications found.</p>
          </div>
        ) : (
          <DataTable
            value={notifications}
            paginator
            rows={pageSize}
            totalRecords={totalRecords}
            first={(page - 1) * pageSize}
            onPage={handlePageChange}
            rowsPerPageOptions={[10, 25, 50]}
            lazy
            loading={isLoading}
            sortMode="multiple"
            emptyMessage="No notifications found."
            selection={selectedNotifications}
            onSelectionChange={(e) => setSelectedNotifications(e.value as NotificationEntry[])}
            selectionMode="checkbox"
          >
            <Column selectionMode="multiple" style={{ width: '3%' }} />
            <Column field="notification_id" header="ID" sortable style={{ width: '8%' }} />
            <Column field="case_id" header="Case ID" sortable style={{ width: '9%' }} />
            <Column header="Type" body={typeTemplate} sortable sortField="type" style={{ width: '9%' }} />
            <Column field="vendor_name" header="Vendor" sortable style={{ width: '18%' }} />
            <Column field="recipient" header="Recipient" sortable style={{ width: '18%' }} />
            <Column field="subject" header="Subject" sortable style={{ width: '18%' }} />
            <Column field="timestamp" header="Timestamp" sortable style={{ width: '12%' }} />
            <Column header="Status" body={statusTemplate} sortable sortField="status" style={{ width: '8%' }} />
          </DataTable>
        )}
      </div>
    </div>
  );
};
