/**
 * TanStack Query hooks for user management.
 * Server state managed here (not Redux).
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { userApi } from '../api/userApi';
import type { CreateUserRequest, UpdateUserRequest } from '../models/User';

const USERS_QUERY_KEY = ['users'];

export const useUsers = (skip = 0, limit = 100) => {
  return useQuery({
    queryKey: [...USERS_QUERY_KEY, skip, limit],
    queryFn: () => userApi.listUsers(skip, limit),
    staleTime: 30_000, // 30 seconds
  });
};

export const useUser = (userId: string) => {
  return useQuery({
    queryKey: ['user', userId],
    queryFn: () => userApi.getUserById(userId),
    enabled: !!userId,
    staleTime: 60_000,
  });
};

export const useCreateUser = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (request: CreateUserRequest) => userApi.createUser(request),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: USERS_QUERY_KEY });
    },
  });
};

export const useUpdateUser = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ userId, request }: { userId: string; request: UpdateUserRequest }) =>
      userApi.updateUser(userId, request),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: USERS_QUERY_KEY });
    },
  });
};

export const useImportEmployees = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (employeeIds: string[]) => userApi.importEmployees(employeeIds),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: USERS_QUERY_KEY });
    },
  });
};
