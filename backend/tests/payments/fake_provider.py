"""A scriptable stand-in for Paystack used by the flow tests (test code only)."""

import hashlib
import hmac
import itertools
import json

from app.integrations.payments import (
    ChargeResult,
    CheckoutSession,
    PaymentProviderError,
    RefundResult,
)

WEBHOOK_SECRET = "sk_test_fake_provider_secret"


class FakePaymentProvider:
    name = "paystack"

    def __init__(self) -> None:
        self.checkouts: list[dict] = []
        self.charges: dict[str, ChargeResult] = {}  # what "Paystack" reports per reference
        self.refund_states: dict[str, str] = {}
        self.refund_requests: list[dict] = []
        self.fail_next: str | None = None  # name of the next call that should fail
        self._ids = itertools.count(1)

    def _maybe_fail(self, call: str) -> None:
        if self.fail_next == call:
            self.fail_next = None
            raise PaymentProviderError(f"simulated {call} failure")

    def create_checkout(self, *, email, amount_cents, currency, reference, callback_url, metadata):
        self._maybe_fail("create_checkout")
        self.checkouts.append(
            {
                "email": email,
                "amount_cents": amount_cents,
                "currency": currency,
                "reference": reference,
                "callback_url": callback_url,
                "metadata": metadata,
            }
        )
        return CheckoutSession(
            checkout_url=f"https://checkout.test/{reference}", reference=reference
        )

    def set_charge(
        self, reference: str, status: str, amount_cents: int, currency: str = "ZAR"
    ) -> None:
        self.charges[reference] = ChargeResult(
            reference,
            status,
            amount_cents,
            currency,
            "tx-" + reference,
            "Approved" if status == "success" else "Declined",
        )

    def verify_charge(self, reference):
        self._maybe_fail("verify_charge")
        return self.charges.get(reference) or ChargeResult(
            reference, "pending", 0, "ZAR", None, None
        )

    def create_refund(self, *, reference, amount_cents, note):
        self._maybe_fail("create_refund")
        refund_id = f"rf-{next(self._ids)}"
        self.refund_states[refund_id] = "pending"
        self.refund_requests.append(
            {"reference": reference, "amount_cents": amount_cents, "note": note, "id": refund_id}
        )
        return RefundResult(refund_id, "pending", amount_cents, reference)

    def fetch_refund(self, refund_id):
        request = next(r for r in self.refund_requests if r["id"] == refund_id)
        return RefundResult(
            refund_id, self.refund_states[refund_id], request["amount_cents"], request["reference"]
        )

    def verify_webhook(self, raw_body, headers):
        expected = hmac.new(WEBHOOK_SECRET.encode(), raw_body, hashlib.sha512).hexdigest()
        return hmac.compare_digest(expected, headers.get("x-paystack-signature", ""))


def signed(event: dict, secret: str = WEBHOOK_SECRET) -> tuple[bytes, dict[str, str]]:
    body = json.dumps(event).encode()
    return body, {
        "x-paystack-signature": hmac.new(secret.encode(), body, hashlib.sha512).hexdigest(),
        "content-type": "application/json",
    }
