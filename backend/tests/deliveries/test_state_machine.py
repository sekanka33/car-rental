"""BR-7: the delivery status graph (no database)."""

import itertools

import pytest

from app.models import Delivery
from app.models.enums import DeliveryStatus as D
from app.services.deliveries import (
    ALLOWED_TRANSITIONS,
    InvalidDeliveryTransitionError,
    transition,
)

EXPECTED = {
    (D.PENDING_SCHEDULE, D.SCHEDULED),
    (D.PENDING_SCHEDULE, D.FAILED),
    (D.PENDING_SCHEDULE, D.CANCELLED),
    (D.SCHEDULED, D.EN_ROUTE),
    (D.SCHEDULED, D.FAILED),
    (D.SCHEDULED, D.CANCELLED),
    (D.EN_ROUTE, D.DELIVERED),
    (D.EN_ROUTE, D.FAILED),
    (D.EN_ROUTE, D.CANCELLED),
    (D.FAILED, D.SCHEDULED),
    (D.FAILED, D.CANCELLED),
}


def test_graph_matches_business_rules() -> None:
    actual = {(src, dst) for src, targets in ALLOWED_TRANSITIONS.items() for dst in targets}
    assert actual == EXPECTED
    assert set(ALLOWED_TRANSITIONS) == set(D)


@pytest.mark.parametrize(("src", "dst"), list(itertools.product(D, D)))
def test_every_transition_is_allowed_or_rejected(src: D, dst: D) -> None:
    delivery = Delivery(status=src)
    if (src, dst) in EXPECTED:
        transition(delivery, dst)
        assert delivery.status == dst
    else:
        with pytest.raises(InvalidDeliveryTransitionError):
            transition(delivery, dst)
        assert delivery.status == src
