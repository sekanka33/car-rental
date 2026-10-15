"""WebSocket live tracking: authentication, authorisation, messages, and when it ends."""

import uuid
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from starlette.websockets import WebSocketDisconnect

from app.api.routes import live
from app.core.security import create_access_token
from app.models import Delivery, User
from tests.api_fixtures import login, register
from tests.conftest import make_settings, requires_db
from tests.tracking.conftest import HANDOVER, OWNER, fix, post, set_off

pytestmark = requires_db


def url(delivery_id: str) -> str:
    return f"/api/v1/deliveries/{delivery_id}/live"


@contextmanager
def watch(api, account, delivery_id):
    """Connect and authenticate; yields (socket, snapshot). The socket is closed even when an
    assertion fails, otherwise the test client would wait for it forever."""
    with api.websocket_connect(url(delivery_id)) as ws:
        ws.send_json({"type": "auth", "token": account.access_token})
        yield ws, ws.receive_json()


def close_code(ws) -> int:
    """The close code of the next frame. Fails on any other message: looping until a close
    would hang forever on a socket that is wrongly kept open (it sends pings)."""
    with pytest.raises(WebSocketDisconnect) as closed:
        message = ws.receive_json()
        pytest.fail(f"expected the socket to close, got {message}")
    return closed.value.code


# --- authentication and authorisation -----------------------------------------------------


@pytest.mark.parametrize(
    "first_message",
    [
        {"type": "auth", "token": "not-a-jwt"},
        {"type": "hello"},
        {"token": "missing type"},
    ],
)
def test_bad_authentication_is_refused(api, delivery_id, first_message) -> None:
    with api.websocket_connect(url(delivery_id)) as ws:
        ws.send_json(first_message)
        assert close_code(ws) == 4401


def test_silent_clients_are_dropped(api, delivery_id, monkeypatch) -> None:
    monkeypatch.setattr(live, "AUTH_TIMEOUT_SECONDS", 0.2)
    with api.websocket_connect(url(delivery_id)) as ws:
        assert close_code(ws) == 4401


def test_only_renter_assignee_and_admins_may_watch(
    api, alice, owner, admin, delivery_id, db_session
) -> None:
    register(api, "bob@example.com")
    bob = login(api, "bob@example.com")
    register(api, "other-owner@example.com", "OWNER")
    other_owner = login(api, "other-owner@example.com")

    for outsider in (bob, other_owner):
        with api.websocket_connect(url(delivery_id)) as ws:
            ws.send_json({"type": "auth", "token": outsider.access_token})
            assert close_code(ws) == 4403
    with api.websocket_connect(url("00000000-0000-0000-0000-000000000000")) as ws:
        ws.send_json({"type": "auth", "token": alice.access_token})
        assert close_code(ws) == 4403  # unknown looks the same as forbidden

    for allowed in (alice, owner, admin):
        with watch(api, allowed, delivery_id) as (ws, snapshot):
            assert snapshot["type"] == "snapshot" and snapshot["status"] == "PENDING_SCHEDULE"


def test_suspended_user_cannot_watch(api, alice, delivery_id, db_session) -> None:
    user = db_session.scalar(select(User).where(User.email == alice.email))
    user.status, user.suspended_at = "SUSPENDED", datetime.now(UTC)
    db_session.flush()
    with api.websocket_connect(url(delivery_id)) as ws:
        ws.send_json({"type": "auth", "token": alice.access_token})
        assert close_code(ws) == 4401


# --- messages ---------------------------------------------------------------------------------


def test_renter_follows_the_delivery_live(api, alice, owner, delivery_id) -> None:
    with watch(api, alice, delivery_id) as (ws, snapshot):
        assert snapshot["location"] is None and snapshot["tracking_active"] is False

        post(api, owner, f"{OWNER}/{delivery_id}/schedule")
        assert ws.receive_json()["status"] == "SCHEDULED"
        post(api, owner, f"{OWNER}/{delivery_id}/start")
        started = ws.receive_json()
        assert (started["type"], started["status"], started["booking_status"]) == (
            "status",
            "EN_ROUTE",
            "IN_TRANSIT",
        )

        post(api, owner, f"{OWNER}/{delivery_id}/location", fix(latitude=-33.91))
        moved = ws.receive_json()
        assert moved["type"] == "location"
        assert moved["location"]["latitude"] == -33.91
        assert moved["eta"]["seconds"] == 600  # fake maps provider

        post(api, owner, f"{OWNER}/{delivery_id}/handover", HANDOVER)
        delivered = ws.receive_json()
        assert delivered["status"] == "DELIVERED" and delivered["location"] is None
        assert delivered["eta"] is None and delivered["tracking_active"] is False
        assert close_code(ws) == 4000  # tracking ended


def test_snapshot_includes_the_latest_position(api, alice, owner, delivery_id) -> None:
    set_off(api, owner, delivery_id)
    post(api, owner, f"{OWNER}/{delivery_id}/location", fix(latitude=-33.95))

    with watch(api, alice, delivery_id) as (_, snapshot):
        assert snapshot["tracking_active"] is True
        assert snapshot["location"]["latitude"] == -33.95


def test_finished_delivery_sends_a_snapshot_then_ends(api, alice, owner, delivery_id) -> None:
    set_off(api, owner, delivery_id)
    post(api, owner, f"{OWNER}/{delivery_id}/handover", HANDOVER)

    with watch(api, alice, delivery_id) as (ws, snapshot):
        assert snapshot["status"] == "DELIVERED"
        assert close_code(ws) == 4000


def test_cancellation_ends_tracking(api, alice, delivery_id) -> None:
    with watch(api, alice, delivery_id) as (ws, _):
        booking_id = api.get("/api/v1/bookings?status=CONFIRMED", headers=alice.headers).json()[0][
            "id"
        ]
        post(api, alice, f"/api/v1/bookings/{booking_id}/cancel")

        assert ws.receive_json()["status"] == "CANCELLED"
        assert close_code(ws) == 4000


def test_admin_cancellation_on_the_way_is_pushed(
    api, api_app, owner, admin, delivery_id, db_session, monkeypatch
) -> None:
    # Recorded at the hub: a concurrent socket here would share the test's single DB session.
    published = []
    monkeypatch.setattr(
        api_app.state.tracking_hub, "publish", lambda _id, message: published.append(message)
    )
    set_off(api, owner, delivery_id)
    booking_id = db_session.scalar(
        select(Delivery.booking_id).where(Delivery.id == uuid.UUID(delivery_id))
    )

    cancel = post(
        api, admin, f"/api/v1/admin/bookings/{booking_id}/cancel", {"reason": "Breakdown"}
    )

    assert cancel.status_code == 200
    assert (published[-1]["status"], published[-1]["location"]) == ("CANCELLED", None)


def test_reassignment_closes_the_previous_assignees_view(
    api, owner, admin, delivery_id, db_session
) -> None:
    register(api, "helper@example.com", "OWNER")
    helper_id = db_session.scalar(select(User.id).where(User.email == "helper@example.com"))
    with watch(api, owner, delivery_id) as (ws, _):
        post(
            api,
            admin,
            f"/api/v1/admin/deliveries/{delivery_id}/assign",
            {"user_id": str(helper_id)},
        )

        assert close_code(ws) == 4403


def test_server_pings_idle_watchers(api, alice, delivery_id, monkeypatch) -> None:
    monkeypatch.setattr(live, "PING_SECONDS", 0.2)
    with watch(api, alice, delivery_id) as (ws, _):
        assert ws.receive_json() == {"type": "ping"}


def test_server_answers_client_pings(api, alice, delivery_id) -> None:
    with watch(api, alice, delivery_id) as (ws, _):
        ws.send_json({"type": "ping"})

        assert ws.receive_json() == {"type": "pong"}


def test_socket_closes_when_the_access_token_expires(api, alice, delivery_id, db_session) -> None:
    settings = make_settings()
    user = db_session.scalar(select(User).where(User.email == alice.email))
    short = create_access_token(
        user_id=user.id,
        token_version=user.token_version,
        secret=settings.jwt_secret_key.get_secret_value(),
        issuer=settings.jwt_issuer,
        audience=settings.jwt_audience,
        ttl=timedelta(seconds=2),
    )
    with api.websocket_connect(url(delivery_id)) as ws:
        ws.send_json({"type": "auth", "token": short})
        assert ws.receive_json()["type"] == "snapshot"
        assert close_code(ws) == 4401  # the app refreshes its token and reconnects
