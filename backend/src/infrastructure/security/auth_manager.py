"""
Authentication manager.
Coordinates login flow: user lookup, password verification, status checks, token issuance.
Supports dual authentication:
  - is_validate_ad=True: Validate via Darwin AD service
  - is_validate_ad=False: Validate via local bcrypt password
"""

import logging
from dataclasses import dataclass

from src.config.settings import settings
from src.domain.repositories.user_repository import IUserRepository
from src.infrastructure.security.jwt_provider import JWTProvider
from src.infrastructure.security.password_encoder import verify_password

logger = logging.getLogger(__name__)


@dataclass
class AuthTokenResponse:
    """Authentication response containing token pair."""

    access_token: str
    refresh_token: str
    token_type: str = "Bearer"
    expires_in: int = 0

    def __post_init__(self) -> None:
        if self.expires_in == 0:
            self.expires_in = settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60


class AuthenticationError(Exception):
    """Base authentication error."""

    def __init__(self, message: str, status_code: int = 401) -> None:
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class UserInactiveError(AuthenticationError):
    """Raised when user account is inactive."""

    def __init__(self) -> None:
        super().__init__("User account is inactive", status_code=403)


class UserBlockedError(AuthenticationError):
    """Raised when user account is blocked."""

    def __init__(self) -> None:
        super().__init__("User account is blocked", status_code=403)


class InvalidCredentialsError(AuthenticationError):
    """Raised when credentials are invalid."""

    def __init__(self) -> None:
        super().__init__("Invalid username or password", status_code=401)


class AuthManager:
    """Handles authentication operations: login and token refresh."""

    def __init__(
        self,
        user_repository: IUserRepository,
        jwt_provider: JWTProvider,
    ) -> None:
        self._user_repo = user_repository
        self._jwt = jwt_provider

    async def login(self, username: str, password: str) -> AuthTokenResponse:
        """
        Authenticate a user with username and password.

        Flow:
        1. Find user by username
        2. If is_validate_ad=True → validate via Darwin AD service
        3. If is_validate_ad=False → verify local password hash
        4. Check is_active
        5. Check is_blocked
        6. Generate token pair

        Raises:
            InvalidCredentialsError: Wrong username or password.
            UserInactiveError: Account is deactivated.
            UserBlockedError: Account is blocked.
        """
        user = await self._user_repo.get_by_username(username)

        if user is None:
            raise InvalidCredentialsError()

        # Branch: AD validation vs local password
        if user.is_validate_ad:
            await self._validate_with_darwin(username, password)
        else:
            if not verify_password(password, user.password_hash):
                raise InvalidCredentialsError()

        if not user.is_active:
            raise UserInactiveError()

        if user.is_blocked:
            raise UserBlockedError()

        access_token = self._jwt.create_access_token(user.username, user.id)
        refresh_token = self._jwt.create_refresh_token(user.username, user.id)

        return AuthTokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
        )

    async def _validate_with_darwin(self, employee_id: str, password: str) -> None:
        """
        Validate credentials against Darwin AD service.

        Raises:
            InvalidCredentialsError: If Darwin says invalid or service is unreachable.
        """
        from src.infrastructure.external.employee_ad.employee_ad_client import (
            EmployeeADClient,
            EmployeeADError,
        )

        client = EmployeeADClient()
        try:
            result = await client.validate_credentials(employee_id, password)
            if not result.is_valid_user:
                raise InvalidCredentialsError()
        except EmployeeADError as exc:
            logger.error("Darwin AD validation failed for %s: %s", employee_id, exc)
            raise InvalidCredentialsError()

    async def refresh(self, refresh_token: str) -> AuthTokenResponse:
        """
        Issue a new access token using a valid refresh token.

        Raises:
            AuthenticationError: Invalid or expired refresh token.
            UserInactiveError: User is no longer active.
            UserBlockedError: User has been blocked since token issuance.
        """
        try:
            payload = self._jwt.verify_token(refresh_token, expected_type="refresh")
        except Exception as e:
            raise AuthenticationError(f"Invalid refresh token: {e}", status_code=401)

        user = await self._user_repo.get_by_username(payload.sub)

        if user is None:
            raise AuthenticationError("User not found", status_code=401)

        if not user.is_active:
            raise UserInactiveError()

        if user.is_blocked:
            raise UserBlockedError()

        new_access_token = self._jwt.create_access_token(user.username, user.id)

        return AuthTokenResponse(
            access_token=new_access_token,
            refresh_token=refresh_token,  # Return the same refresh token
        )
