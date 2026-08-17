# Implementation Plan: User Provisioning (Manual Creation + Darwinbox Import)

## Overview

Implements full-profile manual user creation, a corrected Darwinbox import flow, and lookup-table auto-creation for departments/group companies. Backend-only (FastAPI + SQLAlchemy async + Alembic). Property-based tests use Hypothesis per `design.md`'s Testing Strategy.

## Task Dependency Graph

```json
{
  "waves": [
    {
      "wave": 1,
      "tasks": ["1.1"]
    },
    {
      "wave": 2,
      "tasks": ["2.1", "2.3", "7.1"]
    },
    {
      "wave": 3,
      "tasks": ["2.4"]
    },
    {
      "wave": 4,
      "tasks": ["3.1", "3.2"]
    },
    {
      "wave": 5,
      "tasks": ["4.1", "4.2", "5.1", "5.2", "8.1"]
    },
    {
      "wave": 6,
      "tasks": ["4.4", "5.3", "5.4"]
    },
    {
      "wave": 7,
      "tasks": [
        "4.5", "4.6", "4.7", "4.8", "4.10", "4.11",
        "5.5",
        "8.2"
      ]
    },
    {
      "wave": 8,
      "tasks": ["6.1", "6.2", "5.6", "5.7", "5.8", "5.9", "5.10"]
    },
    {
      "wave": 9,
      "tasks": ["6.3"]
    },
    {
      "wave": 10,
      "tasks": ["6.4", "7.2"]
    },
    {
      "wave": 11,
      "tasks": ["9.1", "9.2"]
    }
  ]
}
```

Notes on dependencies:
- Wave 1 (settings) must land before schema work that references `DARWINBOX_DEFAULT_ROLE_CODE`/`DARWINBOX_DEFAULT_PASSWORD`.
- Wave 2-3 (schema + migration) must land before any `UserService` code (waves 5-6) that reads/writes the new tables/columns.
- Wave 4 (schema updates) must land before `UserService` methods that accept the new request fields.
- Within `UserService`, helper methods (wave 5) must exist before the top-level `create_user`/`import_from_darwinbox` rewrites (wave 6), which must exist before their property/example tests (waves 7-8).
- API endpoint tasks (6.1, 6.2) depend on the corresponding `UserService` methods being implemented (wave 6).
- The legacy controller rewrite (6.3, wave 9) depends on `import_from_darwinbox` (5.5) already working, and its own test (6.4, wave 10) depends on 6.3.
- Final integration tests (wave 11) depend on everything else being complete.

## Tasks

- [ ] 1. Configuration and settings
  - [x] 1.1 Add `DARWINBOX_DEFAULT_PASSWORD` and `DARWINBOX_DEFAULT_ROLE_CODE` to `Settings`
    - Add both fields to `backend/src/config/settings.py` with descriptions matching design.md
    - Add both keys (empty/default values) to `backend/.env.example`; add `DARWINBOX_DEFAULT_PASSWORD` to `backend/.env` for local dev
    - _Requirements: 4.1, 4.2_

- [ ] 2. Database schema: lookup tables
  - [x] 2.1 Create `DepartmentModel` and `GroupCompanyModel`
    - Add `backend/src/infrastructure/database/models/department_model.py` (`departments` table: `name` unique, `is_active`)
    - Add `backend/src/infrastructure/database/models/group_company_model.py` (`group_companies` table: `name` unique, `is_active`)
    - _Requirements: 1.10, 2.7_

  - [x] 2.3 Add `department_id` / `group_company_id` FK columns to `UserDetailsModel`
    - Nullable FKs to `departments.id` / `group_companies.id`, `ondelete="SET NULL"`, keep existing free-text `department`/`group_company` columns untouched
    - _Requirements: 1.10, 2.7_

  - [x] 2.4 Write Alembic migration for all new tables/columns
    - New migration under `backend/src/infrastructure/database/migrations/versions/` creating `departments`, `group_companies`, and altering `user_details`
    - Include unique constraint/index on `departments.name` (case-insensitive) and `group_companies.name`
    - Verify migration applies cleanly: run `alembic upgrade head` against the test DB and `alembic downgrade -1` to confirm reversibility
    - _Requirements: 1.10, 2.7_

- [ ] 3. Request/response schema updates
  - [x] 3.1 Update `CreateUserRequest`
    - Make `password` optional; add `name`, `email` (EmailStr), `department`, `designation_title`, `reporting_manager`, `employee_id`
    - _Requirements: 1.1, 1.3, 1.4, 1.6, 1.7_

  - [x] 3.2 Add `ImportFromDarwinboxRequest` schema
    - New schema in `backend/src/api/v1/schemas/user_request.py` with required `employee_id: str`
    - _Requirements: 2.1_

- [ ] 4. UserService: manual creation rewrite
  - [x] 4.1 Implement `_resolve_password_hash`
    - Returns hash of explicit password when provided; otherwise hashes `settings.DARWINBOX_DEFAULT_PASSWORD`; raises `ConfigurationError` when both are empty
    - _Requirements: 1.3, 1.4, 1.5_

  - [x] 4.2 Implement `_get_or_create_department` and `_get_or_create_group_company`
    - Case-insensitive, whitespace-trimmed lookup; creates a new row only when no case-insensitive match exists; empty/blank names normalize to `"Unspecified"`
    - _Requirements: 1.10, 2.7_

  - [x] 4.4 Rewrite `UserService.create_user` to persist full profile
    - Validate username uniqueness first (unchanged behavior), then resolve password hash, create `users` row, create `user_details` row from all new profile fields, assign role via existing `_assign_role` when `role_id` provided (validating it resolves to an active role first)
    - Ensure `UserResponse`/`_to_response` never expose `password_hash`
    - _Requirements: 1.1, 1.2, 1.6, 1.8, 1.9, 1.11_

  - [ ]* 4.5 Property test: username uniqueness and no-mutation-on-conflict (P1, P2)
    - Use Hypothesis to generate random usernames/profile field combinations; assert exactly one `users`+`user_details` row on success, and zero mutation when the username already exists
    - _Requirements: 1.1, 1.2_

  - [ ]* 4.6 Property test: password fallback vs explicit password (P3, P4, P5)
    - Generate random optional password strings; assert fallback-to-default behavior, explicit-password behavior, and the config-error/no-writes case when default is unset and password is omitted
    - _Requirements: 1.3, 1.4, 1.5_

  - [ ]* 4.7 Property test: profile field round-trip (P6)
    - Generate random valid name/email/department/designation_title/reporting_manager combinations; assert `user_details` persists them verbatim
    - _Requirements: 1.6_

  - [ ]* 4.8 Property test: role assignment validity (P7, P8)
    - Generate random valid active role ids and random invalid/inactive role ids; assert exactly-one-assignment vs reject-with-no-user-created respectively
    - _Requirements: 1.8, 1.9_

  - [ ]* 4.10 Property test: department/group-company case-insensitive dedup (P9)
    - Generate random department names with randomized casing/whitespace variants; assert all variants resolve to the same row id
    - _Requirements: 1.10_

  - [ ]* 4.11 Property test: response never exposes password data (P10)
    - Generate random requests (with/without explicit password); assert the returned response object has no `password_hash`/`password` attribute
    - _Requirements: 1.11, 4.3_

- [ ] 5. UserService: Darwinbox import
  - [x] 5.1 Implement `_get_role_by_code` and fail-fast role check
    - Looks up an active `RoleModel` by code; `import_from_darwinbox` calls this first and raises `ConfigurationError` before any Darwin call or DB write if it resolves to `None`
    - _Requirements: 2.4_

  - [x] 5.2 Implement `_extract_single_employee` and Darwin error/empty-result handling
    - Parses Darwin's `/getselectedemployees` response for the requested employee_id; returns `None` when absent; raises on error-shaped responses without processing any data
    - _Requirements: 2.1, 2.2, 2.3, 2.7 (skip-on-error case)_

  - [x] 5.3 Implement `_upsert_user_details` with strict department/group-company resolution
    - Resolves department/group_company via 4.2 helpers; if the Darwin payload's department/group_company field is malformed (missing/wrong type) raise `ValueError` before any writes for this import (no partial resolution)
    - Upserts (create-or-update) exactly one `user_details` row for the user
    - _Requirements: 2.7 (malformed-data case), 2.8_

  - [x] 5.4 Implement `_ensure_role_assigned` (idempotent role assignment)
    - Creates an active `role_assignments` row for (user, role) only if one doesn't already exist active
    - _Requirements: 2.9, 2.10_

  - [x] 5.5 Implement `UserService.import_from_darwinbox`
    - Order of operations: resolve default role (5.1) → call Darwin (5.2) → get-or-create user (new: `is_validate_ad=True` + default password hash; existing: reuse, password untouched) → resolve org data + upsert details (5.3) → ensure role assignment (5.4)
    - _Requirements: 2.1, 2.2, 2.3, 2.5, 2.6_

  - [ ]* 5.6 Property test: employee-not-found and new-user creation (P11, P12)
    - Generate random employee_ids with a Darwin stub returning no match for some and a valid payload for others; assert 404-style rejection with no rows vs correct new-user creation (`is_validate_ad=True`, default password hash)
    - _Requirements: 2.2, 2.5_

  - [ ]* 5.7 Property test: existing user password untouched (P13)
    - Generate random pre-existing users with random pre-set password hashes; run import for each; assert password_hash unchanged after import
    - _Requirements: 2.6_

  - [ ]* 5.8 Property test: malformed org data fails entire import (P14)
    - Generate random malformed department/group_company payload shapes (null, wrong type, empty structure); assert import raises and creates zero rows
    - _Requirements: 2.7 (malformed-data case)_

  - [ ]* 5.9 Property test: re-import idempotency (P15, P16)
    - Generate random repeat counts (1-5) of importing the same employee_id; assert exactly one `user_details` row, one active role assignment, and no duplicate department/group_company rows regardless of repeat count or name-casing variance across Darwin payloads
    - _Requirements: 2.8, 2.9, 2.10, 2.12_

  - [ ]* 5.10 Example test: Darwin call precedes all writes; Darwin error/unavailable maps correctly
    - Mock `EmployeeADClient` to raise `EmployeeADError`/`EmployeeADUnavailableError`; assert no rows written and the exception propagates for the controller to map to 502
    - Mock Darwin to return an error-shaped response; assert no rows written (Req 2.7 error-skip case)
    - _Requirements: 2.1, 2.3, 2.7 (error-response case)_

- [ ] 6. API endpoints
  - [x] 6.1 Add `POST /api/v1/users/import` endpoint
    - New route in `user_controller.py` calling `UserService.import_from_darwinbox`; maps `ValueError` → 404, `ConfigurationError` → 500, `EmployeeADError`/`EmployeeADUnavailableError` → 502; protected by `require_api_permission("users", "IMPORT")` (reuse existing `users.import` permission)
    - _Requirements: 2.1, 2.2, 2.3, 2.4_

  - [x] 6.2 Update `POST /api/v1/users` controller wiring
    - No route signature change needed beyond the already-updated `CreateUserRequest`; confirm error mapping still covers `ValueError` → 409/422 appropriately (409 for duplicate username, 422 for invalid role ids — distinguish via error message or a dedicated exception type)
    - _Requirements: 1.2, 1.7, 1.9_

  - [x] 6.3 Rewrite `employee_import_controller.py` to delegate to `UserService.import_from_darwinbox`
    - Replace the buggy inline logic (including the `role="USER"` `UserModel` construction bug) with a loop over `request.employee_ids` calling `UserService.import_from_darwinbox` per ID, mapping results into the existing `ImportEmployeesResponse` shape (`created`/`updated`/`failed` counts, per-employee `ImportResult`)
    - If delegation raises for a given employee_id, fail that employee's result entry (not the whole batch) unless the design's "fail request entirely if delegation fails" applies — per Req 3.1, treat delegation failure as fatal to the whole request rather than a per-item soft failure; do not fall back to old logic
    - Mark the route `deprecated=True` in its FastAPI decorator
    - _Requirements: 3.1, 3.2, 3.3_

  - [ ]* 6.4 Example test: legacy endpoint delegation and deprecation
    - Call the legacy endpoint with a valid employee_id and mocked Darwin data; assert resulting DB state matches calling `/users/import` directly
    - Force delegation to raise; assert the legacy endpoint returns an error response (no fallback to old broken logic)
    - Assert the route's OpenAPI entry has `deprecated: true`
    - Assert response shape still matches `ImportEmployeesResponse` (total/created/updated/failed/results)
    - _Requirements: 3.1, 3.2, 3.3_

- [ ] 7. RBAC/data seeding support
  - [x] 7.1 Verify or seed `DARWINBOX_DEFAULT_ROLE_CODE`'s target role
    - Confirm `Reconciliation_User` (the default) exists via `seed_rbac.py`; add a startup/health-check note or seed script assertion so a misconfigured environment fails fast per Req 2.4 rather than at first import call
    - _Requirements: 2.4, 4.2_

  - [ ]* 7.2 Example test: settings loading
    - Assert `DARWINBOX_DEFAULT_PASSWORD` reflects the environment value when set; assert `DARWINBOX_DEFAULT_ROLE_CODE` defaults to `"Reconciliation_User"` when unset and reflects an override when set
    - _Requirements: 4.1, 4.2_

- [ ] 8. Logging safety
  - [x] 8.1 Redact/avoid logging plaintext passwords and raw Darwin PII payloads
    - Remove or redact the existing `logger.info` calls in the import path that log raw Darwin employee payloads (carried over from `employee_import_controller.py`); ensure no code path logs `request.password`, resolved plaintext passwords, or `settings.DARWINBOX_DEFAULT_PASSWORD`
    - _Requirements: 4.3_

  - [ ]* 8.2 Property test: no plaintext password ever appears in captured logs (P from Req 4.3)
    - Generate random password strings (explicit and default-fallback cases); run `create_user` and `import_from_darwinbox` with log capture attached; assert the plaintext password value never appears in any captured log record
    - _Requirements: 4.3_

- [ ] 9. Final integration pass
  - [ ]* 9.1 End-to-end integration test: manual creation full round trip
    - Create a user via `POST /api/v1/users` with full profile + role_id; fetch via `GET /api/v1/users/{id}/details` and `GET /api/v1/users/{id}/roles`; assert all persisted data matches
    - _Requirements: 1.1, 1.6, 1.8_

  - [ ]* 9.2 End-to-end integration test: Darwinbox import full round trip
    - Mock `EmployeeADClient.get_selected_employees` with a fixed payload; call `POST /api/v1/users/import`; assert `departments`, `group_companies`, `role_assignments`, `user_details` are all correctly populated; re-run and assert idempotency holds end-to-end
    - _Requirements: 2.5, 2.7, 2.8, 2.9, 2.10, 2.12_

## Notes

- Login (`POST /api/v1/auth/login`) and Microsoft/Azure SSO are explicitly out of scope for this feature and are not touched by any task above.
- The legacy `/api/v1/users/import-employees` endpoint is kept for backward compatibility (deprecated) rather than removed, per the design's decision to avoid breaking existing callers with no migration path.
- Property-based tests (tasks 4.5, 4.6, 4.7, 4.8, 4.10, 4.11, 5.6, 5.7, 5.8, 5.9, 8.2) use Hypothesis and should be run with `pytest --hypothesis-seed=random` in CI; any failing example found by Hypothesis should be captured and added as a regression fixture.
- Run `alembic upgrade head` (task 2.4) against the local/test database before starting on tasks 4–5, since `UserService` changes depend on the new columns/tables existing.
