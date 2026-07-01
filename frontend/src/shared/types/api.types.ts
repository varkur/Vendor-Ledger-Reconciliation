/** Common API response types */

export interface ApiError {
  success: boolean;
  message: string;
  correlation_id?: string;
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  skip: number;
  limit: number;
}
