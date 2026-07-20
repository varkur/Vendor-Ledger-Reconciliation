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
import { manualLink } from '../components/ReconciliationOutput/reconciliationOutputApi';

interface UnmatchedRow {
  id: string;
  document_number: string;
  reference: string;
  amount: number;
  posting_date: string;
  document_type: string;
  description?: string;
}

function normalizeRows(raw: any): UnmatchedRow[] {
  return (raw?.items ?? []).map((it: any) => ({
    id: it.entry_id ?? it.id,
    document_number: it.document_number ?? '',
    reference: it.reference_number ?? it.document_number ?? '',
    amount: Number(it.amount ?? 0),
    posting_date: it.posting_date ?? '',
    document_type: it.document_category ?? it.document_type ?? '',
    description: it.description ?? '',
  }));
}

export const LinkUnmatchedPage = () => {
  const { requestId, caseId } = useParams<{ requestId: string; caseId: string }>();
  const navigate = useNavigate();
  const toast = useRef<Toast>(null);
  const queryClient = useQueryClient();
  const { companyCode } = useSelectedEntity();

  const [companySelection, setCompanySelection] = useState<UnmatchedRow[]>([]);
  const [vendorSelection, setVendorSelection] = useState<UnmatchedRow[]>([]);
  const [isLinking, setIsLinking] = useState(false);

  const { data: companyData, isLoading: companyLoading, refetch: refetchCompany } = useQuery({
    queryKey: ['unmatched-company-link', caseId],
    queryFn: async () => {
      const { data } = await apiClient.get(`/vlr/reconciliation/${caseId}/unmatched-company`, {
        params: { page: 1, page_size: 100 },
      });
      return normalizeRows(data);
    },
    enabled: !!caseId,
  });

  const { data: vendorData, isLoading: vendorLoading, refetch: refetchVendor } = useQuery({
    queryKey: ['unmatched-vendor-link', caseId],
    queryFn: async () => {
      const { data } = await apiClient.get(`/vlr/reconciliation/${caseId}/unmatched-vendor`, {
        params: { page: 1, page_size: 100 },
      });
      return normalizeRows(data);
    },
    enabled: !!caseId,
  });

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
    if (companySelection.length === 0 && vendorSelection.length === 0) {
      toast.current?.show({ severity: 'warn', summary: 'Nothing selected', detail: 'Select entries on at least one side to link.', life: 4000 });
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
      setCompanySelection([]);
      setVendorSelection([]);
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

  const amountBody = (r: UnmatchedRow) => (
    <span className={r.amount < 0 ? 'text-red-500' : ''}>
      {r.amount.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
    </span>
  );

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

      {Math.abs(netDiff) >= 0.01 && (companySelection.length > 0 || vendorSelection.length > 0) && (
        <Message
          severity="warn"
          className="w-full mb-3"
          text={`Selected entries have a net difference of ${fmt(netDiff)}. You can still link them (the difference will be recorded), or adjust your selection to balance.`}
        />
      )}

      <div className="grid">
        {/* Company (Source 1) */}
        <div className="col-12 md:col-6">
          <div className="em-card" style={{ padding: 0, borderTop: '3px solid #10b981' }}>
            <div className="p-3 flex align-items-center justify-content-between">
              <h4 className="m-0">Company Ledger (Source 1)</h4>
              <Tag value={`${companySelection.length} selected`} />
            </div>
            <DataTable
              value={companyData ?? []}
              selection={companySelection}
              onSelectionChange={(e) => setCompanySelection(e.value as UnmatchedRow[])}
              dataKey="id"
              size="small"
              scrollable
              scrollHeight="440px"
              paginator
              rows={25}
              emptyMessage="No unmatched company entries"
            >
              <Column selectionMode="multiple" headerStyle={{ width: '3rem' }} />
              <Column field="document_number" header="Doc No" />
              <Column field="posting_date" header="Date" />
              <Column field="document_type" header="Type" />
              <Column field="amount" header="Amount" body={amountBody} style={{ textAlign: 'right' }} />
            </DataTable>
          </div>
        </div>

        {/* Vendor (Source 2) */}
        <div className="col-12 md:col-6">
          <div className="em-card" style={{ padding: 0, borderTop: '3px solid #f59e0b' }}>
            <div className="p-3 flex align-items-center justify-content-between">
              <h4 className="m-0">Party Ledger (Source 2)</h4>
              <Tag value={`${vendorSelection.length} selected`} severity="warning" />
            </div>
            <DataTable
              value={vendorData ?? []}
              selection={vendorSelection}
              onSelectionChange={(e) => setVendorSelection(e.value as UnmatchedRow[])}
              dataKey="id"
              size="small"
              scrollable
              scrollHeight="440px"
              paginator
              rows={25}
              emptyMessage="No unmatched vendor entries"
            >
              <Column selectionMode="multiple" headerStyle={{ width: '3rem' }} />
              <Column field="document_number" header="Doc No" />
              <Column field="posting_date" header="Date" />
              <Column field="document_type" header="Type" />
              <Column field="amount" header="Amount" body={amountBody} style={{ textAlign: 'right' }} />
            </DataTable>
          </div>
        </div>
      </div>
    </div>
  );
};
