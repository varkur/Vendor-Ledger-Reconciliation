"""
Check if admin's stored password hash matches 'Admin@123'.
If not, reset it.
"""
import asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
import bcrypt

DATABASE_URL = "postgresql+asyncpg://postgres:root@localhost:5432/vlr_db"


def verify_password(plain_password: str, hashed_password: str) -> bool:
    password_bytes = plain_password.encode("utf-8")
    hashed_bytes = hashed_password.encode("utf-8")
    return bcrypt.checkpw(password_bytes, hashed_bytes)


def hash_password(plain_password: str) -> str:
    password_bytes = plain_password.encode("utf-8")
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password_bytes, salt).decode("utf-8")


async def check_and_fix():
    engine = create_async_engine(DATABASE_URL)
    async with engine.begin() as conn:
        result = await conn.execute(
            text("SELECT username, password_hash FROM users WHERE username = 'admin'")
        )
        row = result.fetchone()
        if not row:
            print("No admin user found!")
            return

        print(f"User: {row.username}")
        print(f"Stored hash: {row.password_hash[:20]}...")

        # Test password
        password_to_test = "Admin@123"
        matches = verify_password(password_to_test, row.password_hash)
        print(f"Password '{password_to_test}' matches: {matches}")

        if not matches:
            new_hash = hash_password(password_to_test)
            await conn.execute(
                text("UPDATE users SET password_hash = :pw WHERE username = 'admin'"),
                {"pw": new_hash}
            )
            print(f"✓ Password reset to '{password_to_test}' for admin user.")
        else:
            print("Password is correct — issue is elsewhere.")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(check_and_fix())
