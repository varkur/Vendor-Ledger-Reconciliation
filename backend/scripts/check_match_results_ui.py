"""
Verify the numbers shown on the Match Results card (Matched Company/Vendor,
Total Company/Vendor, Unmatched) against the underlying data, and check for
any remaining cross-category matches after the latest reconciliation run.
"""
import asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

DATABASE_URL = "postgresql+asyncpg://postgres:root@localhost:5432/vlr_db"


async def main():
    engine = create_async_engine(DATABASE_URL)
    async with engine.begin() as conn:
        result = await conn.execute(text("""
            SELECT c.id, c.status, c.match_statistics
            FROM vlr_reconciliation_cases c
            JOIN vlr_vendors v ON v.id = c.vendor_id
            WHERE v.name ILIKE :name
            ORDER BY c.created_date DESC
            LIMIT 1
        """), {"name": "%INOX AIR%"})
        case = result.fetchone()
        if not case:
            print("Case not found")
            return
        print(f"Case: {case.id}  status={case.status}")
        print(f"Stored match_statistics: {case.match_statistics}")

        # Recompute directly from ledger entries + match_id
        for side in ["company", "vendor"]:
            r = await conn.execute(text("""
                SELECT COUNT(*) AS total,
                       COUNT(*) FILTER (WHERE match_id IS NOT NULL) AS matched
                FROM vlr_ledger_entries WHERE case_id = :cid AND side = :side
            """), {"cid": case.id, "side": side})
            row = r.fetchone()
            print(f"  {side}: total={row.total} matched(has match_id)={row.matched} "
                  f"unmatched={row.total - row.matched}")

        # Category distribution
        for side in ["company", "vendor"]:
            r = await conn.execute(text("""
                SELECT document_category, COUNT(*)
                FROM vlr_ledger_entries WHERE case_id = :cid AND side = :side
                GROUP BY document_category ORDER BY 2 DESC
            """), {"cid": case.id, "side": side})
            print(f"\n-- {side} category distribution --")
            for row in r.fetchall():
                print(f"   {row[0]!r:20} count={row[1]}")

        # Cross-category match check
        r2 = await conn.execute(text("""
            SELECT m.pass_number, m.company_entry_ids, m.vendor_entry_ids
            FROM vlr_match_results m WHERE m.case_id = :cid
        """), {"cid": case.id})
        matches = r2.fetchall()
        r3 = await conn.execute(text("""
            SELECT id, document_category, amount, side FROM vlr_ledger_entries WHERE case_id = :cid
        """), {"cid": case.id})
        entry_map = {str(row.id): row for row in r3.fetchall()}

        cross = []
        pass_counts = {}
        for m in matches:
            pass_counts[m.pass_number] = pass_counts.get(m.pass_number, 0) + 1
            for cid_ in (m.company_entry_ids or []):
                for vid_ in (m.vendor_entry_ids or []):
                    c_e = entry_map.get(str(cid_))
                    v_e = entry_map.get(str(vid_))
                    if c_e and v_e and c_e.document_category and v_e.document_category:
                        if c_e.document_category != v_e.document_category:
                            cross.append((m.pass_number, c_e.document_category, c_e.amount,
                                          v_e.document_category, v_e.amount))

        print(f"\nTotal match records: {len(matches)}")
        print(f"By pass number: {pass_counts}")
        print(f"Cross-category matches: {len(cross)}")
        for row in cross[:20]:
            print(f"   pass={row[0]} company={row[1]}({row[2]}) <-> vendor={row[3]}({row[4]})")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
