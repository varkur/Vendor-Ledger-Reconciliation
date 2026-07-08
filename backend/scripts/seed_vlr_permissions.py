"""Seed VLR-specific permissions for the admin role."""
import asyncio
from uuid import uuid4
from sqlalchemy import text
from src.infrastructure.database.session import async_session_factory


VLR_PERMISSIONS = [
    "vlr.cases.read",
    "vlr.cases.write",
    "vlr.reports.read",
    "vlr.reports.write",
    "vlr.recovery.read",
    "vlr.recovery.write",
    "vlr.audit.read",
]


async def seed():
    async with async_session_factory() as session:
        # Get admin role ID
        result = await session.execute(
            text("SELECT id FROM roles WHERE name = 'admin' OR name = 'Admin' LIMIT 1")
        )
        role_row = result.fetchone()
        if not role_row:
            print("No admin role found, creating one...")
            admin_role_id = str(uuid4())
            await session.execute(
                text(
                    "INSERT INTO roles (id, name, description, is_active, created_by, modified_by) "
                    "VALUES (:id, 'admin', 'Administrator', true, 'seed', 'seed')"
                ),
                {"id": admin_role_id},
            )
        else:
            admin_role_id = str(role_row[0])
        print(f"Admin role ID: {admin_role_id}")

        # Check if admin user has role assignment
        result = await session.execute(
            text("SELECT id FROM users WHERE username = 'admin' LIMIT 1")
        )
        user_row = result.fetchone()
        if user_row:
            admin_user_id = str(user_row[0])
            # Check role assignment
            ra = await session.execute(
                text(
                    "SELECT id FROM role_assignments WHERE user_id = :uid AND role_id = :rid LIMIT 1"
                ),
                {"uid": admin_user_id, "rid": admin_role_id},
            )
            if not ra.fetchone():
                await session.execute(
                    text(
                        "INSERT INTO role_assignments (id, user_id, role_id, is_active, created_by, modified_by) "
                        "VALUES (:id, :uid, :rid, true, 'seed', 'seed')"
                    ),
                    {"id": str(uuid4()), "uid": admin_user_id, "rid": admin_role_id},
                )
                print(f"  Assigned admin role to user {admin_user_id}")

        # Seed permissions
        for perm_code in VLR_PERMISSIONS:
            existing = await session.execute(
                text("SELECT id FROM permissions WHERE code = :code"),
                {"code": perm_code},
            )
            if existing.fetchone():
                print(f"  [skip] {perm_code}")
                continue

            perm_id = str(uuid4())
            parts = perm_code.split(".")
            resource = parts[1] if len(parts) > 1 else perm_code
            action = parts[2] if len(parts) > 2 else "read"

            await session.execute(
                text(
                    "INSERT INTO permissions (id, code, name, description, scope, resource, action, created_by, modified_by) "
                    "VALUES (:id, :code, :name, :desc, 'API', :resource, :action, 'seed', 'seed')"
                ),
                {
                    "id": perm_id,
                    "code": perm_code,
                    "name": perm_code.replace(".", " ").title(),
                    "desc": f"VLR permission: {perm_code}",
                    "resource": resource,
                    "action": action,
                },
            )

            # Assign to admin role
            await session.execute(
                text(
                    "INSERT INTO role_permissions (id, role_id, permission_id, created_by, modified_by) "
                    "VALUES (:id, :role_id, :perm_id, 'seed', 'seed')"
                ),
                {"id": str(uuid4()), "role_id": admin_role_id, "perm_id": perm_id},
            )
            print(f"  [new] {perm_code}")

        await session.commit()
        print("\nDone! VLR permissions seeded for admin role.")


if __name__ == "__main__":
    asyncio.run(seed())
