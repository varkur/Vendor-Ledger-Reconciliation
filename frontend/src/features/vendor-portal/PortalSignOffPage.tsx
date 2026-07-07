/**
 * Vendor Portal Sign-Off page — Vendor confirms/rejects the reconciliation statement.
 */

import { useState, useRef } from 'react';
import { Button } from 'primereact/button';
import { InputTextarea } from 'primereact/inputtextarea';
import { Checkbox } from 'primereact/checkbox';
import { Toast } from 'primereact/toast';
import { Dialog } from 'primereact/dialog';

export const PortalSignOffPage = () => {
  const toast = useRef<Toast>(null);
  const [agreed, setAgreed] = useState(false);
  const [comments, setComments] = useState('');
  const [showConfirmDialog, setShowConfirmDialog] = useState(false);
  const [signOffAction, setSignOffAction] = useState<'approve' | 'reject' | null>(null);
  const [isSubmitted, setIsSubmitted] = useState(false);

  const handleSignOff = (action: 'approve' | 'reject') => {
    setSignOffAction(action);
    setShowConfirmDialog(true);
  };

  const confirmSignOff = () => {
    setShowConfirmDialog(false);
    setIsSubmitted(true);
    toast.current?.show({
      severity: signOffAction === 'approve' ? 'success' : 'info',
      summary: signOffAction === 'approve' ? 'Statement Approved' : 'Statement Disputed',
      detail: signOffAction === 'approve'
        ? 'Thank you. The reconciliation statement has been signed off.'
        : 'Your dispute has been recorded. The reconciliation team will review.',
    });
  };

  if (isSubmitted) {
    return (
      <div style={{ maxWidth: 600, margin: '0 auto', padding: '60px 24px', textAlign: 'center' }}>
        <div className="em-card" style={{ padding: 48 }}>
          <i
            className={signOffAction === 'approve' ? 'pi pi-check-circle' : 'pi pi-info-circle'}
            style={{ fontSize: '4rem', color: signOffAction === 'approve' ? 'var(--color-success, #22c55e)' : 'var(--color-warning, #f59e0b)' }}
          />
          <h2 style={{ marginTop: 20 }}>
            {signOffAction === 'approve' ? 'Sign-Off Complete' : 'Dispute Recorded'}
          </h2>
          <p style={{ color: 'var(--color-text-muted)', maxWidth: 400, margin: '8px auto 0' }}>
            {signOffAction === 'approve'
              ? 'The reconciliation statement has been approved and signed off. You may close this window.'
              : 'Your dispute with comments has been sent to the reconciliation team. They will contact you shortly.'}
          </p>
          {comments && (
            <div style={{ marginTop: 20, padding: 16, background: 'var(--color-surface-alt, #f8f9fa)', borderRadius: 8, textAlign: 'left' }}>
              <strong>Your Comments:</strong>
              <p style={{ margin: '4px 0 0' }}>{comments}</p>
            </div>
          )}
        </div>
      </div>
    );
  }

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
            <span>Request ID:</span>
            <strong>EPL-00087</strong>
          </div>
          <div className="flex justify-content-between">
            <span>Period:</span>
            <strong>April 2025 – March 2026</strong>
          </div>
          <div className="flex justify-content-between">
            <span>Total Items:</span>
            <strong>10</strong>
          </div>
          <div className="flex justify-content-between">
            <span>Matched:</span>
            <strong style={{ color: 'var(--color-success)' }}>6 / 10</strong>
          </div>
          <div className="flex justify-content-between">
            <span>Net Difference:</span>
            <strong style={{ color: 'var(--color-error)' }}>₹52,000</strong>
          </div>
        </div>
      </div>

      {/* Comments */}
      <div className="em-card mb-3">
        <label htmlFor="signoff-comments" style={{ display: 'block', fontWeight: 500, marginBottom: 8 }}>
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
            I have reviewed the reconciliation statement and confirm that the information presented is accurate to the best of my knowledge.
          </label>
        </div>
      </div>

      {/* Actions */}
      <div className="flex gap-3 justify-content-end">
        <Button
          label="Dispute"
          icon="pi pi-times"
          className="p-button-outlined p-button-danger"
          onClick={() => handleSignOff('reject')}
        />
        <Button
          label="Approve & Sign Off"
          icon="pi pi-check"
          onClick={() => handleSignOff('approve')}
          disabled={!agreed}
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
            <Button label="Cancel" className="p-button-text" onClick={() => setShowConfirmDialog(false)} />
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
