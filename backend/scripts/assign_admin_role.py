"""Assign IT_Admin role (full VLR access) to the admin user."""

import asyncio
from uuid import uuid4

from sqlalchemy import select, text

from src.infrastructure.database.session import async_session_factory


async def assign_admin_role():
    async with async_session_factory() as session:
        # Get admin user ID
        result = await session.execute(text("SELECT id FROM users WHERE username = 'admin'"))
        admin_id = result.scalar_one_or_none()
        if admin_id is None:
            print("Admin user not found. Run seed_data.py first.")
            return

        # Get IT_Admin role ID (has all VLR permissions)
        result = await session.execute(text("SELECT id FROM roles WHERE code = 'IT_Admin'"))
        role_id = result.scalar_one_or_none()

        if role_id is None:
            # Fallback: try Reconciliation_Manager
            result = await session.execute(text("SELECT id FROM roles WHERE code = 'Reconciliation_Manager'"))
            role_id = result.scalar_one_or_none()

        if role_id is None:
            print("No VLR role found. Run seed_rbac.py first.")
            result = await session.execute(text("SELECT code FROM roles"))
            codes = [r[0] for r in result.fetchall()]
            print(f"Available roles: {codes}")
            return

        # Check if assignment already exists
        result = await session.execute(
            text("SELECT 1 FROM role_assignments WHERE user_id = :uid AND role_id = :rid"),
            {"uid": str(admin_id), "rid": str(role_id)},
        )
        if result.scalar_one_or_none():
            print("Admin already has VLR role assignment. Skipping.")
            return

        # Assign role
        await session.execute(
            text("INSERT INTO role_assignments (id, user_id, role_id) VALUES (:id, :uid, :rid)"),
            {"id": str(uuid4()), "uid": str(admin_id), "rid": str(role_id)},
        )
        await session.commit()
        print(f"Assigned IT_Admin role to admin user successfully.")
        print(f"  Admin user ID: {admin_id}")
        print(f"  Role ID: {role_id}")


if __name__ == "__main__":
    asyncio.run(assign_admin_role())
