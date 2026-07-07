/**
 * TanStack Query hooks for vendor management.
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  getVendors,
  getVendor,
  createVendor,
  updateVendor,
  deleteVendor,
  bulkImportVendors,
  exportVendors,
  VendorListParams,
  CreateVendorData,
  UpdateVendorData,
} from '../api/vendorApi';

const VENDORS_QUERY_KEY = 'vendors';

/**
 * Fetch paginated vendor list.
 */
export const useVendors = (
  companyCode: string,
  filters?: { search?: string; status?: string },
  page = 1,
  pageSize = 10
) => {
  const params: VendorListParams = {
    company_code: companyCode,
    page,
    page_size: pageSize,
    ...filters,
  };

  return useQuery({
    queryKey: [VENDORS_QUERY_KEY, companyCode, filters, page, pageSize],
    queryFn: () => getVendors(params),
    enabled: !!companyCode,
  });
};

/**
 * Fetch a single vendor by ID.
 */
export const useVendor = (id: string | undefined, companyCode: string) => {
  return useQuery({
    queryKey: [VENDORS_QUERY_KEY, id, companyCode],
    queryFn: () => getVendor(id!, companyCode),
    enabled: !!id && !!companyCode,
  });
};

/**
 * Create a new vendor mutation.
 */
export const useCreateVendor = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: CreateVendorData) => createVendor(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: [VENDORS_QUERY_KEY] });
    },
  });
};

/**
 * Update vendor mutation.
 */
export const useUpdateVendor = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      id,
      data,
      companyCode,
    }: {
      id: string;
      data: UpdateVendorData;
      companyCode: string;
    }) => updateVendor(id, data, companyCode),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: [VENDORS_QUERY_KEY] });
    },
  });
};

/**
 * Delete vendor mutation.
 */
export const useDeleteVendor = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ id, companyCode }: { id: string; companyCode: string }) =>
      deleteVendor(id, companyCode),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: [VENDORS_QUERY_KEY] });
    },
  });
};

/**
 * Bulk import vendors mutation.
 */
export const useBulkImportVendors = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ file, companyCode }: { file: File; companyCode: string }) =>
      bulkImportVendors(file, companyCode),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: [VENDORS_QUERY_KEY] });
    },
  });
};

/**
 * Export vendors — returns a trigger function that downloads the file.
 */
export const useExportVendors = () => {
  const triggerExport = async (companyCode: string, format: 'csv' | 'excel' = 'excel') => {
    const blob = await exportVendors(companyCode, format);
    const ext = format === 'excel' ? 'xlsx' : 'csv';
    const url = window.URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `vendors_export.${ext}`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    window.URL.revokeObjectURL(url);
  };

  return { triggerExport };
};
