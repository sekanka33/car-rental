"""Maps services behind one interface: geocoding the drop-off address and driving ETA.

GoogleMapsProvider uses the Geocoding API (GET /maps/api/geocode/json, region=za) and the
Routes API (POST /directions/v2:computeRoutes with an X-Goog-FieldMask, so only duration and
distance are billed). Without GOOGLE_MAPS_API_KEY no provider is built: tracking still works,
there is just no ETA. Failures never break a location update; they only leave the ETA empty.
"""

import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol

import httpx2 as httpx

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LatLng:
    latitude: Decimal
    longitude: Decimal


@dataclass(frozen=True)
class RouteEstimate:
    duration_seconds: int
    distance_meters: int


class MapsProvider(Protocol):
    def geocode(self, address: str) -> LatLng | None: ...

    def route(self, origin: LatLng, destination: LatLng) -> RouteEstimate | None: ...


class GoogleMapsProvider:
    def __init__(
        self,
        api_key: str,
        *,
        geocode_url: str = "https://maps.googleapis.com/maps/api/geocode/json",
        routes_url: str = "https://routes.googleapis.com/directions/v2:computeRoutes",
        transport=None,
        timeout: float = 5.0,
    ) -> None:
        self._key = api_key
        self._geocode_url = geocode_url
        self._routes_url = routes_url
        self._client = httpx.Client(timeout=timeout, transport=transport)

    def geocode(self, address: str) -> LatLng | None:
        try:
            response = self._client.get(
                self._geocode_url, params={"address": address, "region": "za", "key": self._key}
            )
            body = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("Geocoding failed: %s", exc.__class__.__name__)
            return None
        if body.get("status") != "OK" or not body.get("results"):
            logger.info("Geocoding found nothing (status %s)", body.get("status"))
            return None
        location = body["results"][0]["geometry"]["location"]
        return LatLng(_coord(location["lat"]), _coord(location["lng"]))

    def route(self, origin: LatLng, destination: LatLng) -> RouteEstimate | None:
        def waypoint(point: LatLng) -> dict:
            return {
                "location": {
                    "latLng": {
                        "latitude": float(point.latitude),
                        "longitude": float(point.longitude),
                    }
                }
            }

        try:
            response = self._client.post(
                self._routes_url,
                json={
                    "origin": waypoint(origin),
                    "destination": waypoint(destination),
                    "travelMode": "DRIVE",
                    "routingPreference": "TRAFFIC_AWARE",
                },
                headers={
                    "X-Goog-Api-Key": self._key,
                    "X-Goog-FieldMask": "routes.duration,routes.distanceMeters",
                },
            )
            body = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("Routes request failed: %s", exc.__class__.__name__)
            return None
        routes = body.get("routes") if response.status_code == 200 else None
        if not routes:
            logger.info("Routes returned no route (HTTP %s)", response.status_code)
            return None
        duration = str(routes[0].get("duration", "")).removesuffix("s")  # e.g. "754s"
        try:
            return RouteEstimate(int(float(duration)), int(routes[0].get("distanceMeters", 0)))
        except ValueError:
            return None


def _coord(value: float) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.000001"))


def build_maps_provider(settings) -> MapsProvider | None:
    if settings.google_maps_api_key is None:
        return None
    return GoogleMapsProvider(settings.google_maps_api_key.get_secret_value())
