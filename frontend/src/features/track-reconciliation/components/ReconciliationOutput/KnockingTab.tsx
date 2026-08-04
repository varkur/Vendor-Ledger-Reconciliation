/**
 * KnockingTab — Read-only view of knock-off / reversal (AB) entries.
 *
 * Knock-off entries offset within a single ledger, so they are excluded from
 * the unmatched difference screens. This view lets users inspect them and
 * confirm the residue (sum of all knock-off amounts) nets to zero.
 */

import { DataTable } from 'primereact/datatable';
import { Column } from 'primereact/column';
import { Tag } from 'primereact/tag';
import { ProgressSpinner } from 'primereact/progressspinner';
import { Message } from 'primereact/message';
import { useQuery } from '@tanstack/react-query';

import { apiClient } from '@shared/services/apiClient';
import { LEDGER_COLUMN_DEFS } from './reconciliationOutputApi';
import type { EntryColumns } from './reconciliationOutputApi';

interface KnockRow {
  id: string;
  amount: number;
  columns?: EntryColumns;
}

interface KnockingTabProps {
  caseId: string;
}

const fmt = (n: number) =>
  n.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

export const KnockingTab = ({ caseId }: KnockingTabProps) => {
  const { data, isLoading, error } = useQuery({
    queryKey: ['knocking-entries', caseId],
    queryFn: async () => {
      const { data } = await apiClient.get(`/vlr/reconciliation/${caseId}/knocking`, {
        params: { page: 1, page_size: 1000 },
      });
      return (data?.items ?? []).map((it: any) => ({
        id: it.entry_id ?? it.id,
        amount: Number(it.amount ?? 0),
        columns: it.columns ?? undefined,
      })) as KnockRow[];
    },
    enabled: !!caseId,
  });

  if (isLoading) {
    return (
      <div className="flex justify-content-center align-items-center" style={{ minHeight: 240 }}>
        <ProgressSpinner style={{ width: 44, height: 44 }} />
      </div>
    );
  }

  if (error) {
    return (
      <Message severity="error" className="w-full" text="Failed to load knock-off entries." />
    );
  }

  const rows = data ?? [];
  const residue = rows.reduce((s, r) => s + r.amount, 0);
  const balanced = Math.abs(residue) < 0.01;

  return (
    <div className="em-card" style={{ padding: 0 }}>
      <div className="p-3 flex align-items-center justify-content-between">
        <h4 className="m-0">Knocking Off Entries</h4>
        <div className="flex align-items-center gap-3 text-sm">
          <span className="text-color-secondary">{rows.length} entries</span>
          <span>
            <span className="text-color-secondary">Knocking Residue: </span>
            <span className={`font-bold ${balanced ? 'text-green-600' : 'text-orange-500'}`}>
              {fmt(residue)}
            </span>
          </span>
          <Tag
            value={balanced ? 'Balanced' : 'Residue not zero'}
            severity={balanced ? 'success' : 'warning'}
          />
        </div>
      </div>
      <DataTable
        value={rows}
        dataKey="id"
        size="small"
        scrollable
        scrollHeight="560px"
        paginator
        rows={100}
        rowsPerPageOptions={[25, 50, 100, 200]}
        emptyMessage="No knock-off entries"
      >
        {LEDGER_COLUMN_DEFS.map((c) => (
          <Column
            key={c.field}
            header={c.header}
            body={(row: KnockRow) => {
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
