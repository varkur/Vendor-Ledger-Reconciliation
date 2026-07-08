/**
 * Unit tests for Direct Reconciliation API layer.
 *
 * Validates type contracts and API function signatures.
 * Requirements: 23.1, 25.1, 25.2
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

// Mock the apiClient module
vi.mock('@shared/services/apiClient', () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
  },
}));

import { apiClient } from '@shared/services/apiClient';
import {
  listReconciliationRequests,
  createReconciliationRequest,
  getReconciliationRequest,
  type ListRequestsParams,
  type CreateReconciliationRequest,
  type ReconciliationRequestListResponse,
  type ReconciliationRequestResponse,
} from './directReconciliationApi';

const mockedApiClient = vi.mocked(apiClient);

describe('directReconciliationApi', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('listReconciliationRequests', () => {
    it('calls GET /vlr/requests with correct params', async () => {
      const mockResponse: ReconciliationRequestListResponse = {
        items: [],
        total: 0,
        page: 1,
        page_size: 10,
        total_pages: 0,
      };

      mockedApiClient.get.mockResolvedValue({ data: mockResponse });

      const params: ListRequestsParams = {
        company_code: '1000',
        page: 1,
        page_size: 10,
      };

      const result = await listReconciliationRequests(params);

      expect(mockedApiClient.get).toHaveBeenCalledWith('/vlr/requests', {
        params,
      });
      expect(result).toEqual(mockResponse);
    });

    it('passes optional filter params when provided', async () => {
      const mockResponse: ReconciliationRequestListResponse = {
        items: [],
        total: 0,
        page: 1,
        page_size: 25,
        total_pages: 0,
      };

      mockedApiClient.get.mockResolvedValue({ data: mockResponse });

      const params: ListRequestsParams = {
        company_code: '1000',
        status: 'open',
        fiscal_year: '2024-25',
        page: 2,
        page_size: 25,
      };

      await listReconciliationRequests(params);

      expect(mockedApiClient.get).toHaveBeenCalledWith('/vlr/requests', {
        params,
      });
    });
  });

  describe('createReconciliationRequest', () => {
    it('calls POST /vlr/requests with request body', async () => {
      const mockCreatedRequest: ReconciliationRequestResponse = {
        id: '123e4567-e89b-12d3-a456-426614174000',
        company_code: '1000',
        fiscal_year: '2024-25',
        period_start: '2024-04-01',
        period_end: '2025-03-31',
        status: 'initiation',
        tolerance_amount: null,
        tds_percentage: null,
        gst_percentage: null,
        matching_preferences: null,
        assigned_manager_id: null,
        created_by: 'user1',
        created_date: '2024-07-01T00:00:00Z',
      };

      mockedApiClient.post.mockResolvedValue({ data: mockCreatedRequest });

      const createData: CreateReconciliationRequest = {
        company_code: '1000',
        fiscal_year: '2024-25',
        period_start: '2024-04-01',
        period_end: '2025-03-31',
        vendor_ids: ['vendor-id-1'],
      };

      const result = await createReconciliationRequest(createData);

      expect(mockedApiClient.post).toHaveBeenCalledWith(
        '/vlr/requests',
        createData
      );
      expect(result).toEqual(mockCreatedRequest);
    });
  });

  describe('getReconciliationRequest', () => {
    it('calls GET /vlr/requests/{id} with company_code param', async () => {
      const mockRequest: ReconciliationRequestResponse = {
        id: '123e4567-e89b-12d3-a456-426614174000',
        company_code: '1000',
        fiscal_year: '2024-25',
        period_start: '2024-04-01',
        period_end: '2025-03-31',
        status: 'initiation',
        tolerance_amount: null,
        tds_percentage: null,
        gst_percentage: null,
        matching_preferences: null,
        assigned_manager_id: null,
        created_by: 'user1',
        created_date: '2024-07-01T00:00:00Z',
      };

      mockedApiClient.get.mockResolvedValue({ data: mockRequest });

      const result = await getReconciliationRequest(
        '123e4567-e89b-12d3-a456-426614174000',
        '1000'
      );

      expect(mockedApiClient.get).toHaveBeenCalledWith(
        '/vlr/requests/123e4567-e89b-12d3-a456-426614174000',
        { params: { company_code: '1000' } }
      );
      expect(result).toEqual(mockRequest);
    });
  });
});
