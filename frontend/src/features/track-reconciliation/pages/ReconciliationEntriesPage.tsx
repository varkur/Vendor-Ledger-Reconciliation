/**
 * ReconciliationEntriesPage — Standalone page for a single reconciliation
 * output view (Matched / Recommended / Unmatched Company / Unmatched Vendor /
 * Differences), reached from a "View" link on the summary page.
 *
 * Route: /track-reconciliation/:requestId/case/:caseId/view/:view
 *
 * Each view is its own page (no tabs). The `view` route param selects which
 * entries component to render, so Matched shows only matched, Unmatched shows
 * only unmatched, etc.
 */

import { useParams, useNavigate, useSearchParams } from 'react-router-dom';
import { Button } from 'primereact/button';

import { useSelectedEntity } from '@shared/hooks/useSelectedEntity';
import { apiClient } from '@shared/services/apiClient';
import { useQuery } from '@tanstack/react-query';
import {
  MatchedItemsTab,
  ConfirmationTab,
  UnmatchedCompanyTab,
  UnmatchedVendorTab,
  UnmatchedAllTab,
  KnockingTab,
  DifferencesSummaryTab,
} from '../components/ReconciliationOutput';

/** Route param → page title + which component to render. */
const VIEW_CONFIG: Record<
  string,
  { title: string; icon: string }
> = {
  matched: { title: 'Matched Entries', icon: 'pi pi-check-circle' },
  recommended: { title: 'Recommended Matches', icon: 'pi pi-star' },
  unmatched: { title: 'Unmatched Entries', icon: 'pi pi-exclamation-circle' },
  'unmatched-company': { title: 'Unmatched — Company', icon: 'pi pi-building' },
  'unmatched-vendor': { title: 'Unmatched — Vendor', icon: 'pi pi-users' },
  knocking: { title: 'Knocking Off Entries', icon: 'pi pi-replay' },
  differences: { title: 'Differences Summary', icon: 'pi pi-chart-bar' },
  'manually-mapped': { title: 'Manually Mapped Entries', icon: 'pi pi-link' },
};

export const ReconciliationEntriesPage = () => {
  const { requestId, caseId, view } = useParams<{
    requestId: string;
    caseId: string;
    view: string;
  }>();
  const navigate = useNavigate();
  const { companyCode } = useSelectedEntity();
  const [searchParams] = useSearchParams();
  const statusReason = searchParams.get('status_reason') || undefined;

  const config = (view && VIEW_CONFIG[view]) || VIEW_CONFIG.matched;

  // Case status gates reviewer edit actions (unlink) on the matched view.
  const { data: caseData } = useQuery({
    queryKey: ['case-status', caseId],
    queryFn: async () => {
      const { data } = await apiClient.get(`/vlr/cases/${caseId}`, {
        params: { company_code: companyCode },
      });
      return data;
    },
    enabled: !!caseId && !!companyCode,
  });
  const caseStatus = (caseData as any)?.status || '';
  // Link/unlink is allowed for the entire window between reconciliation
  // finishing and sign-off being requested — a reviewer should be able to
  // adjust matches whether the run auto-completed cleanly, left unmatched
  // entries (statement_mapped), or has already been advanced into the
  // review step. 'auto_completed' was missing here — the exact status a
  // case lands in when everything matched with no residual differences —
  // which meant the link/delink controls silently never appeared for the
  // most common successful-reconciliation outcome.
  const canEditLinks = [
    'auto_completed', 'statement_mapped', 'review_pending', 'review', 'reviewed',
  ].includes(caseStatus);

  const renderView = () => {
    if (!caseId) return null;
    switch (view) {
      case 'recommended':
        return <ConfirmationTab caseId={caseId} />;
      case 'unmatched':
        return <UnmatchedAllTab caseId={caseId} editable={canEditLinks} />;
      case 'knocking':
        return <KnockingTab caseId={caseId} />;
      case 'unmatched-company':
        return <UnmatchedCompanyTab caseId={caseId} />;
      case 'unmatched-vendor':
        return <UnmatchedVendorTab caseId={caseId} />;
      case 'differences':
        return <DifferencesSummaryTab caseId={caseId} />;
      case 'manually-mapped':
        return (
          <MatchedItemsTab
            caseId={caseId}
            editable={canEditLinks}
            statusReasonFilter={statusReason}
            manualOnly={!statusReason}
          />
        );
      case 'matched':
      default:
        return <MatchedItemsTab caseId={caseId} editable={canEditLinks} />;
    }
  };

  return (
    <div>
      {/* Breadcrumb */}
      <div
        className="flex align-items-center gap-2 mb-3"
        style={{ fontSize: 12, color: 'var(--color-text-secondary)' }}
      >
        <span
          className="cursor-pointer"
          onClick={() => navigate('/track-reconciliation')}
          style={{ color: 'var(--color-primary)' }}
        >
          Track Reconciliation
        </span>
        <span>&gt;</span>
        <span
          className="cursor-pointer"
          onClick={() => navigate(`/track-reconciliation/${requestId}`)}
          style={{ color: 'var(--color-primary)' }}
        >
          {requestId}
        </span>
        <span>&gt;</span>
        <span
          className="cursor-pointer"
          onClick={() => navigate(`/track-reconciliation/${requestId}/case/${caseId}`)}
          style={{ color: 'var(--color-primary)' }}
        >
          Summary
        </span>
        <span>&gt;</span>
        <span>{config.title}</span>
      </div>

      {/* Header */}
      <div className="mb-3 flex align-items-center justify-content-between">
        <Button
          icon="pi pi-arrow-left"
          label="Back to Summary"
          className="p-button-text p-button-sm"
          onClick={() => navigate(`/track-reconciliation/${requestId}/case/${caseId}`)}
        />
        <h3 className="m-0 flex align-items-center gap-2">
          <i className={config.icon} />
          {config.title}
        </h3>
        <span style={{ width: 120 }} />
      </div>

      {renderView()}
    </div>
  );
};
