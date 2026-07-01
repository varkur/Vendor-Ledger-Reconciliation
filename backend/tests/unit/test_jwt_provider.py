"""
Unit tests for JWT token creation, validation, and expiration.
"""

import time
from uuid import uuid4
from unittest.mock import patch

import pytest

from src.infrastructure.security.jwt_provider import JWTProvider


class TestJWTProvider:
    """JWT provider unit tests."""

    def setup_method(self):
        self.jwt = JWTProvider()
        self.username = "testuser"
        self.user_id = uuid4()

    def test_create_access_token(self):
        """Access token should be a non-empty string."""
        token = self.jwt.create_access_token(self.username, self.user_id)
        assert isinstance(token, str)
        assert len(token) > 0

    def test_create_refresh_token(self):
        """Refresh token should be a non-empty string."""
        token = self.jwt.create_refresh_token(self.username, self.user_id)
        assert isinstance(token, str)
        assert len(token) > 0

    def test_verify_access_token(self):
        """Valid access token should decode correctly."""
        token = self.jwt.create_access_token(self.username, self.user_id)
        payload = self.jwt.verify_token(token, expected_type="access")

        assert payload.sub == self.username
        assert payload.user_id == str(self.user_id)
        assert payload.token_type == "access"

    def test_verify_refresh_token(self):
        """Valid refresh token should decode correctly."""
        token = self.jwt.create_refresh_token(self.username, self.user_id)
        payload = self.jwt.verify_token(token, expected_type="refresh")

        assert payload.sub == self.username
        assert payload.token_type == "refresh"

    def test_wrong_token_type_raises(self):
        """Verifying access token as refresh should raise ValueError."""
        token = self.jwt.create_access_token(self.username, self.user_id)

        with pytest.raises(ValueError, match="Invalid token type"):
            self.jwt.verify_token(token, expected_type="refresh")

    def test_expired_token_raises(self):
        """Expired token should raise an exception."""
        with patch(
            "src.config.settings.settings.ACCESS_TOKEN_EXPIRE_MINUTES", 0
        ):
            jwt = JWTProvider()
            # Create token that expires immediately
            jwt._access_expire_minutes = 0

        # Create a token with 0 minutes expiry won't actually expire instantly
        # due to datetime precision, so we test with decode instead
        import jwt as pyjwt
        from datetime import datetime, timedelta, timezone

        expired_payload = {
            "sub": self.username,
            "user_id": str(self.user_id),
            "token_type": "access",
            "iat": datetime.now(timezone.utc) - timedelta(hours=2),
            "exp": datetime.now(timezone.utc) - timedelta(hours=1),
        }
        expired_token = pyjwt.encode(
            expired_payload, "change-me-in-production-use-strong-secret", algorithm="HS256"
        )

        with pytest.raises(Exception):
            self.jwt.verify_token(expired_token, expected_type="access")

    def test_decode_token_returns_dict(self):
        """decode_token should return raw payload dictionary."""
        token = self.jwt.create_access_token(self.username, self.user_id)
        payload = self.jwt.decode_token(token)

        assert isinstance(payload, dict)
        assert payload["sub"] == self.username
        assert payload["token_type"] == "access"
