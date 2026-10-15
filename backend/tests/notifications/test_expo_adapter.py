"""Expo push adapter against the documented request and ticket shapes (no network)."""

import json

import httpx2 as httpx
import pytest

from app.integrations.push import ExpoPushProvider, PushDeliveryError, PushMessage, is_expo_token

TOKEN = "ExponentPushToken[xxxxxxxxxxxxxxxxxxxxxx]"


def provider(handler, access_token=None):
    seen: list[httpx.Request] = []

    def record(request):
        seen.append(request)
        return handler(request)

    return ExpoPushProvider(access_token, transport=httpx.MockTransport(record)), seen


def test_sends_documented_fields_and_reads_tickets_in_order() -> None:
    def reply(request):
        n = len(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "data": [
                    {"status": "ok", "id": "r1"},
                    {
                        "status": "error",
                        "message": "x",
                        "details": {"error": "DeviceNotRegistered"},
                    },
                ][:n]
            },
        )

    push, seen = provider(reply, access_token="secret-token")
    tickets = push.send(
        [PushMessage(TOKEN, "Title", "Body", {"link": "/x"}), PushMessage(TOKEN, "T2", "B2")]
    )

    body = json.loads(seen[0].content)
    assert body[0] == {
        "to": TOKEN,
        "title": "Title",
        "body": "Body",
        "data": {"link": "/x"},
        "sound": "default",
        "priority": "high",
    }
    assert seen[0].url == "https://exp.host/--/api/v2/push/send"
    assert seen[0].headers["Authorization"] == "Bearer secret-token"
    assert [t.ok for t in tickets] == [True, False] and tickets[1].device_gone


def test_no_auth_header_without_an_access_token() -> None:
    push, seen = provider(lambda r: httpx.Response(200, json={"data": [{"status": "ok"}]}))
    push.send([PushMessage(TOKEN, "T", "B")])
    assert "Authorization" not in seen[0].headers


def test_more_than_100_messages_are_split() -> None:
    def reply(request):
        return httpx.Response(
            200, json={"data": [{"status": "ok"}] * len(json.loads(request.content))}
        )

    push, seen = provider(reply)
    assert len(push.send([PushMessage(TOKEN, "T", "B")] * 230)) == 230
    assert [len(json.loads(r.content)) for r in seen] == [100, 100, 30]


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(
            429, json={"errors": [{"code": "TOO_MANY_REQUESTS", "message": "slow down"}]}
        ),
        httpx.Response(500, text="oops"),
        httpx.Response(200, json={"data": [{"status": "ok"}, {"status": "ok"}]}),  # wrong count
    ],
)
def test_request_failures_are_retryable_errors(response) -> None:
    push, _ = provider(lambda r: response)
    with pytest.raises(PushDeliveryError):
        push.send([PushMessage(TOKEN, "T", "B")])


def test_network_errors_are_retryable() -> None:
    def boom(request):
        raise httpx.ConnectError("down")

    push, _ = provider(boom)
    with pytest.raises(PushDeliveryError):
        push.send([PushMessage(TOKEN, "T", "B")])


def test_token_format() -> None:
    assert is_expo_token(TOKEN) and is_expo_token("ExpoPushToken[abcdefghij12]")
    assert not is_expo_token("fcm:abc") and not is_expo_token("ExponentPushToken[]")
