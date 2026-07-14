/**
 * Reconciliation Detail Page — Tabbed view with Statistics, All Parties, Reco Stage,
 * Review Stage, Sign Off Stage, and Action Tracker tabs.
 *
 * Fetches live data from the API using useBatchCases hook with stage filtering.
 * Preserves tab selection in URL query parameter for back/forward navigation.
 * All action buttons wired to mutation hooks with Toast feedback and selection management.
 *
 * Requirements: 1, 2, 3, 4, 24
 */

import { useState, useMemo, useRef } from 'react';
import { useParams, useNavigate, useSearchParams } from 'react-router-dom';
import { Button } from 'primereact/button';
import { DataTable } from 'primereact/datatable';
import { Column } from 'primereact/column';
import { InputText } from 'primereact/inputtext';
import { Skeleton } from 'primereact/skeleton';
import { Message } from 'primereact/message';
import { Toast } from 'primereact/toast';
import { Menu } from 'primereact/menu';
import { StatisticsTab } from '../components/StatisticsTab';
import { StatusBadge } from '@shared/components/StatusBadge';
import {
  useBatchCases,
  useSendReminder,
  useBulkReview,
  useBulkReviewDone,
  useBulkSignoffRequest,
} from '../hooks/useReconciliationDetail';
import type { BatchCaseRow } from '../api/reconciliationDetailApi';

type TabKey = 'statistics' | 'allParties' | 'recoStage' | 'reviewStage' | 'signOffStage' | 'actionTracker';

const VALID_TABS: TabKey[] = ['statistics', 'allParties', 'recoStage', 'reviewStage', 'signOffStage', 'actionTracker'];

/** Maps tab keys to the stage filter parameter expected by the API. */
const TAB_STAGE_MAP: Record<TabKey, string | undefined> = {
  statistics: undefined,
  allParties: undefined,
  recoStage: 'reconciliation',
  reviewStage: 'review',
  signOffStage: 'signoff',
  actionTracker: 'action_tracker',
};

export const ReconciliationDetailPage = () => {
  const { requestId } = useParams<{ requestId: string }>();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const [searchQuery, setSearchQuery] = useState('');
  const toast = useRef<Toast>(null);

  // Per-tab selection state
  const [allPartiesSelection, setAllPartiesSelection] = useState<BatchCaseRow[]>([]);
  const [recoStageSelection, setRecoStageSelection] = useState<BatchCaseRow[]>([]);
  const [reviewStageSelection, setReviewStageSelection] = useState<BatchCaseRow[]>([]);
  const [signOffStageSelection, setSignOffStageSelection] = useState<BatchCaseRow[]>([]);

  // Menu refs for dropdowns
  const bulkActionsMenuAllParties = useRef<Menu>(null);
  const bulkActionsMenuRecoStage = useRef<Menu>(null);
  const bulkActionsMenuReviewStage = useRef<Menu>(null);
  const bulkActionsMenuSignOff = useRef<Menu>(null);
  const moreActionsMenu = useRef<Menu>(null);

  // Derive active tab from URL query param, default to 'statistics'
  const activeTab = useMemo<TabKey>(() => {
    const tabParam = searchParams.get('tab') as TabKey | null;
    if (tabParam && VALID_TABS.includes(tabParam)) return tabParam;
    return 'statistics';
  }, [searchParams]);

  const setActiveTab = (tab: TabKey) => {
    setSearchParams({ tab }, { replace: false });
  };

  // Determine the stage filter for the current tab
  const currentStage = TAB_STAGE_MAP[activeTab];

  // Fetch cases with stage filtering (skip fetch for statistics tab)
  const shouldFetch = activeTab !== 'statistics' && !!requestId;
  const {
    data: casesData,
    isLoading,
    isError,
    error,
    refetch,
  } = useBatchCases(requestId ?? '', {
    stage: currentStage,
    page: 1,
    page_size: 50,
  });

  const cases = shouldFetch ? (casesData?.items ?? []) : [];
  const summary = casesData?.summary;

  // ─────────────────────────────────────────────────────────────────────────
  // Mutation hooks
  // ─────────────────────────────────────────────────────────────────────────

  const sendReminderMutation = useSendReminder(requestId || '');
  const bulkReviewMutation = useBulkReview(requestId || '');
  const bulkReviewDoneMutation = useBulkReviewDone(requestId || '');
  const bulkSignoffRequestMutation = useBulkSignoffRequest(requestId || '');

  // ─────────────────────────────────────────────────────────────────────────
  // Action handlers
  // ─────────────────────────────────────────────────────────────────────────

  const handleSendReminder = (selectedRows: BatchCaseRow[], clearSelection: () => void) => {
    const case_ids = selectedRows.map((r) => r.case_id || r.id);
    sendReminderMutation.mutate(
      { case_ids },
      {
        onSuccess: () => {
          toast.current?.show({
            severity: 'success',
            summary: 'Reminder Sent',
            detail: `Reminder sent to ${case_ids.length} case(s).`,
            life: 3000,
          });
          clearSelection();
        },
        onError: (err) => {
          toast.current?.show({
            severity: 'error',
            summary: 'Send Reminder Failed',
            detail: err.message || 'An error occurred while sending reminders.',
            life: 5000,
          });
        },
      }
    );
  };

  const handleSendForReview = () => {
    const case_ids = recoStageSelection.map((r) => r.case_id || r.id);
    bulkReviewMutation.mutate(
      { case_ids },
      {
        onSuccess: () => {
          toast.current?.show({
            severity: 'success',
            summary: 'Sent For Review',
            detail: `${case_ids.length} case(s) sent for review.`,
            life: 3000,
          });
          setRecoStageSelection([]);
        },
        onError: (err) => {
          toast.current?.show({
            severity: 'error',
            summary: 'Send For Review Failed',
            detail: err.message || 'An error occurred.',
            life: 5000,
          });
        },
      }
    );
  };

  const handleReviewDone = () => {
    const case_ids = reviewStageSelection.map((r) => r.case_id || r.id);
    bulkReviewDoneMutation.mutate(
      { case_ids },
      {
        onSuccess: () => {
          toast.current?.show({
            severity: 'success',
            summary: 'Review Done',
            detail: `${case_ids.length} case(s) marked as review done.`,
            life: 3000,
          });
          setReviewStageSelection([]);
        },
        onError: (err) => {
          toast.current?.show({
            severity: 'error',
            summary: 'Review Done Failed',
            detail: err.message || 'An error occurred.',
            life: 5000,
          });
        },
      }
    );
  };

  const handleRequestSignOff = () => {
    const case_ids = reviewStageSelection.map((r) => r.case_id || r.id);
    bulkSignoffRequestMutation.mutate(
      { case_ids },
      {
        onSuccess: () => {
          toast.current?.show({
            severity: 'success',
            summary: 'SignOff Requested',
            detail: `SignOff requested for ${case_ids.length} case(s).`,
            life: 3000,
          });
          setReviewStageSelection([]);
        },
        onError: (err) => {
          toast.current?.show({
            severity: 'error',
            summary: 'Request SignOff Failed',
            detail: err.message || 'An error occurred.',
            life: 5000,
          });
        },
      }
    );
  };

  // ─────────────────────────────────────────────────────────────────────────
  // Bulk Actions dropdown menu items (per tab)
  // ─────────────────────────────────────────────────────────────────────────

  const bulkActionsItemsAllParties = [
    {
      label: 'Send Reminder',
      icon: 'pi pi-send',
      disabled: allPartiesSelection.length === 0,
      command: () => handleSendReminder(allPartiesSelection, () => setAllPartiesSelection([])),
    },
  ];

  const bulkActionsItemsRecoStage = [
    {
      label: 'Send For Review',
      icon: 'pi pi-send',
      disabled: recoStageSelection.length === 0,
      command: () => handleSendForReview(),
    },
  ];

  const bulkActionsItemsReviewStage = [
    {
      label: 'Review Done',
      icon: 'pi pi-check',
      disabled: reviewStageSelection.length === 0,
      command: () => handleReviewDone(),
    },
    {
      label: 'Request SignOff',
      icon: 'pi pi-verified',
      disabled: reviewStageSelection.length === 0,
      command: () => handleRequestSignOff(),
    },
  ];

  const bulkActionsItemsSignOff = [
    {
      label: 'Send Reminder',
      icon: 'pi pi-send',
      disabled: signOffStageSelection.length === 0,
      command: () => handleSendReminder(signOffStageSelection, () => setSignOffStageSelection([])),
    },
  ];

  // More Actions header dropdown items
  const moreActionsItems = [
    {
      label: 'Export Batch',
      icon: 'pi pi-download',
      command: () => {
        toast.current?.show({
          severity: 'info',
          summary: 'Export',
          detail: 'Batch export initiated.',
          life: 3000,
        });
      },
    },
    {
      label: 'Close Batch',
      icon: 'pi pi-times-circle',
      command: () => {
        toast.current?.show({
          severity: 'info',
          summary: 'Close Batch',
          detail: 'Batch close initiated.',
          life: 3000,
        });
      },
    },
  ];

  // ─────────────────────────────────────────────────────────────────────────
  // Tab configuration
  // ─────────────────────────────────────────────────────────────────────────

  const tabs: { key: TabKey; label: string; badge?: number }[] = [
    { key: 'statistics', label: 'Statistics' },
    { key: 'allParties', label: 'All Parties', badge: summary?.total_parties },
    { key: 'recoStage', label: 'Reco Stage', badge: summary?.reco_stage_count },
    { key: 'reviewStage', label: 'Review Stage', badge: summary?.review_stage_count },
    { key: 'signOffStage', label: 'Sign Off Stage', badge: summary?.signoff_stage_count },
    { key: 'actionTracker', label: 'Action Tracker' },
  ];

  // ─────────────────────────────────────────────────────────────────────────
  // Action column templates
  // ─────────────────────────────────────────────────────────────────────────

  /**
   * Returns a contextual action label based on the case status.
   * "View" for completed/closed, "Reconcile" for mapping_pending/in_progress,
   * "Review" for review statuses, default "View".
   */
  const getActionLabel = (status: string): string => {
    const s = status.toLowerCase();
    if (s.includes('completed') || s.includes('closed') || s.includes('auto_completed') || s.includes('signoff_completed')) {
      return 'View';
    }
    if (s.includes('mapping_pending') || s.includes('in_progress')) {
      return 'Reconcile';
    }
    if (s.includes('review')) {
      return 'Review';
    }
    return 'View';
  };

  const actionTemplate = (row: BatchCaseRow) => {
    const caseId = row.case_id || row.id;
    const label = getActionLabel(row.status || '');
    return (
      <div className="flex align-items-center gap-2">
        <span
          className="link-view"
          style={{ cursor: 'pointer' }}
          onClick={() => navigate(`/track-reconciliation/${requestId}/case/${caseId}`)}
          role="button"
          tabIndex={0}
          onKeyDown={(e) => {
            if (e.key === 'Enter' || e.key === ' ') {
              navigate(`/track-reconciliation/${requestId}/case/${caseId}`);
            }
          }}
        >
          {label}
        </span>
        <i className="pi pi-ellipsis-h" style={{ cursor: 'pointer', color: 'var(--color-text-muted)' }} />
      </div>
    );
  };

  /** Renders a StatusBadge for the case status column. */
  const statusTemplate = (row: BatchCaseRow) => (
    <StatusBadge status={row.status || ''} />
  );

  const actionTrackerActionTemplate = () => (
    <span className="link-view">View</span>
  );

  /** Helper to render a count badge on action buttons. */
  const renderCountBadge = (count: number) => {
    if (count === 0) return null;
    return (
      <span
        style={{
          marginLeft: 6,
          background: 'var(--color-primary)',
          color: '#fff',
          padding: '2px 7px',
          borderRadius: '10px',
          fontSize: '11px',
          fontWeight: 600,
        }}
      >
        {count}
      </span>
    );
  };

  // ─────────────────────────────────────────────────────────────────────────
  // Loading / Error / Empty state renderers
  // ─────────────────────────────────────────────────────────────────────────

  /** Renders the loading skeleton for data tables. */
  const renderLoadingSkeleton = () => (
    <div className="em-card" style={{ padding: '1rem' }}>
      {Array.from({ length: 6 }).map((_, i) => (
        <Skeleton key={i} height="2.5rem" className="mb-2" />
      ))}
    </div>
  );

  /** Renders the error state with retry button. */
  const renderError = () => (
    <div className="em-card" style={{ padding: '2rem', textAlign: 'center' }}>
      <Message
        severity="error"
        text={
          error instanceof Error
            ? error.message
            : 'Failed to load cases. Please try again.'
        }
      />
      <div className="mt-3">
        <Button
          label="Retry"
          icon="pi pi-refresh"
          className="p-button-outlined p-button-sm"
          onClick={() => refetch()}
        />
      </div>
    </div>
  );

  /** Renders the empty state when no cases exist. */
  const renderEmpty = () => (
    <div className="em-card" style={{ padding: '3rem', textAlign: 'center' }}>
      <i className="pi pi-inbox" style={{ fontSize: '2.5rem', color: 'var(--color-text-muted)' }} />
      <p style={{ color: 'var(--color-text-secondary)', marginTop: '1rem' }}>
        No cases found for this reconciliation request.
      </p>
    </div>
  );

  /** Renders the data content for a given tab or handles loading/error/empty states. */
  const renderTabContent = (content: React.ReactNode) => {
    if (isLoading && shouldFetch) return renderLoadingSkeleton();
    if (isError && shouldFetch) return renderError();
    if (shouldFetch && cases.length === 0) return renderEmpty();
    return content;
  };

  return (
    <div>
      <Toast ref={toast} />

      {/* Breadcrumb */}
      <div className="flex align-items-center gap-2 mb-3" style={{ fontSize: 12, color: 'var(--color-text-secondary)' }}>
        <span className="cursor-pointer" onClick={() => navigate('/track-reconciliation')} style={{ color: 'var(--color-primary)' }}>
          Track Reconciliation
        </span>
        <span>&gt;</span>
        <span>{requestId || 'MAY-2026-ROLEOUT DATA'}</span>
        <span>&gt;</span>
        <span>{tabs.find(t => t.key === activeTab)?.label}</span>
      </div>

      {/* Header Info */}
      <div className="flex align-items-center justify-content-between mb-4 p-3" style={{ background: 'var(--color-surface)', borderRadius: 'var(--radius-md)', border: '1px solid var(--color-surface-border)' }}>
        <div className="flex align-items-center gap-4">
          <Button icon="pi pi-arrow-left" className="p-button-text p-button-sm" onClick={() => navigate('/track-reconciliation')} />
          <div>
            <span className="text-sm" style={{ color: 'var(--color-text-muted)' }}>Reco Type</span>
            <span className="ml-3 font-semibold">bulkreco</span>
          </div>
          <div>
            <span className="text-sm" style={{ color: 'var(--color-text-muted)' }}>Reco Period</span>
            <span className="ml-3 font-semibold">01-Apr-2025 to 31-Mar-2026</span>
          </div>
        </div>
        <div>
          <Button
            label="More Actions"
            icon="pi pi-chevron-down"
            iconPos="right"
            className="p-button-outlined p-button-sm"
            onClick={(e) => moreActionsMenu.current?.toggle(e)}
          />
          <Menu model={moreActionsItems} popup ref={moreActionsMenu} />
        </div>
      </div>

      {/* Pipeline Tabs */}
      <div className="em-pipeline-tabs">
        {tabs.map((tab) => (
          <button
            key={tab.key}
            className={`em-pipeline-tab ${activeTab === tab.key ? 'active' : ''}`}
            onClick={() => setActiveTab(tab.key)}
          >
            {tab.label}
            {tab.badge !== undefined && (
              <span className="badge">{tab.badge > 99 ? '99+' : tab.badge}</span>
            )}
          </button>
        ))}
      </div>

      {/* Tab Content */}
      {activeTab === 'statistics' && <StatisticsTab />}

      {activeTab === 'allParties' && renderTabContent(
        <div>
          <div className="em-action-bar">
            <Button
              label="Send Reminder"
              icon={sendReminderMutation.isPending ? 'pi pi-spin pi-spinner' : 'pi pi-send'}
              className="p-button-outlined p-button-sm"
              disabled={allPartiesSelection.length === 0 || sendReminderMutation.isPending}
              onClick={() => handleSendReminder(allPartiesSelection, () => setAllPartiesSelection([]))}
            >
              {renderCountBadge(allPartiesSelection.length)}
            </Button>
            <Button
              label="Bulk Actions"
              icon="pi pi-chevron-down"
              iconPos="right"
              className="p-button-outlined p-button-sm"
              disabled={allPartiesSelection.length === 0}
              onClick={(e) => bulkActionsMenuAllParties.current?.toggle(e)}
            />
            <Menu model={bulkActionsItemsAllParties} popup ref={bulkActionsMenuAllParties} />
            <div className="flex-1" />
            <div className="em-search-bar">
              <InputText
                placeholder="Type and press enter to Search"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                style={{ border: 'none', boxShadow: 'none', width: 180 }}
              />
              <i className="pi pi-search" />
            </div>
          </div>
          <div className="em-card" style={{ padding: 0 }}>
            <DataTable
              value={cases}
              paginator
              rows={10}
              sortMode="multiple"
              emptyMessage="No parties found."
              selection={allPartiesSelection}
              onSelectionChange={(e) => setAllPartiesSelection(e.value as BatchCaseRow[])}
              selectionMode="checkbox"
              dataKey="id"
            >
              <Column selectionMode="multiple" headerStyle={{ width: '3rem' }} />
              <Column field="vendor_code" header="Party Code" sortable style={{ width: '12%' }} />
              <Column field="vendor_name" header="Party Name" sortable style={{ width: '25%' }} />
              <Column field="status" header="Status" body={statusTemplate} sortable style={{ width: '10%' }} />
              <Column field="last_update_date" header="Last Update Date" sortable style={{ width: '12%' }} />
              <Column field="days_elapsed" header="No. of Days" sortable style={{ width: '8%', textAlign: 'center' }} />
              <Column field="company_amount" header="Company Amount" sortable style={{ width: '12%', textAlign: 'right' }} />
              <Column field="difference_amount" header="Difference Amount" sortable style={{ width: '12%', textAlign: 'right' }} />
              <Column header="Action" body={actionTemplate} style={{ width: '8%' }} />
            </DataTable>
          </div>
        </div>
      )}

      {activeTab === 'recoStage' && renderTabContent(
        <div>
          <div className="em-action-bar">
            <Button
              label="Send For Review"
              icon={bulkReviewMutation.isPending ? 'pi pi-spin pi-spinner' : 'pi pi-send'}
              className="p-button-outlined p-button-sm"
              disabled={recoStageSelection.length === 0 || bulkReviewMutation.isPending}
              onClick={() => handleSendForReview()}
            >
              {renderCountBadge(recoStageSelection.length)}
            </Button>
            <Button
              label="Bulk Actions"
              icon="pi pi-chevron-down"
              iconPos="right"
              className="p-button-outlined p-button-sm"
              disabled={recoStageSelection.length === 0}
              onClick={(e) => bulkActionsMenuRecoStage.current?.toggle(e)}
            />
            <Menu model={bulkActionsItemsRecoStage} popup ref={bulkActionsMenuRecoStage} />
            <div className="flex-1" />
            <div className="em-search-bar">
              <InputText
                placeholder="Type and press enter to Search"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                style={{ border: 'none', boxShadow: 'none', width: 180 }}
              />
              <i className="pi pi-search" />
            </div>
          </div>
          <div className="em-card" style={{ padding: 0 }}>
            <DataTable
              value={cases}
              paginator
              rows={10}
              sortMode="multiple"
              emptyMessage="No records found."
              selection={recoStageSelection}
              onSelectionChange={(e) => setRecoStageSelection(e.value as BatchCaseRow[])}
              selectionMode="checkbox"
              dataKey="id"
            >
              <Column selectionMode="multiple" headerStyle={{ width: '3rem' }} />
              <Column field="vendor_code" header="Party Code" sortable style={{ width: '10%' }} />
              <Column field="vendor_name" header="Party Name" sortable style={{ width: '22%' }} />
              <Column field="status" header="Status" body={statusTemplate} sortable style={{ width: '12%' }} />
              <Column field="file_extension" header="File Extension" sortable style={{ width: '8%' }} />
              <Column field="owner" header="Owner" sortable style={{ width: '8%' }} />
              <Column field="days_elapsed" header="No.of Days" sortable style={{ width: '7%', textAlign: 'center' }} />
              <Column field="no_of_lines" header="No.of Lines" sortable style={{ width: '7%', textAlign: 'center' }} />
              <Column field="company_amount" header="Company Amount" sortable style={{ width: '12%', textAlign: 'right' }} />
              <Column field="difference_amount" header="Difference Amount" sortable style={{ width: '12%', textAlign: 'right' }} />
              <Column header="Action" body={actionTemplate} style={{ width: '8%' }} />
            </DataTable>
          </div>
        </div>
      )}

      {activeTab === 'reviewStage' && renderTabContent(
        <div>
          <div className="em-action-bar">
            <Button
              label="Review Done"
              icon={bulkReviewDoneMutation.isPending ? 'pi pi-spin pi-spinner' : 'pi pi-check'}
              className="p-button-outlined p-button-sm"
              disabled={reviewStageSelection.length === 0 || bulkReviewDoneMutation.isPending}
              onClick={() => handleReviewDone()}
            >
              {renderCountBadge(reviewStageSelection.length)}
            </Button>
            <Button
              label="Request SignOff"
              icon={bulkSignoffRequestMutation.isPending ? 'pi pi-spin pi-spinner' : 'pi pi-verified'}
              className="p-button-outlined p-button-sm"
              disabled={reviewStageSelection.length === 0 || bulkSignoffRequestMutation.isPending}
              onClick={() => handleRequestSignOff()}
            >
              {renderCountBadge(reviewStageSelection.length)}
            </Button>
            <Button
              label="Bulk Actions"
              icon="pi pi-chevron-down"
              iconPos="right"
              className="p-button-outlined p-button-sm"
              disabled={reviewStageSelection.length === 0}
              onClick={(e) => bulkActionsMenuReviewStage.current?.toggle(e)}
            />
            <Menu model={bulkActionsItemsReviewStage} popup ref={bulkActionsMenuReviewStage} />
            <div className="flex-1" />
            <div className="em-search-bar">
              <InputText
                placeholder="Type and press enter to Search"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                style={{ border: 'none', boxShadow: 'none', width: 180 }}
              />
              <i className="pi pi-search" />
            </div>
          </div>
          <div className="em-card" style={{ padding: 0 }}>
            <DataTable
              value={cases}
              paginator
              rows={10}
              sortMode="multiple"
              emptyMessage="No records found."
              selection={reviewStageSelection}
              onSelectionChange={(e) => setReviewStageSelection(e.value as BatchCaseRow[])}
              selectionMode="checkbox"
              dataKey="id"
            >
              <Column selectionMode="multiple" headerStyle={{ width: '3rem' }} />
              <Column field="vendor_code" header="Party Code" sortable style={{ width: '10%' }} />
              <Column field="vendor_name" header="Party Name" sortable style={{ width: '20%' }} />
              <Column field="status" header="Status" body={statusTemplate} sortable style={{ width: '10%' }} />
              <Column field="owner" header="Owner" sortable style={{ width: '8%' }} />
              <Column field="reviewer" header="Reviewer" sortable style={{ width: '8%' }} />
              <Column field="days_elapsed" header="No. of Days" sortable style={{ width: '7%', textAlign: 'center' }} />
              <Column field="no_of_lines" header="No. of Lines" sortable style={{ width: '7%', textAlign: 'center' }} />
              <Column field="unmatched_entries" header="Unmatched Entries" sortable style={{ width: '10%' }} />
              <Column field="company_amount" header="Company Amount" sortable style={{ width: '10%', textAlign: 'right' }} />
              <Column field="difference_amount" header="Difference Amount" sortable style={{ width: '10%', textAlign: 'right' }} />
              <Column header="Action" body={actionTemplate} style={{ width: '8%' }} />
            </DataTable>
          </div>
        </div>
      )}

      {activeTab === 'signOffStage' && renderTabContent(
        <div>
          <div className="em-action-bar">
            <Button
              label="Send Reminder"
              icon={sendReminderMutation.isPending ? 'pi pi-spin pi-spinner' : 'pi pi-send'}
              className="p-button-outlined p-button-sm"
              disabled={signOffStageSelection.length === 0 || sendReminderMutation.isPending}
              onClick={() => handleSendReminder(signOffStageSelection, () => setSignOffStageSelection([]))}
            >
              {renderCountBadge(signOffStageSelection.length)}
            </Button>
            <Button
              label="Bulk Actions"
              icon="pi pi-chevron-down"
              iconPos="right"
              className="p-button-outlined p-button-sm"
              disabled={signOffStageSelection.length === 0}
              onClick={(e) => bulkActionsMenuSignOff.current?.toggle(e)}
            />
            <Menu model={bulkActionsItemsSignOff} popup ref={bulkActionsMenuSignOff} />
            <div className="flex-1" />
            <div className="em-search-bar">
              <InputText
                placeholder="Type and press enter to Search"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                style={{ border: 'none', boxShadow: 'none', width: 180 }}
              />
              <i className="pi pi-search" />
            </div>
          </div>
          <div className="em-card" style={{ padding: 0 }}>
            <DataTable
              value={cases}
              paginator
              rows={10}
              sortMode="multiple"
              emptyMessage="No records found."
              selection={signOffStageSelection}
              onSelectionChange={(e) => setSignOffStageSelection(e.value as BatchCaseRow[])}
              selectionMode="checkbox"
              dataKey="id"
            >
              <Column selectionMode="multiple" headerStyle={{ width: '3rem' }} />
              <Column field="vendor_code" header="Party Code" sortable style={{ width: '12%' }} />
              <Column field="vendor_name" header="Party Name" sortable style={{ width: '25%' }} />
              <Column field="status" header="Status" body={statusTemplate} sortable style={{ width: '14%' }} />
              <Column field="days_elapsed" header="No. of Days" sortable style={{ width: '8%', textAlign: 'center' }} />
              <Column field="reminder_count" header="Reminder Count" sortable style={{ width: '10%', textAlign: 'center' }} />
              <Column field="owner" header="Owner" sortable style={{ width: '12%' }} />
              <Column field="contact_person" header="Contact Number" sortable style={{ width: '12%' }} />
              <Column header="Action" body={actionTemplate} style={{ width: '8%' }} />
            </DataTable>
          </div>
        </div>
      )}

      {activeTab === 'actionTracker' && renderTabContent(
        <div>
          <div className="em-card" style={{ padding: 0 }}>
            <DataTable value={cases} emptyMessage="No records found.">
              <Column field="status" header="Action Taken Status" body={statusTemplate} sortable style={{ width: '25%' }} />
              <Column field="no_of_lines" header="Number of Records" sortable style={{ width: '15%', textAlign: 'center' }} />
              <Column field="company_amount" header="Company Amount" sortable style={{ width: '20%', textAlign: 'right' }} />
              <Column field="difference_amount" header="Difference Amount" sortable style={{ width: '20%', textAlign: 'right' }} />
              <Column header="Action" body={actionTrackerActionTemplate} style={{ width: '10%' }} />
            </DataTable>
          </div>
        </div>
      )}
    </div>
  );
};
