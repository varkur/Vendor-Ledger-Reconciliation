# Enterprise Audit Logging Architecture

## Overview

This document describes the automatic, table-level audit logging system that captures **before and after snapshots** for every INSERT, UPDATE, and DELETE operation across all database tables. The system provides:

1. **Automatic change detection** — No manual instrumentation required per model
2. **Before/After snapshots** — Full row state captured as JSON (old_value / new_value)
3. **Actor attribution** — Every change linked to the user who made it
4. **Changed column tracking** — UPDATE operations record exactly which columns were modified
5. **Transactional consistency** — Audit records committed atomically with the data change
6. **Non-intrusive design** — Audit failures are logged but never break business operations

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                        HTTP REQUEST                                  │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │             AuditContextMiddleware                            │   │
│  │  • Extracts user_id, username from request.state             │   │
│  │  • Extracts IP (x-forwarded-for or client.host)              │   │
│  │  • Extracts user-agent header                                │   │
│  │  • Sets request-scoped context via contextvars               │   │
│  └──────────────────────────┬───────────────────────────────────┘   │
│                             │                                       │
│                    ┌────────▼────────┐                               │
│                    │  audit_context  │  (ContextVar per request)     │
│                    │  • actor_id     │                               │
│                    │  • username     │                               │
│                    │  • ip_address   │                               │
│                    │  • user_agent   │                               │
│                    │  • tenant_id    │                               │
│                    └────────┬────────┘                               │
│                             │                                       │
└─────────────────────────────┼───────────────────────────────────────┘
                              │
┌─────────────────────────────┼───────────────────────────────────────┐
│                     SQLAlchemy Session                               │
│                             │                                       │
│  ┌──────────────────────────▼──────────────────────────────────┐    │
│  │              before_flush Event Listener                     │    │
│  │                                                             │    │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐        │    │
│  │  │ session.new │  │session.dirty│  │session.deleted│       │    │
│  │  │  (INSERTS)  │  │  (UPDATES)  │  │  (DELETES)   │       │    │
│  │  └──────┬──────┘  └──────┬──────┘  └──────┬───────┘       │    │
│  │         │                 │                 │               │    │
│  │         ▼                 ▼                 ▼               │    │
│  │  ┌─────────────────────────────────────────────────────┐   │    │
│  │  │           Serialize old/new state to JSON           │   │    │
│  │  │           Create AuditLogModel entries              │   │    │
│  │  │           Add to same session (same TX)             │   │    │
│  │  └─────────────────────────────────────────────────────┘   │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                             │                                       │
│                    ┌────────▼────────┐                               │
│                    │  session.commit │ (audit + data in one TX)      │
│                    └────────┬────────┘                               │
│                             │                                       │
└─────────────────────────────┼───────────────────────────────────────┘
                              │
┌─────────────────────────────┼───────────────────────────────────────┐
│                     DATABASE (PostgreSQL)                            │
│                                                                     │
│  ┌───────────┐  ┌──────────────┐  ┌────────────────┐               │
│  │  users    │  │ user_details │  │    tenants     │               │
│  └───────────┘  └──────────────┘  └────────────────┘               │
│  ┌───────────┐  ┌──────────────┐  ┌────────────────┐               │
│  │  roles    │  │ permissions  │  │role_permissions│               │
│  └───────────┘  └──────────────┘  └────────────────┘               │
│  ┌───────────────────┐                                              │
│  │ role_assignments  │                                              │
│  └───────────────────┘                                              │
│                             │                                       │
│                             ▼                                       │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │              audit_logs (append-only, immutable)              │   │
│  │                                                              │   │
│  │  • id (UUID PK)         • resource_type (table name)         │   │
│  │  • actor_id             • resource_id (row PK)               │   │
│  │  • actor_username       • old_value (JSON — before)          │   │
│  │  • action (INSERT/      • new_value (JSON — after)           │   │
│  │    UPDATE/DELETE)        • extra_data (changed_columns)       │   │
│  │  • tenant_id            • ip_address, user_agent             │   │
│  │  • created_at (UTC)                                          │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## How It Works

### 1. Request Enters → Context Set

When an HTTP request arrives, `AuditContextMiddleware` runs after authentication and stores the actor's identity into a Python `ContextVar`. This is async-safe and request-scoped — each concurrent request has its own context.

### 2. Business Logic Modifies Data

Application code creates, updates, or deletes model instances via the SQLAlchemy session as normal. No extra code is needed — the audit system is transparent.

### 3. Before Flush → Snapshots Captured

When `session.commit()` is called, SQLAlchemy fires the `before_flush` event. The audit listener iterates over:

| Collection | Action | What's Captured |
|------------|--------|-----------------|
| `session.new` | INSERT | `new_value` = full row after creation |
| `session.dirty` | UPDATE | `old_value` = previous state, `new_value` = new state, `changed_columns` |
| `session.deleted` | DELETE | `old_value` = full row before deletion |

### 4. Audit Entries Written in Same Transaction

Audit log rows are added to the same session and committed atomically. If the business operation rolls back, the audit entries roll back too — no phantom audit records.

### 5. Request Ends → Context Cleared

`AuditContextMiddleware` clears the context in its `finally` block, preventing leakage between requests.

---

## Database Schema

### audit_logs Table

| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID (PK) | Unique entry identifier |
| `actor_id` | UUID (nullable, indexed) | User who made the change |
| `actor_username` | VARCHAR(255) (indexed) | Denormalized for fast querying |
| `action` | VARCHAR(50) (indexed) | INSERT, UPDATE, or DELETE |
| `resource_type` | VARCHAR(100) (indexed) | Table name (e.g., `users`, `roles`) |
| `resource_id` | VARCHAR(100) | Primary key of the affected row |
| `tenant_id` | UUID (nullable, indexed) | Tenant context |
| `old_value` | TEXT (JSON) | Full row state **before** the change |
| `new_value` | TEXT (JSON) | Full row state **after** the change |
| `ip_address` | VARCHAR(45) | Client IP address |
| `user_agent` | VARCHAR(512) | Client user-agent string |
| `extra_data` | TEXT (JSON) | Metadata (e.g., `{"changed_columns": [...]}`) |
| `created_at` | TIMESTAMPTZ (indexed) | When the change occurred (UTC) |

### Design Constraints

- **Append-only**: No UPDATE or DELETE operations permitted on `audit_logs`
- **No foreign keys**: Audit table has no FK constraints (survives if referenced rows are deleted)
- **Does NOT inherit BaseModel**: Avoids the `modified_date`/`modified_by` fields that imply mutability

---

## Audit Entry Examples

### INSERT — New User Created

```json
{
  "id": "a1b2c3d4-...",
  "actor_id": "admin-uuid-...",
  "actor_username": "admin",
  "action": "INSERT",
  "resource_type": "users",
  "resource_id": "new-user-uuid-...",
  "old_value": null,
  "new_value": {
    "id": "new-user-uuid-...",
    "username": "john.doe",
    "is_active": "True",
    "is_blocked": "False",
    "is_validate_ad": "True",
    "created_by": "admin",
    "created_date": "2026-06-18T10:30:00+00:00"
  },
  "extra_data": null,
  "ip_address": "192.168.1.100",
  "created_at": "2026-06-18T10:30:00+00:00"
}
```

### UPDATE — User Blocked

```json
{
  "id": "e5f6g7h8-...",
  "actor_id": "admin-uuid-...",
  "actor_username": "admin",
  "action": "UPDATE",
  "resource_type": "users",
  "resource_id": "user-uuid-...",
  "old_value": {
    "id": "user-uuid-...",
    "username": "john.doe",
    "is_active": "True",
    "is_blocked": "False",
    "modified_by": "system",
    "modified_date": "2026-06-15T08:00:00+00:00"
  },
  "new_value": {
    "id": "user-uuid-...",
    "username": "john.doe",
    "is_active": "True",
    "is_blocked": "True",
    "modified_by": "admin",
    "modified_date": "2026-06-18T11:00:00+00:00"
  },
  "extra_data": "{\"changed_columns\": [\"is_blocked\", \"modified_by\", \"modified_date\"]}",
  "ip_address": "192.168.1.100",
  "created_at": "2026-06-18T11:00:00+00:00"
}
```

### DELETE — Role Removed

```json
{
  "id": "i9j0k1l2-...",
  "actor_id": "admin-uuid-...",
  "actor_username": "admin",
  "action": "DELETE",
  "resource_type": "roles",
  "resource_id": "role-uuid-...",
  "old_value": {
    "id": "role-uuid-...",
    "code": "TEMP_ROLE",
    "name": "Temporary Role",
    "is_system": "False",
    "is_active": "True"
  },
  "new_value": null,
  "extra_data": null,
  "ip_address": "192.168.1.100",
  "created_at": "2026-06-18T12:00:00+00:00"
}
```

---

## File Structure

```
backend/src/
├── api/middleware/
│   └── audit_context_middleware.py     # Sets actor context per request
├── domain/entities/
│   └── audit_log.py                    # AuditAction enum (INSERT/UPDATE/DELETE + domain actions)
├── infrastructure/
│   ├── database/
│   │   ├── audit_context.py            # ContextVar: actor_id, username, IP, tenant
│   │   ├── audit_listener.py           # before_flush event handler (core engine)
│   │   ├── session.py                  # Registers listener on session factory
│   │   └── models/
│   │       └── audit_log_model.py      # SQLAlchemy model (append-only)
│   └── security/
│       └── audit_service.py            # Manual audit helper (convenience methods)
```

---

## Tables Covered

All models inheriting from `BaseModel` are automatically audited:

| Table | Audited | Notes |
|-------|---------|-------|
| `users` | ✅ | Username, status changes (password_hash redacted recommended) |
| `user_details` | ✅ | Employee AD data changes |
| `tenants` | ✅ | Tenant creation/updates |
| `roles` | ✅ | Role CRUD |
| `permissions` | ✅ | Permission definitions |
| `role_permissions` | ✅ | Permission grants/revocations |
| `role_assignments` | ✅ | User role assignments |
| `audit_logs` | ❌ | Excluded (prevents infinite recursion) |

---

## Excluded Tables

The following are excluded from automatic audit logging:

| Table | Reason |
|-------|--------|
| `audit_logs` | Self-referential — would cause infinite recursion |

To add more exclusions, update the `EXCLUDED_TABLES` set in `audit_listener.py`:

```python
EXCLUDED_TABLES = {"audit_logs", "session_tokens", "cache_entries"}
```

---

## Context Flow

### How Actor Identity Propagates

```
HTTP Request
    │
    ▼
┌─────────────────────────────────┐
│  Auth Middleware                 │  ← Validates JWT, sets request.state.user_id
└────────────────┬────────────────┘
                 │
                 ▼
┌─────────────────────────────────┐
│  AuditContextMiddleware         │  ← Reads request.state → sets ContextVar
└────────────────┬────────────────┘
                 │
                 ▼
┌─────────────────────────────────┐
│  Route Handler / Service Layer  │  ← Business logic (no audit awareness needed)
└────────────────┬────────────────┘
                 │
                 ▼
┌─────────────────────────────────┐
│  session.commit()               │  ← Triggers before_flush
└────────────────┬────────────────┘
                 │
                 ▼
┌─────────────────────────────────┐
│  Audit Listener                 │  ← Reads ContextVar → creates audit entries
└─────────────────────────────────┘
```

### Background Jobs / Scripts

For operations outside HTTP requests (Celery tasks, management scripts), set the context manually:

```python
from src.infrastructure.database.audit_context import set_audit_context

set_audit_context(
    actor_username="celery-worker",
    ip_address="internal",
)

# ... perform database operations ...
# Audit entries will show actor_username="celery-worker"
```

---

## Usage Examples

### No Code Needed (Automatic)

Any normal SQLAlchemy operation is automatically audited:

```python
# This INSERT is automatically captured
user = UserModel(username="jane.doe", password_hash="...", role="USER")
session.add(user)
await session.commit()
# → audit_logs row: action=INSERT, resource_type=users, new_value={...}

# This UPDATE is automatically captured
user.is_blocked = True
await session.commit()
# → audit_logs row: action=UPDATE, old_value={is_blocked: False}, new_value={is_blocked: True}

# This DELETE is automatically captured
await session.delete(user)
await session.commit()
# → audit_logs row: action=DELETE, old_value={...}, new_value=null
```

### Manual Audit (Domain-Specific Events)

For business-level events that need richer context, use `AuditService` directly:

```python
from src.infrastructure.security.audit_service import AuditService
from src.domain.entities.audit_log import AuditAction

audit = AuditService(session)
await audit.log(
    actor_id=current_user.id,
    actor_username=current_user.username,
    action=AuditAction.LOGIN_SUCCESS,
    resource_type="Authentication",
    resource_id=current_user.username,
    ip_address=request.client.host,
    user_agent=request.headers.get("user-agent"),
)
```

---

## Querying Audit Logs

### Find All Changes to a Specific Row

```sql
SELECT action, old_value, new_value, actor_username, created_at
FROM audit_logs
WHERE resource_type = 'users'
  AND resource_id = 'user-uuid-here'
ORDER BY created_at DESC;
```

### Find All Changes by a Specific User

```sql
SELECT action, resource_type, resource_id, created_at
FROM audit_logs
WHERE actor_username = 'admin'
ORDER BY created_at DESC
LIMIT 100;
```

### Find All Deletes in Last 24 Hours

```sql
SELECT resource_type, resource_id, old_value, actor_username, created_at
FROM audit_logs
WHERE action = 'DELETE'
  AND created_at > NOW() - INTERVAL '24 hours'
ORDER BY created_at DESC;
```

### Find What Changed on a Specific Column

```sql
SELECT resource_id, old_value, new_value, actor_username, created_at
FROM audit_logs
WHERE resource_type = 'users'
  AND action = 'UPDATE'
  AND extra_data::jsonb -> 'changed_columns' ? 'is_blocked'
ORDER BY created_at DESC;
```

---

## Performance Considerations

| Aspect | Approach |
|--------|----------|
| **Write overhead** | Minimal — audit entries added in same flush cycle, single round-trip to DB |
| **Serialization** | Lightweight — only column values, no relationship traversal |
| **Table growth** | Partition `audit_logs` by `created_at` monthly for large deployments |
| **Indexing** | Indexed on `action`, `resource_type`, `actor_username`, `created_at` |
| **Exclusions** | Add high-churn tables (session tokens, cache) to `EXCLUDED_TABLES` |

### Recommended Partitioning (High Volume)

```sql
-- Convert to partitioned table (PostgreSQL 12+)
CREATE TABLE audit_logs_partitioned (
    LIKE audit_logs INCLUDING ALL
) PARTITION BY RANGE (created_at);

-- Monthly partitions
CREATE TABLE audit_logs_2026_06 PARTITION OF audit_logs_partitioned
    FOR VALUES FROM ('2026-06-01') TO ('2026-07-01');
```

---

## Security Considerations

| Concern | Mitigation |
|---------|------------|
| **Sensitive data in snapshots** | Consider redacting `password_hash` via a custom serializer override |
| **Immutability** | No UPDATE/DELETE permissions should be granted on `audit_logs` |
| **Access control** | Audit log API endpoints require ADMIN role |
| **Tamper resistance** | For compliance, consider write-once storage or cryptographic chaining |
| **Data retention** | Implement retention policy — archive old partitions to cold storage |

### Redacting Sensitive Fields

To exclude specific columns from audit snapshots, override serialization in `audit_listener.py`:

```python
# Columns to redact from audit snapshots (value replaced with "***")
REDACTED_COLUMNS = {
    "users": {"password_hash"},
}

def _model_to_dict(instance) -> dict:
    mapper = inspect(type(instance))
    table_name = instance.__tablename__
    redacted = REDACTED_COLUMNS.get(table_name, set())
    result = {}
    for col in mapper.columns:
        key = col.key
        if key in redacted:
            result[key] = "***"
        else:
            result[key] = _serialize_value(getattr(instance, key, None))
    return result
```

---

## Relationship to Existing Audit Service

The system has two complementary layers:

| Layer | When | Use Case |
|-------|------|----------|
| **Automatic (audit_listener)** | Every DB write | Full before/after for all tables — forensics, compliance |
| **Manual (AuditService)** | Explicit calls | Domain events (login, permission grants) with richer context |

Both write to the same `audit_logs` table. The automatic layer uses actions `INSERT`, `UPDATE`, `DELETE` while the manual layer uses domain-specific actions like `ROLE_ASSIGNED`, `LOGIN_SUCCESS`, etc.

---

## Setup

The audit system is self-activating. No additional setup is required beyond what's already in place:

1. **Session factory** registers the listener on import (`session.py`)
2. **Middleware** is added to the FastAPI app (`main.py`)
3. **audit_logs table** already exists from the RBAC migration

### Verify It's Working

```bash
# Make any API call that modifies data, then check:
SELECT * FROM audit_logs WHERE action IN ('INSERT', 'UPDATE', 'DELETE') ORDER BY created_at DESC LIMIT 10;
```

---

## Future Enhancements

| Enhancement | Description |
|-------------|-------------|
| **Diff view in UI** | Show side-by-side old/new JSON with highlighted changes |
| **Retention policies** | Auto-archive entries older than N months |
| **Streaming to SIEM** | Forward audit events to Elasticsearch/Splunk in real-time |
| **Cryptographic chaining** | Hash each entry with the previous — tamper-evident log |
| **Bulk operation batching** | Optimize for large batch imports (aggregate into single entry) |
| **Column-level redaction config** | YAML/env-driven list of columns to redact per table |
