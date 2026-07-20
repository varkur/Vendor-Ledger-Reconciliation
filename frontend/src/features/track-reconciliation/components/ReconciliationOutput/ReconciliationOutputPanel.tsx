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
import { TabPanel, TabView } from 'primereact/tabview';
import { Toast } from 'primereact/toast';

import { DifferencesSummaryTab } from './DifferencesSummaryTab';
import { MatchedItemsTab } from './MatchedItemsTab';
import { UnmatchedCompanyTab } from './UnmatchedCompanyTab';
import { UnmatchedVendorTab } from './UnmatchedVendorTab';

// ─────────────────────────────────────────────────────────────────────────────
// Types
// ─────────────────────────────────────────────────────────────────────────────

export interface ReconciliationOutputPanelProps {
  /** The reconciliation case ID to display output for. */
  caseId: string;
  /** When true, reviewer actions (unlink, etc.) are enabled. */
  editable?: boolean;
}

// ─────────────────────────────────────────────────────────────────────────────
// Component
// ─────────────────────────────────────────────────────────────────────────────

export const ReconciliationOutputPanel = ({ caseId, editable = false }: ReconciliationOutputPanelProps) => {
  const toast = useRef<Toast>(null);

  return (
    <div className="reconciliation-output-panel">
      <Toast ref={toast} />

      <TabView aria-label="Reconciliation output tabs">
        <TabPanel header="Matched Items" leftIcon="pi pi-check-circle mr-2">
          <MatchedItemsTab caseId={caseId} editable={editable} />
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
    </div>
  );
};
