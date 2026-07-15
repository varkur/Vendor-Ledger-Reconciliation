"""Send email TO yourself FROM yourself to bypass internal routing issues."""
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime

HOST = "smtp.office365.com"
PORT = 587
USERNAME = "Emcure.MendixAD@emcure.com"
PASSWORD = "P0s$w0rd#7654"
SENDER = "Emcure.MendixAD@emcure.com"
TO_EMAIL = "vaishnavi.varkur@emcure.com"

# Try with proper headers that won't get flagged
msg = MIMEMultipart("alternative")
msg["Subject"] = f"VLR Reconciliation - Action Required [{datetime.now().strftime('%H:%M')}]"
msg["From"] = f"Emcure VLR System <{SENDER}>"
msg["To"] = TO_EMAIL
msg["Reply-To"] = SENDER
msg["X-Priority"] = "1"
msg["Importance"] = "High"

body = """
<html><body style="font-family:Segoe UI,Arial,sans-serif;color:#333;">
<table width="100%" cellpadding="0" cellspacing="0" style="max-width:600px;margin:0 auto;">
<tr><td style="background:#C41E3A;padding:20px;text-align:center;">
<h1 style="color:white;margin:0;font-size:20px;">Emcure VLR - Vendor Ledger Reconciliation</h1>
</td></tr>
<tr><td style="padding:24px;background:#fff;">
<p>Dear Vendor,</p>
<p>You have been invited to participate in a ledger reconciliation by <strong>Emcure Pharmaceuticals Limited</strong>.</p>
<p><strong>Period:</strong> 01-Apr-2025 to 31-Mar-2026</p>
<p>Please click the button below to upload your statement:</p>
<p style="text-align:center;margin:24px 0;">
<a href="http://localhost:3000/portal/access/3bdd2c6b-20f6-48dc-b039-73a9e7659d02" 
   style="background:#C41E3A;color:white;padding:12px 30px;text-decoration:none;border-radius:4px;font-weight:bold;display:inline-block;">
Upload Statement
</a>
</p>
<p style="font-size:12px;color:#888;">This link expires in 90 days. For questions, contact the reconciliation team.</p>
</td></tr>
<tr><td style="background:#f5f5f5;padding:12px;text-align:center;font-size:11px;color:#888;">
Emcure Pharmaceuticals Limited | VLR System
</td></tr>
</table>
</body></html>
"""
msg.attach(MIMEText(body, "html"))

print(f"Sending to: {TO_EMAIL}")
try:
    server = smtplib.SMTP(HOST, PORT, timeout=30)
    server.ehlo()
    server.starttls()
    server.ehlo()
    server.login(USERNAME, PASSWORD)
    server.sendmail(SENDER, [TO_EMAIL], msg.as_string())
    server.quit()
    print("SENT OK - Check inbox in 1-2 minutes")
    print("Subject: VLR Reconciliation - Action Required")
except Exception as e:
    print(f"FAILED: {e}")
