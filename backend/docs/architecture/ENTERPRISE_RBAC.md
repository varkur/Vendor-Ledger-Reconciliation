# Enterprise RBAC Architecture

## Overview

This document describes the enterprise-grade Role-Based Access Control (RBAC) system implemented across the full stack. The system provides:

1. **Pure permission-based access** — No hardcoded role checks anywhere in the codebase
2. **Multiple roles per user** — Users can be assigned multiple roles simultaneously
3. **Menu-level permissions** — Controls UI sidebar/navigation visibility
4. **API-level permissions** — Controls endpoint access
5. **Field-level permissions** — Controls field read/write visibility per resource
6. **Multi-tenant RBAC** — Tenant-scoped roles and assignments (SaaS-ready)
7. **Tree-based permission UI** — Checkbox tree grouped by feature for easy management
8. **Full audit trail** — All permission changes are logged

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                           FRONTEND (React)                          │
│                                                                     │
│  ┌─────────────┐  ┌──────────────┐  ┌─────────────────────────┐   │
│  │  MenuGate   │  │PermissionGate│  │      FieldGate          │   │
│  │  Component  │  │  Component   │  │      Component          │   │
│  └──────┬──────┘  └──────┬───────┘  └───────────┬─────────────┘   │
│         │                 │                      │                  │
│         └─────────────────┼──────────────────────┘                  │
│                           │                                         │
│                    ┌──────┴───────┐                                  │
│                    │  rbacSlice   │  (Redux — loads on login)        │
│                    └──────┬───────┘                                  │
│                           │ GET /rbac/my-permissions/*               │
└───────────────────────────┼─────────────────────────────────────────┘
                            │
┌───────────────────────────┼─────────────────────────────────────────┐
│                      BACKEND (FastAPI)                               │
│                           │                                         │
│  ┌────────────────────────▼──────────────────────────────────┐      │
│  │              rbac_controller.py (API layer)               │      │
│  │  • /rbac/roles         • /rbac/permissions                │      │
│  │  • /rbac/assignments   • /rbac/audit-logs                 │      │
│  │  • /rbac/my-permissions/menu                              │      │
│  │  • /rbac/my-permissions/fields/{resource}                 │      │
│  │  • /rbac/my-permissions/all (debug)                       │      │
│  └────────────────────────┬──────────────────────────────────┘      │
│                           │                                         │
│  ┌────────────────────────▼──────────────────────────────────┐      │
│  │         permission_manager.py (Business Logic)            │      │
│  │  • Resolves effective permissions per user                │      │
│  │  • Handles role hierarchy (parent_role_id inheritance)    │      │
│  │  • Tenant-scoped permission resolution                   │      │
│  │  • require_permission() / require_api_permission()        │      │
│  └────────────────────────┬──────────────────────────────────┘      │
│                           │                                         │
│  ┌────────────────────────▼──────────────────────────────────┐      │
│  │           audit_listener.py (Automatic Logging)           │      │
│  │  • Captures INSERT/UPDATE/DELETE on all tables            │      │
│  │  • Before/after JSON snapshots                           │      │
│  └───────────────────────────────────────────────────────────┘      │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
                            │
┌───────────────────────────┼─────────────────────────────────────────┐
│                     DATABASE (PostgreSQL)                            │
│                                                                     │
│  ┌──────────┐  ┌───────┐  ┌─────────────┐  ┌──────────────────┐   │
│  │ tenants  │  │ roles │  │ permissions │  │ role_permissions │   │
│  └──────────┘  └───┬───┘  └──────┬──────┘  │   (M:N join)    │   │
│                    │              │          └──────────────────┘   │
│              ┌─────┴──────┐      │                                  │
│              │   role_    │      │                                  │
│              │assignments │      │                                  │
│              └─────┬──────┘      │                                  │
│                    │             │                                  │
│              ┌─────┴──────┐     │                                  │
│              │   users    │     │                                  │
│              └────────────┘     │                                  │
│                                 │                                  │
│  ┌──────────────────────────────┴──────────────────────────────┐   │
│  │              audit_logs (append-only, immutable)             │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Database Schema

### Tables

| Table | Purpose | Key Columns |
|-------|---------|-------------|
| `users` | Authentication accounts | username, password_hash, is_active, is_blocked, is_validate_ad |
| `tenants` | Multi-tenant org boundaries | code, name, domain, is_active |
| `roles` | Named roles (system or custom) | code, name, tenant_id, parent_role_id, is_system |
| `permissions` | Granular permission definitions | code, scope (MENU/API/FIELD), resource, action |
| `role_permissions` | M:N join (role ↔ permission) | role_id, permission_id |
| `role_assignments` | Links users to roles (multiple per user) | user_id, role_id, tenant_id, is_active |
| `audit_logs` | Immutable event log | actor_id, action, resource_type, old/new_value, ip, created_at |

**Note**: The `users` table has no `role` column. All role management is via `role_assignments`.

### Permission Scopes

| Scope | Purpose | Example Code | Effect |
|-------|---------|--------------|--------|
| `MENU` | Sidebar visibility | `menu.users` | User sees "Users" nav link |
| `API` | Endpoint access | `users.create` | User can call POST /users |
| `FIELD` | Field read/write | `users.salary` | User can see salary column |

### Default Permissions (Seeded)

| Category | Permissions |
|----------|-------------|
| Menu | dashboard, users, roles, audit_logs, services, reports, settings |
| Users API | list, create, update, delete, export, import |
| Roles API | list, create, update, assign |
| RBAC | rbac.manage (CRUD roles/permissions/assignments) |
| Audit | audit.read |
| Services | services.employee_ad |
| Reports | reports.export |
| Fields | users.salary (read/update), users.email (read/update), users.phone (read) |

### Default Roles (Seeded)

| Role | Permissions |
|------|-------------|
| ADMIN | ALL permissions (27 total) |
| MANAGER | Dashboard, Users (list/export), Reports, Services, email/phone fields |
| USER | Dashboard, Services only |

---

## Access Control — No Hardcoded Roles

The codebase contains **zero** `require_role("ADMIN")` calls. All access control uses:

```python
# Permission-based (checks permission code in user's assigned roles)
@router.get("/users", dependencies=[Depends(require_api_permission("users", "READ"))])

# Or by specific permission code
@router.get("/audit-logs", dependencies=[Depends(require_permission("audit.read"))])
```

### Backend Permission Guards

| Endpoint Group | Permission Required |
|----------------|-------------------|
| GET/POST /users | `users.list` / `users.create` |
| PATCH /users | `users.update` |
| All /rbac/* CRUD | `rbac.manage` |
| GET /rbac/audit-logs | `audit.read` |
| All /services/employee-ad | `services.employee_ad` |
| POST /users/import-employees | `users.import` |

### Frontend Route Guards

Routes use `menuKey` matching RBAC menu permissions:

```tsx
<PrivateRoute menuKey="users"><UserListPage /></PrivateRoute>
<PrivateRoute menuKey="roles"><RolesPage /></PrivateRoute>
<PrivateRoute menuKey="audit_logs"><AuditLogsPage /></PrivateRoute>
<PrivateRoute menuKey="services"><EmployeeADServicePage /></PrivateRoute>
```

---

## File Structure

### Backend

```
backend/src/
├── api/v1/
│   ├── endpoints/
│   │   ├── rbac_controller.py          # RBAC REST API
│   │   └── user_controller.py          # User CRUD + /users/{id}/roles
│   └── schemas/
│       └── rbac_schema.py              # Pydantic request/response models
├── domain/entities/
│   ├── role.py                         # Role, Permission, PermissionScope, PermissionAction
│   └── audit_log.py                    # AuditLog + AuditAction enum
├── infrastructure/
│   ├── database/
│   │   ├── models/
│   │   │   ├── role_model.py           # roles, permissions, role_permissions, role_assignments
│   │   │   └── audit_log_model.py      # audit_logs (append-only)
│   │   ├── audit_listener.py           # Automatic before/after audit (session event)
│   │   └── audit_context.py            # Request-scoped actor context (contextvars)
│   └── security/
│       ├── permission_manager.py       # Permission resolution + FastAPI dependencies
│       └── audit_service.py            # Manual audit log writer
└── scripts/
    └── seed_rbac.py                    # Seeds permissions, roles, role-permission links, user assignments
```

### Frontend

```
frontend/src/
├── core/rbac/
│   ├── types.ts                        # Permission, Role, response types
│   ├── rbacApi.ts                      # GET /rbac/my-permissions/*
│   ├── rbacSlice.ts                    # Redux state (menuKeys, fieldPerms)
│   ├── usePermissions.ts              # Hooks: useMenuPermission, useFieldPermissions
│   └── PermissionGate.tsx             # MenuGate, PermissionGate, FieldGate
├── features/rbac-admin/
│   ├── pages/
│   │   ├── RolesPage.tsx              # Tree-based permission management
│   │   └── AuditLogsPage.tsx          # Audit log viewer
│   └── api/rbacAdminApi.ts            # Admin CRUD API client
├── features/user-management/
│   ├── components/
│   │   └── UserTable.tsx              # User list + Roles tree popup
│   └── pages/UserListPage.tsx
└── app/
    ├── router/
    │   ├── AppRouter.tsx              # Routes with menuKey guards
    │   └── PrivateRoute.tsx           # RBAC-based route protection
    └── layouts/MainLayout.tsx         # Sidebar driven by menuKeys
```

---

## API Reference

### User Permission Queries (Authenticated)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/rbac/my-permissions/menu` | Menu keys + permissions for current user |
| GET | `/api/v1/rbac/my-permissions/fields/{resource}` | Field-level perms for a resource |
| GET | `/api/v1/rbac/my-permissions/all` | All permissions (debug endpoint) |

### Role Management (requires `rbac.manage`)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/rbac/roles` | List roles with permissions |
| POST | `/api/v1/rbac/roles` | Create a new role |
| PATCH | `/api/v1/rbac/roles/{role_id}` | Update role |
| POST | `/api/v1/rbac/roles/grant-permission` | Grant permission to role |
| POST | `/api/v1/rbac/roles/revoke-permission` | Revoke permission from role |

### Role Assignment (requires `rbac.manage`)

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/rbac/assignments` | Assign role to user |
| POST | `/api/v1/rbac/assignments/revoke` | Revoke role from user |

### User Roles (Authenticated)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/users/{user_id}/roles` | Get roles + permissions tree for a user |

### Audit Logs (requires `audit.read`)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/rbac/audit-logs` | Query with filters (action, actor, resource) |

---

## Frontend Usage Examples

### Route protection (PrivateRoute)

```tsx
<PrivateRoute menuKey="users">
  <UserListPage />
</PrivateRoute>
```

### Sidebar visibility (MainLayout)

Menu items use `menuKey` — only shown if the key exists in the user's RBAC menu permissions:

```tsx
{ label: 'Users', icon: 'pi pi-users', path: '/users', menuKey: 'users' }
```

### Permission-based button visibility

```tsx
import { PermissionGate } from '@core/rbac';

<PermissionGate permission="users.create">
  <Button label="Create User" />
</PermissionGate>
```

### Field-level visibility

```tsx
import { FieldGate } from '@core/rbac';

<FieldGate resource="users" field="salary" action="READ">
  <Column field="salary" header="Salary" />
</FieldGate>
```

### Tree-based permission assignment (RolesPage)

Permissions are displayed in a PrimeReact Tree with checkboxes, grouped by:
- **Scope** (Menu Access / API Access / Field-Level Access)
- **Feature** (Users, Roles, Reports, etc.)

Checking a parent node selects all children. Partial selection shows intermediate state.

---

## User Roles — Multiple Roles per User

A user can have multiple roles assigned simultaneously. The effective permissions are the **union** of all permissions from all assigned roles.

### Viewing User Roles (UserTable)

The Users page has a shield (🛡) button per row. Clicking it opens a Tree popup showing:
```
🛡 Administrator (ADMIN)
   ├── 🔑 Dashboard Menu
   ├── 🔑 Users Menu
   ├── 🔑 List Users (READ)
   └── ...
🛡 Manager (MANAGER)
   ├── 🔑 Reports Menu
   └── ...
```

### Assigning Roles

Roles are assigned via `POST /api/v1/rbac/assignments`:
```json
{ "user_id": "uuid", "role_id": "uuid", "tenant_id": null }
```

---

## Multi-Tenant Support

| Feature | Implementation |
|---------|---------------|
| Tenant-scoped roles | `roles.tenant_id` — NULL means global role |
| Scoped assignments | `role_assignments.tenant_id` — assigns role within a tenant |
| Resolution logic | PermissionManager merges global + tenant roles for a user |
| API filtering | `GET /rbac/roles?tenant_id=...` returns global + tenant roles |

---

## Setup & Operations

### Initial Setup

```bash
# 1. Run all migrations
alembic upgrade head

# 2. Seed default permissions, roles, and user assignments
python -m scripts.seed_rbac
```

### Adding a New Permission

1. Add to `DEFAULT_PERMISSIONS` in `seed_rbac.py`
2. Add to `ROLE_PERMISSIONS["ADMIN"]` list
3. Run: `python -m scripts.seed_rbac`
4. Use in code: `require_permission("your.new.code")`

### Adding a New Role

1. Create via UI: Navigate to `/roles` → "New Role"
2. Assign permissions via the tree checkbox UI
3. Assign to users via the RBAC assignments API

---

## Security Design Decisions

| Decision | Rationale |
|----------|-----------|
| No `users.role` column | Replaced by `role_assignments` — supports multiple roles |
| No hardcoded `ADMIN` checks | All access via permission codes — fully configurable |
| `require_permission()` dependencies | Declarative, audit-friendly, easy to find/grep |
| Permission codes are strings | Can be added/removed without schema changes |
| Immutable audit logs | Append-only table, no UPDATE/DELETE |
| Non-blocking audit writes | Audit failures never break business operations |
