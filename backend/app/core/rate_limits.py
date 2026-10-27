"""Small per-process sliding-window limits for public and costly API operations."""

import math
import threading
import time
from collections import deque
from collections.abc import Callable

from fastapi import Request

from app.api.deps import AppSettings
from app.core.errors import RateLimitError


class RateLimiter:
    """Thread-safe in-memory limits; the API currently requires a single process."""

    def __init__(
        self,
        *,
        clock: Callable[[], float] = time.monotonic,
        max_entries: int = 10_000,
    ) -> None:
        self._clock = clock
        self._max_entries = max_entries
        self._windows: dict[tuple[str, str], tuple[int, deque[float]]] = {}
        self._lock = threading.Lock()
        self._checks = 0

    def enforce(self, scope: str, identity: str, limit: int, window_seconds: int) -> None:
        now = self._clock()
        key = (scope, identity)
        with self._lock:
            self._checks += 1
            current = self._windows.get(key)
            if current is None:
                self._prune(now)
                if len(self._windows) >= self._max_entries:
                    raise RateLimitError(1)
                hits: deque[float] = deque()
                self._windows[key] = (window_seconds, hits)
            else:
                _, hits = current

            cutoff = now - window_seconds
            while hits and hits[0] <= cutoff:
                hits.popleft()
            if len(hits) >= limit:
                retry_after = max(1, math.ceil(window_seconds - (now - hits[0])))
                raise RateLimitError(retry_after)
            hits.append(now)
            self._windows[key] = (window_seconds, hits)

    def _prune(self, now: float) -> None:
        if self._checks % 128:
            return
        expired = [
            key
            for key, (window, hits) in self._windows.items()
            if not hits or hits[-1] <= now - window
        ]
        for key in expired:
            del self._windows[key]


def enforce_request_limit(
    request: Request,
    scope: str,
    limit: int,
    window_seconds: int,
    identity: str | None = None,
) -> None:
    client = request.client
    identity = identity or (client.host if client is not None else "unknown")
    limiter: RateLimiter = request.app.state.rate_limiter
    limiter.enforce(scope, identity, limit, window_seconds)


def enforce_marketplace_limit(request: Request, settings: AppSettings) -> None:
    enforce_request_limit(
        request,
        "marketplace",
        settings.marketplace_requests_per_minute,
        60,
    )
