/**
 * UnmatchedAllTab — Read-only unified view of ALL unmatched entries
 * (company + party) in a single table, distinguished by a Source column.
 *
 * Mirrors the layout of the Link Unmatched page, but without selection or
 * linking — used by the standalone "Unmatched" view page.
 */

import { useMemo } from 'react';
import { DataTable } from 'primereact/datatable';
import { Column } from 'primereact/column';
import { Tag } from 'primereact/tag';
import { ProgressSpinner } from 'primereact/progressspinner';
import { Message } from 'primereact/message';
import { useQuery } from '@tanstack/react-query';

import { apiClient } from '@shared/services/apiClient';
import { LEDGER_COLUMN_DEFS } from './reconciliationOutputApi';
import type { EntryColumns } from './reconciliationOutputApi';

type LedgerSource = 'Company' | 'Party';

interface UnmatchedRow {
  id: string;
  source: LedgerSource;
  columns?: EntryColumns;
}

function normalizeRows(raw: any, source: LedgerSource): UnmatchedRow[] {
  return (raw?.items ?? []).map((it: any) => ({
    id: it.entry_id ?? it.id,
    source,
    columns: it.columns ?? undefined,
  }));
}

interface UnmatchedAllTabProps {
  caseId: string;
}

export const UnmatchedAllTab = ({ caseId }: UnmatchedAllTabProps) => {
  const { data: companyData, isLoading: companyLoading, error: companyError } = useQuery({
    queryKey: ['unmatched-company-all', caseId],
    queryFn: async () => {
      const { data } = await apiClient.get(`/vlr/reconciliation/${caseId}/unmatched-company`, {
        params: { page: 1, page_size: 1000 },
      });
      return normalizeRows(data, 'Company');
    },
    enabled: !!caseId,
  });

  const { data: vendorData, isLoading: vendorLoading, error: vendorError } = useQuery({
    queryKey: ['unmatched-vendor-all', caseId],
    queryFn: async () => {
      const { data } = await apiClient.get(`/vlr/reconciliation/${caseId}/unmatched-vendor`, {
        params: { page: 1, page_size: 1000 },
      });
      return normalizeRows(data, 'Party');
    },
    enabled: !!caseId,
  });

  const allRows = useMemo(
    () => [...(companyData ?? []), ...(vendorData ?? [])],
    [companyData, vendorData]
  );

  const companyCount = companyData?.length ?? 0;
  const partyCount = vendorData?.length ?? 0;

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
    <div className="em-card" style={{ padding: 0 }}>
      <div className="p-3 flex align-items-center justify-content-between">
        <h4 className="m-0">Unmatched Data</h4>
        <div className="flex align-items-center gap-2">
          <Tag value={`${companyCount} company`} />
          <Tag value={`${partyCount} party`} severity="warning" />
        </div>
      </div>
      <DataTable
        value={allRows}
        dataKey="id"
        size="small"
        scrollable
        scrollHeight="600px"
        paginator
        rows={100}
        rowsPerPageOptions={[25, 50, 100, 200]}
        emptyMessage="No unmatched entries"
      >
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
  );
};
