"""Migrations apply cleanly, reverse cleanly, and match the SQLAlchemy models."""

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import Engine, inspect, text

from app.db.base import Base
from tests.conftest import alembic_config, requires_db

CORE_TABLES = {
    "users",
    "roles",
    "user_roles",
    "owner_profiles",
    "customer_profiles",
    "vehicles",
    "vehicle_images",
    "vehicle_prices",
    "bookings",
    "payments",
    "deliveries",
    "audit_logs",
}

pytestmark = requires_db


def _tables(engine: Engine) -> set[str]:
    return set(inspect(engine).get_table_names()) - {"alembic_version"}


def test_upgrade_creates_all_core_tables(migrated_engine: Engine) -> None:
    assert _tables(migrated_engine) == CORE_TABLES


def test_models_match_migrations(migrated_engine: Engine) -> None:
    with migrated_engine.connect() as connection:
        context = MigrationContext.configure(
            connection, opts={"compare_type": True, "compare_server_default": True}
        )
        differences = compare_metadata(context, Base.metadata)

    assert differences == []


def test_downgrade_to_base_and_upgrade_again(migrated_engine: Engine) -> None:
    config = alembic_config()

    command.downgrade(config, "base")
    assert _tables(migrated_engine) == set()
    with migrated_engine.connect() as connection:
        leftover = connection.scalar(
            text("SELECT count(*) FROM pg_proc WHERE proname = 'audit_logs_block_modification'")
        )
    assert leftover == 0

    command.upgrade(config, "head")
    assert _tables(migrated_engine) == CORE_TABLES


def test_roles_are_seeded(migrated_engine: Engine) -> None:
    with migrated_engine.connect() as connection:
        names = connection.scalars(text("SELECT name FROM roles ORDER BY id")).all()

    assert names == ["ADMIN", "OWNER", "RENTER"]
