"""BR-5.5: the booking status graph (no database)."""

import itertools

import pytest

from app.models import Booking
from app.models.enums import BookingStatus as S
from app.services.bookings import ALLOWED_TRANSITIONS, InvalidTransitionError, transition

EXPECTED = {
    (S.PENDING_PAYMENT, S.CONFIRMED),
    (S.PENDING_PAYMENT, S.EXPIRED),
    (S.PENDING_PAYMENT, S.CANCELLED),
    (S.CONFIRMED, S.DELIVERY_SCHEDULED),
    (S.CONFIRMED, S.CANCELLED),
    (S.DELIVERY_SCHEDULED, S.IN_TRANSIT),
    (S.DELIVERY_SCHEDULED, S.CANCELLED),
    (S.IN_TRANSIT, S.DELIVERED),
    (S.DELIVERED, S.ACTIVE_RENTAL),
    (S.ACTIVE_RENTAL, S.RETURN_PENDING),
    (S.RETURN_PENDING, S.COMPLETED),
}


def test_graph_matches_business_rules() -> None:
    actual = {(src, dst) for src, targets in ALLOWED_TRANSITIONS.items() for dst in targets}
    assert actual == EXPECTED
    assert set(ALLOWED_TRANSITIONS) == set(S)  # every status is covered


@pytest.mark.parametrize(("src", "dst"), list(itertools.product(S, S)))
def test_every_transition_is_allowed_or_rejected(src: S, dst: S) -> None:
    booking = Booking(status=src)
    if (src, dst) in EXPECTED:
        transition(booking, dst)
        assert booking.status == dst
    else:
        with pytest.raises(InvalidTransitionError):
            transition(booking, dst)
        assert booking.status == src


@pytest.mark.parametrize("final", [S.CANCELLED, S.EXPIRED, S.COMPLETED])
def test_final_states_are_final(final: S) -> None:
    assert ALLOWED_TRANSITIONS[final] == frozenset()
