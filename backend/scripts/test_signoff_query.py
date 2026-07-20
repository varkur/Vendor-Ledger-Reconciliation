"""Replicate the signoff stage query to confirm it returns the case."""
import asyncio
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from src.infrastructure.database.models.vlr.reconciliation_case_model import ReconciliationCaseModel
from src.infrastructure.database.models.vlr.vendor_model import VendorModel

DATABASE_URL = "postgresql+asyncpg://postgres:root@localhost:5432/vlr_db"

SIGNOFF = ["approved", "signed_off", "signoff_requested", "signoff_completed", "closed"]

async def run():
    engine = create_async_engine(DATABASE_URL)
    Session = sessionmaker(engine, class_=AsyncSession)
    async with Session() as session:
        request_id = "618c4006-73c9-4be7-9b94-a3131db01e35"
        q = (
            select(ReconciliationCaseModel, VendorModel)
            .join(VendorModel, ReconciliationCaseModel.vendor_id == VendorModel.id)
            .where(
                ReconciliationCaseModel.request_id == request_id,
                ReconciliationCaseModel.is_deleted == False,
                ReconciliationCaseModel.status.in_(SIGNOFF),
            )
        )
        res = await session.execute(q)
        rows = res.all()
        print(f"Signoff stage query returned {len(rows)} case(s)")
        for case, vendor in rows:
            print(f"  {vendor.vendor_code} - {case.status}")
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(run())
