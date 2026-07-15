"""Check vendor contacts for ABHCS4531M."""
import asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

DATABASE_URL = "postgresql+asyncpg://postgres:root@localhost:5432/vlr_db"


async def check():
    engine = create_async_engine(DATABASE_URL)
    async with engine.begin() as conn:
        result = await conn.execute(
            text("""
                SELECT vc.name, vc.email, vc.is_primary, v.vendor_code, v.name as vendor_name
                FROM vlr_vendor_contacts vc
                JOIN vlr_vendors v ON vc.vendor_id = v.id
                WHERE v.vendor_code = 'ABHCS4531M'
            """)
        )
        rows = result.fetchall()
        if rows:
            print(f"Contacts for ABHCS4531M:")
            for row in rows:
                print(f"  name={row.name}, email={row.email}, is_primary={row.is_primary}")
        else:
            print("No contacts found for vendor ABHCS4531M!")

        # Also check the latest case portal token
        result2 = await conn.execute(
            text("""
                SELECT c.id, c.portal_token, c.token_expiry, c.status
                FROM vlr_reconciliation_cases c
                JOIN vlr_vendors v ON c.vendor_id = v.id
                WHERE v.vendor_code = 'ABHCS4531M'
                ORDER BY c.created_date DESC LIMIT 1
            """)
        )
        row2 = result2.fetchone()
        if row2:
            print(f"\nLatest case: id={row2.id}, status={row2.status}")
            print(f"  portal_token={row2.portal_token}")
            print(f"  token_expiry={row2.token_expiry}")
            print(f"  Portal URL: http://localhost:3000/portal/access/{row2.portal_token}")
        else:
            print("\nNo cases found")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(check())
