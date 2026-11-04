"""Emit records consumed by the configured Sentinel JSON formatter."""

from __future__ import annotations

import logging


def get_logger(module: str) -> logging.Logger:
    return logging.getLogger(module)


def log_event(logger: logging.Logger, level: int, *, event: str, **fields: object) -> None:
    payload: dict[str, object] = {
        "request_id": None,
        "method": None,
        "duration_ms": None,
        "error_code": None,
        **fields,
        "event": event,
    }
    logger.log(level, event, extra={"sentinel": payload})
