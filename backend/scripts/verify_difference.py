"""Verify the reconciliation difference ties out."""
import asyncio
from decimal import Decimal
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

DATABASE_URL = "postgresql+asyncpg://postgres:root@localhost:5432/vlr_db"

async def check():
    engine = create_async_engine(DATABASE_URL)
    async with engine.begin() as conn:
        cr = await conn.execute(text("SELECT id, company_opening_balance, company_closing_balance, vendor_opening_balance, vendor_closing_balance, net_difference FROM vlr_reconciliation_cases ORDER BY created_date DESC LIMIT 1"))
        c = cr.fetchone()
        cid = c.id
        print(f"Case {cid}")
        print(f"  Company: opening={c.company_opening_balance}, closing={c.company_closing_balance}")
        print(f"  Vendor:  opening={c.vendor_opening_balance}, closing={c.vendor_closing_balance}")
        print(f"  Stored net_difference={c.net_difference}\n")

        # Sum of ALL entries per side (excluding balance rows)
        for side in ['company', 'vendor']:
            r = await conn.execute(text("""
                SELECT COALESCE(SUM(amount),0) FROM vlr_ledger_entries
                WHERE case_id=:c AND side=:s
                  AND document_category NOT IN ('Opening Balance','Closing Balance')
            """), {"c": cid, "s": side})
            print(f"  {side} txn sum (excl balances): {r.scalar()}")

        # Sum of UNMATCHED entries per side (excl balances)
        print()
        for side in ['company', 'vendor']:
            r = await conn.execute(text("""
                SELECT COALESCE(SUM(amount),0) FROM vlr_ledger_entries
                WHERE case_id=:c AND side=:s AND match_id IS NULL
                  AND document_category NOT IN ('Opening Balance','Closing Balance')
            """), {"c": cid, "s": side})
            print(f"  {side} UNMATCHED sum (excl balances): {r.scalar()}")

    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(check())
