"""
Dependency Injection container.
Wires domain interfaces to infrastructure implementations.
Used for overriding dependencies in tests and different environments.
"""

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.repositories.user_repository import IUserRepository
from src.infrastructure.database.repositories.user_repository_impl import (
    UserRepositoryImpl,
)
from src.infrastructure.database.session import get_db_session
from src.infrastructure.security.auth_manager import AuthManager
from src.infrastructure.security.jwt_provider import JWTProvider


class Container:
    """
    Simple DI container for managing service instances.
    In production, consider dependency-injector library for more complex graphs.
    """

    @staticmethod
    def get_jwt_provider() -> JWTProvider:
        return JWTProvider()

    @staticmethod
    def get_user_repository(session: AsyncSession) -> IUserRepository:
        return UserRepositoryImpl(session)

    @staticmethod
    def get_auth_manager(
        user_repo: IUserRepository,
        jwt_provider: JWTProvider,
    ) -> AuthManager:
        return AuthManager(user_repository=user_repo, jwt_provider=jwt_provider)
