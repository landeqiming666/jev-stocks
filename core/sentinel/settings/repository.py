from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from datetime import datetime
from typing import cast

from sentinel.errors import InternalError
from sentinel.logging_setup import get_logger, log_event
from sentinel.storage import Database


class SettingsRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    def raw(self) -> dict[str, object]:
        with self._db.read() as reader:
            reader.execute("SELECT key, value_json FROM setting ORDER BY key")
            rows = reader.fetchall()
        values: dict[str, object] = {}
        for key, text in rows:
            name = cast(str, key)
            try:
                values[name] = json.loads(cast(str, text), parse_constant=_invalid_constant)
            except (ValueError, RecursionError):
                log_event(
                    get_logger(__name__),
                    logging.ERROR,
                    event="settings.data_corrupt",
                    error_code="INTERNAL",
                )
                raise InternalError(detail=f"setting:{name}") from None
        return values

    def write_patch(self, values: Mapping[str, object], now: datetime) -> None:
        if not values:
            return
        try:
            rows = [
                (
                    key,
                    json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False),
                    now,
                )
                for key, value in values.items()
            ]
            with self._db.write() as tx:
                for row in rows:
                    tx.execute("SELECT value_json FROM setting WHERE key=?", [row[0]])
                    existing = tx.fetchone()
                    if (
                        existing is not None
                        and json.loads(cast(str, existing[0]), parse_constant=_invalid_constant)
                        == values[row[0]]
                    ):
                        continue
                    tx.execute(
                        "INSERT INTO setting VALUES (?, ?, ?) ON CONFLICT (key) "
                        "DO UPDATE SET value_json=excluded.value_json, "
                        "updated_at=excluded.updated_at",
                        row,
                    )
        except Exception:
            log_event(
                get_logger(__name__),
                logging.ERROR,
                event="settings.write_failed",
                error_code="INTERNAL",
            )
            raise InternalError(detail="setting:write") from None


def _invalid_constant(value: str) -> object:
    raise ValueError("invalid JSON constant")
