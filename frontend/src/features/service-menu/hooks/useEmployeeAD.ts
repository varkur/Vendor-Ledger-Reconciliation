/**
 * TanStack Query hooks for Employee AD Service operations.
 */

import { useQuery, useMutation } from '@tanstack/react-query';
import {
  employeeAdApi,
  type ValidateCredentialsRequest,
} from '../api/employeeAdApi';

export const useEmployeeADHealth = () => {
  return useQuery({
    queryKey: ['employee-ad', 'health'],
    queryFn: () => employeeAdApi.healthCheck(),
    staleTime: 10_000,
    retry: 1,
  });
};

export const useValidateCredentials = () => {
  return useMutation({
    mutationFn: (request: ValidateCredentialsRequest) =>
      employeeAdApi.validateCredentials(request),
  });
};

export const useGetSelectedEmployees = () => {
  return useMutation({
    mutationFn: (employeeIds: string[]) =>
      employeeAdApi.getSelectedEmployees(employeeIds),
  });
};

export const useGetEmployees = () => {
  return useMutation({
    mutationFn: () => employeeAdApi.getEmployees(),
  });
};

export const useGetHierarchy = () => {
  return useMutation({
    mutationFn: () => employeeAdApi.getHierarchy(),
  });
};
