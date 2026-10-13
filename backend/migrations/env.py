"""Alembic environment.

The database URL comes from (in order):
1. `config.attributes["database_url"]` — set programmatically (used by the test suite);
2. the application settings (DATABASE_URL in the environment or backend/.env).
"""

from logging.config import fileConfig

import sqlalchemy as sa
from alembic import context
from sqlalchemy import create_engine, pool
from sqlalchemy.sql.naming import conv

import app.models  # noqa: F401  (registers every table on Base.metadata)
from app.core.config import Settings
from app.db.base import Base

config = context.config

if config.config_file_name is not None and config.attributes.get("configure_logger", True):
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def get_url() -> str:
    url = config.attributes.get("database_url")
    if url:
        return url
    return Settings().database_url.get_secret_value()  # type: ignore[call-arg]


def render_item(type_: str, obj: object, autogen_context) -> str | bool | None:
    """Emit exactly one CHECK constraint per VARCHAR-backed enum column.

    Alembic rebuilds each table before rendering, which copies Enum types and their
    type-bound CHECK. With SQLAlchemy 2.1 Alembic no longer recognises that copy, so
    the same constraint would be rendered twice and CREATE TABLE would fail. We keep
    the convention-named original (`ck_<table>_<enum>`), drop the copy, and render the
    column type without its own constraint.
    """
    if type_ == "type" and isinstance(obj, sa.Enum) and not obj.native_enum:
        values = ", ".join(repr(value) for value in obj.enums)
        return (
            f"sa.Enum({values}, name={obj.name!r}, native_enum=False, "
            f"length={obj.length}, create_constraint=False)"
        )
    if (
        type_ == "check"
        and isinstance(obj, sa.CheckConstraint)
        and obj._type_bound
        and not isinstance(obj.name, conv)
    ):
        return None  # duplicate copy of a type-bound CHECK; skip it
    return False


def run_migrations_offline() -> None:
    """Emit SQL to stdout instead of executing it (`alembic upgrade head --sql`)."""
    context.configure(
        url=get_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        render_item=render_item,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = create_engine(get_url(), poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
            render_item=render_item,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
