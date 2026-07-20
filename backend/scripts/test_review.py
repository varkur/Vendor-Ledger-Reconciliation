"""Test sending a case to review directly."""
import asyncio
from uuid import UUID
from sqlalchemy import text
from src.infrastructure.database.session import async_session_factory
from src.infrastructure.database.repositories.vlr.case_repository_impl import CaseRepositoryImpl
from src.infrastructure.database.repositories.vlr.request_repository_impl import RequestRepositoryImpl
from src.infrastructure.database.repositories.vlr.vendor_repository_impl import VendorRepositoryImpl
from src.domain.services.vlr.request_manager_service import RequestManagerService, CaseStatus


async def run():
    async with async_session_factory() as session:
        r = await session.execute(text("SELECT id, status FROM vlr_reconciliation_cases ORDER BY created_date DESC LIMIT 1"))
        row = r.fetchone()
        cid, status = row.id, row.status
        print(f"Case {cid}, current status: {status}")

        case_repo = CaseRepositoryImpl(session)
        service = RequestManagerService(
            request_repository=RequestRepositoryImpl(session),
            case_repository=case_repo,
            vendor_repository=VendorRepositoryImpl(session),
        )
        try:
            await service.transition_case_status(UUID(str(cid)), "1000", CaseStatus.REVIEW_PENDING)
            await session.commit()
            print("SUCCESS: transitioned to review_pending")
        except Exception as e:
            print(f"FAILED transition: {type(e).__name__}: {e}")

if __name__ == "__main__":
    asyncio.run(run())
