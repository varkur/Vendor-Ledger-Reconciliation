"""
Tenant domain entity for multi-tenant RBAC support.
"""

from dataclasses import dataclass, field
from uuid import UUID

from src.domain.entities.base_entity import BaseEntity


@dataclass
class Tenant(BaseEntity):
    """
    Represents an organizational tenant in a multi-tenant system.

    Each tenant has isolated:
    - Roles (tenant-specific roles + inherited global roles)
    - User-role assignments
    - Data visibility boundaries
    """

    code: str = field(default="")           # Unique short code, e.g. "ACME"
    name: str = field(default="")           # Display name
    domain: str = field(default="")         # Email domain for auto-assignment
    is_active: bool = field(default=True)
    settings: str = field(default="{}")     # JSON-serialized tenant config

    def matches_email_domain(self, email: str) -> bool:
        """Check if an email belongs to this tenant's domain."""
        if not self.domain:
            return False
        return email.lower().endswith(f"@{self.domain.lower()}")
