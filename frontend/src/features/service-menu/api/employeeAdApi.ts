/**
 * Employee AD Service API calls.
 * Maps to backend: /api/v1/services/employee-ad/*
 *
 * Darwin endpoints exposed:
 *   GET  /health               - Service reachability check
 *   POST /validate-credentials - Validate AD credentials
 *   POST /selected-employees   - Get employees by IDs
 *   GET  /employees            - Get all employees
 *   GET  /hierarchy            - Get hierarchy data
 */

import { apiClient } from '@shared/services/apiClient';

export interface HealthCheckResponse {
  service: string;
  configured: boolean;
  base_url: string;
  status: string;
  status_code?: number;
  url: string;
  error?: string;
}

export interface ValidateCredentialsRequest {
  employee_id: string;
  password: string;
}

export interface ValidateCredentialsResponse {
  is_success: boolean;
  is_valid_user: boolean;
  raw_response: Record<string, unknown>;
}

export const employeeAdApi = {
  healthCheck: async (): Promise<HealthCheckResponse> => {
    const { data } = await apiClient.get<HealthCheckResponse>(
      '/services/employee-ad/health'
    );
    return data;
  },

  validateCredentials: async (
    request: ValidateCredentialsRequest
  ): Promise<ValidateCredentialsResponse> => {
    const { data } = await apiClient.post<ValidateCredentialsResponse>(
      '/services/employee-ad/validate-credentials',
      request
    );
    return data;
  },

  getSelectedEmployees: async (
    employeeIds: string[]
  ): Promise<Record<string, unknown>> => {
    const { data } = await apiClient.post<Record<string, unknown>>(
      '/services/employee-ad/selected-employees',
      { employee_ids: employeeIds }
    );
    return data;
  },

  getEmployees: async (): Promise<Record<string, unknown>> => {
    const { data } = await apiClient.get<Record<string, unknown>>(
      '/services/employee-ad/employees'
    );
    return data;
  },

  getHierarchy: async (): Promise<Record<string, unknown>> => {
    const { data } = await apiClient.get<Record<string, unknown>>(
      '/services/employee-ad/hierarchy'
    );
    return data;
  },
};
