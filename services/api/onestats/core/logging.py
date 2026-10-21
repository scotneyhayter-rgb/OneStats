"""Structured logging — safe by default (no credentials or sensitive data).

A minimal JSON formatter (stdlib only) keeps logs structured without extra dependencies.
Callers must never log secrets or personal data; the DB password is never passed to a
logger, and connection errors are logged without the connection string.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime

_SENSITIVE_KEYS = {"password", "db_password", "secret", "token", "authorization"}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        for key, value in getattr(record, "extra_fields", {}).items():
            if key.lower() not in _SENSITIVE_KEYS:
                payload[key] = value
        return json.dumps(payload, default=str)


def configure_logging(level: str = "INFO", json_output: bool = False) -> None:
    handler = logging.StreamHandler(sys.stdout)
    if json_output:
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s")
        )
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level.upper())


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
