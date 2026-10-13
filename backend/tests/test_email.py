import smtplib

import pytest

from app.integrations import email as email_module
from app.integrations.email import (
    EmailDeliveryError,
    EmailMessage,
    SmtpEmailSender,
    build_email_sender,
)
from tests.conftest import make_settings

MESSAGE = EmailMessage(to="renter@example.com", subject="Hello", body="Body text")


class FakeSMTP:
    instances: list["FakeSMTP"] = []
    fail_on_send = False

    def __init__(self, host, port, timeout):
        self.host, self.port, self.timeout = host, port, timeout
        self.calls: list[str] = []
        self.sent = []
        FakeSMTP.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.calls.append("quit")

    def starttls(self, context):
        self.calls.append("starttls")

    def login(self, username, password):
        self.calls.append(f"login:{username}")

    def send_message(self, message):
        if FakeSMTP.fail_on_send:
            raise smtplib.SMTPRecipientsRefused({})
        self.calls.append("send")
        self.sent.append(message)


@pytest.fixture(autouse=True)
def fake_smtp(monkeypatch: pytest.MonkeyPatch):
    FakeSMTP.instances, FakeSMTP.fail_on_send = [], False
    monkeypatch.setattr(email_module.smtplib, "SMTP", FakeSMTP)


def sender() -> SmtpEmailSender:
    return SmtpEmailSender(
        host="smtp.example.com", port=587, username="apikey", password="pw", sender="App <a@b.co>"
    )


def test_smtp_sender_uses_starttls_and_authenticates() -> None:
    sender().send(MESSAGE)

    smtp = FakeSMTP.instances[0]
    assert (smtp.host, smtp.port) == ("smtp.example.com", 587)
    assert smtp.calls == ["starttls", "login:apikey", "send", "quit"]
    sent = smtp.sent[0]
    assert sent["To"] == "renter@example.com" and sent["From"] == "App <a@b.co>"
    assert sent.get_content().strip() == "Body text"


def test_smtp_failures_raise_delivery_error() -> None:
    FakeSMTP.fail_on_send = True

    with pytest.raises(EmailDeliveryError):
        sender().send(MESSAGE)


def test_settings_select_the_sender() -> None:
    smtp = build_email_sender(
        make_settings(email_backend="smtp", smtp_host="smtp.example.com", smtp_password="x")
    )
    console = build_email_sender(make_settings())

    assert isinstance(smtp, SmtpEmailSender)
    assert type(console).__name__ == "ConsoleEmailSender"


@pytest.mark.parametrize(
    "overrides",
    [{"app_env": "production"}, {"email_backend": "smtp"}],
    ids=["console-in-production", "smtp-without-host"],
)
def test_unsafe_email_configuration_rejected(overrides: dict) -> None:
    with pytest.raises(ValueError):
        make_settings(**overrides)
