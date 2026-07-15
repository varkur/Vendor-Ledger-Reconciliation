"""Reset: Delete all requests/cases/ledger entries for vendor ABHCS4531M so user can test fresh."""
import asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

DATABASE_URL = "postgresql+asyncpg://postgres:root@localhost:5432/vlr_db"


async def reset():
    engine = create_async_engine(DATABASE_URL)
    async with engine.begin() as conn:
        vid_result = await conn.execute(
            text("SELECT id FROM vlr_vendors WHERE vendor_code = 'ABHCS4531M' LIMIT 1")
        )
        vid_row = vid_result.fetchone()
        if not vid_row:
            print("Vendor not found")
            return
        vendor_id = str(vid_row.id)

        # Find all cases for this vendor
        cases = await conn.execute(
            text("SELECT id, request_id FROM vlr_reconciliation_cases WHERE vendor_id = :vid"),
            {"vid": vendor_id}
        )
        case_rows = cases.fetchall()
        request_ids = set()

        for case_row in case_rows:
            cid = case_row.id
            request_ids.add(case_row.request_id)
            # Delete match results
            await conn.execute(text("DELETE FROM vlr_match_results WHERE case_id = :cid"), {"cid": cid})
            # Delete exceptions
            await conn.execute(text("DELETE FROM vlr_reco_exceptions WHERE case_id = :cid"), {"cid": cid})
            # Delete ledger entries
            await conn.execute(text("DELETE FROM vlr_ledger_entries WHERE case_id = :cid"), {"cid": cid})
            # Delete notifications
            await conn.execute(text("DELETE FROM vlr_notifications WHERE case_id = :cid"), {"cid": cid})

        # Delete all cases for this vendor
        await conn.execute(
            text("DELETE FROM vlr_reconciliation_cases WHERE vendor_id = :vid"),
            {"vid": vendor_id}
        )

        # Delete requests
        for rid in request_ids:
            await conn.execute(text("DELETE FROM vlr_reconciliation_requests WHERE id = :rid"), {"rid": rid})

        print(f"Cleaned up {len(case_rows)} case(s) and {len(request_ids)} request(s) for ABHCS4531M.")
        print("Ready for fresh test.")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(reset())
