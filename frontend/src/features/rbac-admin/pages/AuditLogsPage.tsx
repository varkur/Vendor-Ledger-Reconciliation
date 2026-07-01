/**
 * Audit Logs page.
 * Displays all RBAC-related audit events with filtering.
 */

import { useEffect, useRef, useState } from 'react';
import { Column } from 'primereact/column';
import { DataTable, type DataTablePageEvent } from 'primereact/datatable';
import { Dropdown } from 'primereact/dropdown';
import { InputText } from 'primereact/inputtext';
import { Tag } from 'primereact/tag';
import { Toast } from 'primereact/toast';
import { Toolbar } from 'primereact/toolbar';
import { Button } from 'primereact/button';
import { ContentViewerDialog } from '@shared/components/ContentViewerDialog';
import { rbacAdminApi } from '../api/rbacAdminApi';
import type { AuditLogEntry } from '../models/rbac-admin.types';

const ACTION_OPTIONS = [
  { label: 'All Actions', value: '' },
  { label: 'Role Created', value: 'ROLE_CREATED' },
  { label: 'Role Updated', value: 'ROLE_UPDATED' },
  { label: 'Role Assigned', value: 'ROLE_ASSIGNED' },
  { label: 'Role Revoked', value: 'ROLE_REVOKED' },
  { label: 'Permission Created', value: 'PERMISSION_CREATED' },
  { label: 'Permission Granted', value: 'PERMISSION_GRANTED' },
  { label: 'Permission Revoked', value: 'PERMISSION_REVOKED' },
  { label: 'User Blocked', value: 'USER_BLOCKED' },
  { label: 'User Unblocked', value: 'USER_UNBLOCKED' },
  { label: 'Login Success', value: 'LOGIN_SUCCESS' },
  { label: 'Login Failed', value: 'LOGIN_FAILED' },
];

const RESOURCE_OPTIONS = [
  { label: 'All Resources', value: '' },
  { label: 'Role', value: 'Role' },
  { label: 'Permission', value: 'Permission' },
  { label: 'RoleAssignment', value: 'RoleAssignment' },
  { label: 'RolePermission', value: 'RolePermission' },
  { label: 'Authentication', value: 'Authentication' },
];

export const AuditLogsPage = () => {
  const toast = useRef<Toast>(null);
  const [logs, setLogs] = useState<AuditLogEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [totalRecords, setTotalRecords] = useState(0);
  const [first, setFirst] = useState(0);
  const [rows, setRows] = useState(20);

  // Filters
  const [actionFilter, setActionFilter] = useState('');
  const [resourceFilter, setResourceFilter] = useState('');
  const [actorFilter, setActorFilter] = useState('');

  // Content viewer state
  const [viewerVisible, setViewerVisible] = useState(false);
  const [viewerContent, setViewerContent] = useState<string | null>(null);
  const [viewerTitle, setViewerTitle] = useState('');

  useEffect(() => {
    loadLogs();
  }, [first, rows, actionFilter, resourceFilter, actorFilter]);

  const loadLogs = async () => {
    setLoading(true);
    try {
      const params: Record<string, any> = {
        skip: first,
        limit: rows,
      };
      if (actionFilter) params.action = actionFilter;
      if (resourceFilter) params.resource_type = resourceFilter;
      if (actorFilter) params.actor_username = actorFilter;

      const data = await rbacAdminApi.listAuditLogs(params);
      setLogs(data.logs);
      setTotalRecords(data.total);
    } catch (error: any) {
      toast.current?.show({
        severity: 'error',
        summary: 'Error',
        detail: error.response?.data?.detail || 'Failed to load audit logs',
        life: 5000,
      });
    } finally {
      setLoading(false);
    }
  };

  const onPage = (event: DataTablePageEvent) => {
    setFirst(event.first);
    setRows(event.rows);
  };

  // ─── Column Templates ───

  const actionTemplate = (log: AuditLogEntry) => {
    let severity: 'success' | 'info' | 'warning' | 'danger' = 'info';
    if (log.action.includes('CREATED') || log.action.includes('GRANTED') || log.action === 'LOGIN_SUCCESS') {
      severity = 'success';
    } else if (log.action.includes('REVOKED') || log.action.includes('DELETED') || log.action === 'LOGIN_FAILED') {
      severity = 'danger';
    } else if (log.action.includes('UPDATED') || log.action.includes('ASSIGNED')) {
      severity = 'warning';
    }
    return <Tag value={log.action} severity={severity} />;
  };

  const dateTemplate = (log: AuditLogEntry) => {
    const d = new Date(log.created_at);
    return (
      <span title={d.toISOString()}>
        {d.toLocaleDateString()} {d.toLocaleTimeString()}
      </span>
    );
  };

  const changeTemplate = (log: AuditLogEntry) => {
    const value = log.new_value || log.old_value;
    if (!value) return <span className="text-400">—</span>;

    const openViewer = () => {
      // Combine old + new values for a complete diff view
      const combined: Record<string, unknown> = {};
      if (log.old_value) {
        try { combined.before = JSON.parse(log.old_value); } catch { combined.before = log.old_value; }
      }
      if (log.new_value) {
        try { combined.after = JSON.parse(log.new_value); } catch { combined.after = log.new_value; }
      }
      const display = Object.keys(combined).length === 1
        ? JSON.stringify(Object.values(combined)[0])
        : JSON.stringify(combined);

      setViewerContent(display);
      setViewerTitle(`${log.action} — ${log.resource_type}`);
      setViewerVisible(true);
    };

    let preview: string;
    try {
      preview = JSON.stringify(JSON.parse(value));
    } catch {
      preview = value;
    }

    return (
      <button
        className="p-link text-left w-full flex align-items-center gap-1 border-none bg-transparent cursor-pointer p-0"
        onClick={openViewer}
        title="Click to view full details"
        aria-label="View details"
      >
        <code
          className="text-xs text-600 block"
          style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: 'calc(100% - 1.5rem)' }}
        >
          {preview}
        </code>
        <i className="pi pi-external-link text-xs text-400 flex-shrink-0" />
      </button>
    );
  };

  // ─── Toolbar ───

  const toolbarContent = () => (
    <div className="flex flex-wrap gap-3 align-items-center">
      <Dropdown
        value={actionFilter}
        options={ACTION_OPTIONS}
        onChange={(e) => { setFirst(0); setActionFilter(e.value); }}
        placeholder="Filter by Action"
        className="w-12rem"
        aria-label="Filter by action type"
      />
      <Dropdown
        value={resourceFilter}
        options={RESOURCE_OPTIONS}
        onChange={(e) => { setFirst(0); setResourceFilter(e.value); }}
        placeholder="Filter by Resource"
        className="w-12rem"
        aria-label="Filter by resource type"
      />
      <InputText
        value={actorFilter}
        onChange={(e) => setActorFilter(e.target.value)}
        onKeyDown={(e) => { if (e.key === 'Enter') { setFirst(0); loadLogs(); } }}
        placeholder="Filter by actor..."
        className="w-12rem"
        aria-label="Filter by actor username"
      />
      <Button
        icon="pi pi-refresh"
        severity="secondary"
        outlined
        onClick={loadLogs}
        tooltip="Refresh"
        aria-label="Refresh audit logs"
      />
    </div>
  );

  return (
    <div className="p-4">
      <Toast ref={toast} />

      {/* Header */}
      <div className="mb-4">
        <h2 className="text-2xl font-semibold text-900 m-0">Audit Logs</h2>
        <p className="text-600 mt-1 mb-0">
          View all security-relevant operations: role changes, permission grants, and authentication events
        </p>
      </div>

      <div className="surface-card p-4 border-round shadow-1">
        <Toolbar className="mb-4" start={toolbarContent} />

        <DataTable
          value={logs}
          loading={loading}
          stripedRows
          paginator
          lazy
          first={first}
          rows={rows}
          totalRecords={totalRecords}
          onPage={onPage}
          rowsPerPageOptions={[10, 20, 50]}
          emptyMessage="No audit logs found"
          tableStyle={{ width: '100%', tableLayout: 'auto' }}
        >
          <Column header="Time" body={dateTemplate} style={{ whiteSpace: 'nowrap', width: '1%' }} />
          <Column field="actor_username" header="Actor" sortable style={{ whiteSpace: 'nowrap', width: '1%' }} />
          <Column header="Action" body={actionTemplate} style={{ whiteSpace: 'nowrap', width: '1%' }} />
          <Column field="resource_type" header="Resource" style={{ whiteSpace: 'nowrap', width: '1%' }} />
          <Column field="resource_id" header="Resource ID" style={{ whiteSpace: 'nowrap', width: '1%' }} />
          <Column header="Details" body={changeTemplate} style={{ width: '300px', minWidth: '300px', maxWidth: '300px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} />
          <Column field="ip_address" header="IP" style={{ whiteSpace: 'nowrap', width: '1%' }} />
        </DataTable>
      </div>

      {/* Content Viewer Popup */}
      <ContentViewerDialog
        visible={viewerVisible}
        onHide={() => setViewerVisible(false)}
        title={viewerTitle}
        content={viewerContent}
        contentType="json"
      />
    </div>
  );
};
