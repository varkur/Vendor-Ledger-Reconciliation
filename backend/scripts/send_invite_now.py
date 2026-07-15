"""Send vendor invite email to vaishnavi right now for the existing case."""
import asyncio
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

DATABASE_URL = "postgresql+asyncpg://postgres:root@localhost:5432/vlr_db"


async def send():
    engine = create_async_engine(DATABASE_URL)
    async with engine.begin() as conn:
        # Get email config
        result = await conn.execute(
            text("SELECT key, value FROM vlr_settings WHERE key LIKE 'email.%'")
        )
        config = {row.key.split(".")[-1]: row.value for row in result.fetchall()}

        # Get latest case portal token
        result2 = await conn.execute(text("""
            SELECT c.portal_token, r.period_start, r.period_end
            FROM vlr_reconciliation_cases c
            JOIN vlr_reconciliation_requests r ON c.request_id = r.id
            JOIN vlr_vendors v ON c.vendor_id = v.id
            WHERE v.vendor_code = 'ABHCS4531M'
            ORDER BY c.created_date DESC LIMIT 1
        """))
        row = result2.fetchone()
        if not row:
            print("No case found!")
            return

        portal_url = f"http://localhost:3000/portal/access/{row.portal_token}"
        period_start = str(row.period_start)
        period_end = str(row.period_end)

    await engine.dispose()

    # Send email
    to_email = "vaishnavi.varkur@emcure.com"
    sender = config["sender_email"]
    
    body_html = f"""
    <html>
    <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
        <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
            <h2 style="color: #C41E3A;">Vendor Ledger Reconciliation Request</h2>
            <p>Dear Sir/Madam,</p>
            <p>
                You have been invited to participate in a ledger reconciliation by
                <strong>Emcure Pharmaceuticals Limited</strong>.
            </p>
            <p><strong>Reconciliation Period:</strong> {period_start} to {period_end}</p>
            <p>
                Please click the link below to access the portal and upload your
                ledger statement:
            </p>
            <p style="text-align: center; margin: 30px 0;">
                <a href="{portal_url}"
                   style="background-color: #C41E3A; color: white; padding: 12px 30px;
                          text-decoration: none; border-radius: 5px; font-weight: bold;">
                    Upload Statement
                </a>
            </p>
            <p style="font-size: 12px; color: #666;">
                This link is valid for 90 days. If you have any questions, please
                contact the reconciliation team.
            </p>
            <p style="font-size: 12px; color: #666;">
                Portal Link: <a href="{portal_url}">{portal_url}</a>
            </p>
        </div>
    </body>
    </html>
    """

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"Ledger Reconciliation Request - {period_start} to {period_end}"
    msg["From"] = sender
    msg["To"] = to_email
    msg.attach(MIMEText(body_html, "html"))

    server = smtplib.SMTP(config["smtp_host"], int(config["smtp_port"]), timeout=30)
    server.ehlo()
    server.starttls()
    server.ehlo()
    server.login(config["smtp_username"], config["smtp_password"])
    server.sendmail(sender, [to_email], msg.as_string())
    server.quit()
    print(f"Email sent to {to_email}")
    print(f"Portal URL: {portal_url}")


if __name__ == "__main__":
    asyncio.run(send())
