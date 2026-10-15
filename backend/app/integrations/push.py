"""Push notifications through the Expo Push Service (one API for FCM and APNs).

POST https://exp.host/--/api/v2/push/send with up to 100 messages; the response has one
ticket per message, in order: {"status": "ok", "id": ...} or {"status": "error",
"details": {"error": "DeviceNotRegistered"}}. A DeviceNotRegistered token must not be used
again. EXPO_ACCESS_TOKEN is only needed if "enhanced push security" is on in EAS.

Not implemented yet: fetching push receipts (/push/getReceipts) about 15 minutes later, which
reports errors that only appear after FCM/APNs processing.
"""

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx2 as httpx

logger = logging.getLogger(__name__)
EXPO_TOKEN = re.compile(r"^Expo(nent)?PushToken\[[A-Za-z0-9_\-]{10,}\]$")
MAX_BATCH = 100


@dataclass(frozen=True)
class PushMessage:
    to: str
    title: str
    body: str
    data: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PushTicket:
    ok: bool
    error: str | None = None  # e.g. "DeviceNotRegistered"

    @property
    def device_gone(self) -> bool:
        return self.error == "DeviceNotRegistered"


class PushDeliveryError(Exception):
    """The whole request failed (network, 4xx/5xx): retry later."""


class PushProvider(Protocol):
    def send(self, messages: list[PushMessage]) -> list[PushTicket]: ...


def is_expo_token(token: str) -> bool:
    return bool(EXPO_TOKEN.match(token))


class ExpoPushProvider:
    def __init__(
        self,
        access_token: str | None = None,
        *,
        url: str = "https://exp.host/--/api/v2/push/send",
        transport=None,
        timeout: float = 10.0,
    ) -> None:
        self._url = url
        headers = {"Accept": "application/json", "Accept-Encoding": "gzip, deflate"}
        if access_token:
            headers["Authorization"] = f"Bearer {access_token}"
        self._client = httpx.Client(timeout=timeout, transport=transport, headers=headers)

    def send(self, messages: list[PushMessage]) -> list[PushTicket]:
        tickets: list[PushTicket] = []
        for start in range(0, len(messages), MAX_BATCH):
            tickets += self._send_batch(messages[start : start + MAX_BATCH])
        return tickets

    def _send_batch(self, batch: list[PushMessage]) -> list[PushTicket]:
        payload = [
            {
                "to": m.to,
                "title": m.title,
                "body": m.body,
                "data": m.data,
                "sound": "default",
                "priority": "high",
            }
            for m in batch
        ]
        try:
            response = self._client.post(self._url, json=payload)
            body = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise PushDeliveryError(f"Expo push request failed: {exc.__class__.__name__}") from exc
        if response.status_code != 200 or not isinstance(body.get("data"), list):
            codes = [e.get("code") for e in body.get("errors", []) if isinstance(e, dict)]
            raise PushDeliveryError(
                f"Expo push rejected the request (HTTP {response.status_code} {codes})"
            )
        tickets = []
        for item in body["data"]:
            if item.get("status") == "ok":
                tickets.append(PushTicket(ok=True))
            else:
                error = (item.get("details") or {}).get("error") or "Unknown"
                tickets.append(PushTicket(ok=False, error=str(error)[:100]))
        if len(tickets) != len(batch):
            raise PushDeliveryError("Expo push returned a different number of tickets")
        return tickets


class InMemoryPushProvider:
    """Records messages; used by tests and local development without devices."""

    def __init__(self) -> None:
        self.sent: list[PushMessage] = []
        self.gone: set[str] = set()  # tokens to report as DeviceNotRegistered
        self.fail_next = False

    def send(self, messages: list[PushMessage]) -> list[PushTicket]:
        if self.fail_next:
            self.fail_next = False
            raise PushDeliveryError("simulated outage")
        self.sent += messages
        return [
            PushTicket(ok=False, error="DeviceNotRegistered")
            if m.to in self.gone
            else PushTicket(ok=True)
            for m in messages
        ]


def build_push_provider(settings) -> PushProvider | None:
    if not settings.push_enabled:
        return None
    token = settings.expo_access_token.get_secret_value() if settings.expo_access_token else None
    return ExpoPushProvider(token)
