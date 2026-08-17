/** User domain types matching backend UserResponse */

export interface User {
  id: string;
  username: string;
  is_active: boolean;
  is_blocked: boolean;
  is_validate_ad: boolean;
  employee_id: string | null;
  employee_name: string | null;
  email: string | null;
  last_login: string | null;
  created_by: string;
  created_date: string;
  modified_by: string;
  modified_date: string;
}

export interface UserListResponse {
  users: User[];
  total: number;
  skip: number;
  limit: number;
}

export interface CreateUserRequest {
  username: string;
  password?: string | null;
  is_validate_ad: boolean;
  role_id: string | null;
  name: string;
  email: string;
  department: string;
  designation_title?: string;
  reporting_manager?: string;
  employee_id?: string | null;
}

export interface UpdateUserRequest {
  is_active?: boolean;
  is_blocked?: boolean;
  is_validate_ad?: boolean;
  role_id?: string | null;
}

export interface RolePermission {
  code: string;
  name: string;
  scope: string;
  resource: string;
  action: string;
}

export interface UserRole {
  id: string;
  code: string;
  name: string;
  permissions: RolePermission[];
}

export interface UserRolesResponse {
  user_id: string;
  roles: UserRole[];
}

export interface ImportResult {
  employee_id: string;
  status: 'created' | 'updated' | 'failed';
  message?: string;
}

export interface ImportEmployeesResponse {
  total: number;
  created: number;
  updated: number;
  failed: number;
  results: ImportResult[];
}
