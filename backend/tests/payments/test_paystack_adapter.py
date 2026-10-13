"""The Paystack adapter against a mocked HTTP transport (request shapes follow Paystack's
official OpenAPI spec). No network access and no real money."""

import hashlib
import hmac
import json

import httpx2 as httpx
import pytest

from app.integrations.payments import PaymentProviderError, PaystackProvider

SECRET = "sk_test_" + "0" * 40


def provider(handler) -> tuple[PaystackProvider, list[httpx.Request]]:
    seen: list[httpx.Request] = []

    def record(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    return PaystackProvider(SECRET, transport=httpx.MockTransport(record)), seen


def ok(data: dict) -> httpx.Response:
    return httpx.Response(200, json={"status": True, "message": "ok", "data": data})


def test_initialize_sends_integer_cents_in_zar() -> None:
    paystack, seen = provider(
        lambda r: ok(
            {
                "authorization_url": "https://checkout.paystack.com/abc",
                "access_code": "abc",
                "reference": "PAY1",
            }
        )
    )

    session = paystack.create_checkout(
        email="renter@example.com",
        amount_cents=210000,
        currency="ZAR",
        reference="PAY1",
        callback_url="https://app.example/return",
        metadata={"booking_id": "b1"},
    )

    request = seen[0]
    assert (request.method, str(request.url)) == (
        "POST",
        "https://api.paystack.co/transaction/initialize",
    )
    assert request.headers["authorization"] == f"Bearer {SECRET}"
    assert json.loads(request.content) == {
        "email": "renter@example.com",
        "amount": 210000,
        "currency": "ZAR",
        "reference": "PAY1",
        "metadata": {"booking_id": "b1"},
        "callback_url": "https://app.example/return",
    }
    assert session.checkout_url == "https://checkout.paystack.com/abc"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("success", "success"),
        ("failed", "failed"),
        ("abandoned", "failed"),
        ("reversed", "failed"),
        ("ongoing", "pending"),
        ("pending", "pending"),
        ("processing", "pending"),
        ("", "pending"),
    ],
)
def test_verify_maps_statuses_conservatively(raw: str, expected: str) -> None:
    paystack, seen = provider(
        lambda r: ok(
            {
                "id": 99,
                "status": raw,
                "reference": "PAY1",
                "amount": 210000,
                "currency": "ZAR",
                "gateway_response": "Approved",
            }
        )
    )

    result = paystack.verify_charge("PAY1")

    assert str(seen[0].url) == "https://api.paystack.co/transaction/verify/PAY1"
    assert result.status == expected
    assert (result.amount_cents, result.currency, result.transaction_id) == (210000, "ZAR", "99")


def test_refund_create_and_fetch() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return ok(
                {
                    "id": 7,
                    "status": "pending",
                    "amount": 50000,
                    "transaction": {"reference": "PAY1"},
                }
            )
        return ok(
            {"id": 7, "status": "processed", "amount": 50000, "transaction": {"reference": "PAY1"}}
        )

    paystack, seen = provider(handler)

    created = paystack.create_refund(reference="PAY1", amount_cents=50000, note="Cancelled")
    fetched = paystack.fetch_refund("7")

    assert json.loads(seen[0].content) == {
        "transaction": "PAY1",
        "amount": 50000,
        "merchant_note": "Cancelled",
    }
    assert str(seen[1].url) == "https://api.paystack.co/refund/7"
    assert (created.refund_id, created.status, fetched.status) == ("7", "pending", "processed")


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(401, json={"status": False, "message": "Invalid key"}),
        httpx.Response(200, json={"status": False, "message": "Duplicate reference"}),
        httpx.Response(502, text="<html>bad gateway</html>"),
    ],
    ids=["unauthorised", "status-false", "non-json"],
)
def test_provider_errors_are_raised(response: httpx.Response) -> None:
    paystack, _ = provider(lambda r: response)

    with pytest.raises(PaymentProviderError):
        paystack.verify_charge("PAY1")


def test_network_failure_is_a_provider_error() -> None:
    def boom(request):
        raise httpx.ConnectError("down")

    paystack, _ = provider(boom)
    with pytest.raises(PaymentProviderError):
        paystack.create_checkout(
            email="a@b.co",
            amount_cents=100,
            currency="ZAR",
            reference="R",
            callback_url=None,
            metadata={},
        )


def test_webhook_signature_is_hmac_sha512_of_the_raw_body() -> None:
    paystack, _ = provider(lambda r: ok({}))
    body = b'{"event":"charge.success","data":{"reference":"PAY1"}}'
    good = hmac.new(SECRET.encode(), body, hashlib.sha512).hexdigest()

    assert paystack.verify_webhook(body, {"x-paystack-signature": good})
    assert not paystack.verify_webhook(body + b" ", {"x-paystack-signature": good})  # body tampered
    assert not paystack.verify_webhook(body, {"x-paystack-signature": "0" * 128})
    assert not paystack.verify_webhook(body, {})
    other = hmac.new(b"sk_test_other", body, hashlib.sha512).hexdigest()
    assert not paystack.verify_webhook(body, {"x-paystack-signature": other})


@pytest.mark.parametrize(
    ("key", "allow_live", "ok_"),
    [
        ("sk_test_abc", False, True),
        ("sk_live_abc", False, False),
        ("sk_live_abc", True, True),
        ("pk_test_abc", False, False),
    ],
    ids=["test-key", "live-key-blocked", "live-key-explicitly-allowed", "public-key-rejected"],
)
def test_live_keys_need_explicit_approval(key: str, allow_live: bool, ok_: bool) -> None:
    from tests.conftest import make_settings

    if ok_:
        make_settings(paystack_secret_key=key, allow_live_payments=allow_live)
    else:
        with pytest.raises(ValueError):
            make_settings(paystack_secret_key=key, allow_live_payments=allow_live)
