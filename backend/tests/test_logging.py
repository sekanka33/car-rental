import json
import logging
from datetime import datetime

from app.core.logging import JsonFormatter


def test_json_formatter_includes_request_metadata_without_query_values() -> None:
    record = logging.LogRecord(
        "app.api",
        logging.INFO,
        "main.py",
        10,
        "http_request",
        (),
        None,
    )
    record.request_id = "request-123"
    record.method = "GET"
    record.path = "/api/v1/health"
    record.status_code = 200
    record.duration_ms = 1.25

    entry = json.loads(JsonFormatter().format(record))

    assert datetime.fromisoformat(entry["timestamp"]).tzinfo is not None
    assert {key: value for key, value in entry.items() if key != "timestamp"} == {
        "level": "INFO",
        "logger": "app.api",
        "message": "http_request",
        "request_id": "request-123",
        "method": "GET",
        "path": "/api/v1/health",
        "status_code": 200,
        "duration_ms": 1.25,
    }
