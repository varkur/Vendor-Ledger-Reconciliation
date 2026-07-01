"""
User repository implementation (Adapter).
Implements the IUserRepository using SQLAlchemy async.
"""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.entities.user import User
from src.domain.repositories.user_repository import IUserRepository
from src.infrastructure.database.models.user_model import UserModel


class UserRepositoryImpl(IUserRepository):
    """Concrete implementation of user persistence using SQLAlchemy."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, user_id: UUID) -> User | None:
        stmt = select(UserModel).where(UserModel.id == user_id)
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return self._to_entity(model) if model else None

    async def get_by_username(self, username: str) -> User | None:
        stmt = select(UserModel).where(UserModel.username == username)
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return self._to_entity(model) if model else None

    async def create(self, user: User) -> User:
        model = UserModel(
            id=user.id,
            username=user.username,
            password_hash=user.password_hash,
            is_active=user.is_active,
            is_blocked=user.is_blocked,
            is_validate_ad=user.is_validate_ad,
            created_by=user.created_by,
            modified_by=user.modified_by,
        )
        self._session.add(model)
        await self._session.flush()
        return self._to_entity(model)

    async def update(self, user: User) -> User:
        stmt = select(UserModel).where(UserModel.id == user.id)
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        if model is None:
            raise ValueError(f"User with id {user.id} not found")

        model.username = user.username
        model.password_hash = user.password_hash
        model.is_active = user.is_active
        model.is_blocked = user.is_blocked
        model.is_validate_ad = user.is_validate_ad
        model.modified_by = user.modified_by
        model.modified_date = user.modified_date

        await self._session.flush()
        return self._to_entity(model)

    async def delete(self, user_id: UUID) -> None:
        stmt = select(UserModel).where(UserModel.id == user_id)
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        if model:
            await self._session.delete(model)
            await self._session.flush()

    async def list_all(self, skip: int = 0, limit: int = 100) -> list[User]:
        stmt = select(UserModel).offset(skip).limit(limit)
        result = await self._session.execute(stmt)
        models = result.scalars().all()
        return [self._to_entity(m) for m in models]

    async def exists_by_username(self, username: str) -> bool:
        stmt = select(UserModel.id).where(UserModel.username == username)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none() is not None

    @staticmethod
    def _to_entity(model: UserModel) -> User:
        """Map ORM model to domain entity."""
        return User(
            id=model.id,
            username=model.username,
            password_hash=model.password_hash,
            is_active=model.is_active,
            is_blocked=model.is_blocked,
            is_validate_ad=model.is_validate_ad,
            created_by=model.created_by,
            created_date=model.created_date,
            modified_by=model.modified_by,
            modified_date=model.modified_date,
        )
