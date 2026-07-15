"""
Quick fix: Set is_validate_ad=False for admin user so login uses local password
instead of the Darwin AD service (which is unreachable locally).
"""
import asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

DATABASE_URL = "postgresql+asyncpg://postgres:root@localhost:5432/vlr_db"


async def fix_admin():
    engine = create_async_engine(DATABASE_URL)
    async with engine.begin() as conn:
        # Check current state
        result = await conn.execute(
            text("SELECT id, username, is_validate_ad, is_active, is_blocked FROM users WHERE username = 'admin'")
        )
        row = result.fetchone()
        if row:
            print(f"Found user: {row.username}, is_validate_ad={row.is_validate_ad}, is_active={row.is_active}, is_blocked={row.is_blocked}")
            if row.is_validate_ad:
                await conn.execute(
                    text("UPDATE users SET is_validate_ad = false WHERE username = 'admin'")
                )
                print("✓ Set is_validate_ad=False for admin. Login will now use local password.")
            else:
                print("is_validate_ad is already False. Issue might be elsewhere.")
        else:
            print("No 'admin' user found in the database!")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(fix_admin())
