"""Atomic ticker replacement and offline ranked search over DuckDB."""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import duckdb

from sentinel.clock import parse_iso, to_iso
from sentinel.errors import InternalError, SourceError, UserError
from sentinel.logging_setup import get_logger, log_event
from sentinel.storage import Database

from .models import ImportStats, Instrument, SearchHit, TickerRow
from .normalize import DEFAULT_LIMIT, norm_query, normalize_symbol, validate_search
from .source import EXCHANGE_MAP

_REFRESH_KEY = "lastTickerRefreshAt"
_COLUMNS = "instrument_id, market, symbol, exchange, name, name_zh, currency, cik, is_active"
_UPSERT = """
INSERT INTO instrument VALUES (?, 'us', ?, ?, ?, ?, 'USD', ?, TRUE, 'sec_company_tickers', ?)
ON CONFLICT (market, symbol) DO UPDATE SET
  exchange=excluded.exchange, name=excluded.name, name_zh=excluded.name_zh,
  currency=excluded.currency, cik=excluded.cik, is_active=excluded.is_active,
  source=excluded.source, updated_at=excluded.updated_at
"""
_SEARCH = """
WITH ranked AS (
  SELECT a.instrument_id, max(CASE
    WHEN a.alias = ? THEN CASE WHEN a.kind = 'symbol' THEN 120 ELSE 100 END
    WHEN starts_with(a.alias, ?) THEN CASE WHEN a.kind = 'symbol' THEN 80 ELSE 60 END
    ELSE 30 END) AS score
  FROM instrument_alias a JOIN instrument i USING (instrument_id)
  WHERE i.is_active AND contains(a.alias, ?)
  GROUP BY a.instrument_id
)
SELECT i.instrument_id, i.market, i.symbol, i.exchange, i.name, i.name_zh,
       i.currency, i.cik, i.is_active, r.score
FROM ranked r JOIN instrument i USING (instrument_id)
ORDER BY r.score DESC, i.symbol ASC LIMIT ?
"""


@dataclass(frozen=True)
class _AliasEntry:
    name_zh: str
    aliases: tuple[str, ...]


@contextmanager
def _database_errors() -> Iterator[None]:
    try:
        yield
    except duckdb.Error as exc:
        raise InternalError(detail="instrument database operation failed") from exc


def _utc(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise InternalError(detail="instrument timestamp requires an aware datetime")
    return value.astimezone(UTC)


def _cik(raw: object) -> str | None:
    if type(raw) is int:
        return f"{raw:010d}" if 1 <= raw <= 9999999999 else None
    if isinstance(raw, str) and re.fullmatch(r"[0-9]{1,10}", raw) and int(raw) > 0:
        return raw.zfill(10)
    return None


def _instrument(row: tuple[object, ...]) -> Instrument:
    return Instrument(*cast(tuple[str, str, str, str, str, str | None, str, str | None, bool], row))


class InstrumentRepository:
    def __init__(
        self,
        db: Database,
        *,
        resource_dir: Path | None = None,
        alias_path: Path | None = None,
    ) -> None:
        self._db = db
        if resource_dir is not None and alias_path is not None:
            raise InternalError(detail="choose resource_dir or alias_path")
        directory = (
            resource_dir
            if resource_dir is not None
            else Path(__file__).resolve().parents[4] / "resources"
        )
        self._alias_path = (
            alias_path if alias_path is not None else directory / "aliases" / "us_zh.json"
        )
        self._logger = get_logger(__name__)
        self._load_aliases()

    def _load_aliases(self) -> dict[str, _AliasEntry]:
        try:
            payload = json.loads(self._alias_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, ValueError, RecursionError) as exc:
            raise InternalError(detail="instrument aliases are unreadable or malformed") from exc
        if not isinstance(payload, list):
            raise InternalError(detail="instrument aliases require an array")
        result: dict[str, _AliasEntry] = {}
        for entry in payload:
            if not isinstance(entry, dict) or set(entry) != {"symbol", "name_zh", "aliases"}:
                raise InternalError(detail="invalid instrument alias entry")
            symbol = normalize_symbol(entry["symbol"])
            name_zh, aliases = entry["name_zh"], entry["aliases"]
            if (
                symbol is None
                or symbol in result
                or not isinstance(name_zh, str)
                or not norm_query(name_zh)
                or not isinstance(aliases, list)
                or any(not isinstance(alias, str) or not norm_query(alias) for alias in aliases)
            ):
                raise InternalError(detail="invalid or duplicate instrument alias entry")
            result[symbol] = _AliasEntry(name_zh, tuple(aliases))
        return result

    def replace_from_sec(
        self,
        rows: Sequence[TickerRow],
        *,
        fetched_at: datetime,
        require_nonempty: bool = False,
    ) -> ImportStats:
        """An explicit empty batch deactivates US tickers and advances the watermark."""
        if type(require_nonempty) is not bool:
            raise UserError("INVALID_ARGUMENT", field="require_nonempty")
        fetched_at = _utc(fetched_at)
        aliases = self._load_aliases()
        selected: dict[str, tuple[TickerRow, str]] = {}
        skipped_exchange = skipped_symbol = duplicates = 0
        for row in rows:
            if not isinstance(row.exchange, str) or row.exchange not in EXCHANGE_MAP:
                skipped_exchange += 1
                continue
            symbol, cik = normalize_symbol(row.ticker), _cik(row.cik)
            if symbol is None or cik is None:
                skipped_symbol += 1
                continue
            if symbol in selected:
                duplicates += 1
                if cik >= selected[symbol][1]:
                    continue
            selected[symbol] = (row, cik)
        if require_nonempty and not selected:
            raise SourceError("SOURCE_UNAVAILABLE", reason="TICKER_SCHEMA")
        records: list[list[object]] = []
        alias_rows: list[list[object]] = []
        for symbol, (row, cik) in selected.items():
            instrument_id = "us:" + symbol
            chinese = aliases.get(symbol)
            records.append(
                [
                    instrument_id,
                    symbol,
                    EXCHANGE_MAP[row.exchange],
                    row.name,
                    chinese.name_zh if chinese else None,
                    cik,
                    fetched_at,
                ]
            )
            candidates = [(symbol, "symbol")]
            if chinese:
                candidates.append((chinese.name_zh, "name_zh"))
            if isinstance(row.name, str):
                candidates.append((row.name, "name_en"))
            if chinese:
                candidates.extend((alias, "alias") for alias in chinese.aliases)
            seen: set[str] = set()
            for text, kind in candidates:
                alias = norm_query(text)
                if alias and alias not in seen:
                    seen.add(alias)
                    alias_rows.append([instrument_id, alias, kind])
        with _database_errors(), self._db.write() as tx:
            tx.execute(
                "SELECT count(*) FROM instrument WHERE market = 'us' AND is_active "
                "AND symbol NOT IN (SELECT unnest(?))",
                [list(selected)],
            )
            count_row = tx.fetchone()
            assert count_row is not None
            deactivated = cast(int, count_row[0])
            tx.execute(
                "UPDATE instrument SET is_active = FALSE, updated_at = ? "
                "WHERE market = 'us' AND is_active AND symbol NOT IN (SELECT unnest(?))",
                [fetched_at, list(selected)],
            )
            tx.execute(
                "DELETE FROM instrument_alias WHERE instrument_id IN (SELECT unnest(?))",
                [["us:" + symbol for symbol in selected]],
            )
            if records:
                tx.executemany(_UPSERT, records)
            if alias_rows:
                tx.executemany("INSERT INTO instrument_alias VALUES (?, ?, ?)", alias_rows)
            tx.execute(
                "INSERT INTO setting VALUES (?, ?, ?) ON CONFLICT (key) DO UPDATE SET "
                "value_json=excluded.value_json, updated_at=excluded.updated_at",
                [_REFRESH_KEY, json.dumps(to_iso(fetched_at)), fetched_at],
            )
        if duplicates:
            log_event(
                self._logger, logging.WARNING, event="instruments.duplicates", count=duplicates
            )
        return ImportStats(
            len(rows), len(selected), skipped_exchange, skipped_symbol, duplicates, deactivated
        )

    def search(self, query: str, *, limit: int = DEFAULT_LIMIT) -> list[SearchHit]:
        normalized = validate_search(query, limit)
        with _database_errors(), self._db.read() as reader:
            reader.execute(_SEARCH, [normalized, normalized, normalized, limit])
            return [SearchHit(_instrument(row[:9]), cast(int, row[9])) for row in reader.fetchall()]

    def get(self, instrument_id: str) -> Instrument | None:
        with _database_errors(), self._db.read() as reader:
            reader.execute(
                f"SELECT {_COLUMNS} FROM instrument WHERE instrument_id = ?", [instrument_id]
            )
            row = reader.fetchone()
            return None if row is None else _instrument(row)

    def is_empty(self) -> bool:
        with _database_errors(), self._db.read() as reader:
            reader.execute("SELECT count(*) FROM instrument WHERE market = 'us'")
            return reader.fetchone() == (0,)

    def last_refresh_at(self) -> datetime | None:
        with _database_errors(), self._db.read() as reader:
            reader.execute("SELECT value_json FROM setting WHERE key = ?", [_REFRESH_KEY])
            row = reader.fetchone()
        if row is None:
            return None
        try:
            value = json.loads(cast(str, row[0]))
            if value is None:
                return None
            if not isinstance(value, str):
                raise ValueError("invalid refresh timestamp")
            return parse_iso(value)
        except (ValueError, TypeError, RecursionError) as exc:
            raise InternalError(detail="invalid instrument refresh watermark") from exc
