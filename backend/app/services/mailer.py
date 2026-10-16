"""Sending email (public account verification). One function; three ways out:

- tests: kept in OUTBOX for assertions;
- an SMTP server when CARCUX_SMTP_HOST is set (Mailpit in the local stack);
- otherwise written to the log, so a developer can still follow the link.
"""

import logging
import smtplib
from email.message import EmailMessage

from app.core.config import Settings

log = logging.getLogger("carcux.mail")
OUTBOX: list[EmailMessage] = []


def send(settings: Settings, to: str, subject: str, text: str) -> None:
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = settings.mail_from, to, subject
    msg.set_content(text)
    if settings.environment == "test":
        OUTBOX.append(msg)
        return
    if not settings.smtp_host:
        log.warning("No SMTP host set; email to %s not sent:\n%s\n%s", to, subject, text)
        return
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as smtp:
        if settings.smtp_starttls:
            smtp.starttls()
        if settings.smtp_user and settings.smtp_password:
            smtp.login(settings.smtp_user, settings.smtp_password.get_secret_value())
        smtp.send_message(msg)
