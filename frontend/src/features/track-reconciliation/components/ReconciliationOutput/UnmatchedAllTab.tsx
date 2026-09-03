/**
 * UnmatchedAllTab — Unified view of ALL unmatched entries (company + party)
 * in a single table, distinguished by a Source column.
 *
 * When `editable` is true (reached via the reconciliation summary's
 * "Unmatched"/matching drill-down), the reviewer can select entries across
 * both sides and manually link them — same mandatory-reason flow as the
 * dedicated Link Unmatched page — without leaving this view.
 */

import { useMemo, useRef, useState } from 'react';
import { DataTable } from 'primereact/datatable';
import { Column } from 'primereact/column';
import { Button } from 'primereact/button';
import { Dialog } from 'primereact/dialog';
import { Dropdown } from 'primereact/dropdown';
import { InputText } from 'primereact/inputtext';
import { InputTextarea } from 'primereact/inputtextarea';
import { Tag } from 'primereact/tag';
import { Toast } from 'primereact/toast';
import { ProgressSpinner } from 'primereact/progressspinner';
import { Message } from 'primereact/message';
import { useQuery, useQueryClient } from '@tanstack/react-query';

import { apiClient } from '@shared/services/apiClient';
import { LEDGER_COLUMN_DEFS, manualLink, getStatusReasons } from './reconciliationOutputApi';
import type { EntryColumns } from './reconciliationOutputApi';

type LedgerSource = 'Company' | 'Party';

interface UnmatchedRow {
  id: string;
  source: LedgerSource;
  amount: number;
  columns?: EntryColumns;
}

function normalizeRows(raw: any, source: LedgerSource): UnmatchedRow[] {
  return (raw?.items ?? []).map((it: any) => ({
    id: it.entry_id ?? it.id,
    source,
    amount: Number(it.amount ?? 0),
    columns: it.columns ?? undefined,
  }));
}

interface UnmatchedAllTabProps {
  caseId: string;
  /** Enables selection + "Link Selected" — off by default (read-only). */
  editable?: boolean;
  /**
   * Pre-applied, non-editable filter to a single Particulars-statement
   * difference group (e.g. "Invoice Difference", "Other Differences") —
   * from the reconciliation statement's group-header "View" drill-in. Bug
   * fix: previously every difference group's View button routed here with
   * NO filter at all, so every group showed the same full unmatched list.
   * When set, the free-text search box is hidden since the view is already
   * scoped to one group.
   */
  groupFilter?: string;
}

export const UnmatchedAllTab = ({ caseId, editable = false, groupFilter }: UnmatchedAllTabProps) => {
  const toast = useRef<Toast>(null);
  const queryClient = useQueryClient();

  const { data: companyData, isLoading: companyLoading, error: companyError, refetch: refetchCompany } = useQuery({
    queryKey: ['unmatched-company-all', caseId, groupFilter],
    queryFn: async () => {
      const { data } = await apiClient.get(`/vlr/reconciliation/${caseId}/unmatched-company`, {
        params: { page: 1, page_size: 1000, group_filter: groupFilter || undefined },
      });
      return normalizeRows(data, 'Company');
    },
    enabled: !!caseId,
  });

  const { data: vendorData, isLoading: vendorLoading, error: vendorError, refetch: refetchVendor } = useQuery({
    queryKey: ['unmatched-vendor-all', caseId, groupFilter],
    queryFn: async () => {
      const { data } = await apiClient.get(`/vlr/reconciliation/${caseId}/unmatched-vendor`, {
        params: { page: 1, page_size: 1000, group_filter: groupFilter || undefined },
      });
      return normalizeRows(data, 'Party');
    },
    enabled: !!caseId,
  });

  const allRows = useMemo(
    () => [...(companyData ?? []), ...(vendorData ?? [])],
    [companyData, vendorData]
  );

  const [searchTerm, setSearchTerm] = useState('');

  const filteredRows = useMemo(() => {
    const term = searchTerm.trim().toLowerCase();
    if (!term) return allRows;
    return allRows.filter((row) => {
      if (!row.columns) return false;
      return Object.values(row.columns as Record<string, unknown>).some(
        (v) => v !== null && v !== undefined && String(v).toLowerCase().includes(term)
      );
    });
  }, [allRows, searchTerm]);

  const companyCount = companyData?.length ?? 0;
  const partyCount = vendorData?.length ?? 0;

  // ─── Manual link state (only used when editable) ─────────────────────────
  const [selection, setSelection] = useState<UnmatchedRow[]>([]);
  const [isLinking, setIsLinking] = useState(false);
  const [showReasonDialog, setShowReasonDialog] = useState(false);
  const [selectedReason, setSelectedReason] = useState<string | null>(null);
  const [linkNotes, setLinkNotes] = useState('');

  const { data: statusReasons, isLoading: reasonsLoading } = useQuery({
    queryKey: ['manual-link-status-reasons'],
    queryFn: getStatusReasons,
    staleTime: Infinity,
    enabled: editable,
  });

  const companySelection = useMemo(() => selection.filter((r) => r.source === 'Company'), [selection]);
  const vendorSelection = useMemo(() => selection.filter((r) => r.source === 'Party'), [selection]);
  const companySum = useMemo(() => companySelection.reduce((s, r) => s + r.amount, 0), [companySelection]);
  const vendorSum = useMemo(() => vendorSelection.reduce((s, r) => s + r.amount, 0), [vendorSelection]);
  const netDiff = companySum + vendorSum;
  const fmt = (n: number) => n.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

  const handleLink = () => {
    if (selection.length === 0) {
      toast.current?.show({ severity: 'warn', summary: 'Nothing selected', detail: 'Select at least one entry to link.', life: 4000 });
      return;
    }
    setSelectedReason(null);
    setLinkNotes('');
    setShowReasonDialog(true);
  };

  const handleConfirmLink = async () => {
    if (!selectedReason) {
      toast.current?.show({ severity: 'warn', summary: 'Reason required', detail: 'Select why these entries are being linked.', life: 4000 });
      return;
    }
    setIsLinking(true);
    try {
      const res = await manualLink(
        caseId,
        companySelection.map((r) => r.id),
        vendorSelection.map((r) => r.id),
        selectedReason,
        linkNotes || undefined
      );
      toast.current?.show({ severity: 'success', summary: 'Linked', detail: res.message, life: 5000 });
      setSelection([]);
      setShowReasonDialog(false);
      refetchCompany();
      refetchVendor();
      queryClient.invalidateQueries({ queryKey: ['case-detail', caseId] });
      queryClient.invalidateQueries({ queryKey: ['vlr', 'reconciliation', caseId] });
    } catch (error: any) {
      const detail = error.response?.data?.detail || 'Failed to link entries.';
      toast.current?.show({ severity: 'error', summary: 'Link Failed', detail, life: 8000 });
    } finally {
      setIsLinking(false);
    }
  };

  if (companyLoading || vendorLoading) {
    return (
      <div className="flex justify-content-center align-items-center" style={{ minHeight: 240 }}>
        <ProgressSpinner style={{ width: 44, height: 44 }} />
      </div>
    );
  }

  if (companyError || vendorError) {
    return (
      <Message
        severity="error"
        className="w-full"
        text="Failed to load unmatched entries. Please try again."
      />
    );
  }

  return (
    <div>
      {editable && <Toast ref={toast} />}

      {editable && (
        <div className="flex align-items-center justify-content-end gap-3 mb-3">
          <div className="text-sm">
            <span className="text-color-secondary">Company: </span>
            <span className="font-semibold">{fmt(companySum)}</span>
            <span className="text-color-secondary ml-3">Vendor: </span>
            <span className="font-semibold">{fmt(vendorSum)}</span>
            <span className="text-color-secondary ml-3">Net: </span>
            <span className={`font-bold ${Math.abs(netDiff) < 0.01 ? 'text-green-600' : 'text-orange-500'}`}>{fmt(netDiff)}</span>
          </div>
          <Button
            label="Link Selected"
            icon="pi pi-link"
            loading={isLinking}
            disabled={companySelection.length === 0 && vendorSelection.length === 0}
            onClick={handleLink}
          />
        </div>
      )}

      {editable && Math.abs(netDiff) >= 0.01 && selection.length > 0 && (
        <Message
          severity="warn"
          className="w-full mb-3"
          text={`Selected entries have a net difference of ${fmt(netDiff)}. You can still link them (the difference will be recorded), or adjust your selection to balance.`}
        />
      )}

      <div className="em-card" style={{ padding: 0 }}>
        <div className="p-3 flex align-items-center justify-content-between">
          <h4 className="m-0">Unmatched Data</h4>
          <div className="flex align-items-center gap-3">
            {groupFilter ? (
              <Tag value={`Group: ${groupFilter}`} severity="info" />
            ) : (
              <div className="em-search-bar">
                <InputText
                  placeholder="Search unmatched entries..."
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                  style={{ border: 'none', boxShadow: 'none', width: 220 }}
                  aria-label="Search unmatched entries"
                />
                <i className="pi pi-search" />
              </div>
            )}
            {editable && <Tag value={`${companySelection.length} company`} />}
            {editable && <Tag value={`${vendorSelection.length} party`} severity="warning" />}
            {!editable && <Tag value={`${companyCount} company`} />}
            {!editable && <Tag value={`${partyCount} party`} severity="warning" />}
          </div>
        </div>
        <DataTable
          value={filteredRows}
          selection={editable ? selection : undefined}
          onSelectionChange={editable ? (e) => setSelection(e.value as UnmatchedRow[]) : undefined}
          dataKey="id"
          size="small"
          scrollable
          scrollHeight="600px"
          paginator
          rows={100}
          rowsPerPageOptions={[25, 50, 100, 200]}
          emptyMessage="No unmatched entries"
        >
          {editable && <Column selectionMode="multiple" headerStyle={{ width: '3rem' }} frozen />}
          <Column
            header="Source"
            frozen
            style={{ minWidth: '7rem' }}
            body={(row: UnmatchedRow) => (
              <Tag
                value={row.source}
                severity={row.source === 'Company' ? 'info' : 'warning'}
              />
            )}
          />
          {LEDGER_COLUMN_DEFS.map((c) => (
            <Column
              key={c.field}
              header={c.header}
              body={(row: UnmatchedRow) => {
                const v = row.columns ? (row.columns as any)[c.field] : undefined;
                return v === undefined || v === null || v === '' ? '—' : String(v);
              }}
              style={{
                minWidth: '9rem',
                whiteSpace: 'nowrap',
                textAlign: c.field === 'amount' || c.field === 'amount_in_doc_curr' ? 'right' : 'left',
              }}
            />
          ))}
        </DataTable>
      </div>

      {editable && (
        <Dialog
          header="Reason for Linking"
          visible={showReasonDialog}
          onHide={() => setShowReasonDialog(false)}
          style={{ width: '32rem' }}
          modal
        >
          <p className="text-color-secondary mb-4">
            Linking {companySelection.length} company + {vendorSelection.length} party
            entr{companySelection.length + vendorSelection.length === 1 ? 'y' : 'ies'}.
            Net difference: <strong>{fmt(netDiff)}</strong>
          </p>

          <label htmlFor="unmatched-link-reason" className="block font-medium mb-2">
            Reason <span className="text-red-500">*</span>
          </label>
          <Dropdown
            id="unmatched-link-reason"
            value={selectedReason}
            onChange={(e) => setSelectedReason(e.value)}
            options={statusReasons ?? []}
            placeholder={reasonsLoading ? 'Loading reasons...' : 'Select a reason'}
            disabled={reasonsLoading}
            filter
            className="w-full mb-4"
            aria-required="true"
          />

          <label htmlFor="unmatched-link-notes" className="block font-medium mb-2">
            Notes (optional)
          </label>
          <InputTextarea
            id="unmatched-link-notes"
            value={linkNotes}
            onChange={(e) => setLinkNotes(e.target.value)}
            rows={3}
            className="w-full mb-4"
            placeholder="Any additional context for this manual link..."
          />

          <div className="flex justify-content-end gap-2">
            <Button
              label="Cancel"
              className="p-button-text"
              onClick={() => setShowReasonDialog(false)}
              disabled={isLinking}
            />
            <Button
              label="Confirm Link"
              icon="pi pi-link"
              loading={isLinking}
              disabled={!selectedReason}
              onClick={handleConfirmLink}
            />
          </div>
        </Dialog>
      )}
    </div>
  );
};
