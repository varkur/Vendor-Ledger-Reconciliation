"""Check what ledger entries exist for the current case."""
import asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

DATABASE_URL = "postgresql+asyncpg://postgres:root@localhost:5432/vlr_db"

async def check():
    engine = create_async_engine(DATABASE_URL)
    async with engine.begin() as conn:
        # Get the case
        result = await conn.execute(text("""
            SELECT c.id, c.status, c.match_statistics, c.upload_count
            FROM vlr_reconciliation_cases c
            ORDER BY c.created_date DESC LIMIT 1
        """))
        case = result.fetchone()
        if not case:
            print("No cases found")
            return
        print(f"Case: id={case.id}, status={case.status}, upload_count={case.upload_count}")
        print(f"Match stats: {case.match_statistics}")

        # Count entries per side
        for side in ['company', 'vendor']:
            r = await conn.execute(text(
                "SELECT COUNT(*), COALESCE(SUM(amount),0) FROM vlr_ledger_entries WHERE case_id = :cid AND side = :side"
            ), {"cid": case.id, "side": side})
            row = r.fetchone()
            print(f"  {side}: {row[0]} entries, total amount={row[1]}")

        # Count match results
        r2 = await conn.execute(text(
            "SELECT COUNT(*) FROM vlr_match_results WHERE case_id = :cid"
        ), {"cid": case.id})
        print(f"  Match results: {r2.scalar_one()}")

        # Count exceptions
        r3 = await conn.execute(text(
            "SELECT COUNT(*) FROM vlr_reco_exceptions WHERE case_id = :cid"
        ), {"cid": case.id})
        print(f"  Exceptions: {r3.scalar_one()}")

    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(check())
