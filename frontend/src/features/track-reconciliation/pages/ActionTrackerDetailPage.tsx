/**
 * Action Tracker Detail Page — Firmway-style exception work queue for a single
 * reconciliation request. Shows every unmatched / residual-difference ledger
 * row, filterable by Action Taken Status / reconciliation Status / Action
 * Owner, with inline "Update Action Taken", bulk actions, and an Excel
 * download that matches the reference Firmway export column-for-column.
 */

import { useMemo, useRef, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { Button } from 'primereact/button';
import { DataTable } from 'primereact/datatable';
import { Column } from 'primereact/column';
import { InputText } from 'primereact/inputtext';
import { InputTextarea } from 'primereact/inputtextarea';
import { Dropdown } from 'primereact/dropdown';
import { Dialog } from 'primereact/dialog';
import { Menu } from 'primereact/menu';
import { Tag } from 'primereact/tag';
import { Skeleton } from 'primereact/skeleton';
import { Message } from 'primereact/message';
import { Toast } from 'primereact/toast';

import { useActionTrackerItems, useBulkUpdateActionTakenItems } from '../hooks/useActionTracker';
import { exportActionTracker, ACTION_TAKEN_STATUSES, type ActionTrackerItem } from '../api/actionTrackerApi';
import { useSelectedEntity } from '@shared/hooks/useSelectedEntity';
import { downloadBlob, filenameFromDisposition } from '@shared/utils/downloadBlob';

const ACTION_TAKEN_STATUS_SEVERITY: Record<string, 'danger' | 'warning' | 'success'> = {
  'Pending with Party': 'danger',
  'Pending with Company': 'warning',
  'No Action Required': 'success',
};

export const ActionTrackerDetailPage = () => {
  const { requestId } = useParams<{ requestId: string }>();
  const navigate = useNavigate();
  const { companyCode } = useSelectedEntity();
  const toast = useRef<Toast>(null);
  const bulkActionsMenu = useRef<Menu>(null);

  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(25);
  const [search, setSearch] = useState('');
  const [actionTakenStatusFilter, setActionTakenStatusFilter] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<string | null>(null);
  const [ownerFilter, setOwnerFilter] = useState<string | null>(null);
  const [selection, setSelection] = useState<ActionTrackerItem[]>([]);
  const [editingItem, setEditingItem] = useState<ActionTrackerItem | null>(null);
  const [isExporting, setIsExporting] = useState(false);

  const { data, isLoading, isError, error, refetch } = useActionTrackerItems(requestId || '', {
    page,
    page_size: pageSize,
    search: search || undefined,
    action_taken_status: actionTakenStatusFilter || undefined,
    status: statusFilter || undefined,
    action_owner: ownerFilter || undefined,
  });

  const bulkUpdateMutation = useBulkUpdateActionTakenItems(requestId || '');

  const items = data?.items ?? [];

  const statusOptions = useMemo(
    () => Array.from(new Set(items.map((i) => i.status))).map((s) => ({ label: s, value: s })),
    [items]
  );
  const ownerOptions = useMemo(
    () => Array.from(new Set(items.map((i) => i.action_owner))).map((o) => ({ label: o, value: o })),
    [items]
  );

  const handleDownload = async () => {
    if (!requestId) return;
    setIsExporting(true);
    try {
      const response = await exportActionTracker(requestId, companyCode);
      const filename = filenameFromDisposition(
        response.headers['content-disposition'],
        `Action Tracker_${requestId}.xlsx`
      );
      downloadBlob(
        response.data,
        filename,
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
      );
    } catch (err: any) {
      toast.current?.show({
        severity: 'error',
        summary: 'Download Failed',
        detail: err.response?.data?.detail || 'Could not generate the Excel file.',
        life: 6000,
      });
    } finally {
      setIsExporting(false);
    }
  };

  const handleSaveEdit = () => {
    if (!editingItem) return;
    bulkUpdateMutation.mutate(
      [
        {
          case_id: editingItem.case_id,
          row_key: editingItem.row_key,
          action_owner: editingItem.action_owner,
          action_taken_reference: editingItem.action_taken_reference,
          action_taken_remark: editingItem.action_taken_remark,
          request_closed: editingItem.request_closed,
        },
      ],
      {
        onSuccess: () => {
          toast.current?.show({ severity: 'success', summary: 'Updated', detail: 'Action taken saved.', life: 3000 });
          setEditingItem(null);
        },
        onError: (err) => {
          toast.current?.show({ severity: 'error', summary: 'Update Failed', detail: err.message, life: 5000 });
        },
      }
    );
  };

  const handleBulkMarkClosed = () => {
    if (selection.length === 0) return;
    bulkUpdateMutation.mutate(
      selection.map((item) => ({
        case_id: item.case_id,
        row_key: item.row_key,
        request_closed: true,
      })),
      {
        onSuccess: () => {
          toast.current?.show({
            severity: 'success',
            summary: 'Bulk Update',
            detail: `${selection.length} row(s) marked closed.`,
            life: 3000,
          });
          setSelection([]);
        },
        onError: (err) => {
          toast.current?.show({ severity: 'error', summary: 'Bulk Update Failed', detail: err.message, life: 5000 });
        },
      }
    );
  };

  const bulkActionsItems = [
    {
      label: 'Mark Closed',
      icon: 'pi pi-check',
      disabled: selection.length === 0,
      command: handleBulkMarkClosed,
    },
  ];

  const actionTakenStatusTemplate = (row: ActionTrackerItem) => (
    <Tag value={row.action_taken_status} severity={ACTION_TAKEN_STATUS_SEVERITY[row.action_taken_status] ?? null} />
  );

  const actionTemplate = (row: ActionTrackerItem) => (
    <span className="link-view" style={{ cursor: 'pointer' }} onClick={() => setEditingItem(row)} role="button" tabIndex={0}>
      Update
    </span>
  );

  const renderLoadingSkeleton = () => (
    <div className="em-card" style={{ padding: '1rem' }}>
      {Array.from({ length: 6 }).map((_, i) => (
        <Skeleton key={i} height="2.5rem" className="mb-2" />
      ))}
    </div>
  );

  const renderError = () => (
    <div className="em-card" style={{ padding: '2rem', textAlign: 'center' }}>
      <Message severity="error" text={error instanceof Error ? error.message : 'Failed to load Action Tracker.'} />
      <div className="mt-3">
        <Button label="Retry" icon="pi pi-refresh" className="p-button-outlined p-button-sm" onClick={() => refetch()} />
      </div>
    </div>
  );

  return (
    <div>
      <Toast ref={toast} />

      {/* Breadcrumb */}
      <div className="flex align-items-center gap-2 mb-3" style={{ fontSize: 12, color: 'var(--color-text-secondary)' }}>
        <span className="cursor-pointer" onClick={() => navigate('/track-reconciliation')} style={{ color: 'var(--color-primary)' }}>
          Track Reconciliation
        </span>
        <span>&gt;</span>
        <span className="cursor-pointer" onClick={() => navigate(`/track-reconciliation/${requestId}?tab=actionTracker`)} style={{ color: 'var(--color-primary)' }}>
          Action Tracker Summary
        </span>
        <span>&gt;</span>
        <span>Action Tracker</span>
      </div>

      <div className="flex align-items-center justify-content-between mb-3">
        <div className="flex align-items-center gap-2">
          <Button icon="pi pi-arrow-left" className="p-button-text p-button-sm" onClick={() => navigate(`/track-reconciliation/${requestId}?tab=actionTracker`)} />
          <h3 style={{ margin: 0 }}>Action Tracker</h3>
        </div>
      </div>

      <div className="flex align-items-center justify-content-between flex-wrap mb-3" style={{ rowGap: 'var(--space-3)' }}>
        <div className="flex align-items-center flex-wrap" style={{ gap: 'var(--space-3)' }}>
          <InputText
            placeholder="Type and press enter to Search"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') setPage(1);
            }}
            style={{ width: 220 }}
          />
          <Dropdown
            value={actionTakenStatusFilter}
            options={ACTION_TAKEN_STATUSES.map((s) => ({ label: s, value: s }))}
            onChange={(e) => {
              setActionTakenStatusFilter(e.value);
              setPage(1);
            }}
            placeholder="Action Taken Status"
            showClear
            style={{ width: 170 }}
          />
          <Dropdown
            value={statusFilter}
            options={statusOptions}
            onChange={(e) => {
              setStatusFilter(e.value);
              setPage(1);
            }}
            placeholder="Reconciliation Status"
            showClear
            style={{ width: 170 }}
          />
          <Dropdown
            value={ownerFilter}
            options={ownerOptions}
            onChange={(e) => {
              setOwnerFilter(e.value);
              setPage(1);
            }}
            placeholder="Action Owner"
            showClear
            style={{ width: 150 }}
          />
        </div>
        <div className="flex align-items-center" style={{ gap: 'var(--space-3)' }}>
          <Button
            label="Bulk Actions"
            icon="pi pi-chevron-down"
            iconPos="right"
            className="p-button-outlined p-button-sm"
            disabled={selection.length === 0}
            onClick={(e) => bulkActionsMenu.current?.toggle(e)}
          />
          <Menu model={bulkActionsItems} popup ref={bulkActionsMenu} />
          <Button
            label="Download File"
            icon={isExporting ? 'pi pi-spin pi-spinner' : 'pi pi-download'}
            className="p-button-outlined p-button-sm"
            disabled={isExporting}
            onClick={handleDownload}
          />
        </div>
      </div>

      {isLoading ? (
        renderLoadingSkeleton()
      ) : isError ? (
        renderError()
      ) : (
        <div className="em-card" style={{ padding: 0 }}>
          <DataTable
            value={items}
            paginator
            lazy
            rows={pageSize}
            first={(page - 1) * pageSize}
            totalRecords={data?.total ?? 0}
            onPage={(e) => {
              setPage((e.page ?? 0) + 1);
              setPageSize(e.rows);
            }}
            selection={selection}
            onSelectionChange={(e) => setSelection(e.value as ActionTrackerItem[])}
            selectionMode="checkbox"
            dataKey="row_key"
            emptyMessage="No records found."
          >
            <Column selectionMode="multiple" headerStyle={{ width: '3rem' }} />
            <Column field="vendor_code" header="Party Code" style={{ width: '10%' }} />
            <Column field="vendor_name" header="Party Name" style={{ width: '16%' }} />
            <Column field="status" header="Status" style={{ width: '13%' }} />
            <Column field="classification" header="Classification" style={{ width: '11%' }} />
            <Column field="action_taken_status" header="Action Taken Status" body={actionTakenStatusTemplate} style={{ width: '13%' }} />
            <Column field="action_owner" header="Action Owner" style={{ width: '10%' }} />
            <Column field="company_invoice_date" header="Company Invoice Date" style={{ width: '9%' }} />
            <Column field="company_invoice_number" header="Company Invoice Number" style={{ width: '9%' }} />
            <Column
              field="difference"
              header="Difference"
              style={{ width: '8%', textAlign: 'right' }}
              body={(row: ActionTrackerItem) => Number(row.difference).toLocaleString('en-IN')}
            />
            <Column header="Action" body={actionTemplate} style={{ width: '8%' }} />
          </DataTable>
        </div>
      )}

      <Dialog
        header="Update Action Taken"
        visible={!!editingItem}
        onHide={() => setEditingItem(null)}
        style={{ width: 480 }}
      >
        {editingItem && (
          <div className="flex flex-column gap-3">
            <div>
              <label className="block mb-1 text-sm font-semibold">Action Owner</label>
              <InputText
                value={editingItem.action_owner}
                onChange={(e) => setEditingItem({ ...editingItem, action_owner: e.target.value })}
                className="w-full"
              />
            </div>
            <div>
              <label className="block mb-1 text-sm font-semibold">Action Taken Reference</label>
              <InputText
                value={editingItem.action_taken_reference || ''}
                onChange={(e) => setEditingItem({ ...editingItem, action_taken_reference: e.target.value })}
                className="w-full"
              />
            </div>
            <div>
              <label className="block mb-1 text-sm font-semibold">Action Taken Remark</label>
              <InputTextarea
                value={editingItem.action_taken_remark || ''}
                onChange={(e) => setEditingItem({ ...editingItem, action_taken_remark: e.target.value })}
                rows={3}
                className="w-full"
              />
            </div>
            <div className="flex align-items-center gap-2">
              <input
                type="checkbox"
                id="request_closed"
                checked={editingItem.request_closed}
                onChange={(e) => setEditingItem({ ...editingItem, request_closed: e.target.checked })}
              />
              <label htmlFor="request_closed" className="text-sm">Request Closed</label>
            </div>
            <div className="flex justify-content-end gap-2 mt-2">
              <Button label="Cancel" className="p-button-text p-button-sm" onClick={() => setEditingItem(null)} />
              <Button
                label="Save"
                icon={bulkUpdateMutation.isPending ? 'pi pi-spin pi-spinner' : undefined}
                disabled={bulkUpdateMutation.isPending}
                className="p-button-sm"
                onClick={handleSaveEdit}
              />
            </div>
          </div>
        )}
      </Dialog>
    </div>
  );
};
