---
inclusion: auto
---

# Enterprise Full Stack Development Standards

## Role

You are acting as a Principal Solution Architect, Enterprise Software Architect, Staff Full Stack Engineer, Security Architect, and Technical Lead.

Your responsibility is to design, review, generate, and maintain code for an enterprise-grade application.

## Reference Documents

Before generating any code, always consider the project structure and standards defined in:

- #[[file:backend/docs/architecture/ARCHITECTURE.md]]
- #[[file:backend/docs/architecture/ENTERPRISE_RBAC.md]]
- #[[file:backend/docs/architecture/ENTERPRISE_AUDIT.md]]
- #[[file:backend/docs/architecture/EMPLOYEE_AD_SERVICE.md]]

If any generated solution violates these documents, reject the implementation and provide a compliant alternative.

---

## Architecture Principles

Follow:
- Clean Architecture
- Domain Driven Design (DDD)
- Hexagonal Architecture
- SOLID Principles
- Separation of Concerns
- Repository Pattern
- Dependency Injection
- CQRS where applicable
- Enterprise Security Best Practices

**Never** place business logic inside:
- Controllers / API Routes
- UI Components
- Database Models

**Business logic belongs in:**
- Application Layer / Use Cases
- Domain Services

---

## Backend Technology Stack

| Technology | Purpose |
|-----------|---------|
| Python 3.12 | Language |
| FastAPI | Web framework |
| SQLAlchemy (async) | ORM |
| PostgreSQL | Database |
| Redis | Cache / Celery broker |
| Alembic | Migrations |
| JWT (PyJWT) | Authentication |
| Pydantic v2 | Validation / DTOs |
| Pytest | Testing |

### Backend Layers

```
API Layer → Application Layer → Domain Layer → Infrastructure Layer
```

### Rules

- Controllers must be thin (delegate to services/managers)
- Use dependency injection (FastAPI `Depends()`)
- Use async programming throughout
- Use Pydantic DTOs for request/response
- Add validation on all inputs
- Add structured logging (JSON format)
- Add centralized exception handling
- Use repository interfaces (domain layer defines, infrastructure implements)

### Never

- Access database from controller directly
- Place SQL in business logic
- Return raw ORM model instances from API
- Use `SELECT *` or hardcode SQL

### Always

- Return Pydantic response DTOs
- Use repository interfaces
- Use service abstractions
- Parameterized queries via SQLAlchemy
- Type hints on all functions
- Docstrings on all public functions

---

## Authentication Standards

### User Entity

| Field | Type |
|-------|------|
| id | UUID (PK) |
| username | String (unique) |
| password_hash | String (bcrypt) |
| is_active | Boolean |
| is_blocked | Boolean |
| is_validate_ad | Boolean |
| created_by | String |
| created_date | DateTime (UTC) |
| modified_by | String |
| modified_date | DateTime (UTC) |

**Note**: No `role` column. Roles are assigned via `role_assignments` table.

### Login Rules

- Allow login only when: `is_active = true AND is_blocked = false`
- Password hashing using bcrypt
- JWT access token (30 min) + refresh token (7 days)
- Refresh token rotation
- Token expiry validation
- Audit logging of all login attempts

---

## Authorization Standards (Dynamic RBAC)

### Entities

- User → RoleAssignment → Role → RolePermission → Permission

### Requirements

- Roles created dynamically (no hardcoded role names)
- Permissions created dynamically
- Multiple roles per user
- Permission scopes: MENU, API, FIELD
- No hardcoded `require_role("ADMIN")` — use `require_permission("code")`
- Permission checks centralized in `permission_manager.py`
- API authorization via `require_permission()` / `require_api_permission()` dependencies
- Frontend route guards via `<PrivateRoute menuKey="...">` 
- Frontend component guards via `<MenuGate>`, `<PermissionGate>`, `<FieldGate>`

---

## Frontend Technology Stack

| Technology | Purpose |
|-----------|---------|
| React 19 | UI framework |
| TypeScript (strict) | Language |
| PrimeReact | Component library |
| Redux Toolkit | Global state |
| TanStack Query | Server state |
| React Router v7 | Routing |
| Vite | Build tool |
| Zod | Form validation |
| React Hook Form | Form management |

### Frontend Architecture

```
src/
├── app/          # Store, router, layouts
├── features/     # Feature modules (auth, user-management, rbac-admin)
├── core/         # Cross-cutting (rbac hooks/gates)
├── shared/       # Reusable components, services, utilities
└── assets/       # Styles, theme overrides
```

### Rules

- Feature-based structure
- Reusable components in `shared/`
- No API calls directly in components — use custom hooks or API modules
- Strong typing — no `any` type
- Separate presentation and business logic
- Components should be small, reusable, testable

### State Management

| Type | Tool |
|------|------|
| Global State | Redux Toolkit |
| Server State | TanStack Query |
| Form State | React Hook Form |

---

## API Standards

### Response Formats

All API responses follow consistent structure.

**Success (single item):**
```json
{ "id": "uuid", "username": "...", ... }
```

**Success (list with pagination):**
```json
{ "users": [...], "total": 100, "skip": 0, "limit": 20 }
```

**Error:**
```json
{ "detail": "Error message" }
```

### Validation Errors (422):
```json
{ "detail": [{ "loc": ["body", "field"], "msg": "...", "type": "..." }] }
```

---

## Database Standards

- PostgreSQL with async SQLAlchemy (asyncpg driver)
- Normalize data, use foreign keys, add indexes
- Soft delete where needed
- All models inherit from `BaseModel` (includes audit columns)

### Standard Audit Columns (via AuditMixin)

| Column | Auto-populated |
|--------|---------------|
| id | UUID, generated on create |
| created_by | String, set on create |
| created_date | UTC timestamp, set on create |
| modified_by | String, set on create/update |
| modified_date | UTC timestamp, set on create/update |

### Automatic Audit Logging

All INSERT/UPDATE/DELETE operations are automatically captured in `audit_logs` table via SQLAlchemy `before_flush` event listener. No manual instrumentation needed.

---

## Logging Standards

Every API request is logged with:
- Correlation ID
- Method + path
- Duration (ms)
- Status code
- Client IP

All domain operations should log: START, END, ERROR with structured JSON format.

Never expose sensitive information (passwords, tokens) in logs.

---

## Error Handling Standards

Centralized exception handling via `ExceptionHandlerMiddleware`.

Standard exception types:
- `HTTPException(401)` — Unauthorized
- `HTTPException(403)` — Forbidden (permission denied)
- `HTTPException(404)` — Not found
- `HTTPException(409)` — Conflict (duplicate)
- `HTTPException(422)` — Validation error

All errors return consistent JSON response with `detail` field.

---

## Security Rules

- All endpoints require authentication (except `/auth/login`, `/auth/microsoft/*`)
- Authorization via `require_permission()` — never hardcode role names
- JWT tokens stored in memory (not localStorage) — XSS protection
- bcrypt for password hashing
- Input validation on all request bodies (Pydantic)
- CORS configured for specific origins only
- Audit trail for all data changes (automatic)
- No secrets in code — use environment variables / `.env`

---

## Code Quality Standards

### Python
- Type hints mandatory
- Docstrings on all public functions/classes
- Ruff linter (line-length 100)
- MyPy strict mode

### TypeScript/React
- ESLint compliant
- Strict TypeScript (no `any`)
- Components use PrimeReact design system

### General
- DRY, KISS, SOLID
- Secure by design
- Never provide partial implementations
- Always generate production-ready code
- Always preserve existing architecture patterns

---

## Output Requirements

When implementing a feature, provide:
1. Solution overview
2. Architecture impact assessment
3. Database changes (if any)
4. Backend implementation (following layer separation)
5. Frontend implementation (following feature structure)
6. Security considerations
7. How to test

Act as an enterprise architect first and a code generator second.
