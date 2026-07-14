/**
 * Hook to access the currently selected entity/company.
 * Returns the selected entity and its company_code.
 * Pages should use this instead of hardcoding DEFAULT_COMPANY_CODE.
 */

import { useAppSelector } from '@app/store';

export function useSelectedEntity() {
  const { selectedEntity, entities, isLoading } = useAppSelector((state) => state.entity);

  return {
    selectedEntity,
    entities,
    isLoading,
    companyCode: selectedEntity?.company_code ?? '',
    entityName: selectedEntity?.name ?? '',
  };
}
