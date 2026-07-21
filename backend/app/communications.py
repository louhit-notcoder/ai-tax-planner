from __future__ import annotations

import smtplib
from email.message import EmailMessage

from .config import get_settings


class CommunicationDeliveryError(RuntimeError):
    pass


def send_member_invitation(*, recipient: str, firm_name: str, role: str, token: str) -> None:
    """Deliver a privileged-member invitation through configured SMTP.

    The raw invitation token is never persisted. Production fails closed when the
    approved delivery channel is unavailable instead of returning the token to the UI.
    """
    settings = get_settings()
    if not settings.smtp_host or not settings.smtp_from_email:
        raise CommunicationDeliveryError("Approved SMTP invitation delivery is not configured")
    link = f"{settings.app_base_url}/?invitation={token}"
    message = EmailMessage()
    message["Subject"] = f"Invitation to {firm_name} on Green Papaya"
    message["From"] = settings.smtp_from_email
    message["To"] = recipient
    message.set_content(
        f"You were invited to join {firm_name} as {role}.\n\n"
        f"Open this one-time invitation link: {link}\n\n"
        "Do not forward this link. It expires automatically."
    )
    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30) as smtp:
            if settings.smtp_use_tls:
                smtp.starttls()
            if settings.smtp_username:
                smtp.login(settings.smtp_username, settings.smtp_password or "")
            smtp.send_message(message)
    except Exception as exc:
        raise CommunicationDeliveryError("Invitation delivery failed") from exc
