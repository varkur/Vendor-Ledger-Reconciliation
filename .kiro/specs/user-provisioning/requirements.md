# Requirements Document

## Feature: User Provisioning (Manual Creation + Darwinbox Import)

## Introduction

This feature builds the user-provisioning layer that gets users into the VLR system in the first place, before any authentication (AD-based or local) can occur. It fixes the incomplete manual user creation endpoint (`POST /api/v1/users/`) so it persists full employee profile data, and replaces the broken ad-hoc Darwinbox import endpoint with a correct implementation that uses RBAC role assignments instead of a nonexistent `role` column. Login flows (`/api/v1/auth/login`) and SSO are explicitly out of scope — they are unaffected by this feature and referenced only for context.

Requirements below are derived from `design.md` in this spec.

## Glossary

- **Darwinbox / Darwin**: Emcure's external HRMS/AD service (`EmployeeADClient`) used to fetch employee profile data by employee ID.
- **Manual creation**: Admin-driven user creation via `POST /api/v1/users` where all profile fields are supplied directly in the request.
- **Import**: Admin-driven user creation via `POST /api/v1/users/import` where only an `employee_id` is supplied and profile data is pulled from Darwinbox.
- **`is_validate_ad`**: Boolean flag on `users` indicating the account authenticates via AD/Darwinbox rather than the local password hash (existing login logic, unchanged by this feature).
- **Lookup row**: A normalized reference row (`departments`, `group_companies`) as opposed to a free-text string.
- **RBAC role assignment**: A row in `role_assignments` linking a user to a role; the correct mechanism for granting roles (as opposed to the nonexistent `users.role` column referenced by the current buggy import code).

## Requirements

### Requirement 1: Manual user creation with full profile data

**User Story:** As an admin, I want to create a new user with their full profile (name, email, department, designation, role) in a single request, so that the user is fully provisioned without needing follow-up edits.

#### Acceptance Criteria

1. WHEN an admin submits `POST /api/v1/users` with a `username` that does not already exist THEN the system SHALL create exactly one row in `users` and exactly one corresponding row in `user_details`.
2. IF the submitted `username` already exists THEN the system SHALL reject the request with a 409 Conflict and SHALL NOT modify any existing data.
3. WHEN the request omits `password` THEN the system SHALL set the new user's password hash from `settings.DARWINBOX_DEFAULT_PASSWORD`.
4. WHEN the request includes an explicit `password` THEN the system SHALL hash and store that password instead of the default.
5. IF `password` is omitted AND `settings.DARWINBOX_DEFAULT_PASSWORD` is empty/unset THEN the system SHALL reject the request with a 500-level configuration error and SHALL NOT create any user or profile row.
6. WHEN the request includes `name`, `email`, `department`, and optional `designation_title`/`reporting_manager` THEN the system SHALL persist all of these fields onto the created user's `user_details` row.
7. IF the request's `email` is not a syntactically valid email address THEN the system SHALL reject the request with a 422 Unprocessable Entity before creating any rows.
8. WHEN the request includes a `role_id` referencing an existing active role THEN the system SHALL create exactly one active `role_assignments` row linking the new user to that role.
9. IF the request includes a `role_id` that does not reference an existing active role THEN the system SHALL reject the request with a 422 Unprocessable Entity and SHALL NOT create the user.
10. WHEN the request's `department` value does not match (case-insensitively) any existing `departments` row THEN the system SHALL create a new `departments` row for that value before linking it to the new user's profile.
11. WHEN the response is returned to the caller THEN the system SHALL NOT include `password_hash` or any plaintext password in the response body, regardless of which user or role triggered the request.

### Requirement 2: Darwinbox employee import

**User Story:** As an admin, I want to import a user by supplying just their employee ID, so that the system pulls the employee's profile from Darwinbox and provisions the account automatically without manual data entry.

#### Acceptance Criteria

1. WHEN an admin submits `POST /api/v1/users/import` with an `employee_id` THEN the system SHALL call Darwin's `/getselectedemployees` API for that employee ID before making any database writes.
2. IF Darwin's response contains no matching employee record for the given `employee_id` THEN the system SHALL reject the request with a 404 Not Found and SHALL NOT create any rows.
3. IF the Darwin AD service is unreachable or returns an error THEN the system SHALL propagate a 502 Bad Gateway response and SHALL NOT create any rows.
4. IF `settings.DARWINBOX_DEFAULT_ROLE_CODE` does not resolve to an existing active role THEN the system SHALL reject the request with a 500-level configuration error before calling Darwin or writing any rows.
5. WHEN no existing user has a username matching the `employee_id` THEN the system SHALL create a new `users` row with `is_validate_ad=True` and a password hash derived from `settings.DARWINBOX_DEFAULT_PASSWORD`.
6. WHEN an existing user already has a username matching the `employee_id` THEN the system SHALL NOT modify that user's existing `password_hash`.
7. WHEN the Darwin response includes department and group company values THEN the system SHALL resolve or create matching rows in `departments` and `group_companies` (case-insensitive match on name) and link them to the user's profile.
8. IF Darwin's response is an error response THEN the system SHALL skip all department/group-company/profile data processing and SHALL NOT create or update any rows.
9. IF the department or group company data in an otherwise successful Darwin response is malformed or cannot be resolved THEN the system SHALL fail the entire import (no partial resolution) and SHALL NOT create or update any rows.
10. WHEN the import completes for a given employee THEN the system SHALL create or update exactly one `user_details` row populated from the Darwin response fields.
11. WHEN the import completes for a given employee THEN the system SHALL ensure exactly one active `role_assignments` row exists linking the user to the role identified by `settings.DARWINBOX_DEFAULT_ROLE_CODE`.
12. IF the same `employee_id` is imported more than once THEN the system SHALL NOT create duplicate active `role_assignments` rows, duplicate `departments`/`group_companies` rows for the same name, or duplicate `user_details` rows for the same user.

### Requirement 3: Legacy import endpoint compatibility

**User Story:** As a system integrator relying on the existing `/api/v1/users/import-employees` endpoint, I want it to keep working after this feature ships, so that no existing caller breaks.

#### Acceptance Criteria

1. WHEN a caller submits `POST /api/v1/users/import-employees` THEN the system SHALL delegate to the same corrected import logic used by `POST /api/v1/users/import` (no `role` column write, RBAC-based role assignment, lookup-row auto-creation).
2. WHEN the legacy endpoint is documented in the OpenAPI schema THEN the system SHALL mark it as deprecated in favor of `POST /api/v1/users/import`.
3. WHEN the legacy endpoint is called with a payload shape matching its current `ImportEmployeesRequest`/`ImportEmployeesResponse` contract THEN the system SHALL continue returning a response matching that existing contract.

### Requirement 4: Configuration for default password and default role

**User Story:** As an operator, I want the default password and default import role to be configurable via environment settings, so that they can be changed without a code deployment.

#### Acceptance Criteria

1. WHEN the application loads configuration THEN the system SHALL read `DARWINBOX_DEFAULT_PASSWORD` from the environment/`.env` file via the existing `Settings` mechanism.
2. WHEN the application loads configuration THEN the system SHALL read `DARWINBOX_DEFAULT_ROLE_CODE` from the environment/`.env` file, defaulting to `"Reconciliation_User"` when unset.
3. WHEN any log statement is emitted during user creation or import THEN the system SHALL NOT include the plaintext value of `DARWINBOX_DEFAULT_PASSWORD` or any user's plaintext password in log output.
