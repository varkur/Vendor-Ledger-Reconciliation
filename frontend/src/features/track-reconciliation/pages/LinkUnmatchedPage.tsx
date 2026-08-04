/**
 * Link Unmatched Page — Reviewer manually links unmatched company + vendor entries.
 * Replicates Firmway's "Unmatched Data" Link view (Source 1 = Company, Source 2 = Party).
 *
 * The reviewer selects one or more entries on each side and clicks "Link" to
 * create a manual match. Shows a running selected-sum on each side and the
 * net difference so the reviewer can confirm the pairing balances.
 */

import { useState, useMemo, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { DataTable } from 'primereact/datatable';
import { Column } from 'primereact/column';
import { Button } from 'primereact/button';
import { Toast } from 'primereact/toast';
import { ProgressSpinner } from 'primereact/progressspinner';
import { Message } from 'primereact/message';
import { Tag } from 'primereact/tag';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '@shared/services/apiClient';
import { useSelectedEntity } from '@shared/hooks/useSelectedEntity';
import { manualLink, LEDGER_COLUMN_DEFS } from '../components/ReconciliationOutput/reconciliationOutputApi';
import type { EntryColumns } from '../components/ReconciliationOutput/reconciliationOutputApi';

type LedgerSource = 'Company' | 'Party';

interface UnmatchedRow {
  id: string;
  source: LedgerSource;
  document_number: string;
  reference: string;
  amount: number;
  posting_date: string;
  document_type: string;
  description?: string;
  columns?: EntryColumns;
}

function normalizeRows(raw: any, source: LedgerSource): UnmatchedRow[] {
  return (raw?.items ?? []).map((it: any) => ({
    id: it.entry_id ?? it.id,
    source,
    document_number: it.document_number ?? '',
    reference: it.reference_number ?? it.document_number ?? '',
    amount: Number(it.amount ?? 0),
    posting_date: it.posting_date ?? '',
    document_type: it.document_category ?? it.document_type ?? '',
    description: it.description ?? '',
    columns: it.columns ?? undefined,
  }));
}

export const LinkUnmatchedPage = () => {
  const { requestId, caseId } = useParams<{ requestId: string; caseId: string }>();
  const navigate = useNavigate();
  const toast = useRef<Toast>(null);
  const queryClient = useQueryClient();
  const { companyCode } = useSelectedEntity();

  const [selection, setSelection] = useState<UnmatchedRow[]>([]);
  const [isLinking, setIsLinking] = useState(false);

  const { data: companyData, isLoading: companyLoading, refetch: refetchCompany } = useQuery({
    queryKey: ['unmatched-company-link', caseId],
    queryFn: async () => {
      const { data } = await apiClient.get(`/vlr/reconciliation/${caseId}/unmatched-company`, {
        params: { page: 1, page_size: 500 },
      });
      return normalizeRows(data, 'Company');
    },
    enabled: !!caseId,
  });

  const { data: vendorData, isLoading: vendorLoading, refetch: refetchVendor } = useQuery({
    queryKey: ['unmatched-vendor-link', caseId],
    queryFn: async () => {
      const { data } = await apiClient.get(`/vlr/reconciliation/${caseId}/unmatched-vendor`, {
        params: { page: 1, page_size: 500 },
      });
      return normalizeRows(data, 'Party');
    },
    enabled: !!caseId,
  });

  // Merge both sides into one list; Source column distinguishes them.
  const allRows = useMemo(
    () => [...(companyData ?? []), ...(vendorData ?? [])],
    [companyData, vendorData]
  );

  const companySelection = useMemo(
    () => selection.filter((r) => r.source === 'Company'),
    [selection]
  );
  const vendorSelection = useMemo(
    () => selection.filter((r) => r.source === 'Party'),
    [selection]
  );

  const companySum = useMemo(
    () => companySelection.reduce((s, r) => s + r.amount, 0),
    [companySelection]
  );
  const vendorSum = useMemo(
    () => vendorSelection.reduce((s, r) => s + r.amount, 0),
    [vendorSelection]
  );
  const netDiff = companySum + vendorSum; // opposite signs

  const handleLink = async () => {
    if (selection.length === 0) {
      toast.current?.show({ severity: 'warn', summary: 'Nothing selected', detail: 'Select at least one entry to link.', life: 4000 });
      return;
    }
    setIsLinking(true);
    try {
      const res = await manualLink(
        caseId!,
        companySelection.map((r) => r.id),
        vendorSelection.map((r) => r.id)
      );
      toast.current?.show({ severity: 'success', summary: 'Linked', detail: res.message, life: 5000 });
      setSelection([]);
      refetchCompany();
      refetchVendor();
      queryClient.invalidateQueries({ queryKey: ['case-detail', caseId] });
    } catch (error: any) {
      const detail = error.response?.data?.detail || 'Failed to link entries.';
      toast.current?.show({ severity: 'error', summary: 'Link Failed', detail, life: 8000 });
    } finally {
      setIsLinking(false);
    }
  };

  const fmt = (n: number) => n.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

  if (companyLoading || vendorLoading) {
    return (
      <div className="flex justify-content-center align-items-center" style={{ minHeight: 300 }}>
        <ProgressSpinner style={{ width: 50, height: 50 }} />
      </div>
    );
  }

  return (
    <div>
      <Toast ref={toast} />

      <div className="flex align-items-center justify-content-between mb-3">
        <Button
          label="Back"
          icon="pi pi-arrow-left"
          className="p-button-text p-button-sm"
          onClick={() => navigate(`/track-reconciliation/${requestId}/case/${caseId}`)}
        />
        <h3 className="m-0">Link Unmatched Entries</h3>
        <div className="flex align-items-center gap-3">
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
      </div>

      {Math.abs(netDiff) >= 0.01 && selection.length > 0 && (
        <Message
          severity="warn"
          className="w-full mb-3"
          text={`Selected entries have a net difference of ${fmt(netDiff)}. You can still link them (the difference will be recorded), or adjust your selection to balance.`}
        />
      )}

      {/* Single unified table — all unmatched entries (company + party),
          distinguished by the Source column. */}
      <div className="em-card" style={{ padding: 0 }}>
        <div className="p-3 flex align-items-center justify-content-between">
          <h4 className="m-0">Unmatched Data</h4>
          <div className="flex align-items-center gap-2">
            <Tag value={`${companySelection.length} company`} />
            <Tag value={`${vendorSelection.length} party`} severity="warning" />
          </div>
        </div>
        <DataTable
          value={allRows}
          selection={selection}
          onSelectionChange={(e) => setSelection(e.value as UnmatchedRow[])}
          dataKey="id"
          size="small"
          scrollable
          scrollHeight="560px"
          paginator
          rows={100}
          rowsPerPageOptions={[25, 50, 100, 200]}
          emptyMessage="No unmatched entries"
        >
          <Column selectionMode="multiple" headerStyle={{ width: '3rem' }} frozen />
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
              style={{ minWidth: '9rem', whiteSpace: 'nowrap', textAlign: c.field === 'amount' || c.field === 'amount_in_doc_curr' ? 'right' : 'left' }}
            />
          ))}
        </DataTable>
      </div>
    </div>
  );
};
