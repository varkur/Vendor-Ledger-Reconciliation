/**
 * Approvals Page — Lists pending approval items with approve/reject/delegate actions.
 * Fetches from GET /api/v1/vlr/approvals/pending with entity scoping.
 *
 * Requirements: 17
 */

import { useState, useRef, useCallback } from 'react';
import { DataTable } from 'primereact/datatable';
import { Column } from 'primereact/column';
import { Button } from 'primereact/button';
import { Dialog } from 'primereact/dialog';
import { InputTextarea } from 'primereact/inputtextarea';
import { Dropdown } from 'primereact/dropdown';
import { Toast } from 'primereact/toast';
import { ProgressSpinner } from 'primereact/progressspinner';
import { Message } from 'primereact/message';
import { Skeleton } from 'primereact/skeleton';

import {
  usePendingApprovals,
  useApproveCase,
  useRejectCase,
  useDelegateApproval,
} from '../hooks/useApprovals';
import type { PendingApprovalItem } from '../api/approvalsApi';
import { apiClient } from '@shared/services/apiClient';

// ─────────────────────────────────────────────────────────────────────────────
// Types for user picker
// ─────────────────────────────────────────────────────────────────────────────

interface UserOption {
  label: string;
  value: string;
}

// ─────────────────────────────────────────────────────────────────────────────
// Component
// ─────────────────────────────────────────────────────────────────────────────

export const ApprovalsPage = () => {
  const toast = useRef<Toast>(null);

  // Data fetching
  const { data, isLoading, isError, error, refetch } = usePendingApprovals();

  // Mutations
  const approveMutation = useApproveCase();
  const rejectMutation = useRejectCase();
  const delegateMutation = useDelegateApproval();

  // Reject dialog state
  const [rejectDialogVisible, setRejectDialogVisible] = useState(false);
  const [rejectReason, setRejectReason] = useState('');
  const [selectedCaseForReject, setSelectedCaseForReject] = useState<string | null>(null);

  // Delegate dialog state
  const [delegateDialogVisible, setDelegateDialogVisible] = useState(false);
  const [selectedUserId, setSelectedUserId] = useState<string | null>(null);
  const [selectedCaseForDelegate, setSelectedCaseForDelegate] = useState<string | null>(null);
  const [userOptions, setUserOptions] = useState<UserOption[]>([]);
  const [usersLoading, setUsersLoading] = useState(false);

  // ─────────────────────────────────────────────────────────────────────────
  // Action Handlers
  // ─────────────────────────────────────────────────────────────────────────

  const handleApprove = useCallback(
    (caseId: string) => {
      approveMutation.mutate(
        { caseId, data: {} },
        {
          onSuccess: () => {
            toast.current?.show({
              severity: 'success',
              summary: 'Approved',
              detail: 'Case has been approved successfully.',
              life: 3000,
            });
          },
          onError: (err) => {
            toast.current?.show({
              severity: 'error',
              summary: 'Approval Failed',
              detail: err.message || 'Failed to approve the case. Please try again.',
              life: 5000,
            });
          },
        }
      );
    },
    [approveMutation]
  );

  const openRejectDialog = useCallback((caseId: string) => {
    setSelectedCaseForReject(caseId);
    setRejectReason('');
    setRejectDialogVisible(true);
  }, []);

  const handleRejectConfirm = useCallback(() => {
    if (!selectedCaseForReject || !rejectReason.trim()) return;

    rejectMutation.mutate(
      { caseId: selectedCaseForReject, data: { comments: rejectReason.trim() } },
      {
        onSuccess: () => {
          toast.current?.show({
            severity: 'success',
            summary: 'Rejected',
            detail: 'Case has been rejected.',
            life: 3000,
          });
          setRejectDialogVisible(false);
          setSelectedCaseForReject(null);
          setRejectReason('');
        },
        onError: (err) => {
          toast.current?.show({
            severity: 'error',
            summary: 'Rejection Failed',
            detail: err.message || 'Failed to reject the case. Please try again.',
            life: 5000,
          });
        },
      }
    );
  }, [selectedCaseForReject, rejectReason, rejectMutation]);

  const openDelegateDialog = useCallback(
    async (caseId: string) => {
      setSelectedCaseForDelegate(caseId);
      setSelectedUserId(null);
      setDelegateDialogVisible(true);

      // Fetch users for the picker
      setUsersLoading(true);
      try {
        const { data: usersData } = await apiClient.get<{
          items: Array<{ id: string; username: string; full_name?: string }>;
        }>('/users', { params: { skip: 0, limit: 100 } });
        setUserOptions(
          usersData.items.map((u) => ({
            label: u.full_name || u.username,
            value: u.id,
          }))
        );
      } catch {
        setUserOptions([]);
        toast.current?.show({
          severity: 'warn',
          summary: 'Warning',
          detail: 'Could not load users list.',
          life: 3000,
        });
      } finally {
        setUsersLoading(false);
      }
    },
    []
  );

  const handleDelegateConfirm = useCallback(() => {
    if (!selectedCaseForDelegate || !selectedUserId) return;

    delegateMutation.mutate(
      { caseId: selectedCaseForDelegate, data: { to_user_id: selectedUserId } },
      {
        onSuccess: () => {
          toast.current?.show({
            severity: 'success',
            summary: 'Delegated',
            detail: 'Approval has been delegated successfully.',
            life: 3000,
          });
          setDelegateDialogVisible(false);
          setSelectedCaseForDelegate(null);
          setSelectedUserId(null);
        },
        onError: (err) => {
          toast.current?.show({
            severity: 'error',
            summary: 'Delegation Failed',
            detail: err.message || 'Failed to delegate approval. Please try again.',
            life: 5000,
          });
        },
      }
    );
  }, [selectedCaseForDelegate, selectedUserId, delegateMutation]);

  // ─────────────────────────────────────────────────────────────────────────
  // Column Templates
  // ─────────────────────────────────────────────────────────────────────────

  const vendorNameTemplate = (rowData: PendingApprovalItem) => {
    return <span>{rowData.vendor_name || rowData.vendor_id || '—'}</span>;
  };

  const caseIdTemplate = (rowData: PendingApprovalItem) => {
    const displayId = rowData.id ? rowData.id.substring(0, 8) + '...' : '—';
    return <span title={rowData.id}>{displayId}</span>;
  };

  const amountTemplate = (rowData: PendingApprovalItem) => {
    if (rowData.row_10_balance == null) return <span>—</span>;
    return (
      <span>
        ₹{Number(rowData.row_10_balance).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
      </span>
    );
  };

  const submittedByTemplate = (rowData: PendingApprovalItem) => {
    return <span>{rowData.submitted_by || '—'}</span>;
  };

  const dateTemplate = (rowData: PendingApprovalItem) => {
    if (!rowData.created_date) return <span>—</span>;
    try {
      return (
        <span>
          {new Date(rowData.created_date).toLocaleDateString('en-IN', {
            day: '2-digit',
            month: 'short',
            year: 'numeric',
          })}
        </span>
      );
    } catch {
      return <span>{rowData.created_date}</span>;
    }
  };

  const actionTemplate = (rowData: PendingApprovalItem) => (
    <div className="flex align-items-center gap-2">
      <Button
        label="Approve"
        icon="pi pi-check"
        className="p-button-success p-button-sm"
        loading={approveMutation.isPending && approveMutation.variables?.caseId === rowData.id}
        onClick={() => handleApprove(rowData.id)}
      />
      <Button
        label="Reject"
        icon="pi pi-times"
        className="p-button-danger p-button-sm"
        onClick={() => openRejectDialog(rowData.id)}
      />
      <Button
        label="Delegate"
        icon="pi pi-users"
        className="p-button-info p-button-sm"
        onClick={() => openDelegateDialog(rowData.id)}
      />
    </div>
  );

  // ─────────────────────────────────────────────────────────────────────────
  // Loading State (Skeleton)
  // ─────────────────────────────────────────────────────────────────────────

  if (isLoading && !data) {
    return (
      <div>
        <div className="em-page-header">
          <h2>Approvals</h2>
        </div>
        <div className="em-card">
          <Skeleton width="100%" height="2rem" className="mb-3" />
          <Skeleton width="100%" height="2rem" className="mb-3" />
          <Skeleton width="100%" height="2rem" className="mb-3" />
          <Skeleton width="100%" height="2rem" className="mb-3" />
          <Skeleton width="100%" height="2rem" className="mb-3" />
        </div>
      </div>
    );
  }

  // ─────────────────────────────────────────────────────────────────────────
  // Error State
  // ─────────────────────────────────────────────────────────────────────────

  if (isError) {
    return (
      <div>
        <div className="em-page-header">
          <h2>Approvals</h2>
        </div>
        <div className="flex flex-column align-items-center gap-3" style={{ minHeight: 300, paddingTop: 80 }}>
          <Message
            severity="error"
            text={error?.message || 'Failed to load approvals. Please try again.'}
          />
          <Button
            label="Retry"
            icon="pi pi-refresh"
            onClick={() => refetch()}
            className="p-button-outlined"
          />
        </div>
      </div>
    );
  }

  const approvals = data?.items ?? [];

  // ─────────────────────────────────────────────────────────────────────────
  // Render
  // ─────────────────────────────────────────────────────────────────────────

  return (
    <div>
      <Toast ref={toast} />

      {/* Page Header */}
      <div className="em-page-header">
        <h2>Approvals</h2>
        <div className="em-page-header-actions">
          <Button
            label="Refresh"
            icon="pi pi-refresh"
            className="p-button-outlined"
            onClick={() => refetch()}
            loading={isLoading}
          />
        </div>
      </div>

      {/* Data Table */}
      <div className="em-card" style={{ padding: 0 }}>
        {approvals.length === 0 ? (
          <div className="flex flex-column align-items-center gap-3 p-5">
            <i
              className="pi pi-check-circle"
              style={{ fontSize: '2.5rem', color: 'var(--color-text-muted)' }}
            />
            <h3 style={{ margin: 0, color: 'var(--color-text-muted)' }}>No pending approvals</h3>
            <p style={{ color: 'var(--color-text-muted)', margin: 0 }}>
              All approval items have been processed. New items will appear here when cases are submitted for approval.
            </p>
          </div>
        ) : (
          <DataTable
            value={approvals}
            paginator
            rows={10}
            rowsPerPageOptions={[10, 25, 50]}
            loading={isLoading}
            emptyMessage="No pending approvals."
            dataKey="id"
          >
            <Column header="Vendor Name" body={vendorNameTemplate} style={{ width: '18%' }} />
            <Column header="Case ID" body={caseIdTemplate} style={{ width: '12%' }} />
            <Column header="Amount" body={amountTemplate} style={{ width: '12%' }} />
            <Column header="Submitted By" body={submittedByTemplate} style={{ width: '14%' }} />
            <Column header="Submission Date" body={dateTemplate} style={{ width: '14%' }} />
            <Column header="Actions" body={actionTemplate} style={{ width: '30%' }} />
          </DataTable>
        )}
      </div>

      {/* Reject Reason Dialog */}
      <Dialog
        header="Reject Approval"
        visible={rejectDialogVisible}
        style={{ width: '450px' }}
        modal
        onHide={() => {
          setRejectDialogVisible(false);
          setSelectedCaseForReject(null);
          setRejectReason('');
        }}
        footer={
          <div className="flex justify-content-end gap-2">
            <Button
              label="Cancel"
              icon="pi pi-times"
              className="p-button-text"
              onClick={() => {
                setRejectDialogVisible(false);
                setSelectedCaseForReject(null);
                setRejectReason('');
              }}
            />
            <Button
              label="Reject"
              icon="pi pi-check"
              className="p-button-danger"
              disabled={!rejectReason.trim()}
              loading={rejectMutation.isPending}
              onClick={handleRejectConfirm}
            />
          </div>
        }
      >
        <div className="flex flex-column gap-3">
          <p style={{ margin: 0 }}>Please provide a reason for rejecting this approval:</p>
          <InputTextarea
            value={rejectReason}
            onChange={(e) => setRejectReason(e.target.value)}
            rows={4}
            placeholder="Enter rejection reason..."
            autoFocus
            style={{ width: '100%' }}
          />
        </div>
      </Dialog>

      {/* Delegate User Picker Dialog */}
      <Dialog
        header="Delegate Approval"
        visible={delegateDialogVisible}
        style={{ width: '450px' }}
        modal
        onHide={() => {
          setDelegateDialogVisible(false);
          setSelectedCaseForDelegate(null);
          setSelectedUserId(null);
        }}
        footer={
          <div className="flex justify-content-end gap-2">
            <Button
              label="Cancel"
              icon="pi pi-times"
              className="p-button-text"
              onClick={() => {
                setDelegateDialogVisible(false);
                setSelectedCaseForDelegate(null);
                setSelectedUserId(null);
              }}
            />
            <Button
              label="Delegate"
              icon="pi pi-check"
              className="p-button-info"
              disabled={!selectedUserId}
              loading={delegateMutation.isPending}
              onClick={handleDelegateConfirm}
            />
          </div>
        }
      >
        <div className="flex flex-column gap-3">
          <p style={{ margin: 0 }}>Select a user to delegate this approval to:</p>
          {usersLoading ? (
            <div className="flex justify-content-center p-3">
              <ProgressSpinner style={{ width: '30px', height: '30px' }} />
            </div>
          ) : (
            <Dropdown
              value={selectedUserId}
              options={userOptions}
              onChange={(e) => setSelectedUserId(e.value)}
              placeholder="Select a user..."
              filter
              filterPlaceholder="Search users..."
              style={{ width: '100%' }}
              emptyMessage="No users available"
            />
          )}
        </div>
      </Dialog>
    </div>
  );
};
