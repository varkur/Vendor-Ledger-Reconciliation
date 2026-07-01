# Enterprise Workflow Engine Architecture

## 1. High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          BUSINESS MODULES                                    │
│  Commission Claims │ Purchase Requests │ Vendor Onboarding │ Contracts      │
└─────────────────────────────────┬───────────────────────────────────────────┘
                                  │ (plugs into)
┌─────────────────────────────────┼───────────────────────────────────────────┐
│                    WORKFLOW FRAMEWORK (Reusable Core)                        │
│                                 │                                           │
│  ┌──────────────┐  ┌───────────┴──────────┐  ┌─────────────────────────┐   │
│  │  Workflow    │  │   State Machine      │  │   Approval Matrix       │   │
│  │  Engine      │  │   Engine             │  │   Service               │   │
│  │             │  │                      │  │                         │   │
│  │ • Define    │  │ • States             │  │ • Rules                 │   │
│  │ • Execute   │  │ • Transitions        │  │ • Conditions            │   │
│  │ • Route     │  │ • Validate           │  │ • Assignments           │   │
│  │ • Assign    │  │ • Guard              │  │ • Delegation            │   │
│  └──────┬───────┘  └──────────┬───────────┘  └───────────┬─────────────┘   │
│         │                     │                           │                 │
│  ┌──────┴─────────────────────┴───────────────────────────┴──────────────┐  │
│  │                      Event Bus (Domain Events)                         │  │
│  │  WorkflowStarted │ TaskAssigned │ TaskApproved │ WorkflowCompleted    │  │
│  └──────────────────────────────┬────────────────────────────────────────┘  │
│                                 │                                           │
│  ┌──────────────────────────────┴────────────────────────────────────────┐  │
│  │                      Audit Trail Framework                             │  │
│  │  • Who │ When │ What │ Old/New Values │ IP │ Comments                  │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
                                  │
┌─────────────────────────────────┼───────────────────────────────────────────┐
│                          INFRASTRUCTURE                                      │
│  PostgreSQL │ Redis │ Celery │ Notifications │ File Storage                  │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Database Schema (Complete ER Diagram)

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         WORKFLOW DEFINITION                               │
│                                                                         │
│  ┌───────────────────┐     ┌───────────────────┐                       │
│  │workflow_definition│     │  workflow_status   │                       │
│  │                   │     │                   │                       │
│  │ id (PK)          │     │ id (PK)           │                       │
│  │ code             │     │ workflow_def_id FK │                       │
│  │ name             │     │ code              │                       │
│  │ description      │     │ name              │                       │
│  │ entity_type      │     │ is_initial        │                       │
│  │ version          │     │ is_terminal       │                       │
│  │ is_active        │     │ sequence          │                       │
│  └────────┬──────────┘     └───────────────────┘                       │
│           │                                                             │
│  ┌────────┴──────────┐     ┌───────────────────┐                       │
│  │  workflow_step    │     │workflow_transition │                       │
│  │                   │     │                   │                       │
│  │ id (PK)          │     │ id (PK)           │                       │
│  │ workflow_def_id FK│     │ workflow_def_id FK │                       │
│  │ from_status_id FK│     │ from_status_id FK │                       │
│  │ to_status_id FK  │     │ to_status_id FK   │                       │
│  │ action_code      │     │ action_code       │                       │
│  │ step_type        │     │ guard_expression  │                       │
│  │ sequence         │     │ requires_comment  │                       │
│  │ is_parallel      │     │ auto_execute      │                       │
│  │ sla_hours        │     └───────────────────┘                       │
│  └───────────────────┘                                                 │
│                                                                         │
│  ┌───────────────────┐                                                 │
│  │workflow_action    │                                                 │
│  │                   │                                                 │
│  │ id (PK)          │                                                 │
│  │ workflow_def_id FK│                                                 │
│  │ code             │                                                 │
│  │ name             │                                                 │
│  │ action_type      │     (APPROVE,REJECT,REFER_BACK,CANCEL,CLOSE)    │
│  └───────────────────┘                                                 │
│                                                                         │
│  ┌─────────────────────────┐                                           │
│  │workflow_assignment_rule │                                           │
│  │                         │                                           │
│  │ id (PK)                │                                           │
│  │ workflow_step_id FK    │                                           │
│  │ assignment_type        │   (ROLE, USER, MATRIX, EXPRESSION)        │
│  │ role_id FK             │                                           │
│  │ user_id FK             │                                           │
│  │ matrix_rule_id FK      │                                           │
│  │ expression             │                                           │
│  └─────────────────────────┘                                           │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│                         WORKFLOW RUNTIME                                  │
│                                                                         │
│  ┌───────────────────────┐     ┌───────────────────────┐               │
│  │  workflow_instance    │     │workflow_instance_step │               │
│  │                       │     │                       │               │
│  │ id (PK)              │     │ id (PK)              │               │
│  │ workflow_def_id FK   │     │ instance_id FK       │               │
│  │ entity_type          │     │ step_id FK           │               │
│  │ entity_id            │     │ status               │               │
│  │ current_status_id FK │     │ assigned_to_id FK    │               │
│  │ initiated_by FK     │     │ assigned_at          │               │
│  │ priority            │     │ completed_at         │               │
│  │ due_date            │     │ action_taken         │               │
│  │ started_at          │     │ comments             │               │
│  │ completed_at        │     │ sla_due_at           │               │
│  │ metadata (JSONB)    │     │ is_escalated         │               │
│  └───────────────────────┘     └───────────────────────┘               │
│                                                                         │
│  ┌───────────────────────┐                                             │
│  │  workflow_history     │                                             │
│  │                       │                                             │
│  │ id (PK)              │                                             │
│  │ instance_id FK       │                                             │
│  │ from_status_id FK    │                                             │
│  │ to_status_id FK      │                                             │
│  │ action_code          │                                             │
│  │ actor_id FK          │                                             │
│  │ actor_username       │                                             │
│  │ comments             │                                             │
│  │ metadata (JSONB)     │                                             │
│  │ ip_address           │                                             │
│  │ created_at           │                                             │
│  └───────────────────────┘                                             │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│                         APPROVAL MATRIX                                   │
│                                                                         │
│  ┌───────────────────┐     ┌───────────────────┐                       │
│  │  approval_matrix  │     │  approval_rule    │                       │
│  │                   │     │                   │                       │
│  │ id (PK)          │     │ id (PK)           │                       │
│  │ code             │     │ matrix_id FK      │                       │
│  │ name             │     │ field             │                       │
│  │ entity_type      │     │ operator          │                       │
│  │ priority         │     │ value             │                       │
│  │ is_active        │     │ data_type         │                       │
│  └───────────────────┘     │ logical_group     │                       │
│                            └───────────────────┘                       │
│  ┌───────────────────┐     ┌───────────────────┐                       │
│  │approval_condition │     │approval_assignment│                       │
│  │                   │     │                   │                       │
│  │ id (PK)          │     │ id (PK)           │                       │
│  │ matrix_id FK     │     │ matrix_id FK      │                       │
│  │ condition_type   │     │ assignment_type   │                       │
│  │ expression       │     │ user_id FK        │                       │
│  │ priority         │     │ role_id FK        │                       │
│  └───────────────────┘     │ level            │                       │
│                            └───────────────────┘                       │
│  ┌───────────────────┐     ┌───────────────────┐                       │
│  │approval_delegation│     │  approval_task    │                       │
│  │                   │     │                   │                       │
│  │ id (PK)          │     │ id (PK)           │                       │
│  │ delegator_id FK  │     │ instance_id FK    │                       │
│  │ delegate_id FK   │     │ matrix_id FK      │                       │
│  │ from_date        │     │ assignee_id FK    │                       │
│  │ to_date          │     │ level             │                       │
│  │ entity_type      │     │ status            │                       │
│  │ is_active        │     │ action_taken      │                       │
│  └───────────────────┘     │ due_date          │                       │
│                            │ comments          │                       │
│                            └───────────────────┘                       │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│                         STATE MACHINE                                     │
│                                                                         │
│  ┌───────────────────┐     ┌───────────────────────┐                   │
│  │      state        │     │  state_transition     │                   │
│  │                   │     │                       │                   │
│  │ id (PK)          │     │ id (PK)              │                   │
│  │ machine_id FK    │     │ machine_id FK        │                   │
│  │ code             │     │ from_state_id FK     │                   │
│  │ name             │     │ to_state_id FK       │                   │
│  │ state_type       │     │ action_code          │                   │
│  │ (INITIAL/NORMAL/ │     │ guard_expression     │                   │
│  │  TERMINAL)       │     │ priority             │                   │
│  └───────────────────┘     │ requires_comment     │                   │
│                            └───────────────────────┘                   │
│  ┌───────────────────┐     ┌───────────────────────┐                   │
│  │  state_machine    │     │state_machine_instance │                   │
│  │                   │     │                       │                   │
│  │ id (PK)          │     │ id (PK)              │                   │
│  │ code             │     │ machine_id FK        │                   │
│  │ name             │     │ current_state_id FK  │                   │
│  │ entity_type      │     │ entity_type          │                   │
│  │ version          │     │ entity_id            │                   │
│  │ is_active        │     │ started_at           │                   │
│  └───────────────────┘     │ metadata (JSONB)     │                   │
│                            └───────────────────────┘                   │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│                         AUDIT TRAIL                                       │
│                                                                         │
│  ┌───────────────────┐     ┌───────────────────┐                       │
│  │    audit_event    │     │   audit_change    │                       │
│  │                   │     │                   │                       │
│  │ id (PK)          │     │ id (PK)           │                       │
│  │ event_type       │     │ event_id FK       │                       │
│  │ entity_type      │     │ field_name        │                       │
│  │ entity_id        │     │ old_value         │                       │
│  │ actor_id FK      │     │ new_value         │                       │
│  │ actor_username   │     │ data_type         │                       │
│  │ action           │     └───────────────────┘                       │
│  │ comments         │                                                 │
│  │ ip_address       │     ┌───────────────────┐                       │
│  │ user_agent       │     │  audit_entity     │                       │
│  │ metadata (JSONB) │     │                   │                       │
│  │ created_at       │     │ id (PK)           │                       │
│  └───────────────────┘     │ entity_type       │                       │
│                            │ entity_class      │                       │
│                            │ tracked_fields    │                       │
│                            │ is_active         │                       │
│                            └───────────────────┘                       │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 3. State Machine — State Transition Diagram

```
                    ┌──────────┐
                    │  DRAFT   │ (Initial)
                    └────┬─────┘
                         │ [Submit]
                    ┌────▼─────┐
            ┌───────│SUBMITTED │───────┐
            │       └────┬─────┘       │
            │ [Reject]   │ [Approve]   │ [Cancel]
            │            │             │
     ┌──────▼──┐   ┌────▼─────┐  ┌───▼─────┐
     │REJECTED │   │L1 PENDING│  │CANCELLED│ (Terminal)
     └─────────┘   └────┬─────┘  └─────────┘
     (Terminal)          │
                    ┌────┤
          [Reject]  │    │ [Approve]     [Refer Back]
                    │    │                    │
             ┌──────▼┐  ┌▼─────────┐   ┌────▼─────┐
             │REJECTED│  │L2 PENDING│   │SUBMITTED │
             └────────┘  └────┬─────┘   └──────────┘
                              │
                    ┌─────────┤
          [Reject]  │         │ [Approve]    [Close]
                    │         │                │
             ┌──────▼┐   ┌───▼─────┐    ┌────▼────┐
             │REJECTED│   │APPROVED │    │ CLOSED  │
             └────────┘   └─────────┘    └─────────┘
                          (Terminal)      (Terminal)
```

---

## 4. Runtime Execution Sequence Diagram

```
User          WorkflowEngine    StateMachine    ApprovalMatrix    EventBus    AuditTrail
 │                 │                 │                │              │            │
 │ Submit Claim    │                 │                │              │            │
 ├────────────────►│                 │                │              │            │
 │                 │ Validate        │                │              │            │
 │                 │ Transition      │                │              │            │
 │                 ├────────────────►│                │              │            │
 │                 │                 │ Check Guards   │              │            │
 │                 │                 │ Execute        │              │            │
 │                 │◄────────────────┤                │              │            │
 │                 │                 │                │              │            │
 │                 │ Resolve Approver│                │              │            │
 │                 ├─────────────────────────────────►│              │            │
 │                 │                 │                │ Evaluate     │            │
 │                 │                 │                │ Rules        │            │
 │                 │◄─────────────────────────────────┤              │            │
 │                 │                 │                │              │            │
 │                 │ Create Task     │                │              │            │
 │                 │ Assign Approver │                │              │            │
 │                 │                 │                │              │            │
 │                 │ Publish Event   │                │              │            │
 │                 ├──────────────────────────────────────────────►│            │
 │                 │                 │                │              │            │
 │                 │ Log Audit       │                │              │            │
 │                 ├─────────────────────────────────────────────────────────►│
 │                 │                 │                │              │            │
 │◄────────────────┤                 │                │              │            │
 │  Response       │                 │                │              │            │
```

---

## 5. Folder Structure

```
backend/src/workflow/
├── __init__.py
├── domain/
│   ├── __init__.py
│   ├── entities/
│   │   ├── __init__.py
│   │   ├── workflow_definition.py
│   │   ├── workflow_instance.py
│   │   ├── workflow_step.py
│   │   ├── workflow_status.py
│   │   ├── workflow_transition.py
│   │   ├── workflow_action.py
│   │   └── workflow_history.py
│   ├── value_objects/
│   │   ├── __init__.py
│   │   ├── action_type.py
│   │   ├── step_type.py
│   │   ├── instance_status.py
│   │   └── assignment_type.py
│   ├── events/
│   │   ├── __init__.py
│   │   ├── workflow_events.py
│   │   └── task_events.py
│   └── repositories/
│       ├── __init__.py
│       ├── workflow_definition_repository.py
│       ├── workflow_instance_repository.py
│       └── approval_matrix_repository.py
│
├── application/
│   ├── __init__.py
│   ├── use_cases/
│   │   ├── __init__.py
│   │   ├── start_workflow.py
│   │   ├── execute_action.py
│   │   ├── assign_task.py
│   │   ├── escalate_task.py
│   │   └── complete_workflow.py
│   ├── services/
│   │   ├── __init__.py
│   │   ├── workflow_engine.py
│   │   └── notification_service.py
│   └── dtos/
│       ├── __init__.py
│       ├── workflow_request.py
│       └── workflow_response.py
│
├── state_machine/
│   ├── __init__.py
│   ├── state_machine_service.py
│   ├── state_resolver.py
│   ├── transition_validator.py
│   └── transition_executor.py
│
├── approval_matrix/
│   ├── __init__.py
│   ├── approval_matrix_service.py
│   ├── approval_resolver.py
│   ├── rule_evaluator.py
│   └── assignment_generator.py
│
├── audit/
│   ├── __init__.py
│   ├── audit_service.py
│   ├── audit_interceptor.py
│   ├── audit_decorator.py
│   └── audit_repository.py
│
├── events/
│   ├── __init__.py
│   ├── event_bus.py
│   ├── event_publisher.py
│   ├── event_subscriber.py
│   └── handlers/
│       ├── __init__.py
│       ├── notification_handler.py
│       ├── audit_handler.py
│       └── escalation_handler.py
│
├── infrastructure/
│   ├── __init__.py
│   ├── models/
│   │   ├── __init__.py
│   │   ├── workflow_models.py
│   │   ├── state_machine_models.py
│   │   ├── approval_matrix_models.py
│   │   └── audit_models.py
│   ├── repositories/
│   │   ├── __init__.py
│   │   ├── workflow_definition_repo_impl.py
│   │   ├── workflow_instance_repo_impl.py
│   │   └── approval_matrix_repo_impl.py
│   └── migrations/
│       └── versions/
│           └── create_workflow_tables.py
│
├── api/
│   ├── __init__.py
│   ├── workflow_controller.py
│   ├── approval_controller.py
│   ├── state_machine_controller.py
│   └── schemas/
│       ├── __init__.py
│       ├── workflow_schemas.py
│       ├── approval_schemas.py
│       └── state_machine_schemas.py
│
└── tests/
    ├── __init__.py
    ├── unit/
    │   ├── test_state_machine.py
    │   ├── test_rule_evaluator.py
    │   └── test_workflow_engine.py
    └── integration/
        ├── test_workflow_execution.py
        └── test_approval_flow.py
```

---

## 6. Core Services — Class Design

### 6.1 State Machine Service

```python
class StateMachineService:
    """Manages state transitions for workflow instances."""

    def __init__(self, session, state_resolver, transition_validator, transition_executor):
        ...

    async def get_current_state(self, instance_id: UUID) -> State
    async def get_available_actions(self, instance_id: UUID, actor_id: UUID) -> list[Action]
    async def execute_transition(self, instance_id: UUID, action_code: str, actor_id: UUID, comments: str) -> State
    async def validate_transition(self, instance_id: UUID, action_code: str) -> bool


class StateResolver:
    """Resolves current state and valid transitions."""

    async def resolve_current(self, instance_id: UUID) -> State
    async def resolve_transitions(self, state_id: UUID) -> list[StateTransition]


class TransitionValidator:
    """Validates if a transition is allowed (guard conditions)."""

    async def validate(self, transition: StateTransition, context: dict) -> bool
    async def evaluate_guard(self, expression: str, context: dict) -> bool


class TransitionExecutor:
    """Executes a validated state transition."""

    async def execute(self, instance_id: UUID, transition: StateTransition, actor_id: UUID, comments: str) -> State
```

### 6.2 Approval Matrix Service

```python
class ApprovalMatrixService:
    """Resolves approvers based on configurable rules."""

    def __init__(self, session, rule_evaluator, assignment_generator):
        ...

    async def resolve_approvers(self, entity_type: str, entity_data: dict) -> list[ApprovalAssignment]
    async def create_approval_tasks(self, instance_id: UUID, assignments: list[ApprovalAssignment]) -> list[ApprovalTask]


class ApprovalResolver:
    """Finds matching approval matrix for given entity."""

    async def find_matching_matrix(self, entity_type: str, entity_data: dict) -> ApprovalMatrix | None


class RuleEvaluator:
    """Evaluates approval rules against entity data."""

    def evaluate(self, rules: list[ApprovalRule], entity_data: dict) -> bool
    def evaluate_condition(self, field: str, operator: str, value: str, entity_data: dict) -> bool


class AssignmentGenerator:
    """Generates approval task assignments from matrix results."""

    async def generate(self, matrix: ApprovalMatrix, entity_data: dict) -> list[ApprovalAssignment]
```

### 6.3 Workflow Engine

```python
class WorkflowEngine:
    """Orchestrates workflow execution across all services."""

    def __init__(self, state_machine, approval_matrix, event_bus, audit_service):
        ...

    async def start_workflow(self, definition_code: str, entity_type: str, entity_id: UUID, initiated_by: UUID, metadata: dict) -> WorkflowInstance
    async def execute_action(self, instance_id: UUID, action_code: str, actor_id: UUID, comments: str) -> WorkflowInstance
    async def get_pending_tasks(self, user_id: UUID) -> list[ApprovalTask]
    async def get_workflow_status(self, instance_id: UUID) -> WorkflowInstanceStatus
    async def cancel_workflow(self, instance_id: UUID, actor_id: UUID, reason: str) -> WorkflowInstance
```

### 6.4 Event System

```python
@dataclass
class DomainEvent:
    event_id: UUID
    event_type: str
    entity_type: str
    entity_id: UUID
    actor_id: UUID
    timestamp: datetime
    metadata: dict


class WorkflowStarted(DomainEvent): ...
class TaskAssigned(DomainEvent): ...
class TaskApproved(DomainEvent): ...
class TaskRejected(DomainEvent): ...
class TaskReferredBack(DomainEvent): ...
class WorkflowCompleted(DomainEvent): ...
class WorkflowCancelled(DomainEvent): ...
class SLABreached(DomainEvent): ...


class EventBus:
    """In-process event bus with async handlers."""

    def subscribe(self, event_type: str, handler: Callable) -> None
    async def publish(self, event: DomainEvent) -> None


class EventPublisher:
    """Publishes events to Redis/Celery for distributed processing."""

    async def publish(self, event: DomainEvent) -> None


class EventSubscriber:
    """Subscribes to external events (Celery tasks)."""

    def register_handler(self, event_type: str, handler: Callable) -> None
```

---

## 7. API Contracts

### 7.1 Start Workflow

```
POST /api/v1/workflow/start
Request:
{
  "definition_code": "COMMISSION_CLAIM",
  "entity_type": "commission_claim",
  "entity_id": "uuid",
  "metadata": { "amount": 750000, "company": "Emcure", "department": "Sales" }
}
Response:
{
  "instance_id": "uuid",
  "current_status": "DRAFT",
  "started_at": "2026-06-19T10:00:00Z"
}
```

### 7.2 Execute Action

```
POST /api/v1/workflow/{instance_id}/action
Request:
{
  "action_code": "APPROVE",
  "comments": "Approved - within budget"
}
Response:
{
  "instance_id": "uuid",
  "previous_status": "L1_PENDING",
  "current_status": "L2_PENDING",
  "next_assignee": "finance_head"
}
```

### 7.3 Get Pending Tasks

```
GET /api/v1/workflow/my-tasks?status=PENDING&page=1&page_size=20
Response:
{
  "tasks": [
    {
      "task_id": "uuid",
      "instance_id": "uuid",
      "entity_type": "commission_claim",
      "entity_id": "uuid",
      "current_status": "L1_PENDING",
      "assigned_at": "2026-06-19T10:00:00Z",
      "sla_due_at": "2026-06-20T10:00:00Z",
      "available_actions": ["APPROVE", "REJECT", "REFER_BACK"]
    }
  ],
  "total": 5,
  "page": 1,
  "page_size": 20
}
```

### 7.4 Approval Matrix — Define Rules

```
POST /api/v1/approval-matrix
Request:
{
  "code": "COMMISSION_AMOUNT",
  "name": "Commission Amount Based Approval",
  "entity_type": "commission_claim",
  "rules": [
    { "field": "amount", "operator": "LT", "value": "500000", "data_type": "NUMBER" },
    { "field": "company", "operator": "EQ", "value": "Emcure", "data_type": "STRING" }
  ],
  "assignments": [
    { "level": 1, "assignment_type": "ROLE", "role_id": "manager-uuid" },
    { "level": 2, "assignment_type": "USER", "user_id": "finance-head-uuid" }
  ]
}
```

---

## 8. Sample Runtime Execution

### Commission Claim Approval Flow

```
1. Sales Rep creates claim (amount=750000, company=Emcure)
   → System: WorkflowEngine.start_workflow("COMMISSION_CLAIM", ...)
   → State: DRAFT

2. Sales Rep clicks "Submit"
   → System: WorkflowEngine.execute_action(instance_id, "SUBMIT", ...)
   → StateMachine: DRAFT + SUBMIT → SUBMITTED
   → ApprovalMatrix: amount=750000 > 500000 → needs Finance Head
   → Creates ApprovalTask: assigned to L1 Manager
   → Event: TaskAssigned published
   → Notification: Email sent to L1 Manager

3. L1 Manager clicks "Approve"
   → System: WorkflowEngine.execute_action(instance_id, "APPROVE", ...)
   → StateMachine: SUBMITTED + APPROVE → L1_PENDING
   → Next step: L2 approval needed (Finance Head)
   → Creates ApprovalTask: assigned to Finance Head
   → Event: TaskApproved published

4. Finance Head clicks "Approve"
   → System: WorkflowEngine.execute_action(instance_id, "APPROVE", ...)
   → StateMachine: L1_PENDING + APPROVE → APPROVED (terminal)
   → Event: WorkflowCompleted published
   → Audit: Full trail recorded

5. OR: Finance Head clicks "Refer Back"
   → StateMachine: L1_PENDING + REFER_BACK → SUBMITTED
   → Task reassigned back to Sales Rep
   → Event: TaskReferredBack published
```

---

## 9. Plugging Into Business Modules

A business module integrates by:

```python
# In any business module (e.g., Commission Claims)
from src.workflow.application.services.workflow_engine import WorkflowEngine

class CommissionClaimService:
    def __init__(self, workflow_engine: WorkflowEngine):
        self._workflow = workflow_engine

    async def submit_claim(self, claim_id: UUID, user_id: UUID):
        # Start workflow — no workflow logic in business code
        await self._workflow.start_workflow(
            definition_code="COMMISSION_CLAIM",
            entity_type="commission_claim",
            entity_id=claim_id,
            initiated_by=user_id,
            metadata={"amount": claim.amount, "company": claim.company},
        )
```

**No workflow logic lives in the business module.** The module only calls `start_workflow` and the engine handles everything else based on database configuration.

---

## 10. Production Considerations

| Concern | Solution |
|---------|----------|
| SLA Monitoring | Celery beat task checks overdue tasks every 5 min |
| Escalation | Auto-reassign if SLA breached (configurable per step) |
| Delegation | `approval_delegation` table — out-of-office routing |
| Parallel Approval | Multiple tasks created simultaneously, all must complete |
| Performance | Redis caching for workflow definitions, indexed queries |
| Versioning | `workflow_definition.version` — instances locked to version at start |
| Retry | Failed transitions retry via Celery with exponential backoff |
| Idempotency | Action execution is idempotent (check current state before transitioning) |
