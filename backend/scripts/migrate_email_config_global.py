"""Migrate entity-scoped email settings to global prefix."""
import asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

DATABASE_URL = "postgresql+asyncpg://postgres:root@localhost:5432/vlr_db"


async def migrate():
    engine = create_async_engine(DATABASE_URL)
    async with engine.begin() as conn:
        # Find any email settings that are NOT under the global prefix
        result = await conn.execute(
            text("SELECT id, key, value FROM vlr_settings WHERE key LIKE 'email.%' AND key NOT LIKE 'email.__global__.%'")
        )
        rows = result.fetchall()

        if not rows:
            print("No entity-scoped email settings to migrate.")
            return

        print(f"Found {len(rows)} entity-scoped email settings to migrate:")
        for row in rows:
            # Extract the field name (e.g., "email.5000.smtp_host" -> "smtp_host")
            parts = row.key.split(".")
            field = parts[-1] if len(parts) >= 3 else parts[-1]
            new_key = f"email.__global__.{field}"

            # Check if global version already exists
            existing = await conn.execute(
                text("SELECT id FROM vlr_settings WHERE key = :key AND company_code = '__global__'"),
                {"key": new_key}
            )
            if existing.fetchone():
                print(f"  SKIP {row.key} -> {new_key} (already exists)")
            else:
                # Copy to global prefix
                await conn.execute(
                    text("UPDATE vlr_settings SET key = :new_key WHERE id = :id"),
                    {"new_key": new_key, "id": row.id}
                )
                print(f"  MOVED {row.key} -> {new_key}")

    await engine.dispose()
    print("\nDone. Email config is now global across all entities.")


if __name__ == "__main__":
    asyncio.run(migrate())
