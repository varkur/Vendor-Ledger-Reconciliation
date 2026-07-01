"""
User repository interface (Port).
Defines the contract for user persistence operations.
The domain layer owns this interface; infrastructure implements it.
"""

from abc import ABC, abstractmethod
from uuid import UUID

from src.domain.entities.user import User


class IUserRepository(ABC):
    """Abstract repository for User aggregate persistence."""

    @abstractmethod
    async def get_by_id(self, user_id: UUID) -> User | None:
        """Retrieve a user by their unique identifier."""
        ...

    @abstractmethod
    async def get_by_username(self, username: str) -> User | None:
        """Retrieve a user by username."""
        ...

    @abstractmethod
    async def create(self, user: User) -> User:
        """Persist a new user entity."""
        ...

    @abstractmethod
    async def update(self, user: User) -> User:
        """Update an existing user entity."""
        ...

    @abstractmethod
    async def delete(self, user_id: UUID) -> None:
        """Delete a user by ID."""
        ...

    @abstractmethod
    async def list_all(self, skip: int = 0, limit: int = 100) -> list[User]:
        """List users with pagination."""
        ...

    @abstractmethod
    async def exists_by_username(self, username: str) -> bool:
        """Check if a username already exists."""
        ...
