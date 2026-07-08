# Design Document: VLR Complete Rebuild

## Overview

This design specifies the architecture for a complete rebuild of the Vendor Ledger Reconciliation (VLR) system. The system reconciles company ledger entries (from SAP) against vendor-provided statements through a 10-step workflow. The architecture leverages existing codebase patterns (domain services, repository interfaces, Celery tasks, React Query frontend) while introducing new modules for data transformation, column mapping, workflow orchestration, and reporting.

## Architecture

### System Architecture

The system follows a layered architecture with clear separation of concerns:

```
┌─────────────────────────────────────────────────────────────┐
│                    Frontend (React/PrimeReact)                │
│  React Query │ Redux Toolkit │ Axios │ Feature-based modules │
├─────────────────────────────────────────────────────────────┤
│                    API Layer (FastAPI v1)                     │
│         REST endpoints │ Auth middleware │ Rate limiting      │
├─────────────────────────────────────────────────────────────┤
│                  Domain Services Layer                        │
│  DataTransformationEngine │ ReconciliationEngine │ Workflow   │
│  ColumnMappingEngine │ EmailService │ ReportService          │
├─────────────────────────────────────────────────────────────┤
│               Infrastructure Layer                           │
│  SQLAlchemy Repos │ Celery Tasks │ SAP Adapter │ SMTP        │
├─────────────────────────────────────────────────────────────┤
│                  Data Layer (PostgreSQL + Redis)              │
└─────────────────────────────────────────────────────────────┘
```

### Key Design Decisions

1. **Refactor over rewrite**: Extend existing services (ReconciliationEngineService, VendorService, FileParserService) rather than replacing them
2. **Adapter pattern for SAP**: Abstract interface enables mock testing and future RFC adapter swap
3. **Celery state machine**: Workflow steps execute as Celery tasks with Redis-backed state tracking
4. **Append-only audit**: Audit log table has no UPDATE/DELETE permissions at database level
5. **React Query for data fetching**: All frontend pages use React Query with loading/error/retry patterns

## Components and Interfaces

### Backend Components

#### 1. Data Transformation Engine

**Location**: `backend/src/domain/services/vlr/data_transformation_service.py`

Responsible for invoice number derivation (ZUONR > XBLNR > BELNR fallback), CLEAN function application, sign adjustment (SHKZG → positive/negative), balance calculations, TDS tagging/linking, multi-currency handling, and document type classification.

```python
class DataTransformationService:
    """Transforms raw SAP ledger data into reconciliation-ready format."""

    def __init__(self, config_repository: IConfigRepository):
        self._config_repo = config_repository

    def derive_invoice_number(self, entry: RawSAPEntry) -> DerivedInvoice:
        """Derive invoice number using ZUONR > XBLNR > BELNR priority."""
        ...

    def clean_reference(self, raw_value: str) -> str:
        """Strip leading zeros, special characters, whitespace."""
        ...

    def apply_sign_adjustment(self, amount: Decimal, shkzg: str) -> Decimal:
        """H → positive, S → negative."""
        ...

    def calculate_opening_balance(
        self, entries: list[LedgerEntry], period_start: date, side: str
    ) -> Decimal:
        """Sum of sign-adjusted open items before period start."""
        ...

    def calculate_closing_balance(
        self, opening_balance: Decimal, entries: list[LedgerEntry],
        period_start: date, period_end: date
    ) -> Decimal:
        """Opening balance + net movement within period."""
        ...

    def tag_tds_entries(self, entries: list[LedgerEntry]) -> list[LedgerEntry]:
        """Tag TDS entries and link to parent invoices by reference."""
        ...

    def classify_document_type(self, doc_type: str) -> str:
        """Classify document type using configurable mapping."""
        ...
```

#### 2. SAP Adapter Interface

**Location**: `backend/src/domain/interfaces/sap_adapter_interface.py`

Extends the existing `SAPConnectorService` with an abstract interface enabling pluggable implementations.

```python
from abc import ABC, abstractmethod

class SAPAdapterInterface(ABC):
    """Abstract SAP adapter supporting All Items and Open Items pulls."""

    @abstractmethod
    async def pull_all_items(
        self, vendor_code: str, company_code: str,
        date_from: date, date_to: date,
        doc_type_filters: list[str] | None = None
    ) -> list[SAPLedgerEntry]:
        """Pull all items (cleared and open) from SAP."""
        ...

    @abstractmethod
    async def pull_open_items(
        self, vendor_code: str, company_code: str,
        key_date: date,
        doc_type_filters: list[str] | None = None
    ) -> list[SAPLedgerEntry]:
        """Pull only uncleared items as of key_date."""
        ...

class RealSAPAdapter(SAPAdapterInterface):
    """Production adapter wrapping existing SAPConnectorService."""
    ...

class MockSAPAdapter(SAPAdapterInterface):
    """Test adapter returning realistic data shapes."""
    ...
```

#### 3. Column Mapping Engine

**Location**: `backend/src/domain/services/vlr/column_mapping_service.py`

Handles file preview, column-to-tag assignment, template persistence per vendor, and auto-mapping intelligence based on header library.

```python
class ColumnMappingService:
    """Maps uploaded vendor statement columns to transaction type tags."""

    def __init__(
        self,
        template_repository: IColumnMappingTemplateRepository,
        header_library: HeaderLibrary,
    ):
        self._template_repo = template_repository
        self._header_library = header_library

    def generate_preview(self, file_content: bytes, filename: str) -> FilePreview:
        """Return first 10 rows of uploaded file."""
        ...

    def auto_map_columns(self, headers: list[str]) -> list[ColumnSuggestion]:
        """Compare headers against known library, assign confidence scores."""
        ...

    async def apply_template(self, vendor_id: UUID) -> ColumnMapping | None:
        """Load and apply saved template for vendor."""
        ...

    async def save_template(
        self, vendor_id: UUID, mapping: ColumnMapping
    ) -> None:
        """Persist column mapping as vendor template."""
        ...
```

#### 4. Workflow Orchestrator

**Location**: `backend/src/domain/services/vlr/workflow_orchestrator_service.py`

Celery-based state machine managing the 10-step reconciliation lifecycle with SLA monitoring, rollback support, and step transition validation.

```python
class WorkflowStep(str, Enum):
    INITIATION = "initiation"
    SAP_PULL = "sap_pull"
    TRANSFORMATION = "transformation"
    FINANCE_REVIEW = "finance_review"
    COLUMN_MAPPING = "column_mapping"
    VENDOR_ENGAGEMENT = "vendor_engagement"
    AUTO_RECONCILIATION = "auto_reconciliation"
    EXCEPTION_RESOLUTION = "exception_resolution"
    FINANCE_APPROVAL = "finance_approval"
    VENDOR_SIGN_OFF = "vendor_sign_off"
    CLOSURE = "closure"

VALID_TRANSITIONS: dict[WorkflowStep, list[WorkflowStep]] = {
    WorkflowStep.INITIATION: [WorkflowStep.SAP_PULL],
    WorkflowStep.SAP_PULL: [WorkflowStep.TRANSFORMATION, WorkflowStep.INITIATION],
    WorkflowStep.TRANSFORMATION: [WorkflowStep.FINANCE_REVIEW, WorkflowStep.SAP_PULL],
    WorkflowStep.FINANCE_REVIEW: [WorkflowStep.COLUMN_MAPPING, WorkflowStep.TRANSFORMATION],
    WorkflowStep.COLUMN_MAPPING: [WorkflowStep.VENDOR_ENGAGEMENT, WorkflowStep.FINANCE_REVIEW],
    WorkflowStep.VENDOR_ENGAGEMENT: [WorkflowStep.AUTO_RECONCILIATION, WorkflowStep.COLUMN_MAPPING],
    WorkflowStep.AUTO_RECONCILIATION: [WorkflowStep.EXCEPTION_RESOLUTION, WorkflowStep.VENDOR_ENGAGEMENT],
    WorkflowStep.EXCEPTION_RESOLUTION: [WorkflowStep.FINANCE_APPROVAL, WorkflowStep.AUTO_RECONCILIATION],
    WorkflowStep.FINANCE_APPROVAL: [WorkflowStep.VENDOR_SIGN_OFF, WorkflowStep.EXCEPTION_RESOLUTION],
    WorkflowStep.VENDOR_SIGN_OFF: [WorkflowStep.CLOSURE, WorkflowStep.FINANCE_APPROVAL],
    WorkflowStep.CLOSURE: [],
}

class WorkflowOrchestratorService:
    """Celery-based state machine for 10-step reconciliation lifecycle."""

    def __init__(
        self,
        case_repository: ICaseRepository,
        sla_config: SLAConfiguration,
        notification_service: NotificationService,
    ):
        ...

    async def advance(self, case_id: UUID, target_step: WorkflowStep) -> CaseStatus:
        """Advance case to next step if transition is valid."""
        ...

    async def rollback(self, case_id: UUID, target_step: WorkflowStep) -> CaseStatus:
        """Rollback case to a previous step."""
        ...

    async def check_sla_violations(self) -> list[SLAViolation]:
        """Identify cases that have exceeded their step SLA."""
        ...
```

#### 5. Reconciliation Engine (Enhanced)

**Location**: `backend/src/domain/services/vlr/reconciliation_engine_service.py` (extend existing)

Adds Pass 6 (Date-proximity Match) and Pass 7 (Unmatched Remainder) to the existing 6-pass engine, making it 7 passes total per BRD requirements.

```python
# New pass added to existing MatchPassType enum:
class MatchPassType(IntEnum):
    EXACT = 1
    TOLERANCE = 2
    FUZZY_REFERENCE = 3
    ONE_TO_MANY = 4
    MANY_TO_ONE = 5
    DATE_PROXIMITY = 6  # NEW: Match by amount + date within N days
    UNMATCHED = 7       # Renumbered from 6 to 7
```

#### 6. Email Service (Enhanced)

**Location**: `backend/src/domain/services/vlr/notification_service.py` (extend existing)

Adds scheduled reminder logic (D3/D7/D10), escalation on exhaustion, approval notifications, and upload confirmations. Uses Jinja2 templates rendered from `backend/src/infrastructure/email/templates/`.

```python
class ReminderSchedule:
    """Defines reminder intervals: D3, D7, D10."""
    INTERVALS_DAYS = [3, 7, 10]
    MAX_REMINDERS = 3

class EmailNotificationService:
    """Enhanced notification service with Jinja2 templates and SMTP."""

    async def send_vendor_invite(self, case_id: UUID, portal_link: str) -> None:
        """Send invite with unique portal link."""
        ...

    async def send_scheduled_reminder(self, case_id: UUID, reminder_number: int) -> None:
        """Send D3/D7/D10 reminder based on schedule."""
        ...

    async def send_escalation(self, case_id: UUID, manager_email: str) -> None:
        """Escalate after all reminders exhausted."""
        ...

    async def send_approval_request(self, case_id: UUID, approver_email: str) -> None:
        """Notify finance user that approval is needed."""
        ...
```

#### 7. Report Service (Enhanced)

**Location**: `backend/src/domain/services/vlr/report_service.py` (extend existing)

Adds reconciliation summary (10-row format), aging analysis, exception reports, vendor status tracking, and MIS reports with PDF/Excel export.

```python
class ReportService:
    """Generates reconciliation reports in multiple formats."""

    def generate_reconciliation_summary(self, case_id: UUID) -> ReconciliationSummaryReport:
        """10-row format: Emcure Closing, adjustments, Vendor Closing, Net Diff."""
        ...

    def generate_aging_analysis(
        self, filters: AgingFilters
    ) -> AgingAnalysisReport:
        """Group by vendor/bucket/status. Buckets: 0-30, 31-60, 61-90, 91-180, 180+."""
        ...

    def generate_exception_report(self, filters: ExceptionFilters) -> ExceptionReport:
        """All unmatched/disputed items with resolution history."""
        ...

    def export_to_pdf(self, report: BaseReport) -> bytes:
        ...

    def export_to_excel(self, report: BaseReport) -> bytes:
        ...
```

#### 8. Recovery Service

**Location**: `backend/src/domain/services/vlr/recovery_service.py` (new)

Tracks recoverable amounts, manages follow-up reminders, and maintains a recovery register.

```python
class RecoveryStatus(str, Enum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    RECOVERED = "recovered"
    WRITTEN_OFF = "written_off"

class RecoveryService:
    """Manages recovery register and follow-up reminders."""

    async def create_recovery_item(self, data: RecoveryItemCreate) -> RecoveryItem:
        ...

    async def update_status(
        self, item_id: UUID, status: RecoveryStatus, notes: str
    ) -> RecoveryItem:
        ...

    async def get_overdue_items(self) -> list[RecoveryItem]:
        """Items past their follow-up date."""
        ...

    async def trigger_follow_up_reminders(self) -> int:
        """Auto-trigger reminders for overdue items. Returns count sent."""
        ...
```

#### 9. Audit Trail Service

**Location**: `backend/src/domain/services/vlr/audit_trail_service.py` (new)

Immutable event logging with search, pagination, and export. No UPDATE/DELETE operations permitted.

```python
class AuditEventType(str, Enum):
    LOGIN = "login"
    LOGOUT = "logout"
    CASE_CREATED = "case_created"
    STATUS_CHANGED = "status_changed"
    MATCH_OVERRIDE = "match_override"
    APPROVAL = "approval"
    REJECTION = "rejection"
    VENDOR_INTERACTION = "vendor_interaction"

class AuditTrailService:
    """Immutable audit event logging (append-only)."""

    async def log_event(self, event: AuditEvent) -> None:
        """Append an audit event. No update/delete exposed."""
        ...

    async def search(self, filters: AuditSearchFilters) -> PaginatedResult[AuditEvent]:
        """Search by user, date range, case_id, event_type."""
        ...

    async def export(self, filters: AuditSearchFilters, format: ExportFormat) -> bytes:
        """Export results as Excel or CSV."""
        ...
```

#### 10. Structured Logging Service

**Location**: `backend/src/infrastructure/logging/structured_logger.py` (new)

Cross-cutting JSON structured logging with correlation IDs.

```python
class StructuredLogger:
    """Emits JSON log entries with correlation_id, timestamp, service, operation, duration, outcome."""

    def log_operation(
        self, service_name: str, operation: str,
        duration_ms: float, outcome: str,
        correlation_id: str, error: str | None = None
    ) -> None:
        """Emit structured JSON log entry. Sensitive data is never included."""
        ...
```

### Frontend Components

#### 11. Dashboard Module

**Location**: `frontend/src/features/dashboard/`

Widget-based overview page with React Query hooks for real-time KPI data.

#### 12. Reconciliation Output View (5-tab)

**Location**: `frontend/src/features/track-reconciliation/components/ReconciliationOutput/`

Five tabs: Matched Items, Finance Confirmation Required, Unmatched-Company, Unmatched-Vendor, Differences Summary. Uses PrimeReact DataTable with sorting, filtering, pagination.

#### 13. Column Mapping UI

**Location**: `frontend/src/features/direct-reconciliation/components/ColumnMapping/`

File preview grid (10 rows), per-column dropdowns for tag assignment, auto-mapping suggestions with confidence badges, template save/load.

#### 14. Vendor Portal (Enhanced)

**Location**: `frontend/src/features/vendor-portal/`

Token-based authentication, file upload with progress, statement view, sign-off page. Portal links expire after 90 days.

### API Endpoints (New/Enhanced)

```
# Data Transformation
POST   /api/v1/vlr/transform/{case_id}         → Trigger transformation pipeline

# Column Mapping
POST   /api/v1/vlr/column-mapping/preview       → Upload file, return 10-row preview
POST   /api/v1/vlr/column-mapping/auto-map      → Get auto-mapping suggestions
POST   /api/v1/vlr/column-mapping/save-template → Save mapping template
GET    /api/v1/vlr/column-mapping/template/{vendor_id} → Get saved template

# Workflow
POST   /api/v1/vlr/workflow/{case_id}/advance    → Advance to next step
POST   /api/v1/vlr/workflow/{case_id}/rollback   → Rollback to previous step
GET    /api/v1/vlr/workflow/{case_id}/status      → Get current workflow status
GET    /api/v1/vlr/workflow/sla-violations        → List overdue cases

# Reconciliation Output
GET    /api/v1/vlr/reconciliation/{case_id}/matched       → Tab 1: Matched items
GET    /api/v1/vlr/reconciliation/{case_id}/confirmation  → Tab 2: Needs confirmation
GET    /api/v1/vlr/reconciliation/{case_id}/unmatched-company → Tab 3
GET    /api/v1/vlr/reconciliation/{case_id}/unmatched-vendor  → Tab 4
GET    /api/v1/vlr/reconciliation/{case_id}/summary       → Tab 5: Differences
POST   /api/v1/vlr/reconciliation/{case_id}/confirm       → Accept/reject match

# Dashboard
GET    /api/v1/vlr/dashboard/widgets             → All KPI widget data
GET    /api/v1/vlr/dashboard/recent-confirmations → Recent confirmations table

# Reports
GET    /api/v1/vlr/reports/reconciliation-summary/{case_id} → 10-row summary
GET    /api/v1/vlr/reports/aging-analysis         → Aging by vendor/bucket/status
GET    /api/v1/vlr/reports/exceptions             → Exception report
GET    /api/v1/vlr/reports/vendor-status          → Vendor progress tracking
GET    /api/v1/vlr/reports/mis                    → Monthly MIS report
GET    /api/v1/vlr/reports/export/{report_id}     → Download PDF/Excel

# Recovery
GET    /api/v1/vlr/recovery                       → List recovery items
POST   /api/v1/vlr/recovery                       → Create recovery item
PATCH  /api/v1/vlr/recovery/{item_id}             → Update status/notes
GET    /api/v1/vlr/recovery/{item_id}/follow-ups  → Follow-up log

# Audit Trail
GET    /api/v1/vlr/audit                          → Search audit events
GET    /api/v1/vlr/audit/export                   → Export filtered results

# Vendor Portal
POST   /api/v1/vlr/portal/validate-token          → Validate portal access token
POST   /api/v1/vlr/portal/upload                   → Upload vendor statement
GET    /api/v1/vlr/portal/statement/{case_id}      → View reconciliation results
POST   /api/v1/vlr/portal/sign-off/{case_id}       → Record vendor sign-off
```

### Repository Interfaces (New)

```python
class IColumnMappingTemplateRepository(ABC):
    """Persistence for column mapping templates per vendor."""
    async def get_by_vendor(self, vendor_id: UUID) -> ColumnMappingTemplate | None: ...
    async def save(self, template: ColumnMappingTemplate) -> None: ...
    async def delete(self, vendor_id: UUID) -> None: ...

class IRecoveryRepository(ABC):
    """Persistence for recovery register items."""
    async def create(self, data: dict) -> RecoveryItem: ...
    async def update(self, item_id: UUID, data: dict) -> RecoveryItem: ...
    async def list_overdue(self) -> list[RecoveryItem]: ...
    async def get_follow_ups(self, item_id: UUID) -> list[FollowUpEntry]: ...
    async def add_follow_up(self, item_id: UUID, entry: FollowUpEntry) -> None: ...

class IAuditTrailRepository(ABC):
    """Append-only audit event persistence."""
    async def append(self, event: AuditEvent) -> None: ...
    async def search(self, filters: AuditSearchFilters, pagination: PaginationParams) -> PaginatedResult: ...
    # NOTE: No update() or delete() methods - immutable by design

class IWorkflowRepository(ABC):
    """Workflow step status and SLA tracking."""
    async def get_step_history(self, case_id: UUID) -> list[WorkflowStepEntry]: ...
    async def record_step_transition(self, case_id: UUID, from_step: str, to_step: str) -> None: ...
    async def get_sla_violations(self) -> list[SLAViolation]: ...
```

## Data Models

### New Database Tables

#### `vlr_column_mapping_templates`

```python
class ColumnMappingTemplateModel(BaseModel):
    __tablename__ = "vlr_column_mapping_templates"

    vendor_id: Mapped[UUID] = mapped_column(ForeignKey("vlr_vendors.id"), unique=True)
    mapping_config: Mapped[dict] = mapped_column(JSON, nullable=False)
    # mapping_config: {"column_index": 0, "header": "Invoice No", "tag": "REFERENCE", "confidence": "High"}
    created_by: Mapped[str] = mapped_column(String(100))
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
```

#### `vlr_workflow_step_history`

```python
class WorkflowStepHistoryModel(BaseModel):
    __tablename__ = "vlr_workflow_step_history"

    case_id: Mapped[UUID] = mapped_column(ForeignKey("vlr_reconciliation_cases.id"))
    from_step: Mapped[str] = mapped_column(String(30), nullable=True)  # null for initial
    to_step: Mapped[str] = mapped_column(String(30), nullable=False)
    triggered_by: Mapped[str] = mapped_column(String(100), nullable=False)
    triggered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    sla_deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_rollback: Mapped[bool] = mapped_column(Boolean, default=False)
```

#### `vlr_sla_configurations`

```python
class SLAConfigurationModel(BaseModel):
    __tablename__ = "vlr_sla_configurations"

    step_name: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)
    sla_hours: Mapped[int] = mapped_column(Integer, nullable=False)
    escalation_email: Mapped[str | None] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
```

#### `vlr_recovery_items`

```python
class RecoveryItemModel(BaseModel):
    __tablename__ = "vlr_recovery_items"

    case_id: Mapped[UUID] = mapped_column(ForeignKey("vlr_reconciliation_cases.id"))
    vendor_id: Mapped[UUID] = mapped_column(ForeignKey("vlr_vendors.id"))
    amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="INR")
    status: Mapped[str] = mapped_column(String(20), default="open")
    # status: open, in_progress, recovered, written_off
    identified_date: Mapped[date] = mapped_column(Date, nullable=False)
    next_follow_up_date: Mapped[date | None] = mapped_column(Date)
    follow_up_interval_days: Mapped[int] = mapped_column(Integer, default=7)
    notes: Mapped[str | None] = mapped_column(Text)
```

#### `vlr_recovery_follow_ups`

```python
class RecoveryFollowUpModel(BaseModel):
    __tablename__ = "vlr_recovery_follow_ups"

    recovery_item_id: Mapped[UUID] = mapped_column(ForeignKey("vlr_recovery_items.id"))
    action_taken: Mapped[str] = mapped_column(Text, nullable=False)
    action_by: Mapped[str] = mapped_column(String(100), nullable=False)
    action_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    next_follow_up_date: Mapped[date | None] = mapped_column(Date)
```

#### `vlr_audit_events` (Append-Only)

```python
class AuditEventModel(BaseModel):
    __tablename__ = "vlr_audit_events"

    actor_id: Mapped[UUID | None] = mapped_column(UUID(as_uuid=True))
    actor_username: Mapped[str] = mapped_column(String(100), nullable=False)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    case_id: Mapped[UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    event_details: Mapped[dict] = mapped_column(JSON, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    ip_address: Mapped[str | None] = mapped_column(String(45))

    # NOTE: This table has a PostgreSQL REVOKE rule preventing UPDATE/DELETE
    # Retention: 7 years minimum (managed via partitioning or archival policy)
```

#### `vlr_document_type_mappings` (Configurable)

```python
class DocumentTypeMappingModel(BaseModel):
    __tablename__ = "vlr_document_type_mappings"

    document_type_code: Mapped[str] = mapped_column(String(10), unique=True, nullable=False)
    category: Mapped[str] = mapped_column(String(30), nullable=False)
    # category: Invoice, Payment, Credit Note, Debit Note, TDS, Other
    is_tds: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
```

### Enhanced Existing Models

#### `vlr_ledger_entries` (add columns)

```python
# New columns for data transformation output:
raw_reference: Mapped[str | None]       # Original source value before CLEAN
derived_invoice_number: Mapped[str | None]  # After CLEAN function
invoice_source_field: Mapped[str | None]    # 'ZUONR', 'XBLNR', or 'BELNR'
original_amount: Mapped[Decimal | None]     # Unsigned amount before sign adjustment
shkzg_indicator: Mapped[str | None]         # H or S
adjusted_amount: Mapped[Decimal | None]     # Signed amount
transaction_currency: Mapped[str]           # Original currency code
local_currency_amount: Mapped[Decimal | None]  # INR equivalent
document_category: Mapped[str | None]       # Invoice, Payment, Credit Note, etc.
is_tds: Mapped[bool]                        # TDS tag
tds_parent_entry_id: Mapped[UUID | None]    # Link to parent invoice
```

#### `vlr_reconciliation_cases` (add columns)

```python
# New columns for workflow and balance tracking:
current_workflow_step: Mapped[str | None]    # Current step in 10-step workflow
step_entered_at: Mapped[datetime | None]     # When current step was entered
sla_deadline: Mapped[datetime | None]        # SLA deadline for current step
is_overdue: Mapped[bool]                     # SLA violation flag
company_opening_balance: Mapped[Decimal | None]
company_closing_balance: Mapped[Decimal | None]
vendor_opening_balance: Mapped[Decimal | None]
vendor_closing_balance: Mapped[Decimal | None]
net_difference: Mapped[Decimal | None]
closure_type: Mapped[str | None]             # 'normal' or 'one_sided'
closure_justification: Mapped[str | None]
closure_approved_by: Mapped[str | None]
```

## Error Handling

### Error Categories

| Category | HTTP Code | Handling Strategy |
|----------|-----------|-------------------|
| Validation errors (invalid input, missing fields) | 400 | Return field-level errors with messages |
| Business rule violations (overlap, inactive vendor) | 409/422 | Return specific rule violation message |
| SAP connection failures | 502 | Retry with exponential backoff (3 attempts) |
| Workflow transition violations | 409 | Return current state and valid transitions |
| Authentication/authorization | 401/403 | Standard auth error responses |
| Portal token expired | 410 | Return expiry message, deny access |
| Internal server errors | 500 | Log with correlation ID, return generic message |

### Error Flow

```
Client Request → API Layer → Validation → Domain Service → Repository
                     │              │             │              │
                     ▼              ▼             ▼              ▼
              Auth Error      ValidationError  BusinessRule   DBError
              (401/403)         (400)          Exception       (500)
                                                (409/422)
                     └──────────────────────────────────────────┘
                                        │
                                        ▼
                              ExceptionHandlerMiddleware
                              (existing middleware)
                                        │
                                        ▼
                              Structured JSON error response
                              + Audit log entry
                              + Structured log with correlation_id
```

### Frontend Error Handling Pattern

All React Query hooks follow this pattern:

```typescript
const { data, isLoading, error, refetch } = useQuery({
  queryKey: ['vlr', 'resource', id],
  queryFn: () => vlrApi.getResource(id),
  retry: 2,
  retryDelay: (attempt) => Math.min(1000 * 2 ** attempt, 10000),
});

// Components render:
// - Loading: <ProgressSpinner /> or <Skeleton />
// - Error: <Message severity="error" /> with retry button
// - Empty: <EmptyState /> with actionable guidance
// - Success: Data display
```

### Celery Task Error Handling

- Each Celery task has `max_retries` configured per task type
- Failed tasks clear their idempotency keys (enabling re-trigger)
- Task failures trigger case status rollback to previous step
- All failures are logged with structured JSON including correlation_id

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system—essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: Invoice Number Derivation Priority

*For any* SAP ledger entry, the derived invoice number SHALL be sourced from the first non-empty field in priority order (ZUONR → XBLNR → BELNR), and the CLEAN function SHALL be applied to the result, producing an output with no leading zeros, no special characters, and no surrounding whitespace.

**Validates: Requirements 1.1, 1.2, 1.3, 1.4**

### Property 2: Invoice Derivation Preserves Raw Value

*For any* SAP ledger entry processed by the Data Transformation Engine, both the raw source value and the cleaned derived invoice number SHALL be stored, and the raw value SHALL be recoverable.

**Validates: Requirements 1.5**

### Property 3: Sign Adjustment Correctness

*For any* SAP ledger entry with a SHKZG indicator, the sign-adjusted amount SHALL be positive when SHKZG is "H" (credit) and negative when SHKZG is "S" (debit), and both the original unsigned amount and the SHKZG indicator SHALL remain stored alongside the adjusted value.

**Validates: Requirements 2.1, 2.2, 2.4**

### Property 4: Balance Calculation Arithmetic Invariant

*For any* set of ledger entries and any reconciliation period, the closing balance SHALL equal the opening balance plus the net movement (sum of sign-adjusted entries within the period), and this SHALL hold independently for both company and vendor sides.

**Validates: Requirements 3.1, 3.2, 3.3, 4.1, 4.2, 4.3**

### Property 5: TDS Tagging Completeness

*For any* ledger entry whose document type is configured as TDS, the Data Transformation Engine SHALL tag the entry as `is_tds = true` and attempt to link it to a parent invoice by reference number.

**Validates: Requirements 5.1, 5.2**

### Property 6: Multi-Currency Comparison Invariant

*For any* reconciliation match attempt, the Reconciliation Engine SHALL compare amounts using the same currency for both sides, never mixing transaction currency with local currency in a single comparison.

**Validates: Requirements 6.1, 6.2**

### Property 7: Document Type Classification Determinism

*For any* ledger entry with a document type code present in the configurable mapping table, the Data Transformation Engine SHALL assign exactly one category, and the classification SHALL be deterministic (same input always produces same output).

**Validates: Requirements 7.1, 7.2, 7.3, 7.4**

### Property 8: Column Mapping Preview Row Count

*For any* uploaded file with N data rows, the Column Mapping Engine SHALL return exactly min(10, N) preview rows.

**Validates: Requirements 9.1**

### Property 9: Auto-Mapping Template Application

*For any* vendor with a saved column mapping template and any compatible file upload (matching column count), the Column Mapping Engine SHALL auto-apply the template, and all tag assignments from the template SHALL be present in the applied mapping.

**Validates: Requirements 10.2**

### Property 10: Auto-Mapping Confidence Validity

*For any* auto-mapping suggestion produced by the Column Mapping Engine, the confidence score SHALL be exactly one of {High, Medium, Low}, and suggestions SHALL only reference tags from the supported tag set.

**Validates: Requirements 11.1, 11.2**

### Property 11: Workflow Transition Validity

*For any* Reconciliation Case and any attempted workflow transition, the Workflow Orchestrator SHALL only permit transitions defined in the VALID_TRANSITIONS map. The case SHALL always have a valid status, and rollback SHALL only move to an immediately preceding step.

**Validates: Requirements 12.1, 12.2, 12.4**

### Property 12: SLA Violation Detection

*For any* Reconciliation Case where the time spent in the current workflow step exceeds the configured SLA duration for that step, the Workflow Orchestrator SHALL flag the case as overdue.

**Validates: Requirements 13.2**

### Property 13: Reminder Schedule Correctness

*For any* Reconciliation Case in the Vendor Engagement step where the vendor has not uploaded a statement, reminders SHALL be sent at exactly D3, D7, and D10 intervals from the invite date, and escalation SHALL occur after all three reminders are exhausted without response.

**Validates: Requirements 15.1, 15.2, 15.3**

### Property 14: Notification Case Link Inclusion

*For any* notification email generated by the Email Service, the email body SHALL contain a direct link (URL) to the relevant Reconciliation Case.

**Validates: Requirements 16.3**

### Property 15: No-Double-Match Invariant

*For any* reconciliation result produced by the Reconciliation Engine, no ledger entry ID SHALL appear in more than one match pair or match group across all passes. Entries matched in Pass N SHALL be excluded from Pass N+1 through Pass 7.

**Validates: Requirements 17.3, 17.4, 36.1, 36.2, 36.3**

### Property 16: Match Confidence Score Range

*For any* match result produced by the Reconciliation Engine, the confidence score SHALL be a value in the range [0.0, 1.0].

**Validates: Requirements 17.2**

### Property 17: Finance Confirmation State Transitions

*For any* match entry on the Finance Confirmation tab (Tab 2), accepting the match SHALL move it to confirmed matches, and rejecting the match SHALL return both entries to the unmatched pool. The total entry count across all tabs SHALL remain constant.

**Validates: Requirements 19.3, 19.4**

### Property 18: Differences Summary Consistency

*For any* reconciliation case, the Differences Summary SHALL satisfy: Company Closing Balance - Vendor Closing Balance = Net Difference, and Net Difference SHALL equal the sum of all unmatched/disputed item amounts.

**Validates: Requirements 22.1, 22.2, 22.3, 22.4**

### Property 19: Dashboard Widget Accuracy

*For any* set of Reconciliation Cases in the database, the Dashboard widget values SHALL equal the correct aggregation: Open Cases = count(status not in {closed}), Pending Vendor Upload = count(status = vendor_engagement and upload_count = 0), Overdue Cases = count(is_overdue = true), and Auto-Match Rate = matched_entries / total_entries × 100.

**Validates: Requirements 26.1, 26.2, 26.3, 26.4, 26.7**

### Property 20: Reconciliation Summary Report Net Difference

*For any* fully reconciled case (all entries matched), the Reconciliation Summary Report Net Difference row SHALL equal zero. For partially reconciled cases, the Net Difference SHALL equal the sum of unresolved adjustment amounts.

**Validates: Requirements 27.1, 27.2**

### Property 21: Aging Bucket Assignment Correctness

*For any* unmatched item with a known posting date, the Aging Analysis Report SHALL assign it to exactly one aging bucket based on days outstanding: 0-30, 31-60, 61-90, 91-180, or 180+, and the bucket assignment SHALL be deterministic.

**Validates: Requirements 28.1, 28.2**

### Property 22: Recovery Follow-Up Trigger

*For any* recovery item with status "open" or "in_progress" whose next_follow_up_date is on or before today, the Recovery Module SHALL auto-trigger a follow-up reminder and log the action with a timestamp.

**Validates: Requirements 31.1, 31.2**

### Property 23: One-Sided Closure Authorization

*For any* one-sided closure attempt, the VLR System SHALL require explicit Recon_Manager approval and SHALL record the justification and approver identity. Without Recon_Manager approval, one-sided closure SHALL be rejected.

**Validates: Requirements 32.2, 32.3**

### Property 24: Portal Link Expiry Enforcement

*For any* portal access link, access SHALL be denied after 90 days from the link creation date, and the system SHALL display an expiry message. Access within the 90-day window with a valid token SHALL be permitted.

**Validates: Requirements 33.1, 33.2**

### Property 25: Period Overlap Prevention

*For any* new Reconciliation Case creation attempt, if there exists an active or closed case for the same vendor and company code with an overlapping date range, the system SHALL reject the creation and return the conflicting case reference.

**Validates: Requirements 34.1, 34.2**

### Property 26: Active Vendor Validation

*For any* new reconciliation request, if the specified vendor has an inactive status, the system SHALL reject the request. Only vendors with active status SHALL be accepted.

**Validates: Requirements 35.1, 35.2**

### Property 27: Case Closure Net-Zero Condition

*For any* normal (non-one-sided) case closure attempt, the system SHALL reject closure if the net difference between company and vendor adjusted balances is not zero. One-sided closure approved by Recon_Manager SHALL bypass this check.

**Validates: Requirements 37.1, 37.2, 37.3**

### Property 28: Audit Trail Immutability and Completeness

*For any* audit event created in the system, the record SHALL be immutable (no update or delete operations permitted), and SHALL contain actor_id/username, timestamp, case_id (if applicable), event_type, and event_details. The set of captured event types SHALL include login, logout, case creation, status changes, match overrides, approvals, rejections, and vendor interactions.

**Validates: Requirements 38.1, 38.2, 38.3**

### Property 29: Audit Search Correctness

*For any* audit search query with filters (user, date range, case_id, event_type), all returned results SHALL satisfy every specified filter criterion, and no matching record SHALL be excluded from the results.

**Validates: Requirements 39.1**

### Property 30: Structured Log Entry Completeness

*For any* structured JSON log entry emitted by the system, the entry SHALL contain correlation_id, timestamp, service_name, operation_name, duration_ms, and outcome_status fields. On failure, error_type and error_message SHALL be included without any sensitive data (passwords, tokens, secrets).

**Validates: Requirements 40.1, 40.2, 40.4**


## Testing Strategy

### Property-Based Tests

Property-based tests validate the correctness properties defined above. Each property test runs a minimum of 100 iterations with randomly generated inputs.

**Framework**: `hypothesis` (Python) for backend, `fast-check` (TypeScript) for frontend logic.

**Priority properties for PBT**:
- Property 1 (Invoice Derivation Priority) — generates random SAP entries with various ZUONR/XBLNR/BELNR combinations
- Property 3 (Sign Adjustment) — generates random amounts with H/S indicators
- Property 4 (Balance Calculation) — generates random entry sets and period boundaries
- Property 7 (Document Type Classification) — generates random doc type codes against configurable mapping
- Property 11 (Workflow Transition Validity) — generates random state sequences
- Property 15 (No-Double-Match) — generates random entry sets and verifies invariant after full engine execution
- Property 25 (Period Overlap Prevention) — generates random date ranges for overlap detection
- Property 27 (Case Closure Net-Zero) — generates random balance scenarios
- Property 28 (Audit Immutability) — verifies no mutation operations succeed on audit records

### Unit Tests

Example-based unit tests cover:
- SAP adapter interface contract verification (mock returns correct shapes)
- Column mapping tag enumeration (all 12 tags supported)
- Email template rendering (Jinja2 output verification)
- Workflow SLA configuration loading
- Report export format generation (PDF/Excel)
- Frontend component rendering (loading/error/empty states)
- Portal token validation (valid, expired, invalid)

### Integration Tests

- SAP pull → transformation → reconciliation pipeline end-to-end
- Celery task execution with database state changes
- Email delivery via SMTP (dev mode)
- Frontend page → API → database round-trip (per page)
- Vendor portal authentication and upload flow

### Test Configuration

- Backend: `pytest` with `hypothesis` plugin, `pytest-asyncio` for async tests
- Frontend: `vitest` with `@fast-check/vitest` for property tests
- Minimum 100 iterations per property test
- Each property test references its design document property number
- Tag format: `Feature: vlr-complete-rebuild, Property {N}: {title}`
