"""
SMTP email provider adapter.
Sends emails using the configured SMTP settings from vlr_settings table.
"""

import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from src.domain.services.vlr.notification_service import IEmailSender

logger = logging.getLogger(__name__)


class SmtpEmailSender(IEmailSender):
    """Sends emails via SMTP using stored configuration."""

    def __init__(
        self,
        host: str,
        port: int,
        username: str,
        password: str,
        sender_email: str,
        sender_name: str = "",
        use_tls: bool = True,
    ) -> None:
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self._sender_email = sender_email
        self._sender_name = sender_name
        self._use_tls = use_tls

    async def send_email(
        self,
        to_email: str,
        subject: str,
        body_html: str,
        template_code: str | None = None,
    ) -> bool:
        """Send an email via SMTP. Returns True on success."""
        import asyncio
        import functools

        try:
            result = await asyncio.get_event_loop().run_in_executor(
                None,
                functools.partial(self._send_sync, to_email, subject, body_html),
            )
            return result
        except Exception as e:
            logger.error("Failed to send email to %s: %s", to_email, str(e))
            return False

    def _send_sync(self, to_email: str, subject: str, body_html: str) -> bool:
        """Synchronous SMTP send."""
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        if self._sender_name:
            msg["From"] = f"{self._sender_name} <{self._sender_email}>"
        else:
            msg["From"] = self._sender_email
        msg["To"] = to_email

        html_part = MIMEText(body_html, "html")
        msg.attach(html_part)

        if self._use_tls:
            server = smtplib.SMTP(self._host, self._port, timeout=30)
            server.ehlo()
            server.starttls()
            server.ehlo()
        else:
            server = smtplib.SMTP(self._host, self._port, timeout=30)

        if self._username and self._password:
            server.login(self._username, self._password)

        server.sendmail(self._sender_email, [to_email], msg.as_string())
        server.quit()

        logger.info("Email sent successfully to %s (subject: %s)", to_email, subject)
        return True
