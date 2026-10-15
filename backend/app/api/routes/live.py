"""WebSocket: live delivery status, location and ETA (BR-7.3).

Protocol (JSON text frames):
1. The client connects to `/api/v1/deliveries/{id}/live` and, within 10 seconds, sends
   `{"type": "auth", "token": "<access token>"}`. The token is not put in the URL, so it
   never ends up in proxy or server logs.
2. The server replies with `{"type": "snapshot", ...}`, then sends `location` and `status`
   messages as they happen, and `ping` every 25 seconds. The client may send `ping`; the
   server answers `pong`.
3. Close codes: 4401 not authenticated or the access token expired (refresh, reconnect);
   4403 not allowed (also for unknown deliveries); 4000 tracking ended (delivered,
   cancelled or failed). The renter, the assigned delivery person and administrators may
   watch; access is re-checked on every status change (e.g. after reassignment).
"""

import asyncio
import json
import logging
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, WebSocket
from starlette.concurrency import run_in_threadpool
from starlette.websockets import WebSocketDisconnect, WebSocketState

from app.api.deps import DbSession, authenticate_access_token
from app.core.errors import AppError
from app.services import tracking

logger = logging.getLogger(__name__)
router = APIRouter(tags=["live tracking"])
AUTH_TIMEOUT_SECONDS = 10
PING_SECONDS = 25
CLOSE_UNAUTHENTICATED = 4401
CLOSE_FORBIDDEN = 4403
CLOSE_ENDED = 4000


async def _close(websocket: WebSocket, code: int, reason: str) -> None:
    if websocket.client_state == WebSocketState.CONNECTED:
        try:
            await websocket.close(code=code, reason=reason)
        except RuntimeError:
            pass  # the client went away first


async def _read_auth(websocket: WebSocket) -> str | None:
    try:
        message = await asyncio.wait_for(websocket.receive_text(), AUTH_TIMEOUT_SECONDS)
        body = json.loads(message)
    except (TimeoutError, ValueError, WebSocketDisconnect, KeyError):
        return None
    if isinstance(body, dict) and body.get("type") == "auth" and isinstance(body.get("token"), str):
        return body["token"]
    return None


def _authorise(session, settings, token: str, delivery_id: uuid.UUID):
    """(claims, delivery) if the token is valid and its user may watch; else (claims, None).
    Raises AppError for an invalid token. Ends the (read-only) transaction afterwards so the
    long-lived socket does not hold a database connection."""
    try:
        user, claims = authenticate_access_token(session, settings, token)
        return claims, tracking.find_watchable(session, user, delivery_id)
    finally:
        session.commit()


async def _client_reader(websocket: WebSocket, gone: asyncio.Event) -> None:
    """Answer pings and notice when the client disconnects."""
    try:
        while True:
            message = await websocket.receive()
            if message["type"] == "websocket.disconnect":
                return
            if message.get("text") and json.loads(message["text"]).get("type") == "ping":
                await websocket.send_json({"type": "pong"})
    except Exception:  # noqa: BLE001 - any read error means the client is gone
        return
    finally:
        gone.set()


@router.websocket("/deliveries/{delivery_id}/live")
async def live_delivery(websocket: WebSocket, delivery_id: uuid.UUID, session: DbSession) -> None:
    settings = websocket.app.state.settings
    hub = websocket.app.state.tracking_hub
    await websocket.accept()

    token = await _read_auth(websocket)
    if token is None:
        return await _close(websocket, CLOSE_UNAUTHENTICATED, "Authentication required.")
    try:
        claims, delivery = await run_in_threadpool(
            _authorise, session, settings, token, delivery_id
        )
    except AppError:
        return await _close(websocket, CLOSE_UNAUTHENTICATED, "Invalid or expired access token.")
    if delivery is None:
        return await _close(websocket, CLOSE_FORBIDDEN, "You cannot follow this delivery.")

    queue = hub.subscribe(delivery_id)  # before the snapshot, so no change is missed
    gone = asyncio.Event()
    reader: asyncio.Task | None = None
    try:
        snapshot = await run_in_threadpool(tracking.tracking_payload, session, delivery)
        await run_in_threadpool(session.commit)
        await websocket.send_json({"type": "snapshot", **snapshot})
        if delivery.status not in tracking.WATCHABLE:
            return await _close(websocket, CLOSE_ENDED, "Tracking has ended.")
        reader = asyncio.create_task(_client_reader(websocket, gone))

        while not gone.is_set():
            remaining = (claims.expires_at - datetime.now(UTC)).total_seconds()
            if remaining <= 0:
                return await _close(websocket, CLOSE_UNAUTHENTICATED, "Session expired.")
            getter = asyncio.ensure_future(queue.get())
            waiter = asyncio.ensure_future(gone.wait())
            done, _ = await asyncio.wait(
                {getter, waiter},
                timeout=min(remaining, PING_SECONDS),
                return_when=asyncio.FIRST_COMPLETED,
            )
            waiter.cancel()
            if getter not in done:
                getter.cancel()
                if not gone.is_set() and remaining > PING_SECONDS:
                    await websocket.send_json({"type": "ping"})
                continue
            message = getter.result()
            if message["type"] == "status":
                # Reassignment, suspension or logout-all may have removed access.
                try:
                    _, still = await run_in_threadpool(
                        _authorise, session, settings, token, delivery_id
                    )
                except AppError:
                    return await _close(websocket, CLOSE_UNAUTHENTICATED, "Session ended.")
                if still is None:
                    return await _close(
                        websocket, CLOSE_FORBIDDEN, "You cannot follow this delivery."
                    )
            await websocket.send_json(message)
            if message["status"] not in {s.value for s in tracking.WATCHABLE}:
                return await _close(websocket, CLOSE_ENDED, "Tracking has ended.")
    except (WebSocketDisconnect, RuntimeError):
        return None
    finally:
        hub.unsubscribe(delivery_id, queue)
        if reader is not None:
            reader.cancel()
