"""
FastAPI dependency injection for API v1.
Provides current user resolution from JWT tokens and service factories.
"""

from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.entities.user import User
from src.domain.repositories.user_repository import IUserRepository
from src.infrastructure.database.repositories.user_repository_impl import (
    UserRepositoryImpl,
)
from src.infrastructure.database.session import get_db_session
from src.infrastructure.security.auth_manager import AuthManager
from src.infrastructure.security.jwt_provider import JWTProvider

# Bearer token extraction scheme (enables Swagger "Authorize" button)
bearer_scheme = HTTPBearer(auto_error=True)


def get_jwt_provider() -> JWTProvider:
    """Provide JWT provider instance."""
    return JWTProvider()


def get_user_repository(
    session: AsyncSession = Depends(get_db_session),
) -> IUserRepository:
    """Provide user repository with injected session."""
    return UserRepositoryImpl(session)


def get_auth_manager(
    user_repo: IUserRepository = Depends(get_user_repository),
    jwt_provider: JWTProvider = Depends(get_jwt_provider),
) -> AuthManager:
    """Provide authentication manager with dependencies."""
    return AuthManager(user_repository=user_repo, jwt_provider=jwt_provider)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    jwt_provider: JWTProvider = Depends(get_jwt_provider),
    user_repo: IUserRepository = Depends(get_user_repository),
) -> User:
    """
    Resolve the current authenticated user from the JWT access token.

    Raises:
        HTTPException 401: If token is missing, invalid, or expired.
        HTTPException 401: If user does not exist.
    """
    try:
        payload = jwt_provider.verify_token(credentials.credentials, expected_type="access")
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid or expired token: {e}",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = await user_repo.get_by_username(payload.sub)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user


async def get_current_active_user(
    current_user: User = Depends(get_current_user),
) -> User:
    """
    Ensure the current user is active and not blocked.

    Raises:
        HTTPException 403: If user is inactive or blocked.
    """
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive",
        )
    if current_user.is_blocked:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is blocked",
        )
    return current_user
