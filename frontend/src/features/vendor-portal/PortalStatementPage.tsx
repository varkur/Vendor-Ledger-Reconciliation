/**
 * Vendor Portal Statement page — Shows reconciliation results to the vendor.
 * Loads data from the backend API instead of using mock data.
 *
 * Connects to: GET /api/v1/vlr/portal/statement/{case_id} (with X-Portal-Token header)
 * Requirements: 24.3, 8
 */

import { useRef, useState } from 'react';
import { DataTable } from 'primereact/datatable';
import { Column } from 'primereact/column';
import { Tag } from 'primereact/tag';
import { Button } from 'primereact/button';
import { ProgressSpinner } from 'primereact/progressspinner';
import { Message } from 'primereact/message';
import { Dialog } from 'primereact/dialog';
import { InputTextarea } from 'primereact/inputtextarea';
import { FileUpload, type FileUploadSelectEvent } from 'primereact/fileupload';
import { Toast } from 'primereact/toast';
import { Tooltip } from 'primereact/tooltip';
import { useNavigate } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';

import { usePortalStatement, useRaiseDispute, PORTAL_QUERY_KEY } from './hooks/usePortal';
import { usePortalContext } from './context/PortalContext';
import type { MatchSummaryItem } from './api/portalApi';

export const PortalStatementPage = () => {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const toast = useRef<Toast>(null);
  const { portalToken, caseInfo, isAuthenticated } = usePortalContext();

  // Dispute dialog state
  const [disputeDialogVisible, setDisputeDialogVisible] = useState(false);
  const [disputeReason, setDisputeReason] = useState('');
  const [disputeAttachment, setDisputeAttachment] = useState<File | null>(null);
  const [reasonError, setReasonError] = useState('');
  const [isDisputed, setIsDisputed] = useState(false);

  const caseId = caseInfo?.case_id || null;
  const { data: statement, isLoading, error, refetch } = usePortalStatement(
    caseId,
    portalToken
  );

  const disputeMutation = useRaiseDispute(caseId, portalToken);

  // Redirect to auth if not authenticated
  if (!isAuthenticated || !portalToken) {
    return (
      <div style={{ maxWidth: 600, margin: '0 auto', padding: '60px 24px', textAlign: 'center' }}>
        <div className="em-card" style={{ padding: 40 }}>
          <i
            className="pi pi-lock"
            style={{ fontSize: '3rem', color: 'var(--color-warning, #f59e0b)' }}
          />
          <h3 style={{ marginTop: 16 }}>Authentication Required</h3>
          <p style={{ color: 'var(--color-text-muted)' }}>
            Please use the link from your email to access the portal.
          </p>
        </div>
      </div>
    );
  }

  // Loading state
  if (isLoading) {
    return (
      <div style={{ maxWidth: 1100, margin: '0 auto', padding: '60px 24px', textAlign: 'center' }}>
        <ProgressSpinner style={{ width: 50, height: 50 }} />
        <p style={{ marginTop: 16, color: 'var(--color-text-muted)' }}>
          Loading reconciliation statement...
        </p>
      </div>
    );
  }

  // Error state
  if (error) {
    const errorMessage =
      error.response?.data?.detail || 'Failed to load reconciliation statement.';
    return (
      <div style={{ maxWidth: 600, margin: '0 auto', padding: '60px 24px', textAlign: 'center' }}>
        <div className="em-card" style={{ padding: 40 }}>
          <i
            className="pi pi-exclamation-triangle"
            style={{ fontSize: '3rem', color: 'var(--color-error, #ef4444)' }}
          />
          <h3 style={{ marginTop: 16 }}>Unable to Load Statement</h3>
          <Message severity="error" text={errorMessage} className="mb-3 w-full" />
          <Button label="Retry" icon="pi pi-refresh" onClick={() => refetch()} className="mt-2" />
        </div>
      </div>
    );
  }

  // No data state
  if (!statement) {
    return (
      <div style={{ maxWidth: 600, margin: '0 auto', padding: '60px 24px', textAlign: 'center' }}>
        <div className="em-card" style={{ padding: 40 }}>
          <i
            className="pi pi-info-circle"
            style={{ fontSize: '3rem', color: 'var(--color-text-muted)' }}
          />
          <h3 style={{ marginTop: 16 }}>No Statement Available</h3>
          <p style={{ color: 'var(--color-text-muted)' }}>
            The reconciliation has not produced results yet. Please check back later.
          </p>
        </div>
      </div>
    );
  }

  const formatCurrency = (value: number | null | undefined) => {
    if (value === null || value === undefined) return '—';
    return `₹${Number(value).toLocaleString('en-IN')}`;
  };

  const matchTypeTemplate = (rowData: MatchSummaryItem) => {
    const labels: Record<string, string> = {
      exact: 'Exact Match',
      tolerance: 'Tolerance Match',
      fuzzy_reference: 'Fuzzy Reference',
      one_to_many: 'One-to-Many',
      many_to_one: 'Many-to-One',
      date_proximity: 'Date Proximity',
    };
    return <span>{labels[rowData.match_type] || rowData.match_type}</span>;
  };

  const amountTemplate = (rowData: MatchSummaryItem) => {
    const amount = parseFloat(rowData.total_amount);
    return (
      <span style={{ color: amount < 0 ? 'var(--color-error)' : 'inherit' }}>
        ₹{amount.toLocaleString('en-IN')}
      </span>
    );
  };

  const periodDisplay =
    statement.period_start && statement.period_end
      ? `${statement.period_start} – ${statement.period_end}`
      : 'Not specified';

  const statusSeverity: Record<string, 'success' | 'warning' | 'info' | 'danger'> = {
    matched: 'success',
    signed_off: 'success',
    review: 'warning',
    pending_approval: 'warning',
    data_received: 'info',
    initiated: 'info',
    disputed: 'danger',
  };

  // Determine if disputed (from API status or local state after successful submission)
  const caseIsDisputed = isDisputed || statement.status === 'disputed';

  // Determine displayed status
  const displayStatus = caseIsDisputed ? 'disputed' : statement.status;

  // Sign-off is only allowed when the case is in certain statuses
  const SIGN_OFF_ALLOWED_STATUSES = ['matched', 'review_complete', 'awaiting_signoff'];
  const canProceedToSignOff = !caseIsDisputed && SIGN_OFF_ALLOWED_STATUSES.includes(statement.status);

  const getSignOffDisabledReason = (): string => {
    if (caseIsDisputed) {
      return 'Sign-off is not available because a dispute has been raised on this reconciliation.';
    }
    return 'Sign-off is not available yet. The reconciliation must be in "Matched" or "Review Complete" state before you can proceed.';
  };

  const handleOpenDisputeDialog = () => {
    setDisputeReason('');
    setDisputeAttachment(null);
    setReasonError('');
    setDisputeDialogVisible(true);
  };

  const handleSubmitDispute = () => {
    // Validate reason
    if (!disputeReason.trim()) {
      setReasonError('Reason is required');
      return;
    }
    setReasonError('');

    disputeMutation.mutate(
      { reason: disputeReason.trim(), attachment: disputeAttachment || undefined },
      {
        onSuccess: () => {
          setDisputeDialogVisible(false);
          setIsDisputed(true);
          toast.current?.show({
            severity: 'success',
            summary: 'Dispute Raised',
            detail: 'Your dispute has been submitted successfully. The reconciliation team will review it.',
            life: 5000,
          });
          // Invalidate statement query to refresh status
          queryClient.invalidateQueries({ queryKey: [PORTAL_QUERY_KEY, 'statement', caseId] });
        },
        onError: (err) => {
          const detail = err.response?.data?.detail || 'Failed to submit dispute. Please try again.';
          toast.current?.show({
            severity: 'error',
            summary: 'Error',
            detail,
            life: 5000,
          });
        },
      }
    );
  };

  const handleFileSelect = (e: FileUploadSelectEvent) => {
    const file = e.files?.[0];
    if (file) {
      setDisputeAttachment(file);
    }
  };

  const handleFileClear = () => {
    setDisputeAttachment(null);
  };

  const disputeDialogFooter = (
    <div className="flex justify-content-end gap-2">
      <Button
        label="Cancel"
        icon="pi pi-times"
        severity="secondary"
        outlined
        onClick={() => setDisputeDialogVisible(false)}
        disabled={disputeMutation.isPending}
      />
      <Button
        label="Submit Dispute"
        icon="pi pi-send"
        severity="danger"
        onClick={handleSubmitDispute}
        loading={disputeMutation.isPending}
      />
    </div>
  );

  return (
    <div style={{ maxWidth: 1100, margin: '0 auto', padding: '24px' }}>
      <Toast ref={toast} />

      {/* Header */}
      <div className="flex align-items-center justify-content-between mb-3">
        <div>
          <h2 style={{ margin: 0 }}>Reconciliation Statement</h2>
          <p style={{ color: 'var(--color-text-muted)', margin: '4px 0 0' }}>
            Vendor: {statement.vendor_name} | Period: {periodDisplay}
          </p>
        </div>
        <div className="flex gap-2 align-items-center">
          <Tag
            value={displayStatus.replace(/_/g, ' ').toUpperCase()}
            severity={statusSeverity[displayStatus] || 'info'}
          />
          <Button
            label="Raise Dispute"
            icon="pi pi-exclamation-circle"
            severity="danger"
            outlined
            onClick={handleOpenDisputeDialog}
            disabled={caseIsDisputed}
          />
          <span
            id="sign-off-btn-wrapper"
            className="inline-block"
          >
            <Button
              label="Proceed to Sign-Off"
              icon="pi pi-check"
              onClick={() => navigate('/portal/sign-off')}
              disabled={!canProceedToSignOff}
            />
          </span>
          {!canProceedToSignOff && (
            <Tooltip
              target="#sign-off-btn-wrapper"
              content={getSignOffDisabledReason()}
              position="left"
            />
          )}
        </div>
      </div>

      {/* Summary Cards */}
      <div className="flex gap-3 mb-3">
        <div className="em-card flex-1 text-center">
          <div style={{ fontSize: '1.25rem', fontWeight: 600 }}>
            {formatCurrency(statement.vendor_opening_balance)}
          </div>
          <div style={{ fontSize: '0.8rem', color: 'var(--color-text-muted)' }}>
            Vendor Opening Balance
          </div>
        </div>
        <div className="em-card flex-1 text-center">
          <div style={{ fontSize: '1.25rem', fontWeight: 600 }}>
            {formatCurrency(statement.vendor_closing_balance)}
          </div>
          <div style={{ fontSize: '0.8rem', color: 'var(--color-text-muted)' }}>
            Vendor Closing Balance
          </div>
        </div>
        <div className="em-card flex-1 text-center">
          <div
            style={{ fontSize: '1.25rem', fontWeight: 600, color: 'var(--color-success)' }}
          >
            {statement.total_matched_entries}
          </div>
          <div style={{ fontSize: '0.8rem', color: 'var(--color-text-muted)' }}>
            Matched Entries
          </div>
        </div>
        <div className="em-card flex-1 text-center">
          <div
            style={{ fontSize: '1.25rem', fontWeight: 600, color: 'var(--color-warning)' }}
          >
            {statement.total_unmatched_vendor}
          </div>
          <div style={{ fontSize: '0.8rem', color: 'var(--color-text-muted)' }}>
            Unmatched Vendor Items
          </div>
        </div>
        <div className="em-card flex-1 text-center">
          <div
            style={{
              fontSize: '1.25rem',
              fontWeight: 600,
              color:
                statement.net_difference && Number(statement.net_difference) !== 0
                  ? 'var(--color-error)'
                  : 'var(--color-success)',
            }}
          >
            {formatCurrency(statement.net_difference)}
          </div>
          <div style={{ fontSize: '0.8rem', color: 'var(--color-text-muted)' }}>
            Net Difference
          </div>
        </div>
      </div>

      {/* Match Summary Table */}
      {statement.match_summary.length > 0 && (
        <div className="em-card" style={{ padding: 0 }}>
          <div
            style={{
              padding: '12px 16px',
              borderBottom: '1px solid var(--color-border, #e5e7eb)',
            }}
          >
            <h3 style={{ margin: 0, fontSize: '1rem' }}>Match Summary by Type</h3>
          </div>
          <DataTable
            value={statement.match_summary}
            emptyMessage="No match results available."
          >
            <Column
              header="Match Type"
              body={matchTypeTemplate}
              style={{ width: '40%' }}
            />
            <Column field="count" header="Count" style={{ width: '20%' }} sortable />
            <Column
              header="Total Amount"
              body={amountTemplate}
              style={{ width: '40%' }}
              sortable
              sortField="total_amount"
            />
          </DataTable>
        </div>
      )}

      {/* Empty match summary */}
      {statement.match_summary.length === 0 && (
        <div className="em-card text-center" style={{ padding: 32 }}>
          <i
            className="pi pi-info-circle"
            style={{ fontSize: '2rem', color: 'var(--color-text-muted)' }}
          />
          <p style={{ marginTop: 12, color: 'var(--color-text-muted)' }}>
            Reconciliation matching has not been completed yet. Results will appear
            here once the auto-reconciliation process finishes.
          </p>
        </div>
      )}

      {/* Raise Dispute Dialog */}
      <Dialog
        header="Raise Dispute"
        visible={disputeDialogVisible}
        onHide={() => setDisputeDialogVisible(false)}
        style={{ width: '500px' }}
        footer={disputeDialogFooter}
        closable={!disputeMutation.isPending}
      >
        <div className="flex flex-column gap-3">
          <div>
            <label htmlFor="dispute-reason" className="block mb-2 font-semibold">
              Reason for Dispute <span style={{ color: 'var(--color-error)' }}>*</span>
            </label>
            <InputTextarea
              id="dispute-reason"
              value={disputeReason}
              onChange={(e) => {
                setDisputeReason(e.target.value);
                if (reasonError) setReasonError('');
              }}
              rows={5}
              placeholder="Please describe why you are disputing the reconciliation results..."
              className={`w-full ${reasonError ? 'p-invalid' : ''}`}
              disabled={disputeMutation.isPending}
            />
            {reasonError && (
              <small className="p-error">{reasonError}</small>
            )}
          </div>
          <div>
            <label className="block mb-2 font-semibold">
              Supporting Document (Optional)
            </label>
            <FileUpload
              mode="basic"
              accept=".pdf,.xlsx,.xls,.csv,.doc,.docx,.png,.jpg,.jpeg"
              maxFileSize={10 * 1024 * 1024}
              chooseLabel={disputeAttachment ? disputeAttachment.name : 'Choose File'}
              onSelect={handleFileSelect}
              onClear={handleFileClear}
              auto={false}
              disabled={disputeMutation.isPending}
            />
            <small style={{ color: 'var(--color-text-muted)', display: 'block', marginTop: 4 }}>
              Max 10MB. Accepted formats: PDF, Excel, CSV, Word, Images
            </small>
          </div>
        </div>
      </Dialog>
    </div>
  );
};
