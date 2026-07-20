"""Show sample entries and distinct doc types for the latest case."""
import asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

DATABASE_URL = "postgresql+asyncpg://postgres:root@localhost:5432/vlr_db"

async def check():
    engine = create_async_engine(DATABASE_URL)
    async with engine.begin() as conn:
        # Get latest case
        cr = await conn.execute(text("SELECT id FROM vlr_reconciliation_cases ORDER BY created_date DESC LIMIT 1"))
        case_id = cr.scalar_one()
        print(f"Case: {case_id}\n")

        for side in ['company', 'vendor']:
            print(f"{'='*60}\n  {side.upper()}\n{'='*60}")
            # Distinct doc types
            dt = await conn.execute(text(
                "SELECT DISTINCT document_type FROM vlr_ledger_entries WHERE case_id = :c AND side = :s"
            ), {"c": case_id, "s": side})
            doctypes = [r[0] for r in dt.fetchall()]
            print(f"  Distinct document_types: {doctypes}")

            # Sample rows
            result = await conn.execute(text(f"""
                SELECT document_number, document_type, reference_number, posting_date, amount, description
                FROM vlr_ledger_entries WHERE case_id = :c AND side = :s LIMIT 3
            """), {"c": case_id, "s": side})
            for row in result.fetchall():
                print(f"    doc_num={row.document_number!r}, doc_type={row.document_type!r}, ref={row.reference_number!r}, amt={row.amount}")
            print()
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(check())
