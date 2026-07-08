/**
 * Notifications API functions.
 * Communicates with backend VLR notification history endpoints via Axios.
 *
 * Requirements: 23.5, 25.1, 25.2
 */

import { apiClient } from '@shared/services/apiClient';

const BASE = '/vlr/notifications';

// ─────────────────────────────────────────────────────────────────────────────
// Types
// ─────────────────────────────────────────────────────────────────────────────

/** A single notification entry from the backend. */
export interface NotificationEntry {
  id: string;
  notification_id: string;
  case_id: string;
  type: 'Email' | 'SMS' | 'In-App' | 'WhatsApp';
  recipient: string;
  subject: string;
  timestamp: string;
  status: 'Sent' | 'Delivered' | 'Read' | 'Failed' | 'Pending';
  vendor_name: string;
  is_read: boolean;
}

/** Paginated list response for notifications. */
export interface PaginatedNotificationResponse {
  items: NotificationEntry[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

/** Parameters for listing notification history. */
export interface NotificationListParams {
  page?: number;
  page_size?: number;
  search?: string;
  status?: string;
  type?: string;
}

/** Response from mark-as-read endpoint. */
export interface MarkReadResponse {
  updated_count: number;
}

/** Response from sending reminders. */
export interface SendReminderResponse {
  sent_count: number;
  message: string;
}

// ─────────────────────────────────────────────────────────────────────────────
// API Functions
// ─────────────────────────────────────────────────────────────────────────────

/**
 * List notification history with pagination and optional filtering.
 * GET /api/v1/vlr/notifications
 */
export async function listNotifications(
  params: NotificationListParams
): Promise<PaginatedNotificationResponse> {
  const response = await apiClient.get<PaginatedNotificationResponse>(BASE, { params });
  return response.data;
}

/**
 * Mark one or more notifications as read.
 * PATCH /api/v1/vlr/notifications/mark-read
 */
export async function markNotificationsAsRead(
  notificationIds: string[]
): Promise<MarkReadResponse> {
  const response = await apiClient.patch<MarkReadResponse>(`${BASE}/mark-read`, {
    notification_ids: notificationIds,
  });
  return response.data;
}

/**
 * Send reminders for specified notification IDs (re-send).
 * POST /api/v1/vlr/notifications/send-reminder
 */
export async function sendReminders(
  notificationIds: string[]
): Promise<SendReminderResponse> {
  const response = await apiClient.post<SendReminderResponse>(`${BASE}/send-reminder`, {
    notification_ids: notificationIds,
  });
  return response.data;
}
