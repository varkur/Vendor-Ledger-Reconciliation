"""Delete all reconciliation requests and cases for a clean slate."""
import asyncio
from sqlalchemy import text
from src.infrastructure.database.session import async_session_factory


async def cleanup():
    async with async_session_factory() as session:
        # Delete cases first (FK constraint)
        r = await session.execute(text("DELETE FROM vlr_reconciliation_cases"))
        print(f"Deleted {r.rowcount} cases")
        
        # Delete requests
        r = await session.execute(text("DELETE FROM vlr_reconciliation_requests"))
        print(f"Deleted {r.rowcount} requests")
        
        await session.commit()
        print("Done!")


if __name__ == "__main__":
    asyncio.run(cleanup())
