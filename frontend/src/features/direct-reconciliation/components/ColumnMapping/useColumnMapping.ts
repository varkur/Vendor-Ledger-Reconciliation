/**
 * React Query hooks for column mapping API operations.
 *
 * Requirements: 9.1, 9.2, 9.3, 10.1, 10.2, 10.3, 11.1, 11.2, 11.3, 11.4
 */

import { useMutation, useQuery } from '@tanstack/react-query';

import {
  autoMapColumns,
  getTemplate,
  previewFile,
  saveTemplate,
  type AutoMapResponse,
  type FilePreviewResponse,
  type SaveTemplateRequest,
  type SaveTemplateResponse,
  type TemplateResponse,
} from './columnMappingApi';

/**
 * Mutation hook to upload a file and get a 10-row preview.
 */
export function usePreviewFile() {
  return useMutation<FilePreviewResponse, Error, File>({
    mutationFn: (file: File) => previewFile(file),
  });
}

/**
 * Mutation hook to get auto-mapping suggestions for column headers.
 */
export function useAutoMap() {
  return useMutation<AutoMapResponse, Error, string[]>({
    mutationFn: (headers: string[]) => autoMapColumns(headers),
  });
}

/**
 * Mutation hook to save a column mapping template for a vendor.
 */
export function useSaveTemplate() {
  return useMutation<SaveTemplateResponse, Error, SaveTemplateRequest>({
    mutationFn: (request: SaveTemplateRequest) => saveTemplate(request),
  });
}

/**
 * Query hook to retrieve a saved column mapping template for a vendor.
 * Only fetches when vendorId is provided and non-empty.
 */
export function useGetTemplate(vendorId: string | undefined) {
  return useQuery<TemplateResponse, Error>({
    queryKey: ['vlr', 'column-mapping', 'template', vendorId],
    queryFn: () => getTemplate(vendorId!),
    enabled: !!vendorId,
    retry: 1,
  });
}
