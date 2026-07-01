# Validate AD & Employee AD Service Integration

## Overview

The enterprise-architecture project implements a dual authentication strategy controlled by the `is_validate_ad` flag on each user record:

- **`is_validate_ad = true`**: Login calls the Darwin AD service (`POST /validatecredentials`) to authenticate
- **`is_validate_ad = false`**: Login uses local bcrypt password verification

This allows imported employees to authenticate against Active Directory while manually created admin/system accounts use local passwords.

---

## Architecture Flow

```
┌──────────────────────────────────────────────────────────────────┐
│  Frontend Login Page                                              │
│  POST { username, password } → /api/v1/auth/login                │
└────────────────────────────────────┬─────────────────────────────┘
                                     │
┌────────────────────────────────────▼─────────────────────────────┐
│  auth_controller.py → AuthManager.login(username, password)       │
└────────────────────────────────────┬─────────────────────────────┘
                                     │
                        ┌────────────▼────────────┐
                        │  User lookup by username │
                        │  (user_repository)       │
                        └────────────┬────────────┘
                                     │
                         ┌───────────▼───────────┐
                         │  user.is_validate_ad?  │
                         └───┬───────────────┬───┘
                             │               │
                    TRUE     │               │  FALSE
                             ▼               ▼
              ┌──────────────────┐   ┌──────────────────┐
              │ _validate_with_  │   │ verify_password() │
              │ darwin()         │   │ (bcrypt local)    │
              └────────┬─────────┘   └────────┬─────────┘
                       │                      │
                       ▼                      │
         ┌─────────────────────────┐          │
         │ EmployeeADClient        │          │
         │ .validate_credentials() │          │
         └────────────┬────────────┘          │
                      │                       │
                      ▼                       │
         ┌─────────────────────────┐          │
         │ Darwin AD Service       │          │
         │ POST /validatecreds     │          │
         │ (multipart/form-data)   │          │
         └────────────┬────────────┘          │
                      │                       │
                      ▼                       ▼
              ┌───────────────────────────────────┐
              │  Check is_active, is_blocked       │
              │  Issue JWT access + refresh tokens │
              └───────────────────────────────────┘
```

---

## Backend Implementation

### 1. User Entity (`src/domain/entities/user.py`)

```python
@dataclass
class User(BaseEntity):
    username: str = field(default="")
    password_hash: str = field(default="", repr=False)
    is_active: bool = field(default=True)
    is_blocked: bool = field(default=False)
    is_validate_ad: bool = field(default=True)   # ← AD flag
    role: str = field(default="USER")
```

### 2. ORM Model (`src/infrastructure/database/models/user_model.py`)

```python
class UserModel(BaseModel):
    __tablename__ = "users"

    username: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(512), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_blocked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_validate_ad: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    role: Mapped[str] = mapped_column(String(50), default="USER", nullable=False)
```

### 3. Auth Manager (`src/infrastructure/security/auth_manager.py`)

The login method branches based on the flag:

```python
async def login(self, username: str, password: str) -> AuthTokenResponse:
    user = await self._user_repo.get_by_username(username)

    if user is None:
        raise InvalidCredentialsError()

    # Branch: AD validation vs local password
    if user.is_validate_ad:
        await self._validate_with_darwin(username, password)
    else:
        if not verify_password(password, user.password_hash):
            raise InvalidCredentialsError()

    if not user.is_active:
        raise UserInactiveError()
    if user.is_blocked:
        raise UserBlockedError()

    access_token = self._jwt.create_access_token(user.username, user.id)
    refresh_token = self._jwt.create_refresh_token(user.username, user.id)

    return AuthTokenResponse(access_token=access_token, refresh_token=refresh_token)
```

### 4. Darwin AD Validation (`_validate_with_darwin`)

```python
async def _validate_with_darwin(self, employee_id: str, password: str) -> None:
    """
    Validate credentials against Darwin AD service.
    Raises InvalidCredentialsError if Darwin says invalid or is unreachable.
    """
    from src.infrastructure.external.employee_ad.employee_ad_client import (
        EmployeeADClient,
        EmployeeADError,
    )

    client = EmployeeADClient()
    try:
        result = await client.validate_credentials(employee_id, password)
        if not result.is_valid_user:
            raise InvalidCredentialsError()
    except EmployeeADError as exc:
        logger.error("Darwin AD validation failed for %s: %s", employee_id, exc)
        raise InvalidCredentialsError()
```

### 5. Employee AD Client (`src/infrastructure/external/employee_ad/employee_ad_client.py`)

```python
async def validate_credentials(self, employee_id: str, password: str) -> EmployeeValidationResult:
    """
    POST multipart/form-data to /validatecredentials.
    
    Request format (matching Darwin OpenAPI spec):
        Content-Type: multipart/form-data
        Fields:
            - EmployeeId: string
            - Password: string
    
    Response:
        { "IsSuccess": true/false, "IsValidUser": true/false, ... }
    """
    url = f"{self._base_url}/validatecredentials"

    async with httpx.AsyncClient(verify=False, timeout=30) as client:
        response = await client.post(
            url,
            files={
                "EmployeeId": (None, employee_id),
                "Password": (None, password),
            },
            headers={"accept": "application/json"},
        )
        response.raise_for_status()
        data = response.json()
        return EmployeeValidationResult(
            is_success=bool(data.get("IsSuccess")),
            is_valid_user=bool(data.get("IsValidUser")),
            raw_response=data,
        )
```

---

## Darwin AD Service API Reference

**Base URL**: `https://ad-prod-darwinsvc-prod.apps.emart.oneemcure.local/adintegratorservices/rest/v1`

### POST /validatecredentials

Validates an employee's Active Directory credentials.

**Request:**
```
Content-Type: multipart/form-data

Fields:
  EmployeeId: "93300040"
  Password: "user_password"
```

**Response (Success):**
```json
{
  "IsSuccess": true,
  "IsValidUser": true
}
```

**Response (Invalid Credentials):**
```json
{
  "IsSuccess": true,
  "IsValidUser": false
}
```

### POST /getselectedemployees

Fetches employee profile data by IDs (used during import).

**Request:**
```
Content-Type: multipart/form-data

Fields:
  EmployeeIDs: "93300040,93300041"
```

**Response:**
```json
{
  "employeeData": [
    {
      "employee_id": "93300040",
      "first_name": "Irshad",
      "middle_name": "Minhajuddin",
      "last_name": "Shaikh",
      "company_email_id": "user@darwinbox.in",
      "designation_title": "Indirect Services - SAP",
      "department": "IT Enterprises (P05_IG_ITD_ITE)",
      "business_unit": "P05 - Information Technology",
      "group_company": "Indirect Services - IT General",
      "office_location": "Hinjawadi (Supply Chain Office) Pune",
      "direct_manager_employee_id": "10015309",
      "direct_manager_name": "Siddharth Amarnath",
      "direct_manager_email": "Siddharth.Amarnath@emcure.com",
      "employee_status": "Active",
      "job_level": "CW01 - Contract Worker",
      "division": "Indirect Services",
      "office_state": "Maharashtra",
      "office_city": "Pune",
      "gender": "Male"
    }
  ]
}
```

### GET /getemployees

Returns all employee records. No request body required.

### GET /getHierarchyData

Returns organizational hierarchy data. No request body required.

---

## Database Schema

### users table

| Column | Type | Default | Description |
|--------|------|---------|-------------|
| id | UUID | auto | Primary key |
| username | VARCHAR(255) | - | Unique, maps to employee_id for AD users |
| password_hash | VARCHAR(512) | - | BCrypt hash (unused for AD users after import) |
| is_active | BOOLEAN | true | Account active flag |
| is_blocked | BOOLEAN | false | Account blocked flag |
| is_validate_ad | BOOLEAN | true | **AD authentication flag** |
| role | VARCHAR(50) | USER | ADMIN/MANAGER/USER |
| created_by | VARCHAR(255) | system | Audit field |
| created_date | TIMESTAMP | now() | Audit field |
| modified_by | VARCHAR(255) | system | Audit field |
| modified_date | TIMESTAMP | now() | Audit field |

### user_details table (one-to-one with users)

| Column | Type | Description |
|--------|------|-------------|
| id | UUID | Primary key |
| user_id | UUID (FK → users.id) | Unique, cascade delete |
| employee_id | VARCHAR(50) | Darwin employee ID |
| employee_name | VARCHAR(255) | Full name |
| first_name | VARCHAR(255) | |
| middle_name | VARCHAR(255) | |
| last_name | VARCHAR(255) | |
| email | VARCHAR(255) | Company email |
| designation_title | VARCHAR(255) | Job title |
| department | VARCHAR(255) | |
| business_unit | VARCHAR(255) | |
| group_company | VARCHAR(255) | |
| location | VARCHAR(255) | Office location |
| region | VARCHAR(255) | State |
| zone | VARCHAR(255) | City |
| grade | VARCHAR(50) | Job level |
| office_mobile_no | VARCHAR(50) | |
| personal_mobile_no | VARCHAR(50) | |
| date_of_joining | VARCHAR(50) | |
| reporting_manager | VARCHAR(255) | |
| direct_manager_employee_id | VARCHAR(50) | |
| direct_manager_name | VARCHAR(255) | |
| direct_manager_email | VARCHAR(255) | |
| sap_user_id | VARCHAR(50) | |
| division_id | VARCHAR(50) | |
| territory_id | VARCHAR(50) | |
| + audit columns | | BaseModel fields |

---

## Employee Import Flow

```
User Management Page
  → Click "Fetch Employee" button
  → Dialog: Enter comma-separated employee IDs
  → Click "Import"
        │
        ▼
POST /api/v1/users/import-employees { employee_ids: ["93300040"] }
        │
        ▼
Backend (employee_import_controller.py):
  1. Call Darwin POST /getselectedemployees (multipart: EmployeeIDs)
  2. For each employee in response:
     a. Check if user exists (SELECT WHERE username = employee_id)
     b. IF NOT EXISTS:
        - INSERT into users: username=employee_id, password=bcrypt(employee_id),
          role=USER, is_validate_ad=true
     c. IF EXISTS:
        - Password left unchanged
     d. UPSERT into user_details: all Darwin fields
  3. Return summary: { created: N, updated: N, failed: N, results: [...] }
```

---

## Frontend Integration

### User Management Page Buttons

| Button | Action |
|--------|--------|
| New User | Opens create dialog (username, password, role, validate_ad toggle) |
| Fetch Employee | Opens import dialog (comma-separated IDs → import from Darwin) |
| Edit (pencil icon) | Opens edit dialog (role, active, blocked, validate_ad toggle) |

### Login Flow (Frontend)

The frontend login form is unchanged — it always sends `{ username, password }` to `/api/v1/auth/login`. The backend decides whether to validate locally or against Darwin based on the user's `is_validate_ad` flag. This is transparent to the frontend.

---

## Configuration

### Environment Variable

```env
EMPLOYEE_AD_BASE_URL=https://ad-prod-darwinsvc-prod.apps.emart.oneemcure.local/adintegratorservices/rest/v1
```

### Settings (`src/config/settings.py`)

```python
EMPLOYEE_AD_BASE_URL: str = Field(
    default="https://ad-prod-darwinsvc-prod.apps.emart.oneemcure.local/adintegratorservices/rest/v1",
    description="Base URL for the Darwin AD integrator service",
)
```

---

## Security Considerations

| Concern | Implementation |
|---------|---------------|
| AD validation timeout | 30 seconds — prevents login hanging |
| AD service down | Raises InvalidCredentialsError (fail-closed) |
| SSL certificate | `verify=False` (internal CA, not public) |
| Default password | Set to employee_id on import (AD validates, so local hash unused) |
| Access control | All Employee AD endpoints require ADMIN role |
| Token refresh | Uses local JWT — no AD call on refresh |

---

## File Reference

| File | Purpose |
|------|---------|
| `src/infrastructure/security/auth_manager.py` | Dual auth logic (AD vs local) |
| `src/infrastructure/external/employee_ad/employee_ad_client.py` | Darwin HTTP client |
| `src/api/v1/endpoints/auth_controller.py` | Login endpoint |
| `src/api/v1/endpoints/employee_import_controller.py` | Import/upsert endpoint |
| `src/api/v1/endpoints/employee_ad_controller.py` | Service verification endpoints |
| `src/domain/entities/user.py` | User entity with `is_validate_ad` |
| `src/infrastructure/database/models/user_model.py` | ORM model |
| `src/infrastructure/database/models/user_details_model.py` | Employee details ORM |
| `scripts/seed_data.py` | Admin seed with `is_validate_ad=False` |
| `frontend/src/features/user-management/components/UserForm.tsx` | Create form with AD toggle |
| `frontend/src/features/user-management/components/EditUserDialog.tsx` | Edit form with AD toggle |
| `frontend/src/features/user-management/components/ImportEmployeeDialog.tsx` | Import dialog |
| `frontend/src/features/service-menu/pages/EmployeeADServicePage.tsx` | Service testing UI |
