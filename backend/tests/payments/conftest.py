import pytest

from tests.api_fixtures import *  # noqa: F403  (shared API fixtures)
from tests.payments.fake_provider import FakePaymentProvider


@pytest.fixture
def payment_provider() -> FakePaymentProvider:
    return FakePaymentProvider()
