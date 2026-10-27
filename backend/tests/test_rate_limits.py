import pytest

from app.core.errors import RateLimitError
from app.core.rate_limits import RateLimiter


def test_limit_is_enforced_and_retry_after_matches_window() -> None:
    now = [100.0]
    limiter = RateLimiter(clock=lambda: now[0])

    limiter.enforce("login", "192.0.2.1", 2, 60)
    limiter.enforce("login", "192.0.2.1", 2, 60)
    with pytest.raises(RateLimitError) as error:
        limiter.enforce("login", "192.0.2.1", 2, 60)

    assert error.value.status_code == 429
    assert error.value.headers == {"Retry-After": "60"}

    now[0] += 60
    limiter.enforce("login", "192.0.2.1", 2, 60)


def test_limits_are_independent_by_scope_and_client() -> None:
    limiter = RateLimiter(clock=lambda: 1.0)
    limiter.enforce("login", "192.0.2.1", 1, 60)

    limiter.enforce("marketplace", "192.0.2.1", 1, 60)
    limiter.enforce("login", "192.0.2.2", 1, 60)

    with pytest.raises(RateLimitError):
        limiter.enforce("login", "192.0.2.1", 1, 60)


def test_expired_client_entries_are_pruned_when_capacity_is_reached() -> None:
    now = [1.0]
    limiter = RateLimiter(clock=lambda: now[0], max_entries=1)
    limiter.enforce("login", "192.0.2.1", 1, 1)

    now[0] = 2.0
    limiter._checks = 127
    limiter.enforce("login", "192.0.2.2", 1, 1)

    assert len(limiter._windows) == 1
