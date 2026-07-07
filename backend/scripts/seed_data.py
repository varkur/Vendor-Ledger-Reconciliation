"""
Database seed script.
Creates initial admin user for development/testing.

Usage:
    python -m scripts.seed_data
"""

import asyncio
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.database.models.user_model import UserModel
from src.infrastructure.database.session import async_session_factory
from src.infrastructure.security.password_encoder import hash_password


async def seed_admin_user() -> None:
    """Create default admin user if not exists."""
    async with async_session_factory() as session:
        # Check if admin exists
        from sqlalchemy import select

        stmt = select(UserModel).where(UserModel.username == "admin")
        result = await session.execute(stmt)
        existing = result.scalar_one_or_none()

        if existing:
            print("Admin user already exists. Skipping seed.")
            return

        admin = UserModel(
            id=uuid4(),
            username="admin",
            password_hash=hash_password("Admin@123!"),
            is_active=True,
            is_blocked=False,
            is_validate_ad=False,
            created_by="seed_script",
            modified_by="seed_script",
        )
        session.add(admin)
        await session.commit()
        print(f"Admin user created: username=admin, id={admin.id}")


if __name__ == "__main__":
    asyncio.run(seed_admin_user())
