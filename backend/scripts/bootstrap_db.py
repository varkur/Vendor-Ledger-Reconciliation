"""
One-shot database bootstrap for a fresh Vendor Ledger Reconciliation install.

Runs (in order):
  1. Alembic migrations   -> creates all tables (schema)
  2. seed_data            -> default admin user (admin / Admin@123!)
  3. seed_rbac            -> permissions + VLR roles + role-permission mapping
  4. assign_admin_role    -> gives the admin user full VLR access
  5. seed_vlr_permissions -> VLR-specific permissions for the admin role
  6. seed_vlr_sla         -> default SLA durations per workflow step
  7. seed_workflow        -> sample workflow (optional, safe/idempotent)

Usage (from the backend/ or deploy/app/ directory, with .env configured):
    python -m scripts.bootstrap_db

All steps are idempotent — re-running will skip data that already exists.
Migrations are applied via `alembic upgrade head` before seeding.
"""

import asyncio
import subprocess
import sys
from pathlib import Path


def run_migrations() -> None:
    """Apply all Alembic migrations up to head."""
    backend_dir = Path(__file__).resolve().parent.parent
    print("── Applying database migrations (alembic upgrade head) ──")
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=str(backend_dir),
    )
    if result.returncode != 0:
        print("Migrations failed. Aborting bootstrap.")
        sys.exit(result.returncode)
    print("✓ Migrations applied.\n")


async def run_seeds() -> None:
    """Run all seed scripts in dependency order."""
    from scripts.seed_data import seed_admin_user
    from scripts.seed_rbac import seed as seed_rbac
    from scripts.assign_admin_role import assign_admin_role
    from scripts.seed_vlr_sla import seed as seed_vlr_sla

    print("── 1/5 Admin user ──")
    await seed_admin_user()

    print("\n── 2/5 RBAC permissions & roles (includes all vlr.* permissions) ──")
    await seed_rbac()

    print("\n── 3/5 Assign admin role ──")
    await assign_admin_role()

    print("\n── 4/5 VLR SLA configurations ──")
    await seed_vlr_sla()

    # Workflow seed is optional; skip failures so it never blocks bootstrap.
    print("\n── 5/5 Sample workflow (optional) ──")
    try:
        from scripts.seed_workflow import seed as seed_workflow
        await seed_workflow()
    except Exception as e:  # noqa: BLE001
        print(f"  Skipped workflow seed: {e}")


def main() -> None:
    run_migrations()
    asyncio.run(run_seeds())
    print("\n✅ Database bootstrap complete.")
    print("   Login: username=admin  password=Admin@123!")


if __name__ == "__main__":
    main()
