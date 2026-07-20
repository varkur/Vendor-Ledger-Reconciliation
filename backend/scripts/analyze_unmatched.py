"""Analyze unmatched entries to understand why they didn't match."""
import asyncio
from decimal import Decimal
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

DATABASE_URL = "postgresql+asyncpg://postgres:root@localhost:5432/vlr_db"

async def check():
    engine = create_async_engine(DATABASE_URL)
    async with engine.begin() as conn:
        cr = await conn.execute(text("SELECT id FROM vlr_reconciliation_cases ORDER BY created_date DESC LIMIT 1"))
        cid = cr.scalar_one()

        # Unmatched company entries (match_id is null)
        print("=== UNMATCHED COMPANY ===")
        r = await conn.execute(text("""
            SELECT document_number, document_type, document_category, posting_date, amount, reference_number
            FROM vlr_ledger_entries WHERE case_id = :c AND side = 'company' AND match_id IS NULL
            ORDER BY amount
        """), {"c": cid})
        company_unmatched = r.fetchall()
        for row in company_unmatched:
            print(f"  {row.document_type}/{row.document_category} | {row.posting_date} | amt={row.amount} | ref={row.reference_number}")

        print(f"\n  Total unmatched company: {len(company_unmatched)}")

        print("\n=== UNMATCHED VENDOR ===")
        r2 = await conn.execute(text("""
            SELECT document_number, document_type, document_category, posting_date, amount, reference_number
            FROM vlr_ledger_entries WHERE case_id = :c AND side = 'vendor' AND match_id IS NULL
            ORDER BY amount
        """), {"c": cid})
        vendor_unmatched = r2.fetchall()
        for row in vendor_unmatched:
            print(f"  {row.document_type}/{row.document_category} | {row.posting_date} | amt={row.amount} | ref={row.reference_number}")
        print(f"\n  Total unmatched vendor: {len(vendor_unmatched)}")

        # Check for amount overlaps - unmatched company amounts that appear in unmatched vendor (sign-flipped)
        print("\n=== POTENTIAL MISSED MATCHES (same abs amount, both unmatched) ===")
        comp_amts = {abs(Decimal(str(r.amount))): r for r in company_unmatched}
        for vr in vendor_unmatched:
            va = abs(Decimal(str(vr.amount)))
            if va in comp_amts:
                cr2 = comp_amts[va]
                print(f"  MATCH? company({cr2.posting_date}, {cr2.amount}) <-> vendor({vr.posting_date}, {vr.amount})")

    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(check())
