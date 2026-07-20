"""Send the sign-off request email for the latest case (test)."""
import asyncio
from uuid import UUID
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from src.infrastructure.external.email.vlr_mailer import send_signoff_request_email

DATABASE_URL = "postgresql+asyncpg://postgres:root@localhost:5432/vlr_db"

async def run():
    engine = create_async_engine(DATABASE_URL)
    Session = sessionmaker(engine, class_=AsyncSession)
    async with Session() as session:
        r = await session.execute(text("SELECT id FROM vlr_reconciliation_cases ORDER BY created_date DESC LIMIT 1"))
        cid = r.scalar_one()
        success, msg = await send_signoff_request_email(session, UUID(str(cid)))
        print(f"case={cid}")
        print(f"success={success}, message={msg}")
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(run())
