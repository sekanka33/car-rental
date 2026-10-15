"""Database engine and session management.

Transaction policy: a request gets one Session. Service functions commit
explicitly when a unit of work succeeds; if the request raises, the session is
rolled back. Nothing is committed implicitly after the response is sent.
"""

from collections.abc import Iterator

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker
from starlette.requests import HTTPConnection


def build_engine(database_url: str, *, echo: bool = False) -> Engine:
    return create_engine(
        database_url,
        echo=echo,
        pool_pre_ping=True,  # transparently replace connections dropped by the server
        pool_size=5,
        max_overflow=10,
        connect_args={"connect_timeout": 5},
    )


def build_session_factory(engine: Engine) -> sessionmaker[Session]:
    # expire_on_commit=False lets routes serialise objects after a service commits.
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db(connection: HTTPConnection) -> Iterator[Session]:
    """FastAPI dependency (HTTP and WebSocket): yields a Session; rolls back on failure."""
    session: Session = connection.app.state.session_factory()
    try:
        yield session
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def database_is_reachable(engine: Engine) -> bool:
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
