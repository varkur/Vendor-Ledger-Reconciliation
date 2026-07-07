/**
 * VLR Vendor API module.
 * All functions use the shared apiClient (base URL: /api/v1).
 */

import { apiClient } from '@shared/services/apiClient';

export interface VendorListParams {
  company_code: string;
  page?: number;
  page_size?: number;
  search?: string;
  status?: string;
}

export interface VendorContactResponse {
  id: string;
  name: string;
  email: string;
  phone?: string;
  designation?: string;
  is_primary?: boolean;
  source?: string;
}

export interface VendorResponse {
  id: string;
  vendor_code: string;
  company_code: string;
  name: string;
  pan?: string | null;
  gstin?: string | null;
  city?: string | null;
  status: string;
  is_deleted: boolean;
  created_date?: string;
  modified_date?: string;
  contacts: VendorContactResponse[];
}

export interface VendorListResponse {
  items: VendorResponse[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface VendorContact {
  name: string;
  email: string;
  phone?: string;
}

export interface CreateVendorData {
  vendor_code: string;
  company_code: string;
  name: string;
  pan?: string;
  gstin?: string;
  city?: string;
  status?: string;
  contacts: VendorContact[];
}

export interface UpdateVendorData {
  name?: string;
  pan?: string | null;
  gstin?: string | null;
  city?: string | null;
  status?: string;
  contacts?: VendorContact[];
}

export interface BulkImportResponse {
  imported: number;
  errors: number;
  details?: string[];
}

/**
 * Fetch paginated vendor list with optional filters.
 */
export const getVendors = async (params: VendorListParams): Promise<VendorListResponse> => {
  const { data } = await apiClient.get('/vlr/vendors', { params });
  return data;
};

/**
 * Fetch a single vendor by ID.
 */
export const getVendor = async (id: string, companyCode: string): Promise<VendorResponse> => {
  const { data } = await apiClient.get(`/vlr/vendors/${id}`, {
    params: { company_code: companyCode },
  });
  return data;
};

/**
 * Create a new vendor.
 */
export const createVendor = async (vendorData: CreateVendorData): Promise<VendorResponse> => {
  const { data } = await apiClient.post('/vlr/vendors', vendorData);
  return data;
};

/**
 * Update an existing vendor.
 */
export const updateVendor = async (
  id: string,
  vendorData: UpdateVendorData,
  companyCode: string
): Promise<VendorResponse> => {
  const { data } = await apiClient.put(`/vlr/vendors/${id}`, vendorData, {
    params: { company_code: companyCode },
  });
  return data;
};

/**
 * Delete a vendor.
 */
export const deleteVendor = async (id: string, companyCode: string): Promise<void> => {
  await apiClient.delete(`/vlr/vendors/${id}`, {
    params: { company_code: companyCode },
  });
};

/**
 * Bulk import vendors from a file (CSV/Excel).
 */
export const bulkImportVendors = async (
  file: File,
  companyCode: string
): Promise<BulkImportResponse> => {
  const formData = new FormData();
  formData.append('file', file);

  const { data } = await apiClient.post('/vlr/vendors/bulk-import', formData, {
    params: { company_code: companyCode },
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return data;
};

/**
 * Export vendors in specified format (csv, excel).
 * Returns blob data for file download.
 */
export const exportVendors = async (
  companyCode: string,
  format: 'csv' | 'excel' = 'excel'
): Promise<Blob> => {
  const { data } = await apiClient.get('/vlr/vendors/export', {
    params: { company_code: companyCode, format },
    responseType: 'blob',
  });
  return data;
};
