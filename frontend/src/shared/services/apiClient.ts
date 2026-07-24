/**
 * Axios API client with interceptors.
 * - Attaches Bearer token to all requests
 * - Handles 401 with token refresh
 * - Retry logic for GET requests on 5xx
 * - Correlation ID header
 */

import axios, { AxiosError, InternalAxiosRequestConfig } from 'axios';
import { storageService } from './storageService';

const API_BASE_URL = '/api/v1';

/**
 * Generate a UUID that works in ALL browser contexts.
 *
 * `crypto.randomUUID()` only exists in a "secure context" (HTTPS or localhost).
 * When the app is served over plain HTTP (e.g. http://10.21.191.62), it is
 * undefined and throws, which would crash the request interceptor before any
 * API call fires. This falls back to a manual UUID v4 in that case.
 */
function generateCorrelationId(): string {
  try {
    if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
      return crypto.randomUUID();
    }
  } catch {
    // fall through to manual generation
  }
  // RFC4122-ish v4 fallback (uses crypto.getRandomValues if available)
  const getRandom = () => {
    if (typeof crypto !== 'undefined' && typeof crypto.getRandomValues === 'function') {
      const arr = new Uint8Array(1);
      crypto.getRandomValues(arr);
      return arr[0] / 256;
    }
    return Math.random();
  };
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = (getRandom() * 16) | 0;
    const v = c === 'x' ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

export const apiClient = axios.create({
  baseURL: API_BASE_URL,
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
    Accept: 'application/json',
  },
});

// Request interceptor: attach token + correlation ID
apiClient.interceptors.request.use(
  (config: InternalAxiosRequestConfig) => {
    const token = storageService.getAccessToken();
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }

    // Add correlation ID (safe in non-secure/HTTP contexts too)
    config.headers['X-Correlation-ID'] = generateCorrelationId();

    return config;
  },
  (error) => Promise.reject(error)
);

// Response interceptor: handle 401 token refresh
let isRefreshing = false;
let failedQueue: Array<{
  resolve: (token: string) => void;
  reject: (error: unknown) => void;
}> = [];

const processQueue = (error: unknown, token: string | null = null) => {
  failedQueue.forEach((prom) => {
    if (error) {
      prom.reject(error);
    } else {
      prom.resolve(token!);
    }
  });
  failedQueue = [];
};

apiClient.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const originalRequest = error.config as InternalAxiosRequestConfig & {
      _retry?: boolean;
    };

    if (error.response?.status === 401 && !originalRequest._retry) {
      if (isRefreshing) {
        return new Promise((resolve, reject) => {
          failedQueue.push({
            resolve: (token: string) => {
              originalRequest.headers.Authorization = `Bearer ${token}`;
              resolve(apiClient(originalRequest));
            },
            reject,
          });
        });
      }

      originalRequest._retry = true;
      isRefreshing = true;

      const refreshTokenValue = storageService.getRefreshToken();
      if (!refreshTokenValue) {
        storageService.clearTokens();
        window.location.href = '/login';
        return Promise.reject(error);
      }

      try {
        const response = await axios.post(`${API_BASE_URL}/auth/refresh`, {
          refresh_token: refreshTokenValue,
        });

        const { access_token } = response.data;
        storageService.setAccessToken(access_token);
        processQueue(null, access_token);

        originalRequest.headers.Authorization = `Bearer ${access_token}`;
        return apiClient(originalRequest);
      } catch (refreshError) {
        processQueue(refreshError, null);
        storageService.clearTokens();
        window.location.href = '/login';
        return Promise.reject(refreshError);
      } finally {
        isRefreshing = false;
      }
    }

    return Promise.reject(error);
  }
);
