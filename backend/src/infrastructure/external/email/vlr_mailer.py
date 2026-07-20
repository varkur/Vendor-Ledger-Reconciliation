"""
VLR mailer helpers — send transactional emails directly via SMTP using the
globally configured email settings. Used for vendor invites and sign-off
requests without depending on Celery.
"""

import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.database.models.vlr.reconciliation_case_model import (
    ReconciliationCaseModel,
)
from src.infrastructure.database.models.vlr.vendor_model import VendorModel
from src.infrastructure.database.models.vlr.vendor_contact_model import VendorContactModel
from src.infrastructure.database.repositories.vlr.setting_repository_impl import (
    SettingRepositoryImpl,
)
from src.infrastructure.external.email.smtp_provider import SmtpEmailSender

logger = logging.getLogger(__name__)

PORTAL_BASE_URL = "http://localhost:3000"


async def _load_email_sender(session: AsyncSession) -> SmtpEmailSender | None:
    """Build an SmtpEmailSender from the global email configuration."""
    setting_repo = SettingRepositoryImpl(session)
    prefix = "email.__global__."

    async def _get(key: str, default: str = "") -> str:
        s = await setting_repo.get_by_key("__global__", f"{prefix}{key}")
        return s.value if s else default

    host = await _get("smtp_host")
    sender_email = await _get("sender_email")
    if not host or not sender_email:
        return None

    return SmtpEmailSender(
        host=host,
        port=int(await _get("smtp_port", "587")),
        username=await _get("smtp_username"),
        password=await _get("smtp_password"),
        sender_email=sender_email,
        sender_name=await _get("sender_name"),
        use_tls=(await _get("use_tls", "true")).lower() == "true",
    )


async def _get_vendor_and_contact(
    session: AsyncSession, case: ReconciliationCaseModel
) -> tuple[VendorModel | None, VendorContactModel | None]:
    """Fetch the vendor and its primary (or first) contact for a case."""
    vendor = (await session.execute(
        select(VendorModel).where(VendorModel.id == case.vendor_id)
    )).scalar_one_or_none()
    if vendor is None:
        return None, None

    contact = (await session.execute(
        select(VendorContactModel)
        .where(
            VendorContactModel.vendor_id == vendor.id,
            VendorContactModel.is_primary == True,  # noqa: E712
        )
        .limit(1)
    )).scalar_one_or_none()

    if contact is None:
        contact = (await session.execute(
            select(VendorContactModel)
            .where(VendorContactModel.vendor_id == vendor.id)
            .limit(1)
        )).scalar_one_or_none()

    return vendor, contact


async def send_signoff_request_email(
    session: AsyncSession, case_id: UUID
) -> tuple[bool, str]:
    """
    Send a sign-off request email to the vendor's primary contact with the
    tokenized portal link. Returns (success, message).
    """
    case = (await session.execute(
        select(ReconciliationCaseModel).where(ReconciliationCaseModel.id == case_id)
    )).scalar_one_or_none()
    if case is None:
        return False, "Case not found."

    sender = await _load_email_sender(session)
    if sender is None:
        return False, "Email is not configured."

    vendor, contact = await _get_vendor_and_contact(session, case)
    if vendor is None or contact is None or not contact.email:
        return False, "No vendor contact email found."

    portal_url = f"{PORTAL_BASE_URL}/portal/access/{case.portal_token}"

    body_html = f"""
    <html>
    <body style="font-family: Segoe UI, Arial, sans-serif; line-height: 1.6; color: #333;">
        <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
            <h2 style="color: #C41E3A;">Reconciliation Sign-off Request</h2>
            <p>Dear {contact.name or vendor.name},</p>
            <p>
                The ledger reconciliation between <strong>Emcure Pharmaceuticals Limited</strong>
                and <strong>{vendor.name}</strong> has been reviewed and is ready for your sign-off.
            </p>
            <p>Please review the reconciliation statement and confirm your sign-off using the link below:</p>
            <p style="text-align: center; margin: 30px 0;">
                <a href="{portal_url}"
                   style="background-color: #C41E3A; color: white; padding: 12px 30px;
                          text-decoration: none; border-radius: 5px; font-weight: bold;">
                    Review &amp; Sign Off
                </a>
            </p>
            <p style="font-size: 12px; color: #666;">
                If you have any questions or disagree with the reconciliation, you can raise a
                dispute from the portal. Portal Link:
                <a href="{portal_url}">{portal_url}</a>
            </p>
        </div>
    </body>
    </html>
    """

    subject = f"Sign-off Request - Ledger Reconciliation ({vendor.name})"
    success = await sender.send_email(
        to_email=contact.email,
        subject=subject,
        body_html=body_html,
    )

    if success:
        logger.info("Sign-off request email sent to %s for case %s", contact.email, case_id)
        return True, f"Sign-off request sent to {contact.email}."
    return False, "SMTP delivery failed."
