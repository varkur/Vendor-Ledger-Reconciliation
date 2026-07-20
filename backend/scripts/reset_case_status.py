"""Reset the latest case back to statement_mapped for testing."""
import asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

DATABASE_URL = "postgresql+asyncpg://postgres:root@localhost:5432/vlr_db"

async def run():
    engine = create_async_engine(DATABASE_URL)
    async with engine.begin() as conn:
        r = await conn.execute(text("SELECT id, status FROM vlr_reconciliation_cases ORDER BY created_date DESC LIMIT 1"))
        row = r.fetchone()
        await conn.execute(
            text("UPDATE vlr_reconciliation_cases SET status='statement_mapped' WHERE id=:i"),
            {"i": row.id}
        )
        print(f"Case {row.id}: {row.status} -> statement_mapped")
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(run())
