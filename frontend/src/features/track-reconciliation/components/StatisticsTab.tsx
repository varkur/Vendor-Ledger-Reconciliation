/**
 * Statistics Tab — Fetches live data from the backend and renders
 * pie charts for Statement Status and Reconciliation Status,
 * Amount Statistics, Reason for Difference, and Action Summary.
 */

import { ProgressSpinner } from 'primereact/progressspinner';
import { Message } from 'primereact/message';
import { Button } from 'primereact/button';
import { useRequestStatistics } from '../hooks/useReconciliationDetail';
import type {
  StatementStatusCounts,
  ReconciliationStatusCounts,
  AmountCategoryRow,
  AmountEntry,
  ReminderInfo,
} from '../api/reconciliationDetailApi';

interface StatisticsTabProps {
  requestId: string;
}

export const StatisticsTab = ({ requestId }: StatisticsTabProps) => {
  const { data, isLoading, isError, error, refetch } = useRequestStatistics(requestId);

  // ─── Loading State ───────────────────────────────────────────────────────
  if (isLoading) {
    return (
      <div className="flex align-items-center justify-content-center" style={{ padding: '4rem' }}>
        <ProgressSpinner style={{ width: '50px', height: '50px' }} />
      </div>
    );
  }

  // ─── Error State ─────────────────────────────────────────────────────────
  if (isError) {
    return (
      <div className="em-card" style={{ padding: '2rem', textAlign: 'center' }}>
        <Message
          severity="error"
          text={error?.message || 'Failed to load statistics. Please try again.'}
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
  }

  // ─── Empty State ─────────────────────────────────────────────────────────
  if (!data || data.total_cases === 0) {
    return (
      <div className="em-card" style={{ padding: '3rem', textAlign: 'center' }}>
        <i className="pi pi-chart-bar" style={{ fontSize: '2.5rem', color: 'var(--color-text-muted)' }} />
        <p style={{ color: 'var(--color-text-secondary)', marginTop: '1rem' }}>
          No statistics available yet. Cases have not been created for this request.
        </p>
      </div>
    );
  }

  const { statement_status, reconciliation_status, amount_statistics, reason_for_difference, action_summary, reminder_info } = data;

  return (
    <div>
      {/* Reminder Info Bar */}
      <ReminderInfoBar info={reminder_info} />

      {/* Charts Row */}
      <div className="grid mb-4">
        <div className="col-12 md:col-6">
          <StatementStatusCard status={statement_status} />
        </div>
        <div className="col-12 md:col-6">
          <ReconciliationStatusCard status={reconciliation_status} />
        </div>
      </div>

      {/* Amount Statistics */}
      <AmountStatisticsCard rows={amount_statistics} respondedCount={statement_status.responded} total={statement_status.total} />

      {/* Reason for Difference & Action Summary */}
      <div className="grid">
        <div className="col-12 md:col-6">
          <ReasonForDifferenceCard data={reason_for_difference} />
        </div>
        <div className="col-12 md:col-6">
          <ActionSummaryCard data={action_summary} />
        </div>
      </div>
    </div>
  );
};

// ─────────────────────────────────────────────────────────────────────────────
// Sub-components
// ─────────────────────────────────────────────────────────────────────────────

function ReminderInfoBar({ info }: { info: ReminderInfo }) {
  const lastDate = info.last_reminder_date
    ? new Date(info.last_reminder_date).toLocaleString('en-IN', {
        day: '2-digit',
        month: 'short',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
      })
    : 'N/A';

  return (
    <div className="em-info-bar">
      <span>Reminder Info</span>
      <span>
        No of Reminder Sent: {info.reminders_sent}/{info.max_reminders} | Last Reminder date: {lastDate}
      </span>
    </div>
  );
}

function StatementStatusCard({ status }: { status: StatementStatusCounts }) {
  const { total, responded, not_responded, rejected, failed } = status;
  const pct = (v: number) => (total > 0 ? (v / total) * 100 : 0);

  const segments = [
    { color: '#2196F3', value: pct(responded) },
    { color: '#FF9800', value: pct(not_responded) },
    { color: '#F44336', value: pct(rejected) },
    { color: '#9E9E9E', value: pct(failed) },
  ];

  const gradient = buildConicGradient(segments);

  return (
    <div className="em-stat-card">
      <h4 style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        Statement Status
        <i className="pi pi-info-circle" style={{ fontSize: 12, color: 'var(--color-text-muted)' }} />
        <span style={{ marginLeft: 'auto', fontSize: 14, fontWeight: 700 }}>{total}</span>
      </h4>
      <div className="flex align-items-center gap-4">
        <div
          style={{
            width: 140,
            height: 140,
            borderRadius: '50%',
            background: gradient,
            flexShrink: 0,
          }}
        />
        <div className="flex flex-column gap-2">
          <LegendRow color="#2196F3" label="Responded" value={responded} />
          <LegendRow color="#FF9800" label="Not Responded" value={not_responded} />
          <LegendRow color="#F44336" label="Rejected" value={rejected} />
          <LegendRow color="#9E9E9E" label="Failed" value={failed} />
        </div>
      </div>
    </div>
  );
}

function ReconciliationStatusCard({ status }: { status: ReconciliationStatusCounts }) {
  const total =
    status.in_progress +
    status.statement_received +
    status.mapping_pending +
    status.statement_mapped +
    status.auto_completed +
    status.review_pending +
    status.reviewed +
    status.signoff_requested +
    status.signoff_completed +
    status.reco_rejected;

  const pct = (v: number) => (total > 0 ? (v / total) * 100 : 0);

  const items = [
    { color: '#009688', label: 'In Progress', value: status.in_progress },
    { color: '#2196F3', label: 'Statement Received', value: status.statement_received },
    { color: '#FF9800', label: 'Mapping Pending', value: status.mapping_pending },
    { color: '#4CAF50', label: 'Statement Mapped', value: status.statement_mapped },
    { color: '#8BC34A', label: 'Auto Completed', value: status.auto_completed },
    { color: '#E91E63', label: 'Review Pending', value: status.review_pending },
    { color: '#3F51B5', label: 'Reviewed', value: status.reviewed },
    { color: '#FFC107', label: 'Signoff Requested', value: status.signoff_requested },
    { color: '#00BCD4', label: 'Signoff Completed', value: status.signoff_completed },
    { color: '#F44336', label: 'Reco Rejected', value: status.reco_rejected },
  ];

  const segments = items.map((i) => ({ color: i.color, value: pct(i.value) }));
  const gradient = buildConicGradient(segments);

  const leftItems = items.slice(0, 5);
  const rightItems = items.slice(5);

  return (
    <div className="em-stat-card">
      <h4 style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        Reconciliation Status
        <i className="pi pi-info-circle" style={{ fontSize: 12, color: 'var(--color-text-muted)' }} />
        <span style={{ marginLeft: 'auto', fontSize: 14, fontWeight: 700 }}>{total}</span>
      </h4>
      <div className="flex align-items-center gap-4">
        <div
          style={{
            width: 140,
            height: 140,
            borderRadius: '50%',
            background: gradient,
            flexShrink: 0,
          }}
        />
        <div className="grid" style={{ flex: 1 }}>
          <div className="col-6">
            <div className="flex flex-column gap-2">
              {leftItems.map((item) => (
                <LegendRow key={item.label} color={item.color} label={item.label} value={item.value} small />
              ))}
            </div>
          </div>
          <div className="col-6">
            <div className="flex flex-column gap-2">
              {rightItems.map((item) => (
                <LegendRow key={item.label} color={item.color} label={item.label} value={item.value} small />
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function AmountStatisticsCard({
  rows,
  respondedCount,
  total,
}: {
  rows: AmountCategoryRow[];
  respondedCount: number;
  total: number;
}) {
  return (
    <div className="em-stat-card mb-4">
      <h4>Amount Statistics (Amt in Lakhs)</h4>
      <div className="grid align-items-center">
        <div className="col-12 md:col-5">
          {rows.map((row, idx) => {
            const pct = total > 0 ? Math.round((respondedCount / total) * 100) : 0;
            return (
              <div className="mb-3" key={row.category}>
                <div className="flex align-items-center justify-content-between mb-1">
                  <span className="text-sm">
                    {row.category} (INR {formatAmount(row.company_amount_responded)})
                  </span>
                  <span className="text-sm font-semibold">{pct}%</span>
                </div>
                <div className="em-progress-bar" style={idx === 1 ? { background: '#FFFBEB' } : undefined}>
                  <div
                    className={`em-progress-bar-fill ${idx === 0 ? 'primary' : 'warning'}`}
                    style={{ width: `${pct}%` }}
                  />
                </div>
              </div>
            );
          })}
        </div>
        <div className="col-12 md:col-7">
          <table style={{ width: '100%', fontSize: 12, borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ borderBottom: '1px solid var(--color-surface-border)' }}>
                <th style={{ padding: '8px', textAlign: 'left', fontWeight: 600 }}>Category</th>
                <th style={{ padding: '8px', textAlign: 'right', fontWeight: 600 }}>Total Company Amt</th>
                <th style={{ padding: '8px', textAlign: 'right', fontWeight: 600 }}>Company Amt Responded [A]</th>
                <th style={{ padding: '8px', textAlign: 'right', fontWeight: 600 }}>Party Amt Responded [B]</th>
                <th style={{ padding: '8px', textAlign: 'right', fontWeight: 600 }}>Net Difference [C]=[A]+[B]</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.category} style={{ borderBottom: '1px solid var(--color-surface-border)' }}>
                  <td style={{ padding: '8px' }}>{row.category}</td>
                  <td style={{ padding: '8px', textAlign: 'right' }}>{formatAmount(row.total_company_amount)}</td>
                  <td style={{ padding: '8px', textAlign: 'right' }}>{formatAmount(row.company_amount_responded)}</td>
                  <td style={{ padding: '8px', textAlign: 'right' }}>{formatAmount(row.party_amount_responded)}</td>
                  <td style={{ padding: '8px', textAlign: 'right' }}>{formatAmount(row.net_difference)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

function ReasonForDifferenceCard({ data }: { data: Record<string, AmountEntry> }) {
  const entries = Object.entries(data);

  // Fallback labels for known categories
  const labelMap: Record<string, string> = {
    closing_balance_difference: 'Closing Balance Difference',
    payment_not_booked_by_party: 'Payment not booked by Party',
    invoice_not_booked_by_party: 'Invoice not booked by Party',
    invoice_not_booked_by_company: 'Invoice not booked by Company',
    payment_not_booked_by_company: 'Payment not booked by Company',
  };

  return (
    <div className="em-stat-card">
      <div className="flex align-items-center justify-content-between mb-3">
        <h4 style={{ margin: 0 }}>Reason for Difference (Amt in Lakhs)</h4>
        <span className="link-view text-sm">Show All</span>
      </div>
      <table style={{ width: '100%', fontSize: 12, borderCollapse: 'collapse' }}>
        <thead>
          <tr style={{ borderBottom: '1px solid var(--color-surface-border)' }}>
            <th style={{ padding: '8px', textAlign: 'left', fontWeight: 600 }}>Status</th>
            <th style={{ padding: '8px', textAlign: 'right', fontWeight: 600 }}>Difference Amt</th>
            <th style={{ padding: '8px', textAlign: 'right', fontWeight: 600 }}>No. of Entries</th>
          </tr>
        </thead>
        <tbody>
          {entries.length === 0 ? (
            <tr>
              <td colSpan={3} style={{ padding: '16px', textAlign: 'center', color: 'var(--color-text-muted)' }}>
                No differences found
              </td>
            </tr>
          ) : (
            entries.map(([key, entry], idx) => (
              <tr
                key={key}
                style={idx < entries.length - 1 ? { borderBottom: '1px solid var(--color-surface-border)' } : undefined}
              >
                <td style={{ padding: '8px' }}>{labelMap[key] || key}</td>
                <td style={{ padding: '8px', textAlign: 'right' }}>{formatAmount(entry.amount)}</td>
                <td style={{ padding: '8px', textAlign: 'right' }}>{entry.entry_count}</td>
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}

function ActionSummaryCard({ data }: { data: Record<string, AmountEntry> }) {
  const labelMap: Record<string, string> = {
    total_differences: 'Total Differences',
    pending_with_party: 'Pending with Party',
    pending_with_company: 'Pending with Company',
    no_action_required: 'No Action Required',
  };

  const orderedKeys = ['total_differences', 'pending_with_party', 'pending_with_company', 'no_action_required'];
  const entries = orderedKeys
    .filter((k) => k in data)
    .map((k) => [k, data[k]] as [string, AmountEntry]);

  return (
    <div className="em-stat-card">
      <h4>Action Summary (Amt in Lakhs)</h4>
      <table style={{ width: '100%', fontSize: 12, borderCollapse: 'collapse' }}>
        <thead>
          <tr style={{ borderBottom: '1px solid var(--color-surface-border)' }}>
            <th style={{ padding: '8px', textAlign: 'left', fontWeight: 600 }}>Action Taken Status</th>
            <th style={{ padding: '8px', textAlign: 'right', fontWeight: 600 }}>Amt</th>
            <th style={{ padding: '8px', textAlign: 'right', fontWeight: 600 }}>No. of Entries</th>
          </tr>
        </thead>
        <tbody>
          {entries.length === 0 ? (
            <tr>
              <td colSpan={3} style={{ padding: '16px', textAlign: 'center', color: 'var(--color-text-muted)' }}>
                No actions recorded
              </td>
            </tr>
          ) : (
            entries.map(([key, entry], idx) => (
              <tr
                key={key}
                style={idx < entries.length - 1 ? { borderBottom: '1px solid var(--color-surface-border)' } : undefined}
              >
                <td style={{ padding: '8px' }}>{labelMap[key] || key}</td>
                <td style={{ padding: '8px', textAlign: 'right' }}>{formatAmount(entry.amount)}</td>
                <td style={{ padding: '8px', textAlign: 'right' }}>{entry.entry_count}</td>
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Utility components and helpers
// ─────────────────────────────────────────────────────────────────────────────

function LegendRow({
  color,
  label,
  value,
  small,
}: {
  color: string;
  label: string;
  value: number;
  small?: boolean;
}) {
  return (
    <div className={`flex align-items-center gap-2 ${small ? 'text-sm' : ''}`}>
      <span
        style={{
          width: small ? 8 : 10,
          height: small ? 8 : 10,
          borderRadius: '50%',
          background: color,
          flexShrink: 0,
        }}
      />
      <span className={small ? '' : 'text-sm'}>{label}</span>
      <span className="ml-auto font-semibold">{value}</span>
    </div>
  );
}

/** Build a CSS conic-gradient string from value-percentage segments. */
function buildConicGradient(segments: { color: string; value: number }[]): string {
  const filtered = segments.filter((s) => s.value > 0);
  if (filtered.length === 0) return '#e0e0e0';

  let cumulative = 0;
  const stops: string[] = [];
  for (const seg of filtered) {
    const start = cumulative;
    cumulative += seg.value;
    stops.push(`${seg.color} ${start.toFixed(2)}% ${cumulative.toFixed(2)}%`);
  }
  return `conic-gradient(${stops.join(', ')})`;
}

/** Format a number as amount with Indian locale (2 decimal places). */
function formatAmount(value: number): string {
  return value.toLocaleString('en-IN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}
