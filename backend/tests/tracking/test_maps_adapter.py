"""Google Maps adapter against recorded response shapes (no network)."""

import json
import logging
from decimal import Decimal

import httpx2 as httpx

from app.core.logging import configure_logging
from app.integrations.maps import GoogleMapsProvider, LatLng

CAPE_TOWN = LatLng(Decimal("-33.924870"), Decimal("18.424055"))
SEA_POINT = LatLng(Decimal("-33.915000"), Decimal("18.390000"))


def provider(handler):
    seen: list[httpx.Request] = []

    def record(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    return GoogleMapsProvider("server-key", transport=httpx.MockTransport(record)), seen


def test_geocode_biases_to_south_africa_and_rounds() -> None:
    maps, seen = provider(
        lambda r: httpx.Response(
            200,
            json={
                "status": "OK",
                "results": [{"geometry": {"location": {"lat": -33.9248701234, "lng": 18.42405}}}],
            },
        )
    )

    found = maps.geocode("12 Long Street, Cape Town")

    assert found == LatLng(Decimal("-33.924870"), Decimal("18.424050"))
    params = seen[0].url.params
    assert (params["region"], params["key"], params["address"]) == (
        "za",
        "server-key",
        "12 Long Street, Cape Town",
    )


def test_geocode_without_results_or_on_error_is_none() -> None:
    nothing, _ = provider(lambda r: httpx.Response(200, json={"status": "ZERO_RESULTS"}))
    denied, _ = provider(lambda r: httpx.Response(200, json={"status": "REQUEST_DENIED"}))

    def boom(request):
        raise httpx.ConnectError("down")

    down, _ = provider(boom)
    assert nothing.geocode("Nowhere") is None
    assert denied.geocode("Somewhere") is None
    assert down.geocode("Somewhere") is None


def test_route_asks_only_for_duration_and_distance() -> None:
    maps, seen = provider(
        lambda r: httpx.Response(
            200, json={"routes": [{"duration": "754s", "distanceMeters": 4210}]}
        )
    )

    estimate = maps.route(SEA_POINT, CAPE_TOWN)

    assert (estimate.duration_seconds, estimate.distance_meters) == (754, 4210)
    request = seen[0]
    assert request.headers["X-Goog-FieldMask"] == "routes.duration,routes.distanceMeters"
    assert request.headers["X-Goog-Api-Key"] == "server-key"
    body = json.loads(request.content)
    assert body["travelMode"] == "DRIVE"
    assert body["origin"]["location"]["latLng"] == {"latitude": -33.915, "longitude": 18.39}


def test_route_failures_are_none() -> None:
    empty, _ = provider(lambda r: httpx.Response(200, json={}))
    error, _ = provider(
        lambda r: httpx.Response(403, json={"error": {"status": "PERMISSION_DENIED"}})
    )
    garbage, _ = provider(lambda r: httpx.Response(200, content=b"<html>"))
    assert empty.route(SEA_POINT, CAPE_TOWN) is None
    assert error.route(SEA_POINT, CAPE_TOWN) is None
    assert garbage.route(SEA_POINT, CAPE_TOWN) is None


def test_api_key_stays_out_of_the_logs(caplog) -> None:
    configure_logging("INFO")
    maps, _ = provider(lambda r: httpx.Response(200, json={"status": "ZERO_RESULTS"}))

    with caplog.at_level(logging.DEBUG):
        maps.geocode("12 Long Street, Cape Town")

    assert "server-key" not in caplog.text
