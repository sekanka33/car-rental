import json
import logging
from datetime import UTC, datetime


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for field in ("request_id", "method", "path", "status_code", "duration_ms"):
            value = getattr(record, field, None)
            if value is not None:
                entry[field] = value
        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(entry, ensure_ascii=False)


def configure_logging(level: str) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    logging.basicConfig(level=level, handlers=[handler])
    logging.getLogger().setLevel(level)
    # The HTTP client logs every request URL at INFO, and the Google Geocoding API takes its
    # key as a query parameter, so those lines would put the key in the logs.
    logging.getLogger("httpx2").setLevel(max(logging.WARNING, logging.getLogger().level))
