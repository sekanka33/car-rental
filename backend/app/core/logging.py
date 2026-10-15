import logging


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    # The HTTP client logs every request URL at INFO, and the Google Geocoding API takes its
    # key as a query parameter, so those lines would put the key in the logs.
    logging.getLogger("httpx2").setLevel(max(logging.WARNING, logging.getLogger().level))
