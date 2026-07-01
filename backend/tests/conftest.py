"""
Root test configuration and shared fixtures.
"""

import pytest
from uuid import uuid4
from datetime import datetime, timezone

from src.domain.entities.user import User
from src.infrastructure.security.jwt_provider import JWTProvider
from src.infrastructure.security.password_encoder import hash_password


@pytest.fixture
def jwt_provider() -> JWTProvider:
    """Provide a JWTProvider instance for tests."""
    return JWTProvider()


@pytest.fixture
def sample_user() -> User:
    """Provide a sample active user entity."""
    return User(
        id=uuid4(),
        username="testuser",
        password_hash=hash_password("StrongPass123!"),
        is_active=True,
        is_blocked=False,
        role="USER",
        created_by="system",
        created_date=datetime.now(timezone.utc),
        modified_by="system",
        modified_date=datetime.now(timezone.utc),
    )


@pytest.fixture
def inactive_user() -> User:
    """Provide an inactive user entity."""
    return User(
        id=uuid4(),
        username="inactiveuser",
        password_hash=hash_password("StrongPass123!"),
        is_active=False,
        is_blocked=False,
        role="USER",
    )


@pytest.fixture
def blocked_user() -> User:
    """Provide a blocked user entity."""
    return User(
        id=uuid4(),
        username="blockeduser",
        password_hash=hash_password("StrongPass123!"),
        is_active=True,
        is_blocked=True,
        role="USER",
    )
