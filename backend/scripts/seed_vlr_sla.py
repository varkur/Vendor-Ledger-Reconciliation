"""
Seed script for VLR SLA Configurations.
Creates default SLA durations per workflow step.
Run via: python -m scripts.seed_vlr_sla

This is idempotent — re-running will skip existing data.
"""

import asyncio
import sys
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select
from src.infrastructure.database.session import async_session_factory
from src.infrastructure.database.models.vlr.sla_configuration_model import SLAConfigurationModel


# Default SLA configurations per workflow step
# sla_hours represents the maximum time a case should remain in that step
DEFAULT_SLA_CONFIGS = [
    {"step_name": "initiation", "sla_hours": 4, "escalation_email": None},
    {"step_name": "sap_pull", "sla_hours": 2, "escalation_email": None},
    {"step_name": "transformation", "sla_hours": 2, "escalation_email": None},
    {"step_name": "finance_review", "sla_hours": 48, "escalation_email": None},
    {"step_name": "column_mapping", "sla_hours": 24, "escalation_email": None},
    {"step_name": "vendor_engagement", "sla_hours": 240, "escalation_email": None},
    {"step_name": "auto_reconciliation", "sla_hours": 4, "escalation_email": None},
    {"step_name": "exception_resolution", "sla_hours": 72, "escalation_email": None},
    {"step_name": "finance_approval", "sla_hours": 48, "escalation_email": None},
    {"step_name": "vendor_sign_off", "sla_hours": 120, "escalation_email": None},
    {"step_name": "closure", "sla_hours": 24, "escalation_email": None},
]


async def seed() -> None:
    """Seed default SLA configurations for all VLR workflow steps."""
    async with async_session_factory() as session:
        print("\n── VLR SLA Configurations ──")

        created_count = 0
        skipped_count = 0

        for config in DEFAULT_SLA_CONFIGS:
            existing = await session.execute(
                select(SLAConfigurationModel).where(
                    SLAConfigurationModel.step_name == config["step_name"]
                )
            )
            if existing.scalar_one_or_none():
                print(f"  [skip] SLA for '{config['step_name']}' already exists")
                skipped_count += 1
            else:
                sla = SLAConfigurationModel(
                    id=uuid4(),
                    step_name=config["step_name"],
                    sla_hours=config["sla_hours"],
                    escalation_email=config["escalation_email"],
                    is_active=True,
                    created_by="seed_script",
                    modified_by="seed_script",
                )
                session.add(sla)
                print(f"  [new]  SLA for '{config['step_name']}' = {config['sla_hours']}h")
                created_count += 1

        await session.commit()

        print(f"\n✓ VLR SLA seed complete.")
        print(f"  • Created: {created_count}")
        print(f"  • Skipped: {skipped_count}")
        print(f"\nDefault SLA durations:")
        print(f"  • Initiation: 4h")
        print(f"  • SAP Pull: 2h")
        print(f"  • Transformation: 2h")
        print(f"  • Finance Review: 48h (2 days)")
        print(f"  • Column Mapping: 24h (1 day)")
        print(f"  • Vendor Engagement: 240h (10 days)")
        print(f"  • Auto-Reconciliation: 4h")
        print(f"  • Exception Resolution: 72h (3 days)")
        print(f"  • Finance Approval: 48h (2 days)")
        print(f"  • Vendor Sign-Off: 120h (5 days)")
        print(f"  • Closure: 24h (1 day)")


if __name__ == "__main__":
    print("Seeding VLR SLA Configurations...")
    asyncio.run(seed())
