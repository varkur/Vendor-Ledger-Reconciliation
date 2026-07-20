"""Check summary fields on the latest case."""
import asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

DATABASE_URL = "postgresql+asyncpg://postgres:root@localhost:5432/vlr_db"

async def check():
    engine = create_async_engine(DATABASE_URL)
    async with engine.begin() as conn:
        cr = await conn.execute(text("SELECT id FROM vlr_reconciliation_cases ORDER BY created_date DESC LIMIT 1"))
        cid = cr.scalar_one()

        r = await conn.execute(text("""
            SELECT company_opening_balance, company_closing_balance,
                   vendor_opening_balance, vendor_closing_balance, net_difference
            FROM vlr_reconciliation_cases WHERE id = :c
        """), {"c": cid})
        row = r.fetchone()
        print(f"Case {cid}")
        print(f"  Company opening: {row.company_opening_balance}, closing: {row.company_closing_balance}")
        print(f"  Vendor opening: {row.vendor_opening_balance}, closing: {row.vendor_closing_balance}")
        print(f"  Net difference: {row.net_difference}")

        # Document categories
        for side in ['company', 'vendor']:
            r2 = await conn.execute(text("""
                SELECT document_category, COUNT(*), COALESCE(SUM(amount),0)
                FROM vlr_ledger_entries WHERE case_id = :c AND side = :s
                GROUP BY document_category
            """), {"c": cid, "s": side})
            print(f"\n  {side} categories:")
            for row2 in r2.fetchall():
                print(f"    {row2[0]}: {row2[1]} entries, sum={row2[2]}")
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(check())
