"""Workflow Definition domain entity."""
from dataclasses import dataclass, field
from uuid import UUID, uuid4
from datetime import datetime, timezone


@dataclass
class WorkflowDefinition:
    id: UUID = field(default_factory=uuid4)
    code: str = ""
    name: str = ""
    description: str = ""
    entity_type: str = ""  # e.g. "commission_claim", "purchase_request"
    version: int = 1
    is_active: bool = True
    created_by: str = "system"
    created_date: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
