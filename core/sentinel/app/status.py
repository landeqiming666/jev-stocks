"""今日页的数据状态快照：来源、引擎与离线标记。"""

from __future__ import annotations

from datetime import datetime
from typing import cast

from sentinel import clock
from sentinel.scan.pending import SourceStatus, StatusSnapshot
from sentinel.storage.db import SqlExecutor

from .engines import MODEL_ID, EngineRuntime

SOURCE_FAILURES = frozenset({"SOURCE_UNAVAILABLE", "TIMEOUT", "RATE_LIMITED"})


class RuntimeStatus:
    """只读查询最近一次扫描与当前引擎；不触发任何网络请求。"""

    def __init__(self, *, engine: EngineRuntime, offline: bool) -> None:
        self._engine, self._offline = engine, offline

    def _source(self, reader: SqlExecutor) -> SourceStatus:
        reader.execute(
            "SELECT status, error_code, finished_at FROM scan_run "
            "ORDER BY created_at DESC, rowid DESC LIMIT 1"
        )
        row = reader.fetchone()
        if row is None:
            return SourceStatus(name="sec", state="ok", last_success_at=None, message=None)
        status, code, finished = cast(str, row[0]), cast(str | None, row[1]), row[2]
        finished_at = clock.to_iso(cast(datetime, finished)) if finished is not None else None
        if status == "failed" and code in SOURCE_FAILURES:
            return SourceStatus(
                name="sec", state="degraded", last_success_at=None, message="scan.source_degraded"
            )
        if status in ("succeeded", "partial"):
            return SourceStatus(name="sec", state="ok", last_success_at=finished_at, message=None)
        return SourceStatus(name="sec", state="ok", last_success_at=None, message=None)

    def __call__(self, reader: SqlExecutor, as_of: datetime) -> StatusSnapshot:
        active, state = self._engine.health()
        return StatusSnapshot.model_validate(
            {
                "source": self._source(reader).model_dump(),
                "engine": {
                    "active": active,
                    "model_id": MODEL_ID,
                    "state": state,
                },
                "offline": self._offline,
            }
        )


__all__ = ["RuntimeStatus"]
