"""Quick script to check if contacts were saved during import."""
import asyncio
import sys
sys.path.insert(0, '.')

async def main():
    from sqlalchemy import text
    from src.infrastructure.database.session import async_session_factory
    
    async with async_session_factory() as session:
        # Check vendor count
        result = await session.execute(text("SELECT COUNT(*) FROM vlr_vendors"))
        vendor_count = result.scalar()
        print(f"Total vendors: {vendor_count}")
        
        # Check contact count
        result = await session.execute(text("SELECT COUNT(*) FROM vlr_vendor_contacts"))
        contact_count = result.scalar()
        print(f"Total contacts: {contact_count}")
        
        # Show sample contacts with vendor info
        result = await session.execute(text("""
            SELECT v.vendor_code, v.name as vendor_name, c.name as contact_name, c.email, c.phone, c.source
            FROM vlr_vendor_contacts c
            JOIN vlr_vendors v ON v.id = c.vendor_id
            LIMIT 10
        """))
        rows = result.fetchall()
        if rows:
            print("\nSample contacts:")
            for row in rows:
                print(f"  Vendor: {row[0]} ({row[1]}) -> Contact: {row[2]}, Email: {row[3]}, Phone: {row[4]}, Source: {row[5]}")
        else:
            print("\nNo contacts found in database!")

asyncio.run(main())
