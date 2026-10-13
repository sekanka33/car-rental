"""Payment providers behind one interface. Business code never talks to Paystack directly.

PaystackProvider follows Paystack's official OpenAPI specification
(github.com/PaystackOSS/openapi): POST /transaction/initialize, GET /transaction/verify/
{reference}, POST /refund, GET /refund/{id}. Amounts are integers in the smallest unit
(cents for ZAR). Webhooks are authenticated with HMAC-SHA512 of the raw body keyed with the
secret key (header `x-paystack-signature`).
"""

import hashlib
import hmac
import logging
from dataclasses import dataclass
from typing import Literal, Protocol

import httpx2 as httpx

logger = logging.getLogger(__name__)

ChargeStatus = Literal["success", "failed", "pending"]
RefundState = Literal["processed", "failed", "pending"]


class PaymentProviderError(Exception):
    """The provider could not be reached or rejected the request."""


@dataclass(frozen=True)
class CheckoutSession:
    checkout_url: str
    reference: str


@dataclass(frozen=True)
class ChargeResult:
    reference: str
    status: ChargeStatus
    amount_cents: int
    currency: str
    transaction_id: str | None
    gateway_response: str | None


@dataclass(frozen=True)
class RefundResult:
    refund_id: str
    status: RefundState
    amount_cents: int
    transaction_reference: str | None


class PaymentProvider(Protocol):
    name: str

    def create_checkout(
        self,
        *,
        email: str,
        amount_cents: int,
        currency: str,
        reference: str,
        callback_url: str | None,
        metadata: dict,
    ) -> CheckoutSession: ...

    def verify_charge(self, reference: str) -> ChargeResult: ...

    def create_refund(self, *, reference: str, amount_cents: int, note: str) -> RefundResult: ...

    def fetch_refund(self, refund_id: str) -> RefundResult: ...

    def verify_webhook(self, raw_body: bytes, headers: dict[str, str]) -> bool: ...


# Paystack transaction statuses that are final failures; anything not "success" or listed
# here (e.g. "ongoing", "pending", "processing", "queued") is treated as still pending.
_FAILED_CHARGE = {"failed", "abandoned", "reversed"}
_FAILED_REFUND = {"failed"}


class PaystackProvider:
    name = "paystack"

    def __init__(
        self,
        secret_key: str,
        base_url: str = "https://api.paystack.co",
        *,
        transport=None,
        timeout: float = 10.0,
    ) -> None:
        self._secret = secret_key
        self._client = httpx.Client(
            base_url=base_url,
            headers={"Authorization": f"Bearer {secret_key}", "Content-Type": "application/json"},
            timeout=timeout,
            transport=transport,
        )

    def _call(self, method: str, path: str, json: dict | None = None) -> dict:
        try:
            response = self._client.request(method, path, json=json)
        except httpx.HTTPError as exc:
            raise PaymentProviderError(f"Paystack unreachable: {exc.__class__.__name__}") from exc
        try:
            body = response.json()
        except ValueError as exc:
            raise PaymentProviderError(
                f"Paystack returned non-JSON (HTTP {response.status_code})"
            ) from exc
        if response.status_code >= 400 or not body.get("status"):
            message = str(body.get("message", "request failed"))[:200]
            logger.warning(
                "Paystack %s %s failed: HTTP %s %s", method, path, response.status_code, message
            )
            raise PaymentProviderError(f"Paystack rejected the request: {message}")
        return body["data"]

    def create_checkout(
        self, *, email, amount_cents, currency, reference, callback_url, metadata
    ) -> CheckoutSession:
        payload = {
            "email": email,
            "amount": amount_cents,
            "currency": currency,
            "reference": reference,
            "metadata": metadata,
        }
        if callback_url:
            payload["callback_url"] = callback_url
        data = self._call("POST", "/transaction/initialize", payload)
        return CheckoutSession(checkout_url=data["authorization_url"], reference=data["reference"])

    def verify_charge(self, reference: str) -> ChargeResult:
        data = self._call("GET", f"/transaction/verify/{reference}")
        raw = str(data.get("status", "")).lower()
        status: ChargeStatus = (
            "success" if raw == "success" else "failed" if raw in _FAILED_CHARGE else "pending"
        )
        return ChargeResult(
            reference=str(data.get("reference")),
            status=status,
            amount_cents=int(data.get("amount") or 0),
            currency=str(data.get("currency") or ""),
            transaction_id=str(data["id"]) if data.get("id") is not None else None,
            gateway_response=(
                str(data.get("gateway_response"))[:200] if data.get("gateway_response") else None
            ),
        )

    @staticmethod
    def _refund_result(data: dict) -> RefundResult:
        raw = str(data.get("status", "")).lower()
        status: RefundState = (
            "processed" if raw == "processed" else "failed" if raw in _FAILED_REFUND else "pending"
        )
        transaction = data.get("transaction") or {}
        reference = transaction.get("reference") if isinstance(transaction, dict) else None
        return RefundResult(
            refund_id=str(data["id"]),
            status=status,
            amount_cents=int(data.get("amount") or 0),
            transaction_reference=reference,
        )

    def create_refund(self, *, reference: str, amount_cents: int, note: str) -> RefundResult:
        data = self._call(
            "POST",
            "/refund",
            {"transaction": reference, "amount": amount_cents, "merchant_note": note[:200]},
        )
        return self._refund_result(data)

    def fetch_refund(self, refund_id: str) -> RefundResult:
        return self._refund_result(self._call("GET", f"/refund/{refund_id}"))

    def verify_webhook(self, raw_body: bytes, headers: dict[str, str]) -> bool:
        signature = headers.get("x-paystack-signature", "")
        expected = hmac.new(self._secret.encode(), raw_body, hashlib.sha512).hexdigest()
        return bool(signature) and hmac.compare_digest(expected, signature)


def build_payment_provider(settings) -> PaymentProvider | None:
    """The configured provider, or None when payments are not configured."""
    if settings.paystack_secret_key is None:
        return None
    return PaystackProvider(
        settings.paystack_secret_key.get_secret_value(), settings.paystack_base_url
    )
