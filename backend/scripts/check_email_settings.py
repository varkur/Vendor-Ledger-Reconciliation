"""Check what email settings are stored in the database."""
import asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

DATABASE_URL = "postgresql+asyncpg://postgres:root@localhost:5432/vlr_db"


async def check():
    engine = create_async_engine(DATABASE_URL)
    async with engine.begin() as conn:
        # Check if table exists
        result = await conn.execute(
            text("SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename LIKE '%setting%'")
        )
        tables = result.fetchall()
        print("Tables matching 'setting':", [r[0] for r in tables])

        # Try vlr_settings table
        try:
            result = await conn.execute(
                text("SELECT company_code, key, value FROM vlr_settings WHERE key LIKE '%email%' OR key LIKE '%smtp%' ORDER BY key")
            )
            rows = result.fetchall()
            if rows:
                print(f"\nFound {len(rows)} email-related settings in vlr_settings:")
                for row in rows:
                    print(f"  company_code={row.company_code!r}, key={row.key!r}, value={row.value!r}")
            else:
                print("\nNo email-related settings found in vlr_settings!")
        except Exception as e:
            print(f"\nvlr_settings table error: {e}")

        # Check what entities exist
        print("\n--- Company Profiles ---")
        try:
            result2 = await conn.execute(
                text("SELECT id, company_code, name FROM company_profiles ORDER BY company_code")
            )
            rows2 = result2.fetchall()
            for row in rows2:
                print(f"  id={row.id}, company_code={row.company_code!r}, name={row.name!r}")
        except Exception as e:
            print(f"  Error: {e}")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(check())
