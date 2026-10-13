"""Outgoing email. Business code depends on the EmailSender protocol only.

- SmtpEmailSender: works with any transactional email provider that offers SMTP
  (STARTTLS required). Used in staging and production.
- ConsoleEmailSender: local development only. It logs the message, including links,
  so flows can be tested without a provider. Settings validation refuses it in production.
"""

import logging
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage as MimeMessage
from typing import Protocol

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EmailMessage:
    to: str
    subject: str
    body: str


class EmailDeliveryError(Exception):
    pass


class EmailSender(Protocol):
    def send(self, message: EmailMessage) -> None: ...


class ConsoleEmailSender:
    def send(self, message: EmailMessage) -> None:
        logger.info(
            "DEV EMAIL (not sent)\nTo: %s\nSubject: %s\n\n%s",
            message.to,
            message.subject,
            message.body,
        )


class SmtpEmailSender:
    def __init__(
        self,
        *,
        host: str,
        port: int,
        username: str | None,
        password: str | None,
        sender: str,
        timeout: float = 10.0,
    ) -> None:
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self._sender = sender
        self._timeout = timeout

    def send(self, message: EmailMessage) -> None:
        mime = MimeMessage()
        mime["From"] = self._sender
        mime["To"] = message.to
        mime["Subject"] = message.subject
        mime.set_content(message.body)
        try:
            with smtplib.SMTP(self._host, self._port, timeout=self._timeout) as smtp:
                smtp.starttls(context=ssl.create_default_context())
                if self._username:
                    smtp.login(self._username, self._password or "")
                smtp.send_message(mime)
        except (smtplib.SMTPException, OSError) as exc:
            raise EmailDeliveryError(f"SMTP delivery failed: {exc.__class__.__name__}") from exc


class InMemoryEmailSender:
    """Collects messages in a list; used by automated tests."""

    def __init__(self) -> None:
        self.outbox: list[EmailMessage] = []

    def send(self, message: EmailMessage) -> None:
        self.outbox.append(message)


def build_email_sender(settings) -> EmailSender:
    if settings.email_backend == "smtp":
        return SmtpEmailSender(
            host=settings.smtp_host,
            port=settings.smtp_port,
            username=settings.smtp_username,
            password=settings.smtp_password.get_secret_value() if settings.smtp_password else None,
            sender=settings.email_from,
        )
    if settings.email_backend == "console":
        return ConsoleEmailSender()
    raise ValueError(f"Unsupported EMAIL_BACKEND: {settings.email_backend}")
