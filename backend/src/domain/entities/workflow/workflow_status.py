"""Workflow Status domain entity."""
from dataclasses import dataclass, field
from uuid import UUID, uuid4


@dataclass
class WorkflowStatus:
    id: UUID = field(default_factory=uuid4)
    workflow_definition_id: UUID | None = None
    code: str = ""
    name: str = ""
    is_initial: bool = False
    is_terminal: bool = False
    sequence: int = 0
