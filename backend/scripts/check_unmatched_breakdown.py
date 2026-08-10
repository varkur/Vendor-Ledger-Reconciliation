"""
Break down unmatched entries (match_id IS NULL) by document_category for
both sides, to reconcile the raw DB count (32 company / 119 vendor) against
the "genuine unmatched" UI count (30 company / 17 party) which excludes
Opening/Closing Balance and Knocking Off rows.
"""
import asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

DATABASE_URL = "postgresql+asyncpg://postgres:root@localhost:5432/vlr_db"


async def main():
    engine = create_async_engine(DATABASE_URL)
    async with engine.begin() as conn:
        result = await conn.execute(text("""
            SELECT c.id FROM vlr_reconciliation_cases c
            JOIN vlr_vendors v ON v.id = c.vendor_id
            WHERE v.name ILIKE :name ORDER BY c.created_date DESC LIMIT 1
        """), {"name": "%INOX AIR%"})
        case_id = result.fetchone().id
        print(f"Case: {case_id}\n")

        for side in ["company", "vendor"]:
            r = await conn.execute(text("""
                SELECT document_category, document_type, COUNT(*), COALESCE(SUM(amount),0)
                FROM vlr_ledger_entries
                WHERE case_id = :cid AND side = :side AND match_id IS NULL
                GROUP BY document_category, document_type
                ORDER BY 3 DESC
            """), {"cid": case_id, "side": side})
            rows = r.fetchall()
            total = sum(row[2] for row in rows)
            print(f"-- {side}: unmatched (match_id IS NULL) = {total} total --")
            for row in rows:
                print(f"   category={row[0]!r:20} doc_type={row[1]!r:8} count={row[2]:4} sum={row[3]}")

            genuine = sum(
                row[2] for row in rows
                if row[0] not in ("Opening Balance", "Closing Balance", "Knocking Off")
                and row[1] not in ("AB",)
            )
            print(f"   => 'genuine' unmatched (excl. balances/knock-off) = {genuine}\n")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
