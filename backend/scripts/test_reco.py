"""Test the reconciliation engine directly on the current case."""
import asyncio
from decimal import Decimal
from uuid import UUID
from sqlalchemy import text
from src.infrastructure.database.session import async_session_factory
from src.infrastructure.database.repositories.vlr.ledger_entry_repository_impl import LedgerEntryRepositoryImpl
from src.infrastructure.database.repositories.vlr.match_result_repository_impl import MatchResultRepositoryImpl
from src.infrastructure.database.repositories.vlr.case_repository_impl import CaseRepositoryImpl
from src.infrastructure.database.repositories.vlr.exception_repository_impl import ExceptionRepositoryImpl
from src.domain.services.vlr.reconciliation_engine_service import ReconciliationEngineService


async def run():
    async with async_session_factory() as session:
        # Get latest case
        r = await session.execute(text("SELECT id FROM vlr_reconciliation_cases ORDER BY created_date DESC LIMIT 1"))
        case_id = r.scalar_one()
        print(f"Testing case: {case_id}")

        engine = ReconciliationEngineService(
            ledger_entry_repository=LedgerEntryRepositoryImpl(session),
            match_result_repository=MatchResultRepositoryImpl(session),
            case_repository=CaseRepositoryImpl(session),
            exception_repository=ExceptionRepositoryImpl(session),
        )
        result = await engine.execute(
            case_id=UUID(str(case_id)),
            tolerance=Decimal("0.01"),
            fuzzy_threshold=0.8,
            date_tolerance_days=15,
            tds_percentage=Decimal("10"),
            gst_percentage=Decimal("18"),
        )
        await session.commit()

        s = result.statistics
        print(f"\nResults:")
        print(f"  Company entries: {s.total_company_entries}")
        print(f"  Vendor entries: {s.total_vendor_entries}")
        print(f"  Matched company: {s.total_matched_company}")
        print(f"  Matched vendor: {s.total_matched_vendor}")
        print(f"  Match pairs: {len(result.match_pairs)}")
        print(f"  Match groups: {len(result.match_groups)}")
        print(f"  Unmatched company: {len(result.unmatched_company_ids)}")
        print(f"  Unmatched vendor: {len(result.unmatched_vendor_ids)}")
        print(f"\n  Pass breakdown:")
        for ps in s.pass_statistics:
            print(f"    Pass {ps.pass_number}: {ps.match_count} matches, {ps.percentage}%")


if __name__ == "__main__":
    asyncio.run(run())
