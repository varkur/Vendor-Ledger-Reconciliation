# Architecture Overview

## System Summary

Enterprise-grade full-stack application built with:

- **Backend**: FastAPI (Python 3.12) with Clean Architecture
- **Frontend**: React 19 + TypeScript + Vite + PrimeReact (Sakai-compact theme)
- **Database**: PostgreSQL with async SQLAlchemy (asyncpg)
- **Auth**: JWT tokens + Microsoft OAuth2 (Azure AD SSO)
- **RBAC**: Granular permission system (Menu / API / Field-level)
- **Audit**: Automatic before/after change tracking on all tables

---

## High-Level Architecture

```
┌────────────────────────────────────────────────────────────────┐
│                     FRONTEND (React + Vite)                     │
│                                                                │
│  PrimeReact UI │ Redux Toolkit │ React Router │ Axios          │
│  RBAC Gates    │ Permission Hooks │ Tree-based permission UI   │
└───────────────────────────────┬────────────────────────────────┘
                                │ REST API (JWT Bearer)
┌───────────────────────────────┼────────────────────────────────┐
│                     BACKEND (FastAPI)                           │
│                                                                │
│  ┌──────────┐  ┌──────────────┐  ┌────────────────────────┐   │
│  │ API Layer│  │ Domain Layer │  │ Infrastructure Layer   │   │
│  │ (routes, │  │ (entities,   │  │ (DB, external APIs,   │   │
│  │ schemas, │  │ repositories,│  │  security, audit)     │   │
│  │ deps)    │  │ services)    │  │                        │   │
│  └──────────┘  └──────────────┘  └────────────────────────┘   │
│                                                                │
│  Middleware: CORS │ Correlation ID │ Auth │ Audit Context      │
│  Security: Permission Manager │ JWT Provider │ Password Encoder│
└───────────────────────────────┬────────────────────────────────┘
                                │
┌───────────────────────────────┼────────────────────────────────┐
│                     DATABASE (PostgreSQL)                       │
│                                                                │
│  users │ user_details │ tenants │ roles │ permissions          │
│  role_permissions │ role_assignments │ audit_logs              │
└────────────────────────────────────────────────────────────────┘
```

---

## Project Structure

```
enterprise-architecture/
├── backend/
│   ├── src/
│   │   ├── api/                    # FastAPI routes, schemas, middleware
│   │   │   ├── middleware/         # Auth, CORS, correlation, audit context
│   │   │   └── v1/
│   │   │       ├── endpoints/      # Controllers (auth, users, rbac, employee AD)
│   │   │       ├── schemas/        # Pydantic request/response models
│   │   │       └── dependencies.py # FastAPI DI (current user, repos)
│   │   ├── domain/                 # Business logic (framework-free)
│   │   │   ├── entities/           # User, Role, Permission, AuditLog
│   │   │   └── repositories/       # Abstract interfaces
│   │   ├── infrastructure/         # Adapters and implementations
│   │   │   ├── database/
│   │   │   │   ├── models/         # SQLAlchemy ORM models
│   │   │   │   ├── repositories/   # Concrete repo implementations
│   │   │   │   ├── migrations/     # Alembic migrations
│   │   │   │   ├── session.py      # Async session factory + audit listener
│   │   │   │   ├── audit_listener.py  # Automatic before/after audit
│   │   │   │   └── audit_context.py   # Request-scoped actor context
│   │   │   ├── security/           # JWT, passwords, permission manager, audit service
│   │   │   └── external/           # Darwin AD client
│   │   ├── config/                 # Settings, logging
│   │   └── observability/          # Structured logging, OpenTelemetry
│   ├── scripts/                    # Seed data, DB migration helpers
│   ├── deployment/                 # Docker, Helm, Kubernetes
│   └── docs/                       # Architecture docs, OpenAPI spec
│
└── frontend/
    └── src/
        ├── app/                    # Store, router, layouts
        │   ├── layouts/            # MainLayout (sidebar + topbar)
        │   ├── router/             # AppRouter, PrivateRoute (RBAC-gated)
        │   └── store/              # Redux store configuration
        ├── core/                   # Cross-cutting concerns
        │   └── rbac/               # Permission hooks, gates, slice, API
        ├── features/               # Feature modules
        │   ├── authentication/     # Login, OAuth callback, auth slice
        │   ├── user-management/    # User CRUD, role viewer
        │   ├── rbac-admin/         # Roles page, Audit logs page
        │   └── service-menu/       # Employee AD service
        ├── shared/                 # Reusable components, services
        └── assets/                 # Styles, theme overrides
```

---

## Database Schema

| Table | Purpose |
|-------|---------|
| `users` | Authentication accounts (username, password_hash, is_active, is_blocked) |
| `user_details` | Employee AD data (one-to-one with users) |
| `tenants` | Multi-tenant organization boundaries |
| `roles` | Named roles (ADMIN, MANAGER, USER, custom) |
| `permissions` | Granular permission definitions (scope + resource + action) |
| `role_permissions` | M:N join (role ↔ permission) |
| `role_assignments` | Links users to roles (supports multiple roles per user) |
| `audit_logs` | Immutable before/after change log for all tables |

**Note**: The legacy `users.role` column has been removed. Role assignment is now exclusively via `role_assignments` table.

---

## Authentication Flow

1. User submits credentials → `POST /auth/login`
2. Backend validates password (bcrypt) or delegates to Darwin AD
3. JWT access + refresh tokens returned
4. Frontend stores tokens in memory (not localStorage)
5. All API calls include `Authorization: Bearer <token>`
6. Token refresh handled automatically via interceptor

Alternative: Microsoft OAuth2 SSO via Azure AD redirect flow.

---

## Authorization (RBAC)

All access control is permission-based. No hardcoded role checks exist.

| Layer | Mechanism | Example |
|-------|-----------|---------|
| API endpoints | `require_permission("rbac.manage")` | Protects RBAC CRUD |
| API endpoints | `require_api_permission("users", "READ")` | Protects user list |
| Frontend routes | `<PrivateRoute menuKey="users">` | Redirects if no permission |
| Frontend sidebar | `useMenuPermissions()` hook | Hides/shows nav items |
| Frontend fields | `<FieldGate resource="users" field="salary">` | Hides sensitive fields |

### Permission Scopes

| Scope | Controls | Example |
|-------|----------|---------|
| MENU | Sidebar/navigation visibility | `menu.users` → shows Users link |
| API | Endpoint access | `users.list` → allows GET /users |
| FIELD | Field read/write visibility | `users.salary.read` → shows salary |

---

## Audit Logging

Two complementary layers:

| Layer | Trigger | Use Case |
|-------|---------|----------|
| **Automatic** (audit_listener) | Every INSERT/UPDATE/DELETE | Full before/after snapshots |
| **Manual** (AuditService) | Explicit calls | Domain events (login, role grants) |

Both write to `audit_logs` table with: actor, action, old/new values (JSON), IP, timestamp.

See: [ENTERPRISE_AUDIT.md](./ENTERPRISE_AUDIT.md)

---

## Frontend Design System

- **Theme**: PrimeReact Lara Light Blue + Emcure brand overrides
- **Density**: Compact (Sakai-style) — 13px base font, tight padding
- **Responsive**: Scales down at 1440px and 1280px breakpoints
- **Sidebar**: 220px fixed, hidden below 768px
- **Components**: PrimeReact DataTable, Tree, Dialog, Toast, Tag

---

## Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| No `users.role` column | Multiple roles per user via `role_assignments` |
| `require_permission()` over `require_role()` | Granular, no hardcoded role names |
| Async SQLAlchemy | Non-blocking DB calls for high concurrency |
| JWT in memory (not localStorage) | XSS protection |
| Audit in same transaction | Atomically consistent with data changes |
| Tree-based permission UI | Visual, feature-grouped, checkbox selection |
| Clean Architecture layers | Testable, framework-independent domain logic |

---

## Related Documents

- [ENTERPRISE_RBAC.md](./ENTERPRISE_RBAC.md) — Full RBAC system design
- [ENTERPRISE_AUDIT.md](./ENTERPRISE_AUDIT.md) — Automatic audit logging
- [EMPLOYEE_AD_SERVICE.md](./EMPLOYEE_AD_SERVICE.md) — Darwin AD integration
- [MICROSOFT_OAUTH_ANALYSIS.md](./MICROSOFT_OAUTH_ANALYSIS.md) — Azure AD SSO
