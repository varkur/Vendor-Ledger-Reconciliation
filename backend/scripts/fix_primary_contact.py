"""Fix: Set vaishnavi.varkur@emcure.com as primary contact for ABHCS4531M."""
import asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

DATABASE_URL = "postgresql+asyncpg://postgres:root@localhost:5432/vlr_db"


async def fix():
    engine = create_async_engine(DATABASE_URL)
    async with engine.begin() as conn:
        # Get vendor id
        r = await conn.execute(text(
            "SELECT id FROM vlr_vendors WHERE vendor_code = 'ABHCS4531M' LIMIT 1"
        ))
        vid = r.scalar_one()
        # Clear all primary flags for this vendor
        await conn.execute(text(
            "UPDATE vlr_vendor_contacts SET is_primary = false WHERE vendor_id = :vid"
        ), {"vid": vid})
        # Set vaishnavi as primary
        result = await conn.execute(text(
            "UPDATE vlr_vendor_contacts SET is_primary = true WHERE vendor_id = :vid AND email = 'vaishnavi.varkur@emcure.com'"
        ), {"vid": vid})
        print(f"Done. vaishnavi.varkur@emcure.com is now the primary contact. (rows updated: {result.rowcount})")
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(fix())
