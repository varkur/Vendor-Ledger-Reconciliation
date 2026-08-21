/**
 * Mapping Form Page — Full-page wrapper around MappingFormContent.
 * Used when the user clicks "Map" from the case summary (ColumnMappingPage).
 */

import { useParams, useNavigate } from 'react-router-dom';
import { Button } from 'primereact/button';
import { MappingFormContent } from '../components/MappingFormContent';

export const MappingFormPage = () => {
  const { requestId, caseId, side } = useParams<{ requestId: string; caseId: string; side: string }>();
  const navigate = useNavigate();

  const sideLabel = side === 'company' ? 'Company Ledger Statement' : 'Party Ledger Statement';

  const goToCase = () => navigate(`/track-reconciliation/${requestId}/${caseId}`);

  return (
    <div>
      {/* Header */}
      <div className="flex align-items-center gap-3 mb-4">
        <Button
          icon="pi pi-arrow-left"
          className="p-button-text"
          onClick={goToCase}
        />
        <h2 className="m-0">{sideLabel}</h2>
      </div>

      {caseId && side === 'company' && (
        <MappingFormContent caseId={caseId} side="company" onSubmitted={goToCase} />
      )}
      {caseId && side === 'vendor' && (
        <MappingFormContent caseId={caseId} side="vendor" onSubmitted={goToCase} />
      )}
    </div>
  );
};
