import json
import logging
from datetime import UTC, datetime


class JSONFormatter(logging.Formatter):
    fields = (
        "request_id",
        "duration_ms",
        "http_method",
        "route",
        "status_code",
        "user_id",
        "organization_id",
        "error_code",
    )

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        payload.update(
            {field: getattr(record, field, None) for field in self.fields if hasattr(record, field)}
        )
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, separators=(",", ":"), ensure_ascii=False)


def configure_logging() -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JSONFormatter())
    logging.basicConfig(level=logging.INFO, handlers=[handler], force=True)
