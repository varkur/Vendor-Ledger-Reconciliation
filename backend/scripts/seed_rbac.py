"""
Seed script for RBAC permissions.
Populates default menu, API, and field-level permissions.
Run via: python -m scripts.seed_rbac

This is idempotent — re-running will skip existing permissions.
"""

import asyncio
import sys
from pathlib import Path
from uuid import uuid4

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select
from src.infrastructure.database.session import async_session_factory
from src.infrastructure.database.models.role_model import (
    PermissionModel,
    RoleAssignmentModel,
    RoleModel,
    RolePermissionModel,
)
from src.infrastructure.database.models.user_model import UserModel

# ─── Default Permission Definitions ───

DEFAULT_PERMISSIONS = [
    # Menu permissions — control sidebar/navigation visibility
    {"code": "menu.dashboard", "name": "Dashboard Menu", "scope": "MENU", "resource": "dashboard", "action": "READ"},
    {"code": "menu.users", "name": "Users Menu", "scope": "MENU", "resource": "users", "action": "READ"},
    {"code": "menu.roles", "name": "Roles Menu", "scope": "MENU", "resource": "roles", "action": "READ"},
    {"code": "menu.audit_logs", "name": "Audit Logs Menu", "scope": "MENU", "resource": "audit_logs", "action": "READ"},
    {"code": "menu.services", "name": "Services Menu", "scope": "MENU", "resource": "services", "action": "READ"},
    {"code": "menu.reports", "name": "Reports Menu", "scope": "MENU", "resource": "reports", "action": "READ"},
    {"code": "menu.settings", "name": "Settings Menu", "scope": "MENU", "resource": "settings", "action": "READ"},
    {"code": "menu.workflows", "name": "Workflows Menu", "scope": "MENU", "resource": "workflows", "action": "READ"},

    # API permissions — control endpoint access
    {"code": "users.list", "name": "List Users", "scope": "API", "resource": "users", "action": "READ"},
    {"code": "users.create", "name": "Create User", "scope": "API", "resource": "users", "action": "CREATE"},
    {"code": "users.update", "name": "Update User", "scope": "API", "resource": "users", "action": "UPDATE"},
    {"code": "users.delete", "name": "Delete User", "scope": "API", "resource": "users", "action": "DELETE"},
    {"code": "users.export", "name": "Export Users", "scope": "API", "resource": "users", "action": "EXPORT"},
    {"code": "users.import", "name": "Import Users", "scope": "API", "resource": "users", "action": "IMPORT"},
    {"code": "roles.list", "name": "List Roles", "scope": "API", "resource": "roles", "action": "READ"},
    {"code": "roles.create", "name": "Create Role", "scope": "API", "resource": "roles", "action": "CREATE"},
    {"code": "roles.update", "name": "Update Role", "scope": "API", "resource": "roles", "action": "UPDATE"},
    {"code": "roles.assign", "name": "Assign Roles", "scope": "API", "resource": "roles", "action": "EXECUTE"},
    {"code": "audit.read", "name": "View Audit Logs", "scope": "API", "resource": "audit_logs", "action": "READ"},
    {"code": "reports.export", "name": "Export Reports", "scope": "API", "resource": "reports", "action": "EXPORT"},

    # RBAC management permissions — granular control over roles & permissions CRUD
    {"code": "rbac.read", "name": "View Roles & Permissions", "scope": "API", "resource": "rbac", "action": "READ"},
    {"code": "rbac.create", "name": "Create Roles & Permissions", "scope": "API", "resource": "rbac", "action": "CREATE"},
    {"code": "rbac.update", "name": "Update Roles & Permissions", "scope": "API", "resource": "rbac", "action": "UPDATE"},

    # Employee AD service permission
    {"code": "services.employee_ad", "name": "Access Employee AD Service", "scope": "API", "resource": "services", "action": "EXECUTE"},

    # Field-level permissions — control visibility of sensitive fields
    {"code": "users.salary.read", "name": "View Salary", "scope": "FIELD", "resource": "users.salary", "action": "READ"},
    {"code": "users.salary.update", "name": "Edit Salary", "scope": "FIELD", "resource": "users.salary", "action": "UPDATE"},
    {"code": "users.email.read", "name": "View Email", "scope": "FIELD", "resource": "users.email", "action": "READ"},
    {"code": "users.email.update", "name": "Edit Email", "scope": "FIELD", "resource": "users.email", "action": "UPDATE"},
    {"code": "users.phone.read", "name": "View Phone", "scope": "FIELD", "resource": "users.phone", "action": "READ"},
]

# Role → permission code assignments
ROLE_PERMISSIONS = {
    "ADMIN": [
        # Admin gets ALL permissions
        "menu.dashboard", "menu.users", "menu.roles", "menu.audit_logs",
        "menu.services", "menu.reports", "menu.settings", "menu.workflows",
        "users.list", "users.create", "users.update", "users.delete",
        "users.export", "users.import",
        "roles.list", "roles.create", "roles.update", "roles.assign",
        "audit.read", "reports.export",
        "rbac.read", "rbac.create", "rbac.update", "services.employee_ad",
        "users.salary.read", "users.salary.update",
        "users.email.read", "users.email.update", "users.phone.read",
    ],
    "MANAGER": [
        "menu.dashboard", "menu.users", "menu.reports", "menu.services",
        "users.list", "users.export",
        "reports.export",
        "users.email.read", "users.phone.read",
    ],
    "USER": [
        "menu.dashboard", "menu.services",
    ],
}


async def seed() -> None:
    """Seed default permissions and role-permission mappings."""
    async with async_session_factory() as session:
        # 1. Create permissions (skip existing)
        perm_map: dict[str, str] = {}  # code → id

        for perm_def in DEFAULT_PERMISSIONS:
            existing = await session.execute(
                select(PermissionModel).where(PermissionModel.code == perm_def["code"])
            )
            perm = existing.scalar_one_or_none()

            if perm:
                perm_map[perm.code] = str(perm.id)
                print(f"  [skip] Permission '{perm_def['code']}' already exists")
            else:
                new_perm = PermissionModel(
                    id=uuid4(),
                    code=perm_def["code"],
                    name=perm_def["name"],
                    description="",
                    scope=perm_def["scope"],
                    resource=perm_def["resource"],
                    action=perm_def["action"],
                    is_active=True,
                    created_by="seed_script",
                    modified_by="seed_script",
                )
                session.add(new_perm)
                perm_map[perm_def["code"]] = str(new_perm.id)
                print(f"  [new]  Permission '{perm_def['code']}' created")

        await session.flush()

        # 2. Assign permissions to roles
        for role_code, perm_codes in ROLE_PERMISSIONS.items():
            role_result = await session.execute(
                select(RoleModel).where(RoleModel.code == role_code)
            )
            role = role_result.scalar_one_or_none()
            if not role:
                print(f"  [warn] Role '{role_code}' not found — skipping assignments")
                continue

            for perm_code in perm_codes:
                perm_id = perm_map.get(perm_code)
                if not perm_id:
                    continue

                existing_rp = await session.execute(
                    select(RolePermissionModel).where(
                        RolePermissionModel.role_id == str(role.id),
                        RolePermissionModel.permission_id == perm_id,
                    )
                )
                if existing_rp.scalar_one_or_none():
                    continue

                rp = RolePermissionModel(
                    id=uuid4(),
                    role_id=str(role.id),
                    permission_id=perm_id,
                    created_by="seed_script",
                    modified_by="seed_script",
                )
                session.add(rp)
                print(f"  [link] {role_code} ← {perm_code}")

        await session.commit()
        print("\n✓ RBAC seed complete.")

    # 3. Assign ADMIN role to all existing users who don't have any role assignment
    async with async_session_factory() as session:
        print("\nAssigning default role to existing users without role assignments...")

        # Find the ADMIN role
        admin_role_result = await session.execute(
            select(RoleModel).where(RoleModel.code == "ADMIN")
        )
        admin_role = admin_role_result.scalar_one_or_none()
        if not admin_role:
            print("  [warn] ADMIN role not found — skipping user assignments")
        else:
            # Find all users
            users_result = await session.execute(select(UserModel))
            users = users_result.scalars().all()

            for user in users:
                # Check if user already has any role assignment
                existing_assignment = await session.execute(
                    select(RoleAssignmentModel).where(
                        RoleAssignmentModel.user_id == str(user.id),
                    )
                )
                if existing_assignment.scalar_one_or_none():
                    print(f"  [skip] User '{user.username}' already has a role assignment")
                    continue

                # Assign ADMIN role as default for existing users
                assignment = RoleAssignmentModel(
                    id=uuid4(),
                    user_id=str(user.id),
                    role_id=str(admin_role.id),
                    tenant_id=None,
                    is_active=True,
                    created_by="seed_script",
                    modified_by="seed_script",
                )
                session.add(assignment)
                print(f"  [new]  User '{user.username}' → Role 'ADMIN'")

        await session.commit()
        print("\n✓ Role assignments complete.")


if __name__ == "__main__":
    print("Seeding RBAC permissions...")
    asyncio.run(seed())
