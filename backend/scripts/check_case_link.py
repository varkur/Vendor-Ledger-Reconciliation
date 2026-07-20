"""Check the case's request_id, status, is_deleted."""
import asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

DATABASE_URL = "postgresql+asyncpg://postgres:root@localhost:5432/vlr_db"

async def run():
    engine = create_async_engine(DATABASE_URL)
    async with engine.begin() as conn:
        r = await conn.execute(text(
            "SELECT id, request_id, status, is_deleted FROM vlr_reconciliation_cases ORDER BY created_date DESC LIMIT 1"
        ))
        row = r.fetchone()
        print(f"case_id={row.id}")
        print(f"request_id={row.request_id}")
        print(f"status={row.status}")
        print(f"is_deleted={row.is_deleted}")

        # Check the request company_code
        r2 = await conn.execute(text(
            "SELECT id, company_code FROM vlr_reconciliation_requests WHERE id = :rid"
        ), {"rid": row.request_id})
        req = r2.fetchone()
        print(f"request company_code={req.company_code if req else 'REQUEST NOT FOUND'}")
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(run())
