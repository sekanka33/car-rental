"""Shared test fixtures.

Database tests run against a real PostgreSQL database given by TEST_DATABASE_URL
(environment variable or backend/.env). Its schema is DROPPED and rebuilt with
Alembic at the start of the run, so it must be a dedicated test database.
If TEST_DATABASE_URL is not set, database tests are skipped (reported by `pytest -ra`).
"""

import os
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
# Port 1 refuses connections immediately: used where a database must be unreachable.
UNREACHABLE_DATABASE_URL = "postgresql+psycopg://nobody:nothing@127.0.0.1:1/unreachable"


class _TestDatabaseSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BACKEND_DIR / ".env", extra="ignore")
    test_database_url: str | None = None


TEST_DATABASE_URL = _TestDatabaseSettings().test_database_url

if TEST_DATABASE_URL and not TEST_DATABASE_URL.rsplit("/", 1)[-1].endswith("_test"):
    raise RuntimeError("TEST_DATABASE_URL must name a database ending in '_test' (it is wiped).")

# Signing key used only by the test suite.
TEST_JWT_SECRET = "test-only-signing-key-0123456789abcdefghijklmnopqrstuvwxyz"

# app.main builds a module-level app at import time; give it required settings first.
os.environ.setdefault("DATABASE_URL", TEST_DATABASE_URL or UNREACHABLE_DATABASE_URL)
os.environ.setdefault("JWT_SECRET_KEY", TEST_JWT_SECRET)

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import Engine, create_engine, text  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.core.config import Environment, Settings  # noqa: E402
from app.main import create_app  # noqa: E402

requires_db = pytest.mark.skipif(
    TEST_DATABASE_URL is None, reason="TEST_DATABASE_URL not set (see backend/.env.example)"
)


def make_settings(**overrides: object) -> Settings:
    """Settings for tests; `_env_file=None` keeps a developer's backend/.env out of tests."""
    values: dict[str, object] = {
        "app_env": Environment.TEST,
        "database_url": TEST_DATABASE_URL or UNREACHABLE_DATABASE_URL,
        "jwt_secret_key": TEST_JWT_SECRET,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)  # type: ignore[call-arg]


def alembic_config():
    from alembic.config import Config

    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    config.attributes["database_url"] = TEST_DATABASE_URL
    config.attributes["configure_logger"] = False
    return config


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


@pytest.fixture(scope="session")
def migrated_engine() -> Iterator[Engine]:
    """Rebuild the test database schema from scratch with Alembic, once per run."""
    if TEST_DATABASE_URL is None:
        pytest.skip("TEST_DATABASE_URL not set")
    from alembic import command

    engine = create_engine(TEST_DATABASE_URL)
    with engine.begin() as connection:
        connection.execute(text("DROP SCHEMA public CASCADE"))
        connection.execute(text("CREATE SCHEMA public"))
    command.upgrade(alembic_config(), "head")
    yield engine
    engine.dispose()


@pytest.fixture
def db_session(migrated_engine: Engine) -> Iterator[Session]:
    """A session whose work is rolled back after each test (commits become savepoints)."""
    with migrated_engine.connect() as connection:
        transaction = connection.begin()
        session = Session(
            bind=connection, join_transaction_mode="create_savepoint", expire_on_commit=False
        )
        try:
            yield session
        finally:
            session.close()
            transaction.rollback()
