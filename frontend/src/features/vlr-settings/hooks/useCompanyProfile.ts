/**
 * React Query hooks for Company Profile.
 * Uses the selected entity's company_code to scope data.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  getCompanyProfile,
  updateCompanyProfile,
  type CompanyProfile,
  type CompanyProfileUpdateRequest,
} from '../api/companyProfileApi';
import { useSelectedEntity } from '@shared/hooks/useSelectedEntity';

export const COMPANY_PROFILE_QUERY_KEY = 'company-profile';

/**
 * Hook to load company profile for the currently selected entity.
 */
export function useCompanyProfile() {
  const { companyCode } = useSelectedEntity();

  return useQuery<CompanyProfile, Error>({
    queryKey: [COMPANY_PROFILE_QUERY_KEY, companyCode],
    queryFn: () => getCompanyProfile(companyCode),
    enabled: !!companyCode,
    retry: 2,
    staleTime: 5 * 60 * 1000,
  });
}

/**
 * Mutation hook to update company profile.
 */
export function useUpdateCompanyProfile() {
  const queryClient = useQueryClient();
  const { companyCode } = useSelectedEntity();

  return useMutation<CompanyProfile, Error, CompanyProfileUpdateRequest>({
    mutationFn: (data) => updateCompanyProfile(data, companyCode),
    onSuccess: (data) => {
      queryClient.setQueryData([COMPANY_PROFILE_QUERY_KEY, companyCode], data);
    },
  });
}
