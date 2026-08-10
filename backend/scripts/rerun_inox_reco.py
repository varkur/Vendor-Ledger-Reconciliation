"""
Re-run the reconciliation engine directly (bypassing the API/status guard) for
the INOX AIR PRODUCTS case, using the exact same repository wiring as
case_controller.start_reconciliation, then report cross-category matches.

This lets us verify the category-gating fix against real data without going
through the UI, and confirms the previously-poisoned document_category values
(literal "RV"/"DZ") get corrected by _compute_summary_fields on this run.
"""
import asyncio
from decimal import Decimal
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

DATABASE_URL = "postgresql+asyncpg://postgres:root@localhost:5432/vlr_db"


async def main():
    engine = create_async_engine(DATABASE_URL)
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with Session() as session:
        result = await session.execute(text("""
            SELECT c.id
            FROM vlr_reconciliation_cases c
            JOIN vlr_vendors v ON v.id = c.vendor_id
            WHERE v.name ILIKE :name
            ORDER BY c.created_date DESC
            LIMIT 1
        """), {"name": "%INOX AIR%"})
        row = result.fetchone()
        if not row:
            print("Case not found")
            return
        case_id: UUID = row.id
        print(f"Case: {case_id}")

        from src.infrastructure.database.repositories.vlr.ledger_entry_repository_impl import (
            LedgerEntryRepositoryImpl,
        )
        from src.infrastructure.database.repositories.vlr.match_result_repository_impl import (
            MatchResultRepositoryImpl,
        )
        from src.infrastructure.database.repositories.vlr.exception_repository_impl import (
            ExceptionRepositoryImpl,
        )
        from src.infrastructure.database.repositories.vlr.case_repository_impl import (
            CaseRepositoryImpl,
        )
        from src.domain.services.vlr.reconciliation_engine_service import (
            ReconciliationEngineService,
        )

        ledger_repo = LedgerEntryRepositoryImpl(session)
        match_repo = MatchResultRepositoryImpl(session)
        exception_repo = ExceptionRepositoryImpl(session)
        case_repo = CaseRepositoryImpl(session)

        engine_svc = ReconciliationEngineService(
            ledger_entry_repository=ledger_repo,
            match_result_repository=match_repo,
            case_repository=case_repo,
            exception_repository=exception_repo,
        )

        result = await engine_svc.execute(
            case_id=case_id,
            tolerance=Decimal("0.01"),
            fuzzy_threshold=0.8,
            date_tolerance_days=15,
            tds_percentage=Decimal("0"),
            gst_percentage=Decimal("0"),
        )
        await session.commit()

        print(f"match_pairs={len(result.match_pairs)} match_groups={len(result.match_groups)}")
        print(f"unmatched_company={len(result.unmatched_company_ids)} unmatched_vendor={len(result.unmatched_vendor_ids)}")

    # Re-check category distribution + cross-category matches after the fix
    async with engine.begin() as conn:
        for side in ["company", "vendor"]:
            r = await conn.execute(text("""
                SELECT document_category, document_type, COUNT(*)
                FROM vlr_ledger_entries WHERE case_id = :cid AND side = :side
                GROUP BY document_category, document_type ORDER BY 3 DESC
            """), {"cid": case_id, "side": side})
            print(f"\n-- {side} categories after re-run --")
            for row in r.fetchall():
                print(f"   category={row[0]!r:20} doc_type={row[1]!r:10} count={row[2]}")

        r2 = await conn.execute(text("""
            SELECT m.pass_number, m.company_entry_ids, m.vendor_entry_ids, m.difference_amount
            FROM vlr_match_results m WHERE m.case_id = :cid
        """), {"cid": case_id})
        matches = r2.fetchall()

        r3 = await conn.execute(text("""
            SELECT id, document_category, amount FROM vlr_ledger_entries WHERE case_id = :cid
        """), {"cid": case_id})
        entry_map = {str(row.id): row for row in r3.fetchall()}

        cross = 0
        for m in matches:
            for cid_ in (m.company_entry_ids or []):
                for vid_ in (m.vendor_entry_ids or []):
                    c_e = entry_map.get(str(cid_))
                    v_e = entry_map.get(str(vid_))
                    if c_e and v_e and c_e.document_category and v_e.document_category:
                        if c_e.document_category != v_e.document_category:
                            cross += 1
        print(f"\nCross-category matches after fix: {cross} (out of {len(matches)} match records)")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
