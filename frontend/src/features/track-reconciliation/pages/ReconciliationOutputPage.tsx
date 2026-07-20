/**
 * ReconciliationOutputPage — Renders the 5-tab reconciliation output panel
 * for a specific case within a reconciliation request.
 *
 * Route: /track-reconciliation/:requestId/case/:caseId
 * Requirements: 3
 */

import { useRef, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Button } from 'primereact/button';
import { Toast } from 'primereact/toast';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '@shared/services/apiClient';
import { useSelectedEntity } from '@shared/hooks/useSelectedEntity';
import { ReconciliationOutputPanel } from '../components/ReconciliationOutput';

export const ReconciliationOutputPage = () => {
  const { requestId, caseId } = useParams<{ requestId: string; caseId: string }>();
  const navigate = useNavigate();
  const { companyCode } = useSelectedEntity();
  const toast = useRef<Toast>(null);
  const queryClient = useQueryClient();
  const [isActing, setIsActing] = useState(false);

  // Fetch case status to gate reviewer-only actions
  const { data: caseData } = useQuery({
    queryKey: ['case-status', caseId],
    queryFn: async () => {
      const { data } = await apiClient.get(`/vlr/cases/${caseId}`, {
        params: { company_code: companyCode },
      });
      return data;
    },
    enabled: !!caseId && !!companyCode,
  });

  const caseStatus = (caseData as any)?.status || '';
  const isUnderReview = caseStatus === 'review_pending';
  const isReviewed = caseStatus === 'reviewed';

  const handleReviewDone = async () => {
    setIsActing(true);
    try {
      await apiClient.post('/vlr/cases/bulk-review-done', {
        company_code: companyCode,
        case_ids: [caseId],
      });
      toast.current?.show({ severity: 'success', summary: 'Review Completed', detail: 'Case marked as reviewed.', life: 4000 });
      queryClient.invalidateQueries({ queryKey: ['case-status', caseId] });
    } catch (error: any) {
      toast.current?.show({ severity: 'error', summary: 'Failed', detail: error.response?.data?.detail || 'Failed to complete review.', life: 6000 });
    } finally {
      setIsActing(false);
    }
  };

  const handleRequestSignoff = async () => {
    setIsActing(true);
    try {
      await apiClient.post('/vlr/cases/bulk-signoff-request', {
        company_code: companyCode,
        case_ids: [caseId],
      });
      toast.current?.show({ severity: 'success', summary: 'Sign-off Requested', detail: 'Sign-off has been requested.', life: 4000 });
      queryClient.invalidateQueries({ queryKey: ['case-status', caseId] });
      // Invalidate the batch-cases list so the Sign Off Stage tab refetches
      queryClient.invalidateQueries({ queryKey: ['vlr-reconciliation-detail'] });
      queryClient.invalidateQueries({ queryKey: ['vlr-request-statistics'] });
      setTimeout(() => navigate(`/track-reconciliation/${requestId}?tab=signOffStage`), 1200);
    } catch (error: any) {
      toast.current?.show({ severity: 'error', summary: 'Failed', detail: error.response?.data?.detail || 'Failed to request sign-off.', life: 6000 });
    } finally {
      setIsActing(false);
    }
  };

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

      {/* Back button + Link Unmatched action */}
      <div className="mb-3 flex align-items-center justify-content-between">
        <Button
          icon="pi pi-arrow-left"
          label="Back to Cases"
          className="p-button-text p-button-sm"
          onClick={() => navigate(`/track-reconciliation/${requestId}`)}
        />
        <div className="flex align-items-center gap-2">
          {isUnderReview && (
            <>
              <Button
                icon="pi pi-link"
                label="Link Unmatched"
                className="p-button-sm p-button-outlined"
                onClick={() => navigate(`/track-reconciliation/${requestId}/case/${caseId}/link`)}
              />
              <Button
                icon="pi pi-check"
                label="Review Completed"
                className="p-button-sm"
                loading={isActing}
                onClick={handleReviewDone}
              />
            </>
          )}
          {isReviewed && (
            <Button
              icon="pi pi-verified"
              label="Request Sign-off"
              className="p-button-sm"
              loading={isActing}
              onClick={handleRequestSignoff}
            />
          )}
        </div>
      </div>

      <Toast ref={toast} />

      {/* Reconciliation Output Panel */}
      <ReconciliationOutputPanel caseId={caseId} editable={isUnderReview} />
    </div>
  );
};
