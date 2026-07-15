"""Debug email - send with full error output and try sending to yourself."""
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

# Config from DB
HOST = "smtp.office365.com"
PORT = 587
USERNAME = "Emcure.MendixAD@emcure.com"
PASSWORD = "P0s$w0rd#7654"
SENDER = "Emcure.MendixAD@emcure.com"
TO_EMAIL = "vaishnavi.varkur@emcure.com"

print(f"Sending from: {SENDER}")
print(f"Sending to: {TO_EMAIL}")
print(f"SMTP: {HOST}:{PORT}")
print()

msg = MIMEMultipart("alternative")
msg["Subject"] = "VLR Portal - TEST EMAIL (please confirm receipt)"
msg["From"] = SENDER
msg["To"] = TO_EMAIL

body = """
<html><body style="font-family:Arial,sans-serif;">
<h2 style="color:#C41E3A;">VLR Email Test</h2>
<p>If you can see this email, SMTP delivery is working correctly.</p>
<p>Portal link: <a href="http://localhost:3000/portal/access/3bdd2c6b-20f6-48dc-b039-73a9e7659d02">Click here to access portal</a></p>
<p style="color:#666;font-size:12px;">Sent at: """ + __import__('datetime').datetime.now().isoformat() + """</p>
</body></html>
"""
msg.attach(MIMEText(body, "html"))

try:
    print("Connecting...")
    server = smtplib.SMTP(HOST, PORT, timeout=30)
    server.set_debuglevel(1)  # Full SMTP debug output
    server.ehlo()
    print("STARTTLS...")
    server.starttls()
    server.ehlo()
    print("Logging in...")
    server.login(USERNAME, PASSWORD)
    print("Sending...")
    result = server.sendmail(SENDER, [TO_EMAIL], msg.as_string())
    print(f"\nResult: {result}")
    print("SUCCESS - email accepted by server")
    server.quit()
except Exception as e:
    print(f"\nFAILED: {type(e).__name__}: {e}")
