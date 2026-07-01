"""
Base domain entity with audit fields.
All domain entities inherit from this to ensure consistent audit tracking.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import UUID, uuid4


@dataclass
class BaseEntity:
    """
    Base entity providing identity and audit fields.

    Attributes:
        id: Unique identifier (UUID).
        created_by: Username or system identifier that created the entity.
        created_date: UTC timestamp of creation.
        modified_by: Username or system identifier that last modified the entity.
        modified_date: UTC timestamp of last modification.
    """

    id: UUID = field(default_factory=uuid4)
    created_by: str = field(default="system")
    created_date: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    modified_by: str = field(default="system")
    modified_date: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def mark_modified(self, modified_by: str) -> None:
        """Update modification tracking fields."""
        self.modified_by = modified_by
        self.modified_date = datetime.now(timezone.utc)
