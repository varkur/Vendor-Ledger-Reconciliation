"""Delete existing reconciliation requests for vendor ABHCS4531M in the 2025-2026 period."""
import asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

DATABASE_URL = "postgresql+asyncpg://postgres:root@localhost:5432/vlr_db"


async def delete_requests():
    engine = create_async_engine(DATABASE_URL)
    async with engine.begin() as conn:
        # Find requests that have cases for this vendor in the overlapping period
        # First get the vendor's UUID from vlr_vendors table
        vendor_result = await conn.execute(
            text("SELECT id FROM vlr_vendors WHERE vendor_code = 'ABHCS4531M' LIMIT 1")
        )
        vendor_row = vendor_result.fetchone()
        if not vendor_row:
            print("Vendor ABHCS4531M not found. Trying direct request search...")
            # Fallback: just find all requests in the period
            result = await conn.execute(
                text("""
                    SELECT id, company_code, period_start, period_end, status, created_date
                    FROM vlr_reconciliation_requests
                    WHERE period_start <= '2026-03-31'
                      AND period_end >= '2025-04-01'
                """)
            )
        else:
            vendor_id = str(vendor_row.id)
            print(f"Found vendor ABHCS4531M with id={vendor_id}")
            result = await conn.execute(
                text("""
                    SELECT r.id, r.company_code, r.period_start, r.period_end, r.status, r.created_date
                    FROM vlr_reconciliation_requests r
                    JOIN vlr_reconciliation_cases c ON c.request_id = r.id
                    WHERE c.vendor_id = :vid
                      AND r.period_start <= '2026-03-31'
                      AND r.period_end >= '2025-04-01'
                """),
                {"vid": vendor_id}
            )
        rows = result.fetchall()

        if not rows:
            print("No overlapping requests found for vendor ABHCS4531M in 2025-2026 period.")
            return

        print(f"Found {len(rows)} overlapping request(s):")
        for row in rows:
            print(f"  id={row.id}, company_code={row.company_code}, period={row.period_start} to {row.period_end}, status={row.status}")

        # Delete related cases first (cascading)
        for row in rows:
            req_id = row.id
            # Delete ledger entries for cases of this request
            await conn.execute(
                text("DELETE FROM vlr_ledger_entries WHERE case_id IN (SELECT id FROM vlr_reconciliation_cases WHERE request_id = :rid)"),
                {"rid": req_id}
            )
            # Delete exceptions
            await conn.execute(
                text("DELETE FROM vlr_reco_exceptions WHERE case_id IN (SELECT id FROM vlr_reconciliation_cases WHERE request_id = :rid)"),
                {"rid": req_id}
            )
            # Delete notifications
            await conn.execute(
                text("DELETE FROM vlr_notifications WHERE case_id IN (SELECT id FROM vlr_reconciliation_cases WHERE request_id = :rid)"),
                {"rid": req_id}
            )
            # Delete cases
            await conn.execute(
                text("DELETE FROM vlr_reconciliation_cases WHERE request_id = :rid"),
                {"rid": req_id}
            )
            # Delete the request itself
            await conn.execute(
                text("DELETE FROM vlr_reconciliation_requests WHERE id = :rid"),
                {"rid": req_id}
            )
            print(f"  ✓ Deleted request {req_id} and all related data.")

    await engine.dispose()
    print("\nDone. You can now create a new request for this vendor.")


if __name__ == "__main__":
    asyncio.run(delete_requests())
