"""Domain events for workflow engine."""
from dataclasses import dataclass, field
from uuid import UUID, uuid4
from datetime import datetime, timezone
from typing import Any


@dataclass
class DomainEvent:
    event_id: UUID = field(default_factory=uuid4)
    event_type: str = ""
    entity_type: str = ""
    entity_id: UUID | None = None
    actor_id: UUID | None = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class WorkflowStarted(DomainEvent):
    event_type: str = "WORKFLOW_STARTED"
    instance_id: UUID | None = None


@dataclass
class TaskAssigned(DomainEvent):
    event_type: str = "TASK_ASSIGNED"
    task_id: UUID | None = None
    assignee_id: UUID | None = None


@dataclass
class TaskApproved(DomainEvent):
    event_type: str = "TASK_APPROVED"
    task_id: UUID | None = None


@dataclass
class TaskRejected(DomainEvent):
    event_type: str = "TASK_REJECTED"
    task_id: UUID | None = None


@dataclass
class TaskReferredBack(DomainEvent):
    event_type: str = "TASK_REFERRED_BACK"
    task_id: UUID | None = None


@dataclass
class WorkflowCompleted(DomainEvent):
    event_type: str = "WORKFLOW_COMPLETED"
    instance_id: UUID | None = None


@dataclass
class WorkflowCancelled(DomainEvent):
    event_type: str = "WORKFLOW_CANCELLED"
    instance_id: UUID | None = None


@dataclass
class SLABreached(DomainEvent):
    event_type: str = "SLA_BREACHED"
    task_id: UUID | None = None
