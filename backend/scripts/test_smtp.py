"""Test SMTP connection with current email config and show what's stored."""
import asyncio
import smtplib
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

DATABASE_URL = "postgresql+asyncpg://postgres:root@localhost:5432/vlr_db"


async def check_and_test():
    engine = create_async_engine(DATABASE_URL)
    async with engine.begin() as conn:
        result = await conn.execute(
            text("SELECT key, value FROM vlr_settings WHERE key LIKE 'email.%' ORDER BY key")
        )
        rows = result.fetchall()
        config = {}
        for row in rows:
            field = row.key.split(".")[-1]
            config[field] = row.value
            display_val = "***" if "password" in field else row.value
            print(f"  {field}: {display_val}")

    await engine.dispose()

    # Test SMTP connection
    host = config.get("smtp_host", "")
    port = int(config.get("smtp_port", "587"))
    username = config.get("smtp_username", "")
    password = config.get("smtp_password", "")
    sender = config.get("sender_email", "")
    use_tls = config.get("use_tls", "true") == "true"

    print(f"\nTesting SMTP: {host}:{port} (TLS={use_tls})")
    print(f"  Username: '{username}'")
    print(f"  Sender: '{sender}'")

    try:
        server = smtplib.SMTP(host, port, timeout=15)
        server.ehlo()
        if use_tls:
            server.starttls()
            server.ehlo()
        if username and password:
            server.login(username, password)
            print("  LOGIN: SUCCESS")
        else:
            print("  LOGIN: SKIPPED (no username/password)")
        server.quit()
        print("\n  SMTP connection: OK")
    except Exception as e:
        print(f"\n  SMTP ERROR: {e}")


if __name__ == "__main__":
    asyncio.run(check_and_test())
