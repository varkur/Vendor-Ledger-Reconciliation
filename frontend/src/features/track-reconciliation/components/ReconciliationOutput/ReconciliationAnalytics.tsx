/**
 * ReconciliationAnalytics — the summary landing table (Particulars roll-up).
 * Shows Matched / Unmatched / Recommended Matched / Amount Mismatch / Total
 * with per-side counts and percentages. Each row's "View" opens the relevant
 * output tab.
 */

import { useQuery } from '@tanstack/react-query';
import { Column } from 'primereact/column';
import { DataTable } from 'primereact/datatable';
import { ProgressSpinner } from 'primereact/progressspinner';
import { Message } from 'primereact/message';
import { apiClient } from '@shared/services/apiClient';

interface AnalyticsRow {
  particulars: string;
  company_numbers: number;
  company_percentage: number;
  party_numbers: number;
  party_percentage: number;
  view_tab: string | null;
  _isTotal?: boolean;
}

interface AnalyticsResponse {
  rows: AnalyticsRow[];
  total_company: number;
  total_party: number;
}

interface Props {
  caseId: string;
  /** Called with the tab key ('matched' | 'unmatched') when a row's View is clicked. */
  onView: (tab: string) => void;
}

export const ReconciliationAnalytics = ({ caseId, onView }: Props) => {
  const { data, isLoading, isError, error } = useQuery<AnalyticsResponse, Error>({
    queryKey: ['reco-analytics', caseId],
    queryFn: async () => {
      const { data } = await apiClient.get(`/vlr/reconciliation/${caseId}/analytics`);
      return data as AnalyticsResponse;
    },
    enabled: !!caseId,
  });

  if (isLoading) {
    return (
      <div className="flex justify-content-center align-items-center" style={{ minHeight: 200 }}>
        <ProgressSpinner style={{ width: 40, height: 40 }} />
      </div>
    );
  }
  if (isError) {
    return <Message severity="error" text={error?.message || 'Failed to load analytics.'} />;
  }

  const rows: AnalyticsRow[] = [
    ...(data?.rows ?? []),
    {
      particulars: 'Total',
      company_numbers: data?.total_company ?? 0,
      company_percentage: 100,
      party_numbers: data?.total_party ?? 0,
      party_percentage: 100,
      view_tab: null,
      _isTotal: true,
    },
  ];

  const numFmt = (n: number) => (n ?? 0).toLocaleString('en-IN');
  const pctFmt = (n: number) => `${Math.round(n ?? 0)}`;

  const rowClass = (row: AnalyticsRow) =>
    row._isTotal ? { 'font-bold': true } : {};

  return (
    <div className="em-card" style={{ padding: 0 }}>
      <div className="p-3">
        <h4 className="m-0">Reconciliation Analytics</h4>
      </div>
      <DataTable
        value={rows}
        rowClassName={rowClass as any}
        size="small"
        stripedRows
        aria-label="Reconciliation analytics"
      >
        <Column field="particulars" header="Particulars" style={{ minWidth: '14rem' }} />
        <Column header="Company Numbers" body={(r: AnalyticsRow) => numFmt(r.company_numbers)} style={{ textAlign: 'right' }} />
        <Column header="Company Percentage" body={(r: AnalyticsRow) => pctFmt(r.company_percentage)} style={{ textAlign: 'right' }} />
        <Column header="Party Numbers" body={(r: AnalyticsRow) => numFmt(r.party_numbers)} style={{ textAlign: 'right' }} />
        <Column header="Party Percentage" body={(r: AnalyticsRow) => pctFmt(r.party_percentage)} style={{ textAlign: 'right' }} />
        <Column
          header="Action"
          style={{ width: '8rem', textAlign: 'center' }}
          body={(r: AnalyticsRow) =>
            r.view_tab ? (
              <span
                className="link-view"
                style={{ color: 'var(--color-primary)', cursor: 'pointer', textDecoration: 'underline' }}
                onClick={() => onView(r.view_tab as string)}
              >
                View
              </span>
            ) : null
          }
        />
      </DataTable>
    </div>
  );
};
