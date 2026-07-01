"""
User domain entity.
Contains business logic and invariants for user management.
"""

from dataclasses import dataclass, field
from uuid import UUID

from src.domain.entities.base_entity import BaseEntity


@dataclass
class User(BaseEntity):
    """
    User aggregate root.

    Business Rules:
    - Username must be unique (enforced at repository level).
    - Password hash is never exposed outside the domain/infrastructure boundary.
    - A blocked user cannot authenticate regardless of active status.
    """

    username: str = field(default="")
    password_hash: str = field(default="", repr=False)
    is_active: bool = field(default=True)
    is_blocked: bool = field(default=False)
    is_validate_ad: bool = field(default=True)

    def can_authenticate(self) -> bool:
        """Check if the user is allowed to authenticate."""
        return self.is_active and not self.is_blocked

    def block(self, blocked_by: str) -> None:
        """Block the user from authenticating."""
        self.is_blocked = True
        self.mark_modified(blocked_by)

    def unblock(self, unblocked_by: str) -> None:
        """Unblock the user."""
        self.is_blocked = False
        self.mark_modified(unblocked_by)

    def deactivate(self, deactivated_by: str) -> None:
        """Deactivate the user account."""
        self.is_active = False
        self.mark_modified(deactivated_by)

    def activate(self, activated_by: str) -> None:
        """Activate the user account."""
        self.is_active = True
        self.mark_modified(activated_by)
