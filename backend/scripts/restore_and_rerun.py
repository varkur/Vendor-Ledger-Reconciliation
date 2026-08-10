"""
Restore vendor-side document_category using the saved column mapping
(RV->Invoice, DZ->Payment, AB->Knocking Off) via the same code path as
apply_column_mapping, then re-run reconciliation to verify the category
no longer reverts to "Unknown".
"""
import asyncio
from decimal import Decimal
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

DATABASE_URL = "postgresql+asyncpg://postgres:root@localhost:5432/vlr_db"

DOC_TYPE_MAP = {"RV": "Invoice", "DZ": "Payment", "AB": "Knocking Off"}


async def main():
    engine = create_async_engine(DATABASE_URL)
    async with engine.begin() as conn:
        result = await conn.execute(text("""
            SELECT c.id FROM vlr_reconciliation_cases c
            JOIN vlr_vendors v ON v.id = c.vendor_id
            WHERE v.name ILIKE :name ORDER BY c.created_date DESC LIMIT 1
        """), {"name": "%INOX AIR%"})
        case_id: UUID = result.fetchone().id
        print(f"Case: {case_id}")

        for dt, cat in DOC_TYPE_MAP.items():
            await conn.execute(text("""
                UPDATE vlr_ledger_entries SET document_category = :cat
                WHERE case_id = :cid AND side = 'vendor' AND document_type = :dt
            """), {"cat": cat, "cid": case_id, "dt": dt})
        print("Restored vendor document_category from saved mapping.")

    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with Session() as session:
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

        engine_svc = ReconciliationEngineService(
            ledger_entry_repository=LedgerEntryRepositoryImpl(session),
            match_result_repository=MatchResultRepositoryImpl(session),
            case_repository=CaseRepositoryImpl(session),
            exception_repository=ExceptionRepositoryImpl(session),
        )
        result = await engine_svc.execute(
            case_id=case_id, tolerance=Decimal("0.01"), fuzzy_threshold=0.8,
            date_tolerance_days=15, tds_percentage=Decimal("0"), gst_percentage=Decimal("0"),
        )
        await session.commit()
        print(f"match_pairs={len(result.match_pairs)} unmatched_company={len(result.unmatched_company_ids)} "
              f"unmatched_vendor={len(result.unmatched_vendor_ids)}")

    async with engine.begin() as conn:
        for side in ["company", "vendor"]:
            r = await conn.execute(text("""
                SELECT document_category, COUNT(*) FROM vlr_ledger_entries
                WHERE case_id = :cid AND side = :side GROUP BY document_category ORDER BY 2 DESC
            """), {"cid": case_id, "side": side})
            print(f"\n-- {side} categories AFTER re-run --")
            for row in r.fetchall():
                print(f"   {row[0]!r:20} count={row[1]}")

        r2 = await conn.execute(text("SELECT company_entry_ids, vendor_entry_ids FROM vlr_match_results WHERE case_id = :cid"), {"cid": case_id})
        matches = r2.fetchall()
        r3 = await conn.execute(text("SELECT id, document_category FROM vlr_ledger_entries WHERE case_id = :cid"), {"cid": case_id})
        emap = {str(row.id): row.document_category for row in r3.fetchall()}
        cross = sum(
            1 for m in matches for cid_ in (m.company_entry_ids or []) for vid_ in (m.vendor_entry_ids or [])
            if emap.get(str(cid_)) and emap.get(str(vid_)) and emap.get(str(cid_)) != emap.get(str(vid_))
        )
        print(f"\nCross-category matches: {cross} / {len(matches)}")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
