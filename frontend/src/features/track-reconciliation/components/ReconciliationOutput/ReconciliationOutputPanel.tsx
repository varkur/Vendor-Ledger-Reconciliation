/**
 * ReconciliationOutputPanel — Main component for the 5-tab reconciliation output view.
 *
 * Uses PrimeReact TabView to render:
 * - Tab 1: Matched Items (match type + confidence score)
 * - Tab 2: Finance Confirmation (Accept/Reject/Clarify)
 * - Tab 3: Unmatched Company (Accept/Dispute/Request)
 * - Tab 4: Unmatched Vendor (Accept/Reject/Clarify)
 * - Tab 5: Differences Summary (balances + net difference)
 *
 * Requirements: 18.1-18.4, 19.1-19.4, 20.1-20.3, 21.1-21.3, 22.1-22.4
 */

import { useRef } from 'react';
import { Button } from 'primereact/button';
import { TabPanel, TabView } from 'primereact/tabview';
import { Toast } from 'primereact/toast';
import { Tooltip } from 'primereact/tooltip';

import { useSelectedEntity } from '@shared/hooks/useSelectedEntity';

import { ConfirmationTab } from './ConfirmationTab';
import { DifferencesSummaryTab } from './DifferencesSummaryTab';
import { MatchedItemsTab } from './MatchedItemsTab';
import { UnmatchedCompanyTab } from './UnmatchedCompanyTab';
import { UnmatchedVendorTab } from './UnmatchedVendorTab';
import { useConfirmationItems, useSubmitForApproval } from './useReconciliationOutput';

// ─────────────────────────────────────────────────────────────────────────────
// Types
// ─────────────────────────────────────────────────────────────────────────────

export interface ReconciliationOutputPanelProps {
  /** The reconciliation case ID to display output for. */
  caseId: string;
}

// ─────────────────────────────────────────────────────────────────────────────
// Component
// ─────────────────────────────────────────────────────────────────────────────

export const ReconciliationOutputPanel = ({ caseId }: ReconciliationOutputPanelProps) => {
  const toast = useRef<Toast>(null);
  const { companyCode } = useSelectedEntity();

  // Check confirmation items to determine if all are processed (0 pending)
  const { data: confirmationData } = useConfirmationItems(caseId);
  const allConfirmationProcessed = confirmationData !== undefined && confirmationData.total === 0;

  // Submit for approval mutation
  const submitMutation = useSubmitForApproval(caseId);

  // Determine if case is in submittable state:
  // - All confirmation items must be processed (total === 0)
  // - Case must not already be submitted (we check via mutation state)
  const isSubmittable = allConfirmationProcessed && !submitMutation.isSuccess;

  const tooltipMessage = !allConfirmationProcessed
    ? 'All Finance Confirmation items must be processed before submitting for approval.'
    : submitMutation.isSuccess
      ? 'Case has already been submitted for approval.'
      : '';

  const handleSubmitForApproval = () => {
    submitMutation.mutate(
      { companyCode },
      {
        onSuccess: (data) => {
          toast.current?.show({
            severity: 'success',
            summary: 'Submitted',
            detail: data.message || 'Case submitted for approval successfully.',
            life: 4000,
          });
        },
        onError: (error) => {
          toast.current?.show({
            severity: 'error',
            summary: 'Submission Failed',
            detail: error.message || 'Failed to submit case for approval. Please try again.',
            life: 5000,
          });
        },
      }
    );
  };

  return (
    <div className="reconciliation-output-panel">
      <Toast ref={toast} />

      <TabView aria-label="Reconciliation output tabs">
        <TabPanel header="Matched Items" leftIcon="pi pi-check-circle mr-2">
          <MatchedItemsTab caseId={caseId} />
        </TabPanel>

        <TabPanel header="Finance Confirmation" leftIcon="pi pi-user-edit mr-2">
          <ConfirmationTab caseId={caseId} />
        </TabPanel>

        <TabPanel header="Unmatched - Company" leftIcon="pi pi-building mr-2">
          <UnmatchedCompanyTab caseId={caseId} />
        </TabPanel>

        <TabPanel header="Unmatched - Vendor" leftIcon="pi pi-users mr-2">
          <UnmatchedVendorTab caseId={caseId} />
        </TabPanel>

        <TabPanel header="Differences Summary" leftIcon="pi pi-chart-bar mr-2">
          <DifferencesSummaryTab caseId={caseId} />
        </TabPanel>
      </TabView>

      {/* Submit for Approval section */}
      <div className="flex align-items-center justify-content-end mt-3 gap-2">
        {submitMutation.isSuccess && (
          <span className="text-green-600 font-semibold mr-2">
            <i className="pi pi-check-circle mr-1" />
            Pending Approval
          </span>
        )}
        <span
          id="submit-approval-tooltip-target"
          className="inline-block"
        >
          <Button
            label="Submit for Approval"
            icon="pi pi-send"
            severity="success"
            disabled={!isSubmittable}
            loading={submitMutation.isPending}
            onClick={handleSubmitForApproval}
            aria-label="Submit case for approval"
          />
        </span>
        {!isSubmittable && tooltipMessage && (
          <Tooltip target="#submit-approval-tooltip-target" content={tooltipMessage} position="left" />
        )}
      </div>
    </div>
  );
};
