from collections.abc import Callable, Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import Environment, Settings
from app.main import create_app


def make_settings(**overrides: object) -> Settings:
    """Settings for tests; `_env_file=None` keeps a developer's backend/.env out of tests."""
    values: dict[str, object] = {"app_env": Environment.TEST}
    values.update(overrides)
    return Settings(_env_file=None, **values)  # type: ignore[call-arg]


@pytest.fixture
def app() -> FastAPI:
    return create_app(make_settings())


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    # raise_server_exceptions=False lets us assert on the 500 response itself.
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


@pytest.fixture
def client_for() -> Callable[..., TestClient]:
    """Build a client for an app created with custom settings."""

    def _factory(**overrides: object) -> TestClient:
        return TestClient(create_app(make_settings(**overrides)), raise_server_exceptions=False)

    return _factory
