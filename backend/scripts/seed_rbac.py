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
from src.config.settings import settings
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

    # ─── VLR Permissions ───
    # vlr.vendors.*
    {"code": "vlr.vendors.read", "name": "View Vendors", "scope": "API", "resource": "vlr.vendors", "action": "READ"},
    {"code": "vlr.vendors.write", "name": "Create/Update Vendors", "scope": "API", "resource": "vlr.vendors", "action": "CREATE"},
    {"code": "vlr.vendors.create", "name": "Create Vendor", "scope": "API", "resource": "vlr.vendors", "action": "CREATE"},
    {"code": "vlr.vendors.update", "name": "Update Vendor", "scope": "API", "resource": "vlr.vendors", "action": "UPDATE"},
    {"code": "vlr.vendors.delete", "name": "Delete Vendor", "scope": "API", "resource": "vlr.vendors", "action": "DELETE"},
    {"code": "vlr.vendors.import", "name": "Import Vendors", "scope": "API", "resource": "vlr.vendors", "action": "IMPORT"},

    # vlr.requests.*
    {"code": "vlr.requests.read", "name": "View Reconciliation Requests", "scope": "API", "resource": "vlr.requests", "action": "READ"},
    {"code": "vlr.requests.write", "name": "Create/Update Requests", "scope": "API", "resource": "vlr.requests", "action": "CREATE"},
    {"code": "vlr.requests.create", "name": "Create Reconciliation Request", "scope": "API", "resource": "vlr.requests", "action": "CREATE"},
    {"code": "vlr.requests.update", "name": "Update Reconciliation Request", "scope": "API", "resource": "vlr.requests", "action": "UPDATE"},
    {"code": "vlr.requests.delete", "name": "Delete Reconciliation Request", "scope": "API", "resource": "vlr.requests", "action": "DELETE"},

    # vlr.cases.*
    {"code": "vlr.cases.read", "name": "View Reconciliation Cases", "scope": "API", "resource": "vlr.cases", "action": "READ"},
    {"code": "vlr.cases.write", "name": "Create/Update Cases", "scope": "API", "resource": "vlr.cases", "action": "CREATE"},
    {"code": "vlr.cases.create", "name": "Create Reconciliation Case", "scope": "API", "resource": "vlr.cases", "action": "CREATE"},
    {"code": "vlr.cases.update", "name": "Update Reconciliation Case", "scope": "API", "resource": "vlr.cases", "action": "UPDATE"},
    {"code": "vlr.cases.submit", "name": "Submit Case for Approval", "scope": "API", "resource": "vlr.cases", "action": "EXECUTE"},

    # vlr.exceptions.*
    {"code": "vlr.exceptions.read", "name": "View Exceptions", "scope": "API", "resource": "vlr.exceptions", "action": "READ"},
    {"code": "vlr.exceptions.write", "name": "Resolve/Modify Exceptions", "scope": "API", "resource": "vlr.exceptions", "action": "EXECUTE"},
    {"code": "vlr.exceptions.resolve", "name": "Resolve Exceptions", "scope": "API", "resource": "vlr.exceptions", "action": "EXECUTE"},
    {"code": "vlr.exceptions.write_off", "name": "Write Off Exceptions", "scope": "API", "resource": "vlr.exceptions", "action": "UPDATE"},

    # vlr.approvals.*
    {"code": "vlr.approvals.read", "name": "View Approvals", "scope": "API", "resource": "vlr.approvals", "action": "READ"},
    {"code": "vlr.approvals.approve", "name": "Approve/Reject Cases", "scope": "API", "resource": "vlr.approvals", "action": "EXECUTE"},
    {"code": "vlr.approvals.delegate", "name": "Delegate Approval Authority", "scope": "API", "resource": "vlr.approvals", "action": "UPDATE"},

    # vlr.notifications.*
    {"code": "vlr.notifications.read", "name": "View Notifications", "scope": "API", "resource": "vlr.notifications", "action": "READ"},
    {"code": "vlr.notifications.write", "name": "Send Notifications", "scope": "API", "resource": "vlr.notifications", "action": "CREATE"},

    # vlr.reports.*
    {"code": "vlr.reports.read", "name": "View Reports", "scope": "API", "resource": "vlr.reports", "action": "READ"},
    {"code": "vlr.reports.export", "name": "Export Reports", "scope": "API", "resource": "vlr.reports", "action": "EXPORT"},

    # vlr.settings.*
    {"code": "vlr.settings.read", "name": "View VLR Settings", "scope": "API", "resource": "vlr.settings", "action": "READ"},
    {"code": "vlr.settings.write", "name": "Modify VLR Settings", "scope": "API", "resource": "vlr.settings", "action": "UPDATE"},

    # vlr.portal.*
    {"code": "vlr.portal.read", "name": "View Vendor Portal", "scope": "API", "resource": "vlr.portal", "action": "READ"},
    {"code": "vlr.portal.upload", "name": "Upload Vendor Data", "scope": "API", "resource": "vlr.portal", "action": "CREATE"},
    {"code": "vlr.portal.sign_off", "name": "Vendor Sign-Off", "scope": "API", "resource": "vlr.portal", "action": "EXECUTE"},

    # VLR Menu permissions
    {"code": "menu.vlr_dashboard", "name": "VLR Dashboard Menu", "scope": "MENU", "resource": "vlr_dashboard", "action": "READ"},
    {"code": "menu.vlr_reconciliation", "name": "VLR Reconciliation Menu", "scope": "MENU", "resource": "vlr_reconciliation", "action": "READ"},
    {"code": "menu.vlr_reports", "name": "VLR Reports Menu", "scope": "MENU", "resource": "vlr_reports", "action": "READ"},
    {"code": "menu.vlr_settings", "name": "VLR Settings Menu", "scope": "MENU", "resource": "vlr_settings", "action": "READ"},

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
        # Admin also gets all VLR permissions
        "vlr.vendors.read", "vlr.vendors.write", "vlr.vendors.create", "vlr.vendors.update",
        "vlr.vendors.delete", "vlr.vendors.import",
        "vlr.requests.read", "vlr.requests.write", "vlr.requests.create", "vlr.requests.update", "vlr.requests.delete",
        "vlr.cases.read", "vlr.cases.write", "vlr.cases.create", "vlr.cases.update", "vlr.cases.submit",
        "vlr.exceptions.read", "vlr.exceptions.write", "vlr.exceptions.resolve", "vlr.exceptions.write_off",
        "vlr.approvals.read", "vlr.approvals.approve", "vlr.approvals.delegate",
        "vlr.notifications.read", "vlr.notifications.write",
        "vlr.reports.read", "vlr.reports.export",
        "vlr.settings.read", "vlr.settings.write",
        "vlr.portal.read", "vlr.portal.upload", "vlr.portal.sign_off",
        "menu.vlr_dashboard", "menu.vlr_reconciliation", "menu.vlr_reports", "menu.vlr_settings",
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
    # ─── VLR-Specific Roles ───
    "Reconciliation_User": [
        "menu.vlr_dashboard", "menu.vlr_reconciliation", "menu.vlr_reports",
        "vlr.vendors.read",
        "vlr.requests.read", "vlr.requests.create", "vlr.requests.update",
        "vlr.cases.read", "vlr.cases.create", "vlr.cases.update", "vlr.cases.submit",
        "vlr.exceptions.read", "vlr.exceptions.resolve",
        "vlr.approvals.read",
        "vlr.reports.read", "vlr.reports.export",
        "vlr.portal.read",
        "vlr.settings.read",
    ],
    "Reconciliation_Manager": [
        "menu.vlr_dashboard", "menu.vlr_reconciliation", "menu.vlr_reports", "menu.vlr_settings",
        "vlr.vendors.read", "vlr.vendors.create", "vlr.vendors.update", "vlr.vendors.import",
        "vlr.requests.read", "vlr.requests.create", "vlr.requests.update", "vlr.requests.delete",
        "vlr.cases.read", "vlr.cases.create", "vlr.cases.update", "vlr.cases.submit",
        "vlr.exceptions.read", "vlr.exceptions.resolve", "vlr.exceptions.write_off",
        "vlr.approvals.read", "vlr.approvals.approve", "vlr.approvals.delegate",
        "vlr.reports.read", "vlr.reports.export",
        "vlr.portal.read", "vlr.portal.upload", "vlr.portal.sign_off",
        "vlr.settings.read",
    ],
    "IT_Admin": [
        "menu.vlr_dashboard", "menu.vlr_reconciliation", "menu.vlr_reports", "menu.vlr_settings",
        "menu.users", "menu.roles", "menu.audit_logs",
        "users.list", "users.create", "users.update", "users.delete",
        "users.export", "users.import",
        "roles.list", "roles.create", "roles.update", "roles.assign",
        "audit.read", "rbac.read", "rbac.create", "rbac.update",
        "vlr.vendors.read", "vlr.vendors.write", "vlr.vendors.create", "vlr.vendors.update",
        "vlr.vendors.delete", "vlr.vendors.import",
        "vlr.requests.read", "vlr.requests.write", "vlr.requests.create", "vlr.requests.update", "vlr.requests.delete",
        "vlr.cases.read", "vlr.cases.write", "vlr.cases.create", "vlr.cases.update", "vlr.cases.submit",
        "vlr.exceptions.read", "vlr.exceptions.write", "vlr.exceptions.resolve", "vlr.exceptions.write_off",
        "vlr.approvals.read", "vlr.approvals.approve", "vlr.approvals.delegate",
        "vlr.notifications.read", "vlr.notifications.write",
        "vlr.reports.read", "vlr.reports.export",
        "vlr.settings.read", "vlr.settings.write",
        "vlr.portal.read", "vlr.portal.upload", "vlr.portal.sign_off",
    ],
    "Read_Only_Audit": [
        "menu.vlr_dashboard", "menu.vlr_reports",
        "vlr.vendors.read",
        "vlr.requests.read",
        "vlr.cases.read",
        "vlr.exceptions.read",
        "vlr.approvals.read",
        "vlr.reports.read",
        "vlr.settings.read",
        "vlr.portal.read",
        "audit.read",
    ],
}


async def seed() -> None:
    """Seed default permissions, VLR roles, and role-permission mappings."""
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

        # 2. Ensure VLR-specific roles exist
        VLR_ROLES = [
            {
                "code": "Reconciliation_User",
                "name": "Reconciliation User",
                "description": "VLR user who creates requests, manages cases, and resolves exceptions",
            },
            {
                "code": "Reconciliation_Manager",
                "name": "Reconciliation Manager",
                "description": "VLR manager who approves cases, delegates authority, and manages vendors",
            },
            {
                "code": "IT_Admin",
                "name": "IT Admin",
                "description": "VLR IT administrator with full system settings access",
            },
            {
                "code": "Read_Only_Audit",
                "name": "Read Only Audit",
                "description": "VLR read-only role for auditors and compliance reviewers",
            },
        ]

        for role_def in VLR_ROLES:
            existing_role = await session.execute(
                select(RoleModel).where(RoleModel.code == role_def["code"])
            )
            role = existing_role.scalar_one_or_none()
            if role:
                print(f"  [skip] Role '{role_def['code']}' already exists")
            else:
                new_role = RoleModel(
                    id=uuid4(),
                    code=role_def["code"],
                    name=role_def["name"],
                    description=role_def["description"],
                    is_active=True,
                    created_by="seed_script",
                    modified_by="seed_script",
                )
                session.add(new_role)
                print(f"  [new]  Role '{role_def['code']}' created")

        await session.flush()

        # 3. Assign permissions to roles
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

        # Fail fast if the configured Darwinbox default import role doesn't
        # resolve to an active role — this is the role UserService.import_from_darwinbox
        # assigns to every imported user (settings.DARWINBOX_DEFAULT_ROLE_CODE).
        default_role_result = await session.execute(
            select(RoleModel).where(
                RoleModel.code == settings.DARWINBOX_DEFAULT_ROLE_CODE,
                RoleModel.is_active == True,  # noqa: E712
            )
        )
        if default_role_result.scalar_one_or_none() is None:
            raise RuntimeError(
                f"DARWINBOX_DEFAULT_ROLE_CODE='{settings.DARWINBOX_DEFAULT_ROLE_CODE}' does not "
                "resolve to an existing active role after seeding. Darwinbox import will fail "
                "with a ConfigurationError until this is fixed — either seed the role or update "
                "the DARWINBOX_DEFAULT_ROLE_CODE setting."
            )
        print(
            f"✓ Verified DARWINBOX_DEFAULT_ROLE_CODE='{settings.DARWINBOX_DEFAULT_ROLE_CODE}' "
            "resolves to an active role."
        )

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
