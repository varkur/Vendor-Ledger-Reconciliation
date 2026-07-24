"""Delete all reconciliation data (cases, requests, and dependent child rows)."""
import asyncio
from sqlalchemy import text
from src.infrastructure.database.session import async_session_factory

# Child tables that reference cases/requests, deleted before parents
CHILD_TABLES = [
    "vlr_portal_sign_offs",
    "vlr_match_results",
    "vlr_ledger_entries",
    "vlr_reco_exceptions",
    "vlr_resolution_records",
    "vlr_recovery_follow_ups",
    "vlr_recovery_items",
    "vlr_approval_records",
    "vlr_workflow_step_history",
    "vlr_notifications",
    "vlr_audit_events",
]


async def cleanup():
    async with async_session_factory() as session:
        for tbl in CHILD_TABLES:
            try:
                r = await session.execute(text(f"DELETE FROM {tbl}"))
                print(f"Deleted {r.rowcount} rows from {tbl}")
            except Exception as e:
                print(f"Skipped {tbl}: {e}")
                await session.rollback()

        r = await session.execute(text("DELETE FROM vlr_reconciliation_cases"))
        print(f"Deleted {r.rowcount} cases")

        r = await session.execute(text("DELETE FROM vlr_reconciliation_requests"))
        print(f"Deleted {r.rowcount} requests")

        await session.commit()
        print("Done!")


if __name__ == "__main__":
    asyncio.run(cleanup())
