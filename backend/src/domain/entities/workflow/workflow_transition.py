"""Workflow Transition domain entity."""
from dataclasses import dataclass, field
from uuid import UUID, uuid4


@dataclass
class WorkflowTransition:
    id: UUID = field(default_factory=uuid4)
    workflow_definition_id: UUID | None = None
    from_status_id: UUID | None = None
    to_status_id: UUID | None = None
    action_code: str = ""
    guard_expression: str | None = None
    requires_comment: bool = False
    auto_execute: bool = False
    priority: int = 0
