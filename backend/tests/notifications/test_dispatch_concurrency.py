"""Several workers (API processes, cron) dispatching at once never send a message twice.
Uses committed data and real parallel sessions."""

import threading
from collections.abc import Iterator

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

from app.integrations.email import InMemoryEmailSender
from app.services import notifications
from tests.conftest import make_settings, requires_db
from tests.db.factories import create_user

pytestmark = requires_db
COUNT = 40


@pytest.fixture
def queued(migrated_engine: Engine) -> Iterator[None]:
    with Session(migrated_engine) as session:
        user = create_user(session, email="busy@example.com")
        for n in range(COUNT):
            notifications.notify(
                session, user.id, "load.test", title="T", body="B", dedupe_key=f"load:{n}"
            )
        session.commit()
    yield
    with migrated_engine.begin() as connection:
        connection.execute(text("TRUNCATE notifications, notification_deliveries, users CASCADE"))


def test_parallel_workers_send_each_email_once(migrated_engine: Engine, queued) -> None:
    settings = make_settings()
    senders = [InMemoryEmailSender() for _ in range(4)]
    barrier = threading.Barrier(len(senders))

    def work(sender: InMemoryEmailSender) -> None:
        barrier.wait()
        with Session(migrated_engine) as session:
            notifications.dispatch_all(session, settings, sender, None)

    threads = [threading.Thread(target=work, args=(s,)) for s in senders]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)

    subjects = [m.subject for s in senders for m in s.outbox]
    assert len(subjects) == COUNT  # every email exactly once across all workers
    with migrated_engine.connect() as connection:
        statuses = dict(
            connection.execute(
                text(
                    "SELECT channel, count(*) FROM notification_deliveries GROUP BY channel, status"
                )
            ).all()
        )
    assert statuses == {"EMAIL": COUNT, "PUSH": COUNT}
