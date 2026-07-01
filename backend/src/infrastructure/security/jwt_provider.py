"""
JWT token creation, validation, and decoding.
Handles access tokens and refresh tokens with configurable expiry.
"""

from datetime import datetime, timedelta, timezone
from uuid import UUID

import jwt

from src.config.settings import settings


class TokenPayload:
    """Decoded JWT token payload."""

    def __init__(
        self,
        sub: str,
        user_id: str,
        token_type: str,
        iat: datetime,
        exp: datetime,
    ) -> None:
        self.sub = sub
        self.user_id = user_id
        self.token_type = token_type
        self.iat = iat
        self.exp = exp


class JWTProvider:
    """Handles JWT token lifecycle: creation, verification, and decoding."""

    def __init__(self) -> None:
        self._secret_key = settings.JWT_SECRET_KEY
        self._algorithm = settings.JWT_ALGORITHM
        self._access_expire_minutes = settings.ACCESS_TOKEN_EXPIRE_MINUTES
        self._refresh_expire_days = settings.REFRESH_TOKEN_EXPIRE_DAYS

    def create_access_token(self, username: str, user_id: UUID) -> str:
        """Generate an access token with short-lived expiry."""
        now = datetime.now(timezone.utc)
        payload = {
            "sub": username,
            "user_id": str(user_id),
            "token_type": "access",
            "iat": now,
            "exp": now + timedelta(minutes=self._access_expire_minutes),
        }
        return jwt.encode(payload, self._secret_key, algorithm=self._algorithm)

    def create_refresh_token(self, username: str, user_id: UUID) -> str:
        """Generate a refresh token with longer expiry."""
        now = datetime.now(timezone.utc)
        payload = {
            "sub": username,
            "user_id": str(user_id),
            "token_type": "refresh",
            "iat": now,
            "exp": now + timedelta(days=self._refresh_expire_days),
        }
        return jwt.encode(payload, self._secret_key, algorithm=self._algorithm)

    def verify_token(self, token: str, expected_type: str = "access") -> TokenPayload:
        """
        Verify and decode a JWT token.

        Args:
            token: The encoded JWT string.
            expected_type: Expected token_type claim ("access" or "refresh").

        Returns:
            TokenPayload with decoded claims.

        Raises:
            jwt.ExpiredSignatureError: Token has expired.
            jwt.InvalidTokenError: Token is invalid or malformed.
            ValueError: Token type does not match expected_type.
        """
        payload = jwt.decode(
            token, self._secret_key, algorithms=[self._algorithm]
        )

        token_type = payload.get("token_type")
        if token_type != expected_type:
            raise ValueError(
                f"Invalid token type: expected '{expected_type}', got '{token_type}'"
            )

        return TokenPayload(
            sub=payload["sub"],
            user_id=payload["user_id"],
            token_type=payload["token_type"],
            iat=datetime.fromtimestamp(payload["iat"], tz=timezone.utc),
            exp=datetime.fromtimestamp(payload["exp"], tz=timezone.utc),
        )

    def decode_token(self, token: str) -> dict:
        """Decode a token without type validation. Returns raw payload dict."""
        return jwt.decode(
            token, self._secret_key, algorithms=[self._algorithm]
        )
