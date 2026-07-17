"""Update the case status CHECK constraint to allow new statuses."""
import asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

DATABASE_URL = "postgresql+asyncpg://postgres:root@localhost:5432/vlr_db"

async def update():
    engine = create_async_engine(DATABASE_URL)
    async with engine.begin() as conn:
        # Drop old constraint
        await conn.execute(text(
            "ALTER TABLE vlr_reconciliation_cases DROP CONSTRAINT IF EXISTS ck_vlr_case_valid_status"
        ))
        # Add new constraint with all valid statuses
        await conn.execute(text("""
            ALTER TABLE vlr_reconciliation_cases ADD CONSTRAINT ck_vlr_case_valid_status
            CHECK (status IN (
                'created', 'ledger_confirmed', 'invited', 'data_received',
                'matching', 'matched', 'mapping_pending', 'statement_mapped',
                'in_progress', 'auto_completed',
                'review', 'pending_approval', 'approved',
                'signed_off', 'closed',
                'review_pending', 'reviewed', 'signoff_requested', 'signoff_completed', 'reco_rejected'
            ))
        """))
        print("Status constraint updated successfully.")

        # Also update the current case from 'matched' to 'mapping_pending' since it has unmatched entries
        await conn.execute(text(
            "UPDATE vlr_reconciliation_cases SET status = 'mapping_pending' WHERE status = 'matched'"
        ))
        print("Existing 'matched' cases updated to 'mapping_pending'.")

    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(update())
