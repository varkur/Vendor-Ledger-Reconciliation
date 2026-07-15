"""Test sending an actual email to the primary contact."""
import asyncio
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

DATABASE_URL = "postgresql+asyncpg://postgres:root@localhost:5432/vlr_db"


async def get_config():
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
    await engine.dispose()
    return config


def send_test_email(config, to_email):
    host = config.get("smtp_host", "")
    port = int(config.get("smtp_port", "587"))
    username = config.get("smtp_username", "")
    password = config.get("smtp_password", "")
    sender = config.get("sender_email", "")
    use_tls = config.get("use_tls", "true") == "true"

    print(f"Sending to: {to_email}")
    print(f"From: {sender}")

    msg = MIMEMultipart("alternative")
    msg["Subject"] = "VLR Test - Ledger Reconciliation Request"
    msg["From"] = sender
    msg["To"] = to_email

    body_html = """
    <html><body>
    <h2>Test Email from VLR System</h2>
    <p>This is a test email to verify SMTP delivery works.</p>
    <p>Portal URL: http://localhost:3000/portal/access/test-token</p>
    </body></html>
    """
    msg.attach(MIMEText(body_html, "html"))

    try:
        server = smtplib.SMTP(host, port, timeout=30)
        server.ehlo()
        if use_tls:
            server.starttls()
            server.ehlo()
        if username and password:
            server.login(username, password)

        server.sendmail(sender, [to_email], msg.as_string())
        server.quit()
        print("SUCCESS: Email sent!")
        return True
    except Exception as e:
        print(f"FAILED: {e}")
        return False


if __name__ == "__main__":
    config = asyncio.run(get_config())
    # Send to the primary contact
    send_test_email(config, "SANJAY.KHANDEKAR@EMCURE.COM")
