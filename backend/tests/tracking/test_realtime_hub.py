"""The in-process broadcaster: a slow watcher loses old messages but never blocks the rest."""

import uuid

from app.core.realtime import QUEUE_SIZE, TrackingHub


def test_full_queue_drops_the_oldest_message() -> None:
    hub = TrackingHub()
    delivery_id = uuid.uuid4()
    slow, other = hub.subscribe(delivery_id), hub.subscribe(delivery_id)

    for n in range(QUEUE_SIZE + 5):
        hub._fan_out(delivery_id, {"n": n})

    assert slow.qsize() == other.qsize() == QUEUE_SIZE
    assert slow.get_nowait() == {"n": 5}  # the 5 oldest were dropped


def test_unsubscribe_forgets_empty_deliveries() -> None:
    hub = TrackingHub()
    delivery_id = uuid.uuid4()
    queue = hub.subscribe(delivery_id)
    hub.unsubscribe(delivery_id, queue)

    assert hub.subscriber_count(delivery_id) == 0
    hub._fan_out(delivery_id, {"n": 1})  # nobody listening: no error
