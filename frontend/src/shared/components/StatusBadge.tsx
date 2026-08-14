/**
 * StatusBadge — Reusable status indicator for reconciliation case lifecycle stages.
 *
 * Uses PrimeReact Tag component with consistent color mapping from CSS variables.
 * Supports all lifecycle stages: Requested, Received, Reconciling, In Review,
 * Awaiting Sign-Off, Signed Off, Pending Approval, Approved, Closed, Disputed, Overdue.
 *
 * Requirements: 22, 23
 */

import { Tag } from 'primereact/tag';

/**
 * All known reconciliation case status values (API values use snake_case).
 */
export type CaseStatus =
  | 'requested'
  | 'data_received'
  | 'reconciling'
  | 'in_review'
  | 'awaiting_signoff'
  | 'signed_off'
  | 'pending_approval'
  | 'approved'
  | 'closed'
  | 'disputed'
  | 'overdue';

interface StatusConfig {
  label: string;
  severity: 'success' | 'info' | 'warning' | 'danger' | null;
  style?: React.CSSProperties;
}

/**
 * Maps each status to a display label, PrimeReact Tag severity, and optional custom style.
 *
 * Color mapping using existing CSS variables:
 * - success (green / --color-success): Approved, Signed Off, Closed
 * - info (blue / --color-info): Requested, Data Received, In Review
 * - warning (orange / --color-warning): Awaiting Sign-Off, Pending Approval, Reconciling
 * - danger (red / --color-error): Disputed, Overdue
 */
const STATUS_CONFIG: Record<string, StatusConfig> = {
  created: {
    label: 'Initiated',
    severity: 'info',
  },
  requested: {
    label: 'Requested',
    severity: 'info',
  },
  data_received: {
    label: 'Received',
    severity: 'info',
  },
  reconciling: {
    label: 'Reconciling',
    severity: 'warning',
  },
  in_review: {
    label: 'In Review',
    severity: 'info',
    style: { background: 'var(--color-info)', color: '#fff' },
  },
  awaiting_signoff: {
    label: 'Awaiting Sign-Off',
    severity: 'warning',
  },
  signed_off: {
    label: 'Signed Off',
    severity: 'success',
  },
  pending_approval: {
    label: 'Pending Approval',
    severity: 'warning',
    style: { background: 'var(--color-warning)', color: '#fff' },
  },
  approved: {
    label: 'Approved',
    severity: 'success',
  },
  closed: {
    label: 'Closed',
    severity: 'success',
    style: { background: 'var(--color-success)', color: '#fff' },
  },
  disputed: {
    label: 'Disputed',
    severity: 'danger',
  },
  overdue: {
    label: 'Overdue',
    severity: 'danger',
    style: { background: 'var(--color-error)', color: '#fff' },
  },
};

interface StatusBadgeProps {
  /** The case status value (API snake_case format). */
  status: string;
  /** Optional className for additional styling. */
  className?: string;
}

/**
 * Normalizes a status string to a known key by converting to lowercase
 * and replacing spaces/hyphens with underscores.
 */
function normalizeStatus(status: string): string {
  return status.toLowerCase().replace(/[\s-]+/g, '_');
}

/**
 * StatusBadge component — renders a PrimeReact Tag with consistent color coding
 * for each reconciliation lifecycle stage.
 */
export const StatusBadge = ({ status, className }: StatusBadgeProps) => {
  const normalized = normalizeStatus(status);
  const config = STATUS_CONFIG[normalized];

  if (!config) {
    // Fallback for unknown status values — render plain text with neutral styling
    return (
      <Tag
        value={status}
        severity={null}
        className={className}
        style={{ background: 'var(--color-surface-border)', color: 'var(--color-text-primary)' }}
      />
    );
  }

  return (
    <Tag
      value={config.label}
      severity={config.severity}
      className={className}
      style={config.style}
    />
  );
};
