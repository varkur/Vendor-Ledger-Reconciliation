/**
 * Vendor Portal Sign-Off page — Vendor confirms/rejects the reconciliation statement.
 * Connected to backend API for recording vendor approval.
 *
 * Connects to: POST /api/v1/vlr/portal/sign-off/{case_id} (with X-Portal-Token header)
 * Requirements: 24.4
 */

import { useState, useRef } from 'react';
import { Button } from 'primereact/button';
import { InputTextarea } from 'primereact/inputtextarea';
import { Checkbox } from 'primereact/checkbox';
import { Toast } from 'primereact/toast';
import { Dialog } from 'primereact/dialog';
import { ProgressSpinner } from 'primereact/progressspinner';
import { Message } from 'primereact/message';

import { usePortalSignOff, usePortalStatement } from './hooks/usePortal';
import { usePortalContext } from './context/PortalContext';

export const PortalSignOffPage = () => {
  const toast = useRef<Toast>(null);
  const { portalToken, caseInfo, isAuthenticated } = usePortalContext();

  const [agreed, setAgreed] = useState(false);
  const [comments, setComments] = useState('');
  const [showConfirmDialog, setShowConfirmDialog] = useState(false);
  const [signOffAction, setSignOffAction] = useState<'approve' | 'reject' | null>(null);

  const caseId = caseInfo?.case_id || null;

  // Load statement to get the statement_version and summary data
  const {
    data: statement,
    isLoading: statementLoading,
    error: statementError,
    refetch: refetchStatement,
  } = usePortalStatement(caseId, portalToken);

  // Sign-off mutation
  const signOffMutation = usePortalSignOff(caseId, portalToken);

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

  // Loading state for statement
  if (statementLoading) {
    return (
      <div style={{ maxWidth: 600, margin: '0 auto', padding: '60px 24px', textAlign: 'center' }}>
        <ProgressSpinner style={{ width: 50, height: 50 }} />
        <p style={{ marginTop: 16, color: 'var(--color-text-muted)' }}>
          Loading reconciliation summary...
        </p>
      </div>
    );
  }

  // Error state for statement
  if (statementError) {
    const errorMessage =
      statementError.response?.data?.detail || 'Failed to load reconciliation data.';
    return (
      <div style={{ maxWidth: 600, margin: '0 auto', padding: '60px 24px', textAlign: 'center' }}>
        <div className="em-card" style={{ padding: 40 }}>
          <i
            className="pi pi-exclamation-triangle"
            style={{ fontSize: '3rem', color: 'var(--color-error, #ef4444)' }}
          />
          <h3 style={{ marginTop: 16 }}>Unable to Load Data</h3>
          <Message severity="error" text={errorMessage} className="mb-3 w-full" />
          <Button
            label="Retry"
            icon="pi pi-refresh"
            onClick={() => refetchStatement()}
            className="mt-2"
          />
        </div>
      </div>
    );
  }

  const handleSignOff = (action: 'approve' | 'reject') => {
    setSignOffAction(action);
    setShowConfirmDialog(true);
  };

  const confirmSignOff = () => {
    setShowConfirmDialog(false);

    if (!statement) return;

    const confirmationText =
      signOffAction === 'approve'
        ? `APPROVED: ${comments || 'Vendor confirms the reconciliation statement is accurate.'}`
        : `DISPUTED: ${comments || 'Vendor disputes the reconciliation statement.'}`;

    signOffMutation.mutate(
      {
        confirmation_text: confirmationText,
        statement_version: statement.statement_version,
      },
      {
        onSuccess: (data) => {
          toast.current?.show({
            severity: signOffAction === 'approve' ? 'success' : 'info',
            summary:
              signOffAction === 'approve'
                ? 'Statement Approved'
                : 'Statement Disputed',
            detail: data.message,
            life: 5000,
          });
        },
        onError: (error) => {
          const errorMessage =
            error.response?.data?.detail ||
            'Failed to submit sign-off. Please try again.';
          toast.current?.show({
            severity: 'error',
            summary: 'Sign-Off Failed',
            detail: errorMessage,
            life: 8000,
          });
        },
      }
    );
  };

  // Success state — sign-off submitted
  if (signOffMutation.isSuccess) {
    const result = signOffMutation.data;
    return (
      <div style={{ maxWidth: 600, margin: '0 auto', padding: '60px 24px', textAlign: 'center' }}>
        <div className="em-card" style={{ padding: 48 }}>
          <i
            className={
              signOffAction === 'approve' ? 'pi pi-check-circle' : 'pi pi-info-circle'
            }
            style={{
              fontSize: '4rem',
              color:
                signOffAction === 'approve'
                  ? 'var(--color-success, #22c55e)'
                  : 'var(--color-warning, #f59e0b)',
            }}
          />
          <h2 style={{ marginTop: 20 }}>
            {signOffAction === 'approve' ? 'Sign-Off Complete' : 'Dispute Recorded'}
          </h2>
          <p style={{ color: 'var(--color-text-muted)', maxWidth: 400, margin: '8px auto 0' }}>
            {result.message}
          </p>
          {comments && (
            <div
              style={{
                marginTop: 20,
                padding: 16,
                background: 'var(--color-surface-alt, #f8f9fa)',
                borderRadius: 8,
                textAlign: 'left',
              }}
            >
              <strong>Your Comments:</strong>
              <p style={{ margin: '4px 0 0' }}>{comments}</p>
            </div>
          )}
          <p
            style={{
              marginTop: 16,
              fontSize: '0.8rem',
              color: 'var(--color-text-muted)',
            }}
          >
            Signed at: {new Date(result.signed_at).toLocaleString()} | IP:{' '}
            {result.ip_address}
          </p>
        </div>
      </div>
    );
  }

  const formatCurrency = (value: number | null | undefined) => {
    if (value === null || value === undefined) return '—';
    return `₹${Number(value).toLocaleString('en-IN')}`;
  };

  const periodDisplay =
    statement?.period_start && statement?.period_end
      ? `${statement.period_start} – ${statement.period_end}`
      : 'Not specified';

  return (
    <div style={{ maxWidth: 600, margin: '0 auto', padding: '24px' }}>
      <Toast ref={toast} />

      {/* Header */}
      <div style={{ marginBottom: 24 }}>
        <h2 style={{ margin: 0 }}>Sign-Off Confirmation</h2>
        <p style={{ color: 'var(--color-text-muted)', margin: '4px 0 0' }}>
          Please review the reconciliation statement and confirm your sign-off.
        </p>
      </div>

      {/* Summary Card */}
      <div className="em-card mb-3">
        <h3 style={{ margin: '0 0 12px' }}>Reconciliation Summary</h3>
        <div className="flex flex-column gap-2">
          <div className="flex justify-content-between">
            <span>Vendor:</span>
            <strong>{statement?.vendor_name || caseInfo?.vendor_name || '—'}</strong>
          </div>
          <div className="flex justify-content-between">
            <span>Period:</span>
            <strong>{periodDisplay}</strong>
          </div>
          <div className="flex justify-content-between">
            <span>Matched Entries:</span>
            <strong style={{ color: 'var(--color-success)' }}>
              {statement?.total_matched_entries || 0}
            </strong>
          </div>
          <div className="flex justify-content-between">
            <span>Unmatched Vendor Items:</span>
            <strong style={{ color: 'var(--color-warning)' }}>
              {statement?.total_unmatched_vendor || 0}
            </strong>
          </div>
          <div className="flex justify-content-between">
            <span>Net Difference:</span>
            <strong
              style={{
                color:
                  statement?.net_difference && Number(statement.net_difference) !== 0
                    ? 'var(--color-error)'
                    : 'var(--color-success)',
              }}
            >
              {formatCurrency(statement?.net_difference)}
            </strong>
          </div>
          <div className="flex justify-content-between">
            <span>Status:</span>
            <strong>{statement?.status?.replace(/_/g, ' ').toUpperCase() || '—'}</strong>
          </div>
        </div>
      </div>

      {/* Comments */}
      <div className="em-card mb-3">
        <label
          htmlFor="signoff-comments"
          style={{ display: 'block', fontWeight: 500, marginBottom: 8 }}
        >
          Comments (optional)
        </label>
        <InputTextarea
          id="signoff-comments"
          value={comments}
          onChange={(e) => setComments(e.target.value)}
          rows={4}
          className="w-full"
          placeholder="Add any remarks, dispute reasons, or notes..."
        />
      </div>

      {/* Agreement */}
      <div className="em-card mb-3">
        <div className="flex align-items-start gap-2">
          <Checkbox
            inputId="agree-checkbox"
            checked={agreed}
            onChange={(e) => setAgreed(e.checked ?? false)}
          />
          <label htmlFor="agree-checkbox" style={{ cursor: 'pointer', lineHeight: '1.4' }}>
            I have reviewed the reconciliation statement and confirm that the
            information presented is accurate to the best of my knowledge.
          </label>
        </div>
      </div>

      {/* Sign-off error */}
      {signOffMutation.isError && (
        <Message
          severity="error"
          text={
            signOffMutation.error?.response?.data?.detail ||
            'Failed to submit. Please try again.'
          }
          className="mb-3 w-full"
        />
      )}

      {/* Actions */}
      <div className="flex gap-3 justify-content-end">
        <Button
          label="Dispute"
          icon="pi pi-times"
          className="p-button-outlined p-button-danger"
          onClick={() => handleSignOff('reject')}
          disabled={signOffMutation.isPending}
        />
        <Button
          label="Approve & Sign Off"
          icon="pi pi-check"
          onClick={() => handleSignOff('approve')}
          disabled={!agreed || signOffMutation.isPending}
          loading={signOffMutation.isPending}
        />
      </div>

      {/* Confirmation Dialog */}
      <Dialog
        header={signOffAction === 'approve' ? 'Confirm Approval' : 'Confirm Dispute'}
        visible={showConfirmDialog}
        onHide={() => setShowConfirmDialog(false)}
        style={{ width: 400 }}
        footer={
          <div className="flex justify-content-end gap-2">
            <Button
              label="Cancel"
              className="p-button-text"
              onClick={() => setShowConfirmDialog(false)}
            />
            <Button
              label="Confirm"
              icon="pi pi-check"
              onClick={confirmSignOff}
              severity={signOffAction === 'approve' ? undefined : 'danger'}
            />
          </div>
        }
        modal
      >
        <p>
          {signOffAction === 'approve'
            ? 'Are you sure you want to approve and sign off on this reconciliation statement? This action cannot be undone.'
            : 'Are you sure you want to dispute this reconciliation statement? The team will be notified.'}
        </p>
      </Dialog>
    </div>
  );
};
