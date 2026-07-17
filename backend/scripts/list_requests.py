"""List all reconciliation requests in DB."""
import asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

DATABASE_URL = "postgresql+asyncpg://postgres:root@localhost:5432/vlr_db"

async def check():
    engine = create_async_engine(DATABASE_URL)
    async with engine.begin() as conn:
        result = await conn.execute(text("SELECT id, company_code, status, period_start, period_end, created_date FROM vlr_reconciliation_requests ORDER BY created_date DESC"))
        rows = result.fetchall()
        if rows:
            print(f"Found {len(rows)} request(s):")
            for r in rows:
                print(f"  id={r.id}, status={r.status}, period={r.period_start} to {r.period_end}")
        else:
            print("No requests found!")
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(check())
