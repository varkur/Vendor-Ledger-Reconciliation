"""
Automation Rule repository interface (Port).
Defines the contract for automation rule persistence operations.
"""

from abc import ABC, abstractmethod
from datetime import datetime
from uuid import UUID

from src.domain.repositories.vlr.vendor_repository import PaginatedResult, PaginationParams


class IAutomationRuleRepository(ABC):
    """Abstract repository for AutomationRule persistence."""

    @abstractmethod
    async def get_by_id(self, rule_id: UUID) -> object | None:
        """Retrieve an automation rule by ID."""
        ...

    @abstractmethod
    async def create(self, rule_data: dict) -> object:
        """Persist a new automation rule."""
        ...

    @abstractmethod
    async def update(self, rule_id: UUID, update_data: dict) -> object:
        """Update an existing automation rule."""
        ...

    @abstractmethod
    async def list_by_company(
        self,
        company_code: str,
        pagination: PaginationParams | None = None,
    ) -> PaginatedResult:
        """List automation rules for a company with pagination."""
        ...

    @abstractmethod
    async def get_active_rules(self, company_code: str) -> list[object]:
        """Get all active rules for a company."""
        ...

    @abstractmethod
    async def get_due_rules(self, before: datetime) -> list[object]:
        """Get active rules whose next_execution is due (next_execution <= before)."""
        ...

    @abstractmethod
    async def record_execution(self, execution_data: dict) -> object:
        """Record an automation execution result."""
        ...

    @abstractmethod
    async def get_execution_history(
        self,
        rule_id: UUID,
        pagination: PaginationParams | None = None,
    ) -> PaginatedResult:
        """Get execution history for a rule with pagination."""
        ...

    @abstractmethod
    async def deactivate(self, rule_id: UUID) -> object:
        """Deactivate a rule (set is_active=False)."""
        ...

    @abstractmethod
    async def activate(self, rule_id: UUID) -> object:
        """Activate a rule (set is_active=True)."""
        ...
