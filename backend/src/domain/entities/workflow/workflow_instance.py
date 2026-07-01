"""Workflow Instance domain entity - runtime representation."""
from dataclasses import dataclass, field
from uuid import UUID, uuid4
from datetime import datetime, timezone
from typing import Any


@dataclass
class WorkflowInstance:
    id: UUID = field(default_factory=uuid4)
    workflow_definition_id: UUID | None = None
    entity_type: str = ""
    entity_id: UUID | None = None
    current_status_id: UUID | None = None
    initiated_by: UUID | None = None
    priority: int = 0
    due_date: datetime | None = None
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_completed(self) -> bool:
        return self.completed_at is not None

    def complete(self) -> None:
        self.completed_at = datetime.now(timezone.utc)
