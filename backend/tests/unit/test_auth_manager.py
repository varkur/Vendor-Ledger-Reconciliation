"""
Unit tests for Authentication Manager.
Tests login flows: success, invalid password, inactive user, blocked user.
"""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.domain.entities.user import User
from src.infrastructure.security.auth_manager import (
    AuthManager,
    InvalidCredentialsError,
    UserBlockedError,
    UserInactiveError,
)
from src.infrastructure.security.jwt_provider import JWTProvider
from src.infrastructure.security.password_encoder import hash_password


@pytest.fixture
def mock_user_repo():
    repo = AsyncMock()
    return repo


@pytest.fixture
def jwt_provider():
    return JWTProvider()


@pytest.fixture
def auth_manager(mock_user_repo, jwt_provider):
    return AuthManager(user_repository=mock_user_repo, jwt_provider=jwt_provider)


@pytest.fixture
def active_user():
    return User(
        id=uuid4(),
        username="activeuser",
        password_hash=hash_password("ValidPass123!"),
        is_active=True,
        is_blocked=False,
        role="USER",
    )


class TestLoginSuccess:
    @pytest.mark.asyncio
    async def test_login_success(self, auth_manager, mock_user_repo, active_user):
        """Valid credentials for an active, unblocked user should return tokens."""
        mock_user_repo.get_by_username.return_value = active_user

        result = await auth_manager.login("activeuser", "ValidPass123!")

        assert result.access_token
        assert result.refresh_token
        assert result.token_type == "Bearer"
        assert result.expires_in > 0


class TestLoginInvalidPassword:
    @pytest.mark.asyncio
    async def test_login_wrong_password(self, auth_manager, mock_user_repo, active_user):
        """Wrong password should raise InvalidCredentialsError."""
        mock_user_repo.get_by_username.return_value = active_user

        with pytest.raises(InvalidCredentialsError):
            await auth_manager.login("activeuser", "WrongPassword!")


class TestLoginUserNotFound:
    @pytest.mark.asyncio
    async def test_login_user_not_found(self, auth_manager, mock_user_repo):
        """Non-existent user should raise InvalidCredentialsError."""
        mock_user_repo.get_by_username.return_value = None

        with pytest.raises(InvalidCredentialsError):
            await auth_manager.login("ghost", "anypass")


class TestLoginInactiveUser:
    @pytest.mark.asyncio
    async def test_login_inactive_user(self, auth_manager, mock_user_repo):
        """Inactive user should raise UserInactiveError."""
        user = User(
            id=uuid4(),
            username="inactiveuser",
            password_hash=hash_password("ValidPass123!"),
            is_active=False,
            is_blocked=False,
        )
        mock_user_repo.get_by_username.return_value = user

        with pytest.raises(UserInactiveError):
            await auth_manager.login("inactiveuser", "ValidPass123!")


class TestLoginBlockedUser:
    @pytest.mark.asyncio
    async def test_login_blocked_user(self, auth_manager, mock_user_repo):
        """Blocked user should raise UserBlockedError."""
        user = User(
            id=uuid4(),
            username="blockeduser",
            password_hash=hash_password("ValidPass123!"),
            is_active=True,
            is_blocked=True,
        )
        mock_user_repo.get_by_username.return_value = user

        with pytest.raises(UserBlockedError):
            await auth_manager.login("blockeduser", "ValidPass123!")


class TestRefreshToken:
    @pytest.mark.asyncio
    async def test_refresh_success(self, auth_manager, mock_user_repo, active_user, jwt_provider):
        """Valid refresh token should return new access token."""
        mock_user_repo.get_by_username.return_value = active_user
        refresh = jwt_provider.create_refresh_token(active_user.username, active_user.id)

        result = await auth_manager.refresh(refresh)

        assert result.access_token
        assert result.token_type == "Bearer"

    @pytest.mark.asyncio
    async def test_refresh_invalid_token(self, auth_manager, mock_user_repo):
        """Invalid refresh token should raise AuthenticationError."""
        from src.infrastructure.security.auth_manager import AuthenticationError

        with pytest.raises(AuthenticationError):
            await auth_manager.refresh("invalid.token.here")
