import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.demo_data import DEMO_VEHICLES, DemoDataRefusedError, placeholder_png, seed_demo_data
from app.integrations.storage import InMemoryDocumentStorage
from app.models import AuditLog, User
from app.services.marketplace import SearchFilters, search
from app.services.uploads import detect_content_type
from tests.conftest import make_settings, requires_db


@pytest.mark.parametrize("env", ["test", "staging"])
def test_demo_data_refused_outside_development(env: str) -> None:
    with pytest.raises(DemoDataRefusedError):
        seed_demo_data(None, make_settings(app_env=env), InMemoryDocumentStorage())  # type: ignore[arg-type]


def test_placeholder_photo_is_a_real_png() -> None:
    assert detect_content_type(placeholder_png((10, 20, 30))) == "image/png"


@requires_db
def test_demo_data_is_listed_marked_and_idempotent(db_session: Session) -> None:
    storage = InMemoryDocumentStorage()
    settings = make_settings(app_env="development")

    assert seed_demo_data(db_session, settings, storage) == len(DEMO_VEHICLES)
    assert seed_demo_data(db_session, settings, storage) == 0

    rows, total = search(db_session, SearchFilters(), limit=50, offset=0)
    assert total == len(DEMO_VEHICLES)
    assert all(v.description.startswith("DEMO LISTING") for v, _ in rows)
    emails = db_session.scalars(select(User.email).where(User.email.like("demo-%"))).all()
    assert len(emails) == len(DEMO_VEHICLES) + 1 and all(e.endswith("@example.com") for e in emails)
    assert db_session.scalars(
        select(AuditLog.action).where(AuditLog.action == "vehicle.price_set")
    ).all()
