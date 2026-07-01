"""
Role-Based Access Control (RBAC) manager.
Provides role validation and endpoint protection via FastAPI dependencies.
"""

from enum import StrEnum
from typing import Callable

from fastapi import Depends, HTTPException, status

from src.domain.entities.user import User


class Role(StrEnum):
    """System roles ordered by privilege level."""

    ADMIN = "ADMIN"
    MANAGER = "MANAGER"
    USER = "USER"


# Role hierarchy: higher number = higher privilege
ROLE_HIERARCHY: dict[str, int] = {
    "USER": 1,
    "MANAGER": 2,
    "ADMIN": 3,
}


def has_minimum_role(user_role: str, required_role: str) -> bool:
    """Check if user's role meets or exceeds the required role level."""
    user_level = ROLE_HIERARCHY.get(user_role, 0)
    required_level = ROLE_HIERARCHY.get(required_role, 0)
    return user_level >= required_level


def require_role(required_role: str) -> Callable:
    """
    FastAPI dependency factory for role-based endpoint protection.

    Usage (as route dependency):
        @router.get("/admin", dependencies=[Depends(require_role("ADMIN"))])

    Usage (as parameter dependency for access to user):
        async def endpoint(user: User = Depends(require_role("ADMIN"))):
    """
    from src.api.v1.dependencies import get_current_active_user

    async def role_checker(
        current_user: User = Depends(get_current_active_user),
    ) -> User:
        if not has_minimum_role(current_user.role, required_role):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{required_role}' or higher required",
            )
        return current_user

    return role_checker
