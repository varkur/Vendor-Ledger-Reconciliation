/**
 * React Query hooks for Notification History page.
 * Provides data fetching with loading/error/retry patterns for:
 * - Listing notifications (paginated)
 * - Marking notifications as read
 * - Sending reminders
 *
 * Requirements: 23.5, 25.1, 25.2
 */

import { useMutation, useQuery, useQueryClient, keepPreviousData } from '@tanstack/react-query';

import {
  listNotifications,
  markNotificationsAsRead,
  sendReminders,
  type NotificationListParams,
  type PaginatedNotificationResponse,
  type MarkReadResponse,
  type SendReminderResponse,
} from '../api/notificationsApi';

/** Query key prefix for notifications. */
export const NOTIFICATIONS_QUERY_KEY = 'vlr-notifications';

/**
 * Hook to list notifications with server-side pagination.
 * Uses keepPreviousData for smooth pagination transitions.
 */
export function useNotificationList(params: NotificationListParams) {
  return useQuery<PaginatedNotificationResponse, Error>({
    queryKey: [NOTIFICATIONS_QUERY_KEY, params],
    queryFn: () => listNotifications(params),
    placeholderData: keepPreviousData,
    retry: 2,
    retryDelay: (attempt) => Math.min(1000 * 2 ** attempt, 10000),
  });
}

/**
 * Mutation hook to mark notifications as read.
 * Invalidates the list query on success.
 */
export function useMarkAsRead() {
  const queryClient = useQueryClient();

  return useMutation<MarkReadResponse, Error, string[]>({
    mutationFn: (notificationIds: string[]) => markNotificationsAsRead(notificationIds),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: [NOTIFICATIONS_QUERY_KEY] });
    },
  });
}

/**
 * Mutation hook to send reminders.
 * Invalidates the list query on success so status updates are visible.
 */
export function useSendReminder() {
  const queryClient = useQueryClient();

  return useMutation<SendReminderResponse, Error, string[]>({
    mutationFn: (notificationIds: string[]) => sendReminders(notificationIds),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: [NOTIFICATIONS_QUERY_KEY] });
    },
  });
}
