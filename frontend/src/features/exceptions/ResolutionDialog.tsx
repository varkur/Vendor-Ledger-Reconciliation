/**
 * Resolution Dialog — Action selection with comments for resolving exceptions.
 * Actions: ACM (Accept Mismatch), RDV (Revert to Vendor), MTD (Mark as TDS Difference),
 *          MAA (Mark as Adjusted), WOF (Write Off), ESC (Escalate)
 */

import { useState } from 'react';
import { Dialog } from 'primereact/dialog';
import { Dropdown } from 'primereact/dropdown';
import { InputTextarea } from 'primereact/inputtextarea';
import { Button } from 'primereact/button';

interface ResolutionDialogProps {
  visible: boolean;
  onHide: () => void;
  exception: { exceptionId: string; vendorName: string; description: string } | null;
  onConfirm: (action: string, comments: string) => void;
}

const resolutionActions = [
  { label: 'ACM — Accept Mismatch', value: 'ACM', description: 'Accept the difference and close the exception' },
  { label: 'RDV — Revert to Vendor', value: 'RDV', description: 'Send back to vendor for clarification' },
  { label: 'MTD — Mark as TDS Difference', value: 'MTD', description: 'Classify as TDS deduction difference' },
  { label: 'MAA — Mark as Adjusted', value: 'MAA', description: 'Mark the entry as already adjusted' },
  { label: 'WOF — Write Off', value: 'WOF', description: 'Write off the difference amount' },
  { label: 'ESC — Escalate', value: 'ESC', description: 'Escalate to supervisor for approval' },
];

export const ResolutionDialog = ({ visible, onHide, exception, onConfirm }: ResolutionDialogProps) => {
  const [selectedAction, setSelectedAction] = useState<string | null>(null);
  const [comments, setComments] = useState('');

  const handleConfirm = () => {
    if (selectedAction) {
      onConfirm(selectedAction, comments);
      setSelectedAction(null);
      setComments('');
    }
  };

  const handleHide = () => {
    setSelectedAction(null);
    setComments('');
    onHide();
  };

  const selectedActionDetail = resolutionActions.find((a) => a.value === selectedAction);

  const footer = (
    <div className="flex justify-content-end gap-2">
      <Button label="Cancel" icon="pi pi-times" className="p-button-text" onClick={handleHide} />
      <Button
        label="Confirm Resolution"
        icon="pi pi-check"
        onClick={handleConfirm}
        disabled={!selectedAction}
      />
    </div>
  );

  return (
    <Dialog
      header="Resolve Exception"
      visible={visible}
      onHide={handleHide}
      style={{ width: '500px' }}
      footer={footer}
      modal
    >
      {exception && (
        <div>
          {/* Exception summary */}
          <div className="mb-3 p-3" style={{ background: 'var(--color-surface-alt, #f8f9fa)', borderRadius: 'var(--radius-md, 8px)' }}>
            <div style={{ fontWeight: 600 }}>{exception.exceptionId}</div>
            <div style={{ fontSize: '0.85rem', color: 'var(--color-text-muted)' }}>{exception.vendorName}</div>
            <div style={{ fontSize: '0.85rem', marginTop: 4 }}>{exception.description}</div>
          </div>

          {/* Action Selection */}
          <div className="mb-3">
            <label htmlFor="resolution-action" style={{ display: 'block', fontWeight: 500, marginBottom: 6 }}>
              Resolution Action *
            </label>
            <Dropdown
              id="resolution-action"
              value={selectedAction}
              options={resolutionActions}
              onChange={(e) => setSelectedAction(e.value)}
              placeholder="Select an action"
              className="w-full"
              optionLabel="label"
              optionValue="value"
            />
            {selectedActionDetail && (
              <div style={{ fontSize: '0.8rem', color: 'var(--color-text-muted)', marginTop: 4 }}>
                {selectedActionDetail.description}
              </div>
            )}
          </div>

          {/* Comments */}
          <div className="mb-3">
            <label htmlFor="resolution-comments" style={{ display: 'block', fontWeight: 500, marginBottom: 6 }}>
              Comments
            </label>
            <InputTextarea
              id="resolution-comments"
              value={comments}
              onChange={(e) => setComments(e.target.value)}
              rows={4}
              className="w-full"
              placeholder="Add any additional notes or justification..."
            />
          </div>
        </div>
      )}
    </Dialog>
  );
};
