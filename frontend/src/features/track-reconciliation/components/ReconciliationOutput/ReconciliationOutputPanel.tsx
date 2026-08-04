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

import { useRef, useState } from 'react';
import { TabPanel, TabView } from 'primereact/tabview';
import { Toast } from 'primereact/toast';

import { ConfirmationTab } from './ConfirmationTab';
import { DifferencesSummaryTab } from './DifferencesSummaryTab';
import { MatchedItemsTab } from './MatchedItemsTab';
import { UnmatchedCompanyTab } from './UnmatchedCompanyTab';
import { UnmatchedVendorTab } from './UnmatchedVendorTab';

/**
 * Tab indices for the reconciliation output panel. Exported so parents can
 * open the panel directly on a specific tab (e.g. from an analytics "View").
 */
export const OUTPUT_TAB = {
  MATCHED: 0,
  RECOMMENDED: 1,
  UNMATCHED_COMPANY: 2,
  UNMATCHED_VENDOR: 3,
  DIFFERENCES: 4,
} as const;

// ─────────────────────────────────────────────────────────────────────────────
// Types
// ─────────────────────────────────────────────────────────────────────────────

export interface ReconciliationOutputPanelProps {
  /** The reconciliation case ID to display output for. */
  caseId: string;
  /** When true, reviewer actions (unlink, etc.) are enabled. */
  editable?: boolean;
  /** Controlled active tab index (0-based). */
  activeIndex?: number;
  /** Initial tab to open on (uncontrolled mode). Defaults to Matched. */
  initialTab?: number;
  /** Called when the user switches tabs. */
  onTabChange?: (index: number) => void;
}

// ─────────────────────────────────────────────────────────────────────────────
// Component
// ─────────────────────────────────────────────────────────────────────────────

export const ReconciliationOutputPanel = ({
  caseId,
  editable = false,
  activeIndex,
  initialTab = 0,
  onTabChange,
}: ReconciliationOutputPanelProps) => {
  const toast = useRef<Toast>(null);
  // Fall back to internal tab state when the parent doesn't control the index.
  // (A controlled TabView with an undefined activeIndex renders no active tab,
  // leaving the panel body blank.)
  const [internalIndex, setInternalIndex] = useState(initialTab);
  const isControlled = activeIndex !== undefined;
  const currentIndex = isControlled ? activeIndex : internalIndex;

  return (
    <div className="reconciliation-output-panel">
      <Toast ref={toast} />

      <TabView
        aria-label="Reconciliation output tabs"
        activeIndex={currentIndex}
        onTabChange={(e) => {
          if (!isControlled) setInternalIndex(e.index);
          onTabChange?.(e.index);
        }}
      >
        <TabPanel header="Matched Items" leftIcon="pi pi-check-circle mr-2">
          <MatchedItemsTab caseId={caseId} editable={editable} />
        </TabPanel>

        <TabPanel header="Recommended Matches" leftIcon="pi pi-star mr-2">
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
    </div>
  );
};
