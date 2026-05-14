import logging
import sys
from typing import Any, Dict


class JsonFormatter(logging.Formatter):
    """Optional JSON formatter for structured logging."""

    def format(self, record: logging.LogRecord) -> str:
        import json

        log_obj: Dict[str, Any] = {
            "timestamp": self.formatTime(record),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if hasattr(record, "props") and isinstance(record.props, dict):
            log_obj.update(record.props)
        if record.exc_info:
            log_obj["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_obj, default=str)


class SimpleFormatter(logging.Formatter):
    """Plain-text formatter with level, logger name, and message."""

    def format(self, record: logging.LogRecord) -> str:
        level = record.levelname
        name = record.name
        msg = record.getMessage()
        if record.exc_info:
            exc = self.formatException(record.exc_info)
            return f"[{level}] {name}: {msg}\n{exc}"
        return f"[{level}] {name}: {msg}"


def configure_logging(
    level: int = logging.INFO, json_format: bool = False
) -> None:
    root = logging.getLogger()
    root.setLevel(level)

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)

    if json_format:
        formatter = JsonFormatter()
    else:
        formatter = SimpleFormatter()
    handler.setFormatter(formatter)

    if root.handlers:
        root.handlers.clear()
    root.addHandler(handler)

    # Override uvicorn handlers to use the same simple format
    for uvicorn_logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uvicorn_logger = logging.getLogger(uvicorn_logger_name)
        uvicorn_logger.handlers.clear()
        uvicorn_logger.addHandler(handler)
        uvicorn_logger.propagate = False

    # Reduce noise from third-party libraries
    logging.getLogger("pymongo").setLevel(logging.WARNING)
