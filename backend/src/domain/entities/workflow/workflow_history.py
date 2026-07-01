"""Workflow History domain entity - immutable audit trail of transitions."""
from dataclasses import dataclass, field
from uuid import UUID, uuid4
from datetime import datetime, timezone
from typing import Any


@dataclass
class WorkflowHistory:
    id: UUID = field(default_factory=uuid4)
    instance_id: UUID | None = None
    from_status_id: UUID | None = None
    to_status_id: UUID | None = None
    action_code: str = ""
    actor_id: UUID | None = None
    actor_username: str = ""
    comments: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    ip_address: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
