/**
 * ReconciliationOutputPage — Renders the 5-tab reconciliation output panel
 * for a specific case within a reconciliation request.
 *
 * Route: /track-reconciliation/:requestId/case/:caseId
 * Requirements: 3
 */

import { useParams, useNavigate } from 'react-router-dom';
import { Button } from 'primereact/button';
import { ReconciliationOutputPanel } from '../components/ReconciliationOutput';

export const ReconciliationOutputPage = () => {
  const { requestId, caseId } = useParams<{ requestId: string; caseId: string }>();
  const navigate = useNavigate();

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

      {/* Back button */}
      <div className="mb-3">
        <Button
          icon="pi pi-arrow-left"
          label="Back to Cases"
          className="p-button-text p-button-sm"
          onClick={() => navigate(`/track-reconciliation/${requestId}`)}
        />
      </div>

      {/* Reconciliation Output Panel */}
      <ReconciliationOutputPanel caseId={caseId} />
    </div>
  );
};
