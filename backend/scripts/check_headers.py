"""Check if raw file headers were stored for the latest case."""
import asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

DATABASE_URL = "postgresql+asyncpg://postgres:root@localhost:5432/vlr_db"

async def check():
    engine = create_async_engine(DATABASE_URL)
    async with engine.begin() as conn:
        cr = await conn.execute(text("SELECT id FROM vlr_reconciliation_cases ORDER BY created_date DESC LIMIT 1"))
        cid = cr.scalar_one()
        r = await conn.execute(text(
            "SELECT key, value FROM vlr_settings WHERE key LIKE :k"
        ), {"k": f"file_headers.{cid}.%"})
        rows = r.fetchall()
        if rows:
            for row in rows:
                print(f"{row.key}:\n  {row.value}\n")
        else:
            print(f"No stored headers for case {cid}")
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(check())
