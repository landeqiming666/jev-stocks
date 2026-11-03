from __future__ import annotations

import hashlib
import unicodedata
from collections.abc import Sequence
from dataclasses import astuple, dataclass, fields
from datetime import date, datetime
from typing import cast

from sentinel.domain.classify import Relation
from sentinel.errors import InternalError
from sentinel.storage.db import SqlExecutor, WriteTx

from .base import EngineName, validate_count
from .questions import QUESTION_SET_VERSION


def norm_text(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("text must be a string")
    try:
        value.encode("utf-8")
    except UnicodeError:
        raise ValueError("text contains invalid Unicode") from None
    return unicodedata.normalize("NFC", value).replace("\r\n", "\n").replace("\r", "\n").strip()


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def thesis_content_hash(statement: str, kill_condition: str | None) -> str:
    return _hash(norm_text(statement) + "\n---\n" + norm_text(kill_condition or ""))


def passage_content_hash(text: str) -> str:
    return _hash(norm_text(text))


def decision_cache_key(
    engine: str,
    model_id: str,
    question_set_version: str,
    thesis_hash: str,
    passage_hash: str,
    *,
    thesis_id: str,
    thesis_version: int,
    passage_id: str,
) -> str:
    validate_count(thesis_version, minimum=1)
    components = (
        engine,
        model_id,
        question_set_version,
        thesis_hash,
        passage_hash,
        thesis_id,
        str(thesis_version),
        passage_id,
    )
    if any(
        not isinstance(s, str)
        or not s
        or "|" in s
        or not s.isascii()
        or not s.isprintable()
        or any(c.isspace() for c in s)
        for s in components
    ):
        raise ValueError("invalid cache identity component")
    return _hash("|".join(components))


@dataclass(frozen=True)
class DecisionRow:
    decision_id: str
    thesis_id: str
    thesis_version: int
    passage_id: str
    event_id: str
    instrument_id: str
    relation: Relation
    p_relevant: float
    p_against: float
    p_contradicts: float
    p_kill_met: float | None
    p_supports: float
    headline: float
    evidence_kind: str | None
    evidence_start: int | None
    evidence_end: int | None
    engine: EngineName
    model_id: str
    question_set_version: str
    cache_key: str
    input_tokens: int | None
    tokens_estimated: bool
    latency_ms: int | None
    content_status: str
    created_at: datetime
    seq: int = 0


# seq 来自段落；只把权威 DDL 的字段写入永久判定行。
_COLUMNS = tuple(f.name for f in fields(DecisionRow) if f.name != "seq")
_SELECT = ", ".join(_COLUMNS)


def _row(values: tuple[object, ...]) -> DecisionRow:
    return DecisionRow(**dict(zip(_COLUMNS, values, strict=True)))  # type: ignore[arg-type]


def find_decisions(executor: SqlExecutor, keys: Sequence[str]) -> dict[str, DecisionRow]:
    if not keys:
        return {}
    executor.execute(
        "SELECT "
        + _SELECT
        + " FROM decision WHERE cache_key IN ("
        + ",".join("?" for _ in keys)
        + ")",
        list(keys),
    )
    result = [_row(values) for values in executor.fetchall()]
    return {row.cache_key: row for row in result}


def insert_decision(tx: WriteTx, row: DecisionRow) -> tuple[DecisionRow, bool]:
    tx.execute(
        "INSERT INTO decision (" + _SELECT + ") VALUES (" + ",".join("?" for _ in _COLUMNS) + ") "
        "ON CONFLICT(cache_key) DO NOTHING RETURNING decision_id",
        list(astuple(row)[:-1]),
    )
    inserted = tx.fetchone() is not None
    saved = find_decisions(tx, [row.cache_key]).get(row.cache_key)
    if saved is None:
        raise InternalError(detail="decision insert did not produce a row")
    return saved, inserted


def used_today(executor: SqlExecutor, today: date) -> int:
    executor.execute(
        "SELECT COALESCE(SUM(input_tokens + estimated_tokens), 0) "
        "FROM usage_daily WHERE usage_date = ?",
        [today],
    )
    values = executor.fetchone()
    if values is None:
        raise InternalError(detail="missing usage aggregate")
    return cast(int, values[0])


def add_usage(
    tx: WriteTx,
    today: date,
    engine: EngineName,
    model_id: str,
    input_tokens: int,
    estimated_tokens: int,
    requests: int,
) -> None:
    for value in (input_tokens, estimated_tokens, requests):
        validate_count(value)
    if requests == 0:
        return
    tx.execute(
        "INSERT INTO usage_daily VALUES (?, ?, ?, ?, ?, ?) "
        "ON CONFLICT (usage_date, engine, model_id) DO UPDATE SET "
        "input_tokens = usage_daily.input_tokens + excluded.input_tokens, "
        "estimated_tokens = usage_daily.estimated_tokens + excluded.estimated_tokens, "
        "requests = usage_daily.requests + excluded.requests",
        [today, engine, model_id, input_tokens, estimated_tokens, requests],
    )


__all__ = [
    "QUESTION_SET_VERSION",
    "DecisionRow",
    "norm_text",
    "thesis_content_hash",
    "passage_content_hash",
    "decision_cache_key",
    "find_decisions",
    "insert_decision",
    "used_today",
    "add_usage",
]
