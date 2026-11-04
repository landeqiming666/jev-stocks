"""结构化日志、轮转配置与写前脱敏的单元测试。"""

from __future__ import annotations

import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

import pytest

from sentinel.errors import InternalError
from sentinel.logging_setup import (
    LOG_BACKUP_COUNT,
    LOG_MAX_BYTES,
    configure,
    get_logger,
    log_event,
)
from sentinel.security.redact import MASK, clear_secrets, register_secret


def test_log_line_is_single_json_object_with_required_fields(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SENTINEL_CLOCK", "2026-11-02T00:35:00Z")
    configure(tmp_path)
    logger = get_logger("test")
    log_event(logger, logging.INFO, event="scan.start", request_id="r-1")

    lines = (tmp_path / "core.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert set(payload) >= {
        "ts",
        "level",
        "module",
        "request_id",
        "method",
        "duration_ms",
        "error_code",
    }
    assert payload["ts"] == "2026-11-02T00:35:00Z"
    assert payload["error_code"] is None

    file_handlers = [
        handler for handler in logger.parent.handlers if isinstance(handler, RotatingFileHandler)
    ]
    assert len(file_handlers) == 1
    assert file_handlers[0].maxBytes == LOG_MAX_BYTES
    assert file_handlers[0].backupCount == LOG_BACKUP_COUNT

    blocker = tmp_path / "not-a-directory"
    blocker.write_text("x", encoding="utf-8")
    with pytest.raises(InternalError):
        configure(blocker / "logs")


def test_log_never_contains_registered_secret(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SENTINEL_CLOCK", "2026-11-02T00:35:00Z")
    secret = "sk-test-do-not-use-1234"
    register_secret(secret)
    try:
        configure(tmp_path)
        logger = get_logger("test")
        log_event(logger, logging.INFO, event="secret.test", note=secret)
    finally:
        clear_secrets()

    content = (tmp_path / "core.jsonl").read_text(encoding="utf-8")
    assert secret not in content
    assert MASK in content
