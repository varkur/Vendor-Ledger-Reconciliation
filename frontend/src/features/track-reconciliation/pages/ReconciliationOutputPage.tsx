/**
 * ReconciliationOutputPage — Renders the 5-tab reconciliation output panel
 * for a specific case within a reconciliation request.
 *
 * Route: /track-reconciliation/:requestId/case/:caseId
 * Requirements: 3
 */

import { useRef, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Button } from 'primereact/button';
import { Toast } from 'primereact/toast';
import { DataTable } from 'primereact/datatable';
import { Column } from 'primereact/column';
import { ProgressSpinner } from 'primereact/progressspinner';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '@shared/services/apiClient';
import { useSelectedEntity } from '@shared/hooks/useSelectedEntity';
import { downloadBlob, filenameFromDisposition } from '@shared/utils/downloadBlob';


interface AnalyticsRow {
  particulars: string;
  company_numbers: number;
  company_percentage: number;
  party_numbers: number;
  party_percentage: number;
  view_key: string;
}
interface AnalyticsResponse {
  party_code: string;
  party_name: string;
  party_type: string;
  reco_type: string;
  reco_status: string;
  period_start: string | null;
  period_end: string | null;
  updated_at: string | null;
  rows: AnalyticsRow[];
  total_company_numbers: number;
  total_party_numbers: number;
}

interface ParticularsChild {
  label: string;
  amount: number;
  no_of_entries: number;
  side: string;
  document_category: string;
  view_key: string;
  is_matched_residual?: boolean;
  matched_status?: string;
}
interface ParticularsGroup {
  label: string;
  amount: number;
  no_of_entries: number;
  children: ParticularsChild[];
  view_key: string;
  is_matched_residual?: boolean;
}
interface ParticularsResponse {
  closing_balance_company: number | null;
  closing_balance_party: number | null;
  groups: ParticularsGroup[];
  calculated_balance: number;
}

/** Flattened row for the Particulars DataTable (group header or child). */
interface ParticularsFlatRow {
  key: string;
  label: string;
  amount: number;
  no_of_entries: number | null;
  isGroup: boolean;
  groupIndex: number | null;
  hasChildren: boolean;
  side: string;
  isClosingBalance: boolean;
  isKnocking: boolean;
  isManuallyMapped: boolean;
  statusReason?: string;
  /**
   * Particulars-statement difference group label (e.g. "Invoice
   * Difference", "Other Differences") carried on both group and child
   * rows via the backend's view_key. Passed through as the `group` query
   * param so each group/child's "View" drill-in shows only its own
   * entries instead of the full unmatched list.
   */
  groupFilter?: string;
  /**
   * True when this row aggregates MATCHED (not unmatched) residual entries
   * — TDS deducted, rounding write-off, unexplained gap, amount mismatch.
   * Routes "View" to the Matched/Recommended tab instead of unmatched.
   */
  isMatchedResidual: boolean;
  /** Computed Status/Classification value to filter the Matched/Recommended drill-in by. */
  matchedStatus?: string;
  /**
   * True ONLY on a group-header row whose children are a MIX of matched
   * residuals and genuinely unmatched entries (e.g. "TDS / TCS Difference"
   * = some TDS entries were matched with a residual, others are still
   * unmatched on one side). Bug fix: there is no single destination page
   * that shows both matched and unmatched entries together, so a mixed
   * group's "View" previously routed to the unmatched-only view and
   * silently dropped every matched entry from the drill-in (count showed
   * 34, but "View" only ever showed the 2 unmatched ones). For a mixed
   * group, clicking "View" now expands the row instead of navigating,
   * since each CHILD row underneath already routes correctly on its own.
   */
  isMixedGroup?: boolean;
}

/** Map an analytics row to its dedicated view slug. */
function analyticsViewSlug(r: AnalyticsRow): string {
  const key = (r.view_key || r.particulars || '').toLowerCase();
  if (key.includes('recommend')) return 'recommended';
  if (key.includes('unmatch')) return 'unmatched';
  if (key.includes('match')) return 'matched';
  return 'matched';
}

/** Map a particulars row to its dedicated view slug. */
function particularsViewSlug(r: ParticularsFlatRow): string {
  if (r.isManuallyMapped) return 'manually-mapped';
  if (r.isKnocking) return 'knocking';
  if (r.isClosingBalance) return 'differences';
  // Matched-pair residuals (TDS deducted, rounding write-off, unexplained
  // gap, amount mismatch) live on the Matched/Recommended tabs, not the
  // unmatched views — "Amount Mismatch" rows are still pending Finance
  // confirmation (Recommended); everything else is an auto-accepted match
  // with a residual note (Matched).
  if (r.isMatchedResidual) {
    return r.matchedStatus === 'Amount Mismatch' ? 'recommended' : 'matched';
  }
  // Company-side lines live in the Unmatched-Company view; party lines in
  // Vendor. Group-header rows (no single side — they roll up BOTH sides,
  // e.g. "Invoice Difference" = invoices missing from either ledger) go to
  // the combined Unmatched-All view instead, filtered by group.
  if (r.side === 'company') return 'unmatched-company';
  if (r.side === 'vendor') return 'unmatched-vendor';
  return 'unmatched';
}

function fmtAmount(n: number | null | undefined): string {
  if (n === null || n === undefined) return '';
  return new Intl.NumberFormat('en-IN', { maximumFractionDigits: 0 }).format(n);
}

function fmtDate(iso?: string | null): string {
  if (!iso) return '—';
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(iso));
  const d = m ? new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3])) : new Date(iso);
  return isNaN(d.getTime()) ? String(iso) : d.toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' }).replace(/ /g, '-');
}

export const ReconciliationOutputPage = () => {
  const { requestId, caseId } = useParams<{ requestId: string; caseId: string }>();
  const navigate = useNavigate();
  const { companyCode } = useSelectedEntity();
  const toast = useRef<Toast>(null);
  const queryClient = useQueryClient();
  const [isActing, setIsActing] = useState(false);
  const [isExporting, setIsExporting] = useState(false);
  // Group indices whose child rows are expanded (collapsed by default).
  const [expandedGroups, setExpandedGroups] = useState<Set<number>>(new Set());

  const toggleGroup = (gi: number) => {
    setExpandedGroups((prev) => {
      const next = new Set(prev);
      if (next.has(gi)) next.delete(gi);
      else next.add(gi);
      return next;
    });
  };

  const { data: analytics, isLoading: analyticsLoading } = useQuery<AnalyticsResponse>({
    queryKey: ['reco-analytics', caseId, companyCode],
    queryFn: async () => {
      const { data } = await apiClient.get(`/vlr/reconciliation/${caseId}/analytics`);
      return data as AnalyticsResponse;
    },
    enabled: !!caseId,
  });

  const { data: particulars, isLoading: particularsLoading } = useQuery<ParticularsResponse>({
    queryKey: ['reco-particulars', caseId, companyCode],
    queryFn: async () => {
      const { data } = await apiClient.get(`/vlr/reconciliation/${caseId}/particulars`);
      return data as ParticularsResponse;
    },
    enabled: !!caseId,
  });

  // Flatten groups + children into display rows for the Particulars table.
  // Children are only included when their group is expanded.
  const particularsRows: ParticularsFlatRow[] = [];
  (particulars?.groups ?? []).forEach((g, gi) => {
    const groupIsClosing = g.view_key === 'closing_balance' || /closing balance/i.test(g.label);
    const groupIsKnocking = g.view_key === 'knocking' || /knocking/i.test(g.label);
    const groupIsManuallyMapped = g.view_key === 'manually_mapped' || /manually mapped/i.test(g.label);
    // Group-level view_key now carries the actual Particulars group label
    // (e.g. "Invoice Difference") rather than a generic "unmatched"
    // placeholder — passed through so this group's View only shows its own
    // entries. Closing-balance/knocking/manually-mapped groups keep their
    // dedicated views and don't need this filter.
    const groupFilter = !groupIsClosing && !groupIsKnocking && !groupIsManuallyMapped && !g.is_matched_residual
      ? g.view_key || undefined
      : undefined;
    // A group is "mixed" when it has BOTH matched-residual children and
    // genuinely unmatched children (e.g. TDS / TCS Difference: some TDS
    // entries matched with a residual, others still sit unmatched). Only
    // meaningful for the generic difference groups — closing
    // balance/knocking/manually-mapped groups always have a single
    // consistent destination already.
    const hasMatchedChild = (g.children ?? []).some((c) => c.is_matched_residual);
    const hasUnmatchedChild = (g.children ?? []).some((c) => !c.is_matched_residual);
    const isMixedGroup = !groupIsClosing && !groupIsKnocking && !groupIsManuallyMapped
      && hasMatchedChild && hasUnmatchedChild;
    particularsRows.push({
      key: `g-${gi}`,
      label: g.label,
      amount: g.amount,
      no_of_entries: g.no_of_entries,
      isGroup: true,
      groupIndex: gi,
      hasChildren: (g.children?.length ?? 0) > 0,
      side: '',
      isClosingBalance: groupIsClosing,
      isKnocking: groupIsKnocking,
      isManuallyMapped: groupIsManuallyMapped,
      groupFilter,
      isMatchedResidual: !!g.is_matched_residual,
      isMixedGroup,
    });
    if (expandedGroups.has(gi)) {
      g.children.forEach((c, ci) => {
        particularsRows.push({
          key: `g-${gi}-c-${ci}`,
          label: c.label,
          amount: c.amount,
          no_of_entries: c.no_of_entries,
          isGroup: false,
          groupIndex: gi,
          hasChildren: false,
          side: c.side || '',
          isClosingBalance: groupIsClosing,
          isKnocking: groupIsKnocking,
          isManuallyMapped: groupIsManuallyMapped,
          statusReason: groupIsManuallyMapped ? c.label : undefined,
          isMatchedResidual: !!c.is_matched_residual,
          matchedStatus: c.matched_status || undefined,
          // Only relevant for unmatched children — a matched-residual
          // child routes via matchedStatus/computed_status instead, so
          // don't carry an unused `group` param into that URL.
          groupFilter: c.is_matched_residual ? undefined : groupFilter,
        });
      });
    }
  });
  if (particulars) {
    particularsRows.push({
      key: 'calculated-balance',
      label: 'Calculated Balance',
      amount: particulars.calculated_balance,
      no_of_entries: null,
      isGroup: true,
      side: '',
      isClosingBalance: false,
      isKnocking: false,
      isManuallyMapped: false,
      groupIndex: null,
      hasChildren: false,
      isMatchedResidual: false,
    });
  }

  const handleExport = async () => {
    if (!caseId) return;
    setIsExporting(true);
    try {
      const response = await apiClient.get(`/vlr/reconciliation/${caseId}/export`, {
        responseType: 'blob',
      });
      const filename = filenameFromDisposition(
        response.headers['content-disposition'],
        `Reconciliation-${caseId}.xlsx`,
      );
      downloadBlob(
        response.data,
        filename,
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      );
    } catch (error: any) {
      toast.current?.show({
        severity: 'error',
        summary: 'Export Failed',
        detail: error.response?.data?.detail || 'Could not generate the Excel file.',
        life: 6000,
      });
    } finally {
      setIsExporting(false);
    }
  };

  // Fetch case status to gate reviewer-only actions
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
  const isUnderReview = caseStatus === 'review_pending';
  const isReviewed = caseStatus === 'reviewed';
  const isStatementMapped = caseStatus === 'statement_mapped';
  const isAutoCompleted = caseStatus === 'auto_completed';
  // Link/unlink is allowed for the whole window from reconciliation
  // finishing through the review step — auto_completed (everything matched
  // cleanly, no residual differences) was missing here, which meant the
  // "Link Unmatched" button never showed up for the most common
  // successful-reconciliation outcome.
  const canEditLinks = isUnderReview || isStatementMapped || isAutoCompleted || isReviewed;

  const handleReviewDone = async () => {
    setIsActing(true);
    try {
      await apiClient.post('/vlr/cases/bulk-review-done', {
        company_code: companyCode,
        case_ids: [caseId],
      });
      toast.current?.show({ severity: 'success', summary: 'Review Completed', detail: 'Case marked as reviewed.', life: 4000 });
      queryClient.invalidateQueries({ queryKey: ['case-status', caseId] });
    } catch (error: any) {
      toast.current?.show({ severity: 'error', summary: 'Failed', detail: error.response?.data?.detail || 'Failed to complete review.', life: 6000 });
    } finally {
      setIsActing(false);
    }
  };

  const handleRequestSignoff = async () => {
    setIsActing(true);
    try {
      await apiClient.post('/vlr/cases/bulk-signoff-request', {
        company_code: companyCode,
        case_ids: [caseId],
      });
      toast.current?.show({ severity: 'success', summary: 'Sign-off Requested', detail: 'Sign-off has been requested.', life: 4000 });
      queryClient.invalidateQueries({ queryKey: ['case-status', caseId] });
      // Invalidate the batch-cases list so the Sign Off Stage tab refetches
      queryClient.invalidateQueries({ queryKey: ['vlr-reconciliation-detail'] });
      queryClient.invalidateQueries({ queryKey: ['vlr-request-statistics'] });
      setTimeout(() => navigate(`/track-reconciliation/${requestId}?tab=signOffStage`), 1200);
    } catch (error: any) {
      toast.current?.show({ severity: 'error', summary: 'Failed', detail: error.response?.data?.detail || 'Failed to request sign-off.', life: 6000 });
    } finally {
      setIsActing(false);
    }
  };

  if (!caseId || !requestId) {
    return (
      <div className="p-4">
        <p style={{ color: 'var(--color-error)' }}>Invalid case or request ID.</p>
      </div>
    );
  }

  return (
    <div>
      {/* Breadcrumb */}
      <div className="flex align-items-center gap-2 mb-3" style={{ fontSize: 12, color: 'var(--color-text-secondary)' }}>
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
        <span>{caseId}</span>
      </div>

      {/* Back button + Link Unmatched action */}
      <div className="mb-3 flex align-items-center justify-content-between">
        <Button
          icon="pi pi-arrow-left"
          label="Back to Cases"
          className="p-button-text p-button-sm"
          onClick={() => navigate(`/track-reconciliation/${requestId}`)}
        />
        <div className="flex align-items-center gap-2">
          <Button
            icon={isExporting ? 'pi pi-spin pi-spinner' : 'pi pi-file-excel'}
            label="Download Excel"
            className="p-button-sm p-button-success"
            style={{ color: '#fff' }}
            disabled={isExporting}
            onClick={handleExport}
          />
          {canEditLinks && (
            <Button
              icon="pi pi-link"
              label="Link Unmatched"
              className="p-button-sm p-button-outlined"
              onClick={() => navigate(`/track-reconciliation/${requestId}/case/${caseId}/link`)}
            />
          )}
          {isUnderReview && (
            <Button
              icon="pi pi-check"
              label="Review Completed"
              className="p-button-sm"
              loading={isActing}
              onClick={handleReviewDone}
            />
          )}
          {isReviewed && (
            <Button
              icon="pi pi-verified"
              label="Request Sign-off"
              className="p-button-sm"
              loading={isActing}
              onClick={handleRequestSignoff}
            />
          )}
        </div>
      </div>

      <Toast ref={toast} />

      <div>
          {/* ── Header block ── */}
          <div className="em-card mb-3">
            <div className="grid" style={{ fontSize: 13 }}>
              <div className="col-12 md:col-6 flex justify-content-between py-1">
                <span style={{ color: 'var(--color-text-muted)' }}>Party Code</span>
                <span className="font-semibold">{analytics?.party_code || '—'}</span>
              </div>
              <div className="col-12 md:col-6 flex justify-content-between py-1">
                <span style={{ color: 'var(--color-text-muted)' }}>Reco Type</span>
                <span className="font-semibold">{analytics?.reco_type || 'Ledger'}</span>
              </div>
              <div className="col-12 md:col-6 flex justify-content-between py-1">
                <span style={{ color: 'var(--color-text-muted)' }}>Party Name</span>
                <span className="font-semibold">{analytics?.party_name || '—'}</span>
              </div>
              <div className="col-12 md:col-6 flex justify-content-between py-1">
                <span style={{ color: 'var(--color-text-muted)' }}>Reco Period</span>
                <span className="font-semibold">{fmtDate(analytics?.period_start)} to {fmtDate(analytics?.period_end)}</span>
              </div>
              <div className="col-12 md:col-6 flex justify-content-between py-1">
                <span style={{ color: 'var(--color-text-muted)' }}>Party Type</span>
                <span className="font-semibold">{analytics?.party_type || 'Vendor'}</span>
              </div>
              <div className="col-12 md:col-6 flex justify-content-between py-1">
                <span style={{ color: 'var(--color-text-muted)' }}>Reco Status</span>
                <span className="font-semibold">{(analytics?.reco_status || caseStatus).replace(/_/g, ' ')}</span>
              </div>
            </div>
          </div>

          {/* ── Particulars reconciliation statement ── */}
          {particularsLoading ? (
            <div className="flex justify-content-center p-4"><ProgressSpinner style={{ width: 40, height: 40 }} /></div>
          ) : (
            <div className="em-card mb-3" style={{ padding: 0 }}>
              <DataTable
                value={particularsRows}
                size="small"
                dataKey="key"
                emptyMessage="No reconciling items."
                rowClassName={(row: ParticularsFlatRow) =>
                  row.isGroup ? 'particulars-group-row' : ''
                }
              >
                <Column
                  header="Particulars"
                  body={(r: ParticularsFlatRow) => (
                    <div className="flex align-items-center gap-2">
                      {r.isGroup && r.hasChildren && r.groupIndex !== null ? (
                        <button
                          type="button"
                          onClick={() => toggleGroup(r.groupIndex as number)}
                          aria-label={expandedGroups.has(r.groupIndex) ? 'Collapse' : 'Expand'}
                          style={{
                            border: '1px solid var(--color-surface-border)',
                            background: '#fff',
                            borderRadius: 3,
                            width: 18,
                            height: 18,
                            display: 'inline-flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            cursor: 'pointer',
                            padding: 0,
                            lineHeight: 1,
                          }}
                        >
                          <i
                            className={expandedGroups.has(r.groupIndex) ? 'pi pi-minus' : 'pi pi-plus'}
                            style={{ fontSize: 10 }}
                          />
                        </button>
                      ) : (
                        <span style={{ display: 'inline-block', width: r.isGroup ? 0 : 18 }} />
                      )}
                      <span style={{ fontWeight: r.isGroup ? 700 : 400, paddingLeft: r.isGroup ? 0 : 8 }}>
                        {r.label}
                      </span>
                    </div>
                  )}
                  style={{ minWidth: '20rem' }}
                />
                <Column
                  header="Amount"
                  body={(r: ParticularsFlatRow) => (
                    <span style={{ fontWeight: r.isGroup ? 700 : 400 }}>{fmtAmount(r.amount)}</span>
                  )}
                  style={{ textAlign: 'right', width: '10rem' }}
                />
                <Column
                  header="No. of Entries"
                  body={(r: ParticularsFlatRow) =>
                    r.no_of_entries === null ? '' : (
                      <span style={{ fontWeight: r.isGroup ? 700 : 400 }}>{r.no_of_entries}</span>
                    )
                  }
                  style={{ textAlign: 'center', width: '9rem' }}
                />
                <Column
                  header="Action"
                  style={{ textAlign: 'center', width: '7rem' }}
                  body={(r: ParticularsFlatRow) =>
                    r.key === 'calculated-balance' ? null : (
                      <span
                        className="link-view"
                        style={{ color: 'var(--color-primary)', cursor: 'pointer', fontWeight: 600 }}
                        title={r.isMixedGroup ? 'This group has both matched and unmatched entries — expand to view each separately' : undefined}
                        onClick={() => {
                          // A mixed group (part matched-residual, part
                          // genuinely unmatched) has no single destination
                          // page that shows both — expand it instead so the
                          // user can View each child row separately, rather
                          // than silently landing on the unmatched-only view
                          // and losing every matched entry from the count.
                          if (r.isMixedGroup && r.groupIndex !== null) {
                            toggleGroup(r.groupIndex);
                            return;
                          }
                          const slug = particularsViewSlug(r);
                          const qp = new URLSearchParams();
                          if (r.statusReason) qp.set('status_reason', r.statusReason);
                          if (r.groupFilter) qp.set('group', r.groupFilter);
                          if (r.isMatchedResidual && r.matchedStatus) qp.set('computed_status', r.matchedStatus);
                          const qs = qp.toString() ? `?${qp.toString()}` : '';
                          navigate(`/track-reconciliation/${requestId}/case/${caseId}/view/${slug}${qs}`);
                        }}
                      >
                        {r.isMixedGroup ? 'View breakdown' : 'View'}
                      </span>
                    )
                  }
                />
              </DataTable>
            </div>
          )}

          {/* ── Reconciliation Analytics table ── */}
          <h4 className="mb-2">Reconciliation Analytics</h4>
          {analyticsLoading ? (
            <div className="flex justify-content-center p-4"><ProgressSpinner style={{ width: 40, height: 40 }} /></div>
          ) : (
            <div className="em-card" style={{ padding: 0 }}>
              <DataTable value={analytics?.rows ?? []} size="small" emptyMessage="No analytics available.">
                <Column field="particulars" header="Particulars" style={{ fontWeight: 600 }} />
                <Column field="company_numbers" header="Company Numbers" style={{ textAlign: 'center' }} />
                <Column field="company_percentage" header="Company %" body={(r: AnalyticsRow) => `${r.company_percentage}`} style={{ textAlign: 'center' }} />
                <Column field="party_numbers" header="Party Numbers" style={{ textAlign: 'center' }} />
                <Column field="party_percentage" header="Party %" body={(r: AnalyticsRow) => `${r.party_percentage}`} style={{ textAlign: 'center' }} />
                <Column
                  header="Action"
                  style={{ textAlign: 'center', width: '8rem' }}
                  body={(r: AnalyticsRow) => (
                    <span
                      className="link-view"
                      style={{ color: 'var(--color-primary)', cursor: 'pointer', fontWeight: 600 }}
                      onClick={() => navigate(`/track-reconciliation/${requestId}/case/${caseId}/view/${analyticsViewSlug(r)}`)}
                    >
                      View
                    </span>
                  )}
                />
              </DataTable>
            </div>
          )}
        </div>
    </div>
  );
};
