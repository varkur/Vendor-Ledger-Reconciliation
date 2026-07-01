# Employee AD Service Integration

## Overview

The Employee AD Service integrates the Emcure Darwin Active Directory integrator as an external service within the enterprise architecture. It provides a proxy layer that exposes Darwin AD endpoints through our authenticated API, with ADMIN-only access control.

**Darwin Service Base URL:**
```
https://ad-prod-darwinsvc-prod.apps.emart.oneemcure.local/adintegratorservices/rest/v1
```

**OpenAPI Spec (Documentation UI):**
```
https://ad-prod-darwinsvc-prod.apps.emart.oneemcure.local/rest-doc/adintegratorservices/rest/v1
```

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│  Frontend (React + PrimeReact)                                      │
│                                                                     │
│  ┌─────────────┐   ┌──────────────┐   ┌─────────────────────────┐  │
│  │ MainLayout  │──▶│ AppRouter    │──▶│ EmployeeADServicePage   │  │
│  │ (Sidebar)   │   │ (PrivateRoute│   │ - Health Check          │  │
│  │ Services ▶  │   │  ADMIN)      │   │ - Validate Credentials  │  │
│  │  Employee AD│   └──────────────┘   │ - Get Selected Employees│  │
│  └─────────────┘                      │ - Get All Employees     │  │
│                                       │ - Get Hierarchy Data    │  │
│                                       └───────────┬─────────────┘  │
│                                                   │                 │
│  ┌────────────────────────────────────────────────▼──────────────┐  │
│  │ employeeAdApi.ts (Axios via apiClient)                        │  │
│  │ → POST /api/v1/services/employee-ad/validate-credentials      │  │
│  │ → POST /api/v1/services/employee-ad/selected-employees        │  │
│  │ → GET  /api/v1/services/employee-ad/employees                 │  │
│  │ → GET  /api/v1/services/employee-ad/hierarchy                 │  │
│  │ → GET  /api/v1/services/employee-ad/health                    │  │
│  └────────────────────────────────────────────────┬──────────────┘  │
└───────────────────────────────────────────────────┼─────────────────┘
                                                    │ Vite proxy /api → :8000
┌───────────────────────────────────────────────────▼─────────────────┐
│  Backend (FastAPI)                                                   │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │ API Layer: employee_ad_controller.py                          │   │
│  │ Router prefix: /api/v1/services/employee-ad                   │   │
│  │ Dependencies: [require_role("ADMIN")]                         │   │
│  └──────────────────────────────────────────┬───────────────────┘   │
│                                             │                       │
│  ┌──────────────────────────────────────────▼───────────────────┐   │
│  │ Infrastructure: employee_ad_client.py                         │   │
│  │ - EmployeeADClient (httpx async, verify=False, timeout)       │   │
│  │ - Custom exceptions: EmployeeADError, AuthError, Unavailable  │   │
│  └──────────────────────────────────────────┬───────────────────┘   │
│                                             │                       │
└─────────────────────────────────────────────┼───────────────────────┘
                                              │ HTTPS (SSL verify=False)
┌─────────────────────────────────────────────▼───────────────────────┐
│  Darwin AD Integrator Service (External)                            │
│  Base: /adintegratorservices/rest/v1                                 │
│  Endpoints:                                                         │
│    GET  /getemployees                                               │
│    POST /validatecredentials (multipart/form-data)                   │
│    POST /getselectedemployees (multipart/form-data)                  │
│    GET  /getHierarchyData                                           │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Backend

### File Structure

```
backend/src/
├── api/v1/
│   ├── endpoints/
│   │   └── employee_ad_controller.py    # REST controller (5 endpoints)
│   └── router.py                        # Registers employee_ad_router
├── config/
│   └── settings.py                      # EMPLOYEE_AD_BASE_URL setting
└── infrastructure/external/
    └── employee_ad/
        ├── __init__.py
        └── employee_ad_client.py        # httpx async client
```

### Configuration

| Environment Variable | Default | Description |
|---------------------|---------|-------------|
| `EMPLOYEE_AD_BASE_URL` | `https://ad-prod-darwinsvc-prod.apps.emart.oneemcure.local/adintegratorservices/rest/v1` | Darwin AD service base URL |

Set in `.env`:
```env
EMPLOYEE_AD_BASE_URL=https://ad-prod-darwinsvc-prod.apps.emart.oneemcure.local/adintegratorservices/rest/v1
```

### API Endpoints

All endpoints require JWT authentication with **ADMIN** role.

| Method | Path | Description | Darwin Endpoint |
|--------|------|-------------|-----------------|
| GET | `/api/v1/services/employee-ad/health` | Check Darwin reachability | Base URL ping |
| POST | `/api/v1/services/employee-ad/validate-credentials` | Validate employee credentials | `POST /validatecredentials` |
| POST | `/api/v1/services/employee-ad/selected-employees` | Get employees by IDs | `POST /getselectedemployees` |
| GET | `/api/v1/services/employee-ad/employees` | Get all employees | `GET /getemployees` |
| GET | `/api/v1/services/employee-ad/hierarchy` | Get hierarchy data | `GET /getHierarchyData` |

### Request/Response Examples

#### Health Check
```http
GET /api/v1/services/employee-ad/health
Authorization: Bearer <admin-jwt-token>
```
```json
{
  "service": "Employee AD (Darwin)",
  "configured": true,
  "base_url": "https://ad-prod-darwinsvc-prod.apps.emart.oneemcure.local/adintegratorservices/rest/v1",
  "status": "reachable",
  "status_code": 200,
  "url": "https://ad-prod-darwinsvc-prod.apps.emart.oneemcure.local/adintegratorservices/rest/v1"
}
```

#### Validate Credentials
```http
POST /api/v1/services/employee-ad/validate-credentials
Authorization: Bearer <admin-jwt-token>
Content-Type: application/json

{
  "employee_id": "93300040",
  "password": "secret"
}
```
```json
{
  "is_success": true,
  "is_valid_user": true,
  "raw_response": { "IsSuccess": true, "IsValidUser": true }
}
```

#### Get Selected Employees
```http
POST /api/v1/services/employee-ad/selected-employees
Authorization: Bearer <admin-jwt-token>
Content-Type: application/json

{
  "employee_ids": ["93300040", "93300041"]
}
```

#### Get All Employees
```http
GET /api/v1/services/employee-ad/employees
Authorization: Bearer <admin-jwt-token>
```

#### Get Hierarchy Data
```http
GET /api/v1/services/employee-ad/hierarchy
Authorization: Bearer <admin-jwt-token>
```

### Error Handling

The client maps Darwin HTTP errors to appropriate responses:

| Darwin Status | Our Response | Exception |
|---------------|-------------|-----------|
| 401, 403 | 401 Unauthorized | `EmployeeADAuthError` |
| Other HTTP errors | 502 Bad Gateway | `EmployeeADError` |
| Connection failure | 503 Service Unavailable | `EmployeeADUnavailableError` |

### Client Pattern

```python
class EmployeeADClient:
    """
    - Uses httpx.AsyncClient with verify=False (internal cert)
    - Timeout: 10s (health), 30s (validate), 120s (employees/hierarchy)
    - multipart/form-data for POST endpoints (matching Darwin OpenAPI spec)
    - Custom exception hierarchy for clean error mapping
    """
```

---

## Frontend

### File Structure

```
frontend/src/features/service-menu/
├── api/
│   └── employeeAdApi.ts          # Axios API calls to backend
├── hooks/
│   └── useEmployeeAD.ts          # TanStack Query hooks
├── pages/
│   └── EmployeeADServicePage.tsx  # Full verification UI
└── index.ts                       # Barrel export
```

### Navigation

- **Sidebar Section:** "Services"
- **Menu Item:** "Employee AD" (icon: `pi pi-id-card`)
- **Route:** `/services/employee-ad`
- **Visibility:** ADMIN role only (`visible: user?.role === 'ADMIN'`)
- **Route Guard:** `<PrivateRoute requiredRole="ADMIN">`

### Page Features

The `EmployeeADServicePage` provides a testing/verification UI with:

1. **Service Health Card** — Real-time connectivity status with auto-fetch on page load
2. **Validate Credentials** — Form with Employee ID + Password, shows validation result with raw JSON
3. **Get Selected Employees** — Comma-separated IDs input, displays raw JSON response
4. **Get All Employees** — Single button, displays raw JSON response
5. **Get Hierarchy Data** — Single button, displays raw JSON response

### Hooks (TanStack Query)

| Hook | Type | Description |
|------|------|-------------|
| `useEmployeeADHealth()` | Query | Auto-fetches health on mount, staleTime 10s |
| `useValidateCredentials()` | Mutation | Validates AD credentials |
| `useGetSelectedEmployees()` | Mutation | Fetches employees by IDs |
| `useGetEmployees()` | Mutation | Fetches all employees |
| `useGetHierarchy()` | Mutation | Fetches hierarchy data |

### API Client

Uses the shared `apiClient` (Axios instance at `/api/v1`) which:
- Automatically attaches Bearer JWT token
- Handles 401 token refresh
- Adds correlation ID header

---

## Security

| Layer | Mechanism |
|-------|-----------|
| Frontend Route | `<PrivateRoute requiredRole="ADMIN">` |
| Frontend Menu | `visible: user?.role === 'ADMIN'` |
| Backend Router | `dependencies=[Depends(require_role("ADMIN"))]` |
| Transport to Darwin | HTTPS with `verify=False` (internal CA) |

Non-ADMIN users:
- Cannot see the "Employee AD" menu item
- Are redirected to `/unauthorized` if they navigate directly
- Receive 403 from the backend API

---

## Darwin OpenAPI Spec Reference

```json
{
  "openapi": "3.0.1",
  "info": { "title": "Published EmployeeData", "version": "1.0.0" },
  "servers": [
    { "url": "https://ad-prod-darwinsvc-prod.apps.emart.oneemcure.local/adintegratorservices/rest/v1" }
  ],
  "paths": {
    "/getemployees": { "get": {} },
    "/validatecredentials": { "post": { "requestBody": "multipart/form-data: EmployeeId, Password" } },
    "/getselectedemployees": { "post": { "requestBody": "multipart/form-data: EmployeeIDs" } },
    "/getHierarchyData": { "get": {} }
  }
}
```
