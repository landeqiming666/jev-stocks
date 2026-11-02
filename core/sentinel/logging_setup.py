"""JSON Lines 结构化日志、轮转与写前脱敏。"""

from __future__ import annotations

import json
import logging
import sys
import threading
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import cast

from . import clock
from .errors import InternalError
from .security.redact import redact_obj

LOG_MAX_BYTES = 5_242_880
LOG_BACKUP_COUNT = 3

_LOG_LEVELS: dict[str, int] = {
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "warn": logging.WARNING,
    "error": logging.ERROR,
}
_configure_lock = threading.Lock()


class JsonFormatter(logging.Formatter):
    """把一条 LogRecord 序列化为单行 JSON。"""

    def format(self, record: logging.LogRecord) -> str:
        sentinel = getattr(record, "sentinel", {})
        if not isinstance(sentinel, dict):
            sentinel = {}

        extras = {
            key: value
            for key, value in cast(dict[str, object], sentinel).items()
            if key not in {"event", "request_id", "method", "duration_ms", "error_code"}
        }
        payload: dict[str, object] = {
            **extras,
            "ts": clock.to_iso(clock.now()),
            "level": record.levelname.lower(),
            "module": record.name,
            "request_id": sentinel.get("request_id"),
            "method": sentinel.get("method"),
            "duration_ms": sentinel.get("duration_ms"),
            "error_code": sentinel.get("error_code"),
            "event": sentinel.get("event", record.getMessage()),
        }
        redacted = redact_obj(payload)
        try:
            return json.dumps(
                redacted,
                ensure_ascii=False,
                separators=(",", ":"),
                default=_unserializable,
            )
        except (OverflowError, TypeError, ValueError):
            fallback = {
                "ts": payload["ts"],
                "level": payload["level"],
                "module": payload["module"],
                "request_id": None,
                "method": None,
                "duration_ms": None,
                "error_code": None,
                "event": "<unserializable>",
            }
            return json.dumps(fallback, ensure_ascii=False, separators=(",", ":"))


def _unserializable(_: object) -> str:
    return "<unserializable>"


def configure(log_dir: Path, level: str = "info") -> None:
    """配置 sentinel logger；重复调用会替换已有 handler。"""
    requested_level = level.lower()
    effective_level = _LOG_LEVELS.get(requested_level, logging.INFO)

    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            log_dir / "core.jsonl",
            maxBytes=LOG_MAX_BYTES,
            backupCount=LOG_BACKUP_COUNT,
            encoding="utf-8",
        )
    except OSError as exc:
        raise InternalError("INTERNAL", detail=str(exc)) from exc

    stream_handler = logging.StreamHandler(sys.stderr)
    formatter = JsonFormatter()
    file_handler.setFormatter(formatter)
    stream_handler.setFormatter(formatter)

    logger = logging.getLogger("sentinel")
    with _configure_lock:
        for handler in list(logger.handlers):
            logger.removeHandler(handler)
            handler.close()
        logger.addHandler(stream_handler)
        logger.addHandler(file_handler)
        logger.setLevel(effective_level)
        logger.propagate = False

    if requested_level not in _LOG_LEVELS:
        log_event(
            logger,
            logging.WARNING,
            event="config.log_level_invalid",
            requestedLevel=level,
        )


def get_logger(module: str) -> logging.Logger:
    """取得 sentinel 命名空间下的模块 logger。"""
    if module == "sentinel" or module.startswith("sentinel."):
        return logging.getLogger(module)
    return logging.getLogger(f"sentinel.{module}")


def log_event(
    logger: logging.Logger,
    level: int,
    *,
    event: str,
    request_id: str | None = None,
    method: str | None = None,
    duration_ms: int | None = None,
    error_code: str | None = None,
    **fields: object,
) -> None:
    """写入带固定字段和任意附加字段的结构化事件。"""
    sentinel: dict[str, object] = dict(fields)
    sentinel.update(
        {
            "event": event,
            "request_id": request_id,
            "method": method,
            "duration_ms": duration_ms,
            "error_code": error_code,
        }
    )
    logger.log(level, event, extra={"sentinel": sentinel})


__all__ = [
    "LOG_BACKUP_COUNT",
    "LOG_MAX_BYTES",
    "JsonFormatter",
    "configure",
    "get_logger",
    "log_event",
]
