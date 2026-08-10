"""
Diagnose why invoices still mismatch for INOX AIR PRODUCTS PRIVATE LIMITED
after the category-gating fix. Prints, for the case's ledger entries:
  - side, amount, category, document_type, pass_number, match_id
so we can see whether document_category is actually being populated, and
whether the entries flagged in the export are matched under a pass number
that shouldn't have applied.
"""
import asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

DATABASE_URL = "postgresql+asyncpg://postgres:root@localhost:5432/vlr_db"


async def main():
    engine = create_async_engine(DATABASE_URL)
    async with engine.begin() as conn:
        result = await conn.execute(text("""
            SELECT c.id, c.status, c.request_id, v.name
            FROM vlr_reconciliation_cases c
            JOIN vlr_vendors v ON v.id = c.vendor_id
            WHERE v.name ILIKE :name
            ORDER BY c.created_date DESC
            LIMIT 5
        """), {"name": "%INOX AIR%"})
        cases = result.fetchall()
        if not cases:
            print("No case found for INOX AIR PRODUCTS")
            return

        for case in cases:
            print(f"\n=== Case {case.id} (status={case.status}, request={case.request_id}) ===")

            # Category / document_type distribution per side
            for side in ["company", "vendor"]:
                r = await conn.execute(text("""
                    SELECT document_category, document_type, COUNT(*), COALESCE(SUM(amount),0)
                    FROM vlr_ledger_entries
                    WHERE case_id = :cid AND side = :side
                    GROUP BY document_category, document_type
                    ORDER BY 3 DESC
                """), {"cid": case.id, "side": side})
                rows = r.fetchall()
                print(f"\n-- {side} side: document_category / document_type distribution --")
                for row in rows:
                    print(f"   category={row[0]!r:25} doc_type={row[1]!r:10} count={row[2]:5} sum={row[3]}")

            # Matches by pass_number, with category on each side
            r2 = await conn.execute(text("""
                SELECT m.pass_number, m.match_type, m.confidence_score,
                       m.company_entry_ids, m.vendor_entry_ids,
                       m.matched_amount, m.difference_amount
                FROM vlr_match_results m
                WHERE m.case_id = :cid
                ORDER BY m.pass_number
            """), {"cid": case.id})
            matches = r2.fetchall()
            print(f"\n-- {len(matches)} match records --")

            # Build entry lookup for category/doctype
            r3 = await conn.execute(text("""
                SELECT id, side, amount, document_category, document_type, reference_number, document_number
                FROM vlr_ledger_entries WHERE case_id = :cid
            """), {"cid": case.id})
            entry_map = {str(row.id): row for row in r3.fetchall()}

            mismatched_category_count = 0
            for m in matches:
                comp_ids = m.company_entry_ids or []
                vend_ids = m.vendor_entry_ids or []
                for cid_ in comp_ids:
                    for vid_ in vend_ids:
                        c_e = entry_map.get(str(cid_))
                        v_e = entry_map.get(str(vid_))
                        if c_e is None or v_e is None:
                            continue
                        c_cat = c_e.document_category or ""
                        v_cat = v_e.document_category or ""
                        if c_cat and v_cat and c_cat != v_cat:
                            mismatched_category_count += 1
                            print(f"   [pass={m.pass_number}] company cat={c_cat!r} (amt={c_e.amount}) "
                                  f"<-> vendor cat={v_cat!r} (amt={v_e.amount}) "
                                  f"diff={m.difference_amount}")

            print(f"\n-- Cross-category matches found: {mismatched_category_count} --")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
