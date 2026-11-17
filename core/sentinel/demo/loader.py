"""Fixture parsing, ordered inserts and registry-driven deletes for demo data."""

from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, cast

from sentinel.errors import InternalError
from sentinel.storage.db import SqlExecutor

DEMO_VERSION = "1"
EXPECTED_COUNTS = {
    "instruments": 6,
    "holdings": 5,
    "theses": 6,
    "events": 6,
    "decisions": 12,
    "prices": 1560,
}
REGISTRY = "demo_row"

# (table, columns, primary-key columns, camelCase payload keys)
SCHEMA: tuple[tuple[str, tuple[str, ...], tuple[str, ...], tuple[str, ...]], ...] = (
    (
        "instrument",
        (
            "instrument_id",
            "market",
            "symbol",
            "exchange",
            "name",
            "name_zh",
            "currency",
            "cik",
            "is_active",
            "source",
            "updated_at",
        ),
        ("instrument_id",),
        (
            "instrumentId",
            "market",
            "symbol",
            "exchange",
            "name",
            "nameZh",
            "currency",
            "cik",
            "isActive",
            "source",
            "updatedAt",
        ),
    ),
    (
        "instrument_alias",
        ("instrument_id", "alias", "kind"),
        ("instrument_id", "alias"),
        ("instrumentId", "alias", "kind"),
    ),
    (
        "holding",
        (
            "holding_id",
            "instrument_id",
            "quantity",
            "avg_cost",
            "note",
            "created_at",
            "updated_at",
            "archived_at",
        ),
        ("holding_id",),
        (
            "holdingId",
            "instrumentId",
            "quantity",
            "avgCost",
            "note",
            "createdAt",
            "updatedAt",
            "archivedAt",
        ),
    ),
    (
        "thesis",
        (
            "thesis_id",
            "instrument_id",
            "status",
            "current_version",
            "created_at",
            "updated_at",
            "archived_at",
        ),
        ("thesis_id",),
        (
            "thesisId",
            "instrumentId",
            "status",
            "currentVersion",
            "createdAt",
            "updatedAt",
            "archivedAt",
        ),
    ),
    (
        "thesis_version",
        ("thesis_id", "version", "statement", "kill_condition", "content_hash", "created_at"),
        ("thesis_id", "version"),
        ("thesisId", "version", "statement", "killCondition", "contentHash", "createdAt"),
    ),
    (
        "event_doc",
        (
            "event_id",
            "instrument_id",
            "market",
            "form_type",
            "title",
            "published_at",
            "filing_date",
            "url",
            "items",
            "content_status",
            "fetched_at",
            "source",
        ),
        ("event_id",),
        (
            "eventId",
            "instrumentId",
            "market",
            "formType",
            "title",
            "publishedAt",
            "filingDate",
            "url",
            "items",
            "contentStatus",
            "fetchedAt",
            "source",
        ),
    ),
    (
        "event_file",
        ("event_id", "seq", "file_name", "doc_type", "url", "text_status", "text", "char_count"),
        ("event_id", "seq"),
        ("eventId", "seq", "fileName", "docType", "url", "textStatus", "text", "charCount"),
    ),
    (
        "event_passage",
        (
            "passage_id",
            "event_id",
            "file_seq",
            "seq",
            "text",
            "start_offset",
            "end_offset",
            "content_hash",
        ),
        ("passage_id",),
        (
            "passageId",
            "eventId",
            "fileSeq",
            "seq",
            "text",
            "startOffset",
            "endOffset",
            "contentHash",
        ),
    ),
    (
        "decision",
        (
            "decision_id",
            "thesis_id",
            "thesis_version",
            "passage_id",
            "event_id",
            "instrument_id",
            "relation",
            "p_relevant",
            "p_against",
            "p_contradicts",
            "p_kill_met",
            "p_supports",
            "headline",
            "evidence_kind",
            "evidence_start",
            "evidence_end",
            "engine",
            "model_id",
            "question_set_version",
            "cache_key",
            "input_tokens",
            "tokens_estimated",
            "latency_ms",
            "content_status",
            "created_at",
        ),
        ("decision_id",),
        (
            "decisionId",
            "thesisId",
            "thesisVersion",
            "passageId",
            "eventId",
            "instrumentId",
            "relation",
            "pRelevant",
            "pAgainst",
            "pContradicts",
            "pKillMet",
            "pSupports",
            "headline",
            "evidenceKind",
            "evidenceStart",
            "evidenceEnd",
            "engine",
            "modelId",
            "questionSetVersion",
            "cacheKey",
            "inputTokens",
            "tokensEstimated",
            "latencyMs",
            "contentStatus",
            "createdAt",
        ),
    ),
    (
        "thesis_action",
        ("action_id", "decision_id", "action", "note", "created_at"),
        ("action_id",),
        ("actionId", "decisionId", "action", "note", "createdAt"),
    ),
    (
        "scan_run",
        (
            "run_id",
            "trigger",
            "market",
            "status",
            "window_start",
            "window_end",
            "engine",
            "model_id",
            "question_set_version",
            "instruments",
            "skipped_no_thesis",
            "filings",
            "passages",
            "decisions",
            "cached_decisions",
            "requests",
            "input_tokens",
            "est_cost_usd",
            "duration_ms",
            "error_code",
            "error_message",
            "started_at",
            "finished_at",
            "created_at",
        ),
        ("run_id",),
        (
            "runId",
            "trigger",
            "market",
            "status",
            "windowStart",
            "windowEnd",
            "engine",
            "modelId",
            "questionSetVersion",
            "instruments",
            "skippedNoThesis",
            "filings",
            "passages",
            "decisions",
            "cachedDecisions",
            "requests",
            "inputTokens",
            "estCostUsd",
            "durationMs",
            "errorCode",
            "errorMessage",
            "startedAt",
            "finishedAt",
            "createdAt",
        ),
    ),
    (
        "scan_batch",
        (
            "batch_id",
            "run_id",
            "instrument_id",
            "event_id",
            "status",
            "attempts",
            "passages",
            "decisions",
            "input_tokens",
            "error_code",
            "error_message",
            "started_at",
            "finished_at",
        ),
        ("batch_id",),
        (
            "batchId",
            "runId",
            "instrumentId",
            "eventId",
            "status",
            "attempts",
            "passages",
            "decisions",
            "inputTokens",
            "errorCode",
            "errorMessage",
            "startedAt",
            "finishedAt",
        ),
    ),
    (
        "price_daily",
        (
            "instrument_id",
            "trade_date",
            "open",
            "high",
            "low",
            "close",
            "adj_close",
            "volume",
            "source",
            "fetched_at",
        ),
        ("instrument_id", "trade_date"),
        (
            "instrumentId",
            "tradeDate",
            "open",
            "high",
            "low",
            "close",
            "adjClose",
            "volume",
            "source",
            "fetchedAt",
        ),
    ),
    (
        "paper_account",
        (
            "account_id",
            "name",
            "base_currency",
            "initial_cash",
            "start_date",
            "clock_date",
            "is_demo",
            "created_at",
            "archived_at",
        ),
        ("account_id",),
        (
            "accountId",
            "name",
            "baseCurrency",
            "initialCash",
            "startDate",
            "clockDate",
            "isDemo",
            "createdAt",
            "archivedAt",
        ),
    ),
    (
        "cash_ledger",
        ("entry_id", "account_id", "entry_date", "entry_type", "amount", "ref_id", "created_at"),
        ("entry_id",),
        ("entryId", "accountId", "entryDate", "entryType", "amount", "refId", "createdAt"),
    ),
    (
        "paper_order",
        (
            "order_id",
            "account_id",
            "instrument_id",
            "side",
            "quantity",
            "order_type",
            "status",
            "reject_code",
            "reject_message",
            "created_clock_date",
            "estimate_price",
            "reserved_cash",
            "idempotency_key",
            "request_hash",
            "created_at",
            "updated_at",
        ),
        ("order_id",),
        (
            "orderId",
            "accountId",
            "instrumentId",
            "side",
            "quantity",
            "orderType",
            "status",
            "rejectCode",
            "rejectMessage",
            "createdClockDate",
            "estimatePrice",
            "reservedCash",
            "idempotencyKey",
            "requestHash",
            "createdAt",
            "updatedAt",
        ),
    ),
    (
        "fill",
        (
            "fill_id",
            "order_id",
            "filled_on",
            "price",
            "quantity",
            "amount",
            "fee",
            "slippage_bps",
            "created_at",
        ),
        ("fill_id",),
        (
            "fillId",
            "orderId",
            "filledOn",
            "price",
            "quantity",
            "amount",
            "fee",
            "slippageBps",
            "createdAt",
        ),
    ),
    (
        "position",
        ("account_id", "instrument_id", "quantity", "avg_cost", "updated_at"),
        ("account_id", "instrument_id"),
        ("accountId", "instrumentId", "quantity", "avgCost", "updatedAt"),
    ),
    (
        "equity_snapshot",
        ("account_id", "snapshot_date", "cash", "positions_value", "equity"),
        ("account_id", "snapshot_date"),
        ("accountId", "snapshotDate", "cash", "positionsValue", "equity"),
    ),
    (
        "risk_run",
        (
            "run_id",
            "computed_at",
            "scope",
            "window_label",
            "currency",
            "observations",
            "instrument_ids",
            "params_json",
            "result_json",
        ),
        ("run_id",),
        (
            "runId",
            "computedAt",
            "scope",
            "windowLabel",
            "currency",
            "observations",
            "instrumentIds",
            "paramsJson",
            "resultJson",
        ),
    ),
)
SCHEMA_BY_TABLE = {entry[0]: entry for entry in SCHEMA}
DELETE_ORDER = tuple(reversed([entry[0] for entry in SCHEMA])) + ("setting",)


@dataclass(frozen=True)
class DemoData:
    manifest: dict[str, Any]
    instruments: dict[str, Any]
    portfolio: dict[str, Any]
    filings: dict[str, Any]
    paper: dict[str, Any]
    scan: dict[str, Any]
    risk: dict[str, Any]
    prices: tuple[dict[str, Any], ...]


def pk_json(values: dict[str, Any]) -> str:
    return json.dumps(values, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_resources(resources: Path) -> DemoData:
    try:
        manifest = json.loads((resources / "manifest.json").read_text(encoding="utf-8"))
        payloads = {
            name: json.loads((resources / name).read_text(encoding="utf-8"))
            for name in (
                "instruments.json",
                "portfolio.json",
                "filings.json",
                "paper.json",
                "scan.json",
                "risk.json",
            )
        }
        with (resources / "prices.csv").open(encoding="utf-8", newline="") as handle:
            prices = tuple(
                {
                    "instrumentId": row["instrument_id"],
                    "tradeDate": row["trade_date"],
                    "open": float(row["open"]),
                    "high": float(row["high"]),
                    "low": float(row["low"]),
                    "close": float(row["close"]),
                    "adjClose": float(row["adj_close"]),
                    "volume": int(row["volume"]),
                    "source": row["source"],
                    "fetchedAt": row["fetched_at"],
                }
                for row in csv.DictReader(handle)
            )
    except (OSError, UnicodeError, ValueError, KeyError) as exc:
        raise InternalError(detail="demo: unreadable resources") from exc
    if manifest.get("version") != DEMO_VERSION:
        raise InternalError(detail="demo: unsupported manifest version")
    if manifest.get("counts") != EXPECTED_COUNTS:
        raise InternalError(detail="demo: manifest counts")
    files = manifest.get("files")
    if not isinstance(files, dict):
        raise InternalError(detail="demo: manifest files")
    if set(files) != {
        "instruments.json",
        "portfolio.json",
        "filings.json",
        "prices.csv",
        "paper.json",
        "scan.json",
        "risk.json",
    }:
        raise InternalError(detail="demo: manifest file list")
    for name, digest in files.items():
        path = resources / cast(str, name)
        if not path.is_file() or _hash(path) != digest:
            raise InternalError(detail=f"demo: fixture hash {name}")
    data = DemoData(
        manifest,
        payloads["instruments.json"],
        payloads["portfolio.json"],
        payloads["filings.json"],
        payloads["paper.json"],
        payloads["scan.json"],
        payloads["risk.json"],
        prices,
    )
    if len(data.instruments.get("instruments", [])) != 6:
        raise InternalError(detail="demo: instrument count")
    if len(data.portfolio.get("holdings", [])) != 5 or len(data.portfolio.get("theses", [])) != 6:
        raise InternalError(detail="demo: portfolio count")
    if len(data.filings.get("events", [])) != 6 or len(data.portfolio.get("decisions", [])) != 12:
        raise InternalError(detail="demo: filing count")
    if len(prices) != 1560 or any(row["source"] != "demo" for row in prices):
        raise InternalError(detail="demo: price count")
    _validate_payloads(data)
    _validate_prices(prices)
    return data


def _validate_payloads(data: DemoData) -> None:
    payloads = _payloads(data)
    for table, columns, keys, json_keys in SCHEMA:
        seen: set[tuple[object, ...]] = set()
        for row in payloads[table]:
            if not isinstance(row, dict):
                raise InternalError(detail=f"demo: invalid {table} row")
            identity = tuple(row.get(json_keys[columns.index(key)]) for key in keys)
            if any(value is None for value in identity) or identity in seen:
                raise InternalError(detail=f"demo: duplicate {table} key")
            seen.add(identity)
    instrument_ids = {cast(str, row["instrumentId"]) for row in payloads["instrument"]}
    if instrument_ids != {
        f"us:{symbol}" for symbol in ("ZZAR", "ZZFD", "ZZCL", "ZZBK", "ZZEN", "ZZMD")
    }:
        raise InternalError(detail="demo: instrument ids")
    event_ids = {cast(str, row["eventId"]) for row in payloads["event_doc"]}
    thesis_ids = {cast(str, row["thesisId"]) for row in payloads["thesis"]}
    decision_ids = {cast(str, row["decisionId"]) for row in payloads["decision"]}
    account_ids = {cast(str, row["accountId"]) for row in payloads["paper_account"]}
    for name in ("instrument_alias", "holding", "thesis"):
        if any(row["instrumentId"] not in instrument_ids for row in payloads[name]):
            raise InternalError(detail=f"demo: unknown instrument in {name}")
    for row in payloads["event_doc"]:
        if row["instrumentId"] not in instrument_ids or row.get("source") != "demo":
            raise InternalError(detail="demo: invalid event")
    for name in ("event_file", "event_passage"):
        if any(row["eventId"] not in event_ids for row in payloads[name]):
            raise InternalError(detail=f"demo: unknown event in {name}")
    for row in payloads["thesis_version"]:
        if row["thesisId"] not in thesis_ids:
            raise InternalError(detail="demo: unknown thesis version")
    for row in payloads["decision"]:
        if (
            row["thesisId"] not in thesis_ids
            or row["eventId"] not in event_ids
            or row["instrumentId"] not in instrument_ids
        ):
            raise InternalError(detail="demo: unknown decision reference")
    for row in payloads["thesis_action"]:
        if row["decisionId"] not in decision_ids:
            raise InternalError(detail="demo: unknown action decision")
    for row in payloads["scan_batch"]:
        if row["runId"] != payloads["scan_run"][0]["runId"] or row["eventId"] not in event_ids:
            raise InternalError(detail="demo: unknown scan batch reference")
    for name in ("cash_ledger", "paper_order", "position", "equity_snapshot"):
        if any(row["accountId"] not in account_ids for row in payloads[name]):
            raise InternalError(detail=f"demo: unknown account in {name}")
    for row in payloads["instrument"]:
        if row.get("source") != "demo":
            raise InternalError(detail="demo: instrument source")


def _validate_prices(prices: tuple[dict[str, Any], ...]) -> None:
    by_instrument: dict[str, list[str]] = {}
    per_day: dict[str, int] = {}
    for row in prices:
        day = cast(str, row["tradeDate"])
        by_instrument.setdefault(cast(str, row["instrumentId"]), []).append(day)
        per_day[day] = per_day.get(day, 0) + 1
    if set(by_instrument) != {
        f"us:{symbol}" for symbol in ("ZZAR", "ZZFD", "ZZCL", "ZZBK", "ZZEN", "ZZMD")
    }:
        raise InternalError(detail="demo: price instruments")
    for days in by_instrument.values():
        if len(days) != 260 or days != sorted(set(days)):
            raise InternalError(detail="demo: price date order")
    if len(per_day) != 260 or any(count != 6 for count in per_day.values()):
        raise InternalError(detail="demo: price day coverage")


def _payloads(data: DemoData) -> dict[str, list[dict[str, Any]]]:
    return {
        "instrument": list(data.instruments["instruments"]),
        "instrument_alias": list(data.instruments["aliases"]),
        "holding": list(data.portfolio["holdings"]),
        "thesis": list(data.portfolio["theses"]),
        "thesis_version": list(data.portfolio["thesisVersions"]),
        "event_doc": list(data.filings["events"]),
        "event_file": list(data.filings["files"]),
        "event_passage": list(data.filings["passages"]),
        "decision": list(data.portfolio["decisions"]),
        "thesis_action": list(data.portfolio["actions"]),
        "scan_run": [data.scan["run"]],
        "scan_batch": list(data.scan["batches"]),
        "price_daily": list(data.prices),
        "paper_account": [data.paper["account"]],
        "cash_ledger": list(data.paper["cashLedger"]),
        "paper_order": list(data.paper["orders"]),
        "fill": list(data.paper["fills"]),
        "position": list(data.paper["positions"]),
        "equity_snapshot": list(data.paper["equitySnapshots"]),
        "risk_run": [data.risk],
    }


def insert_all(tx: SqlExecutor, data: DemoData, inserted_at: datetime) -> None:
    payloads = _payloads(data)
    for table, columns, keys, json_keys in SCHEMA:
        indexes = {key: columns.index(key) for key in keys}
        for row in payloads[table]:
            values = [_value(table, key, row.get(key)) for key in json_keys]
            placeholders = ",".join("?" for _ in columns)
            tx.execute(f"INSERT INTO {table} ({','.join(columns)}) VALUES ({placeholders})", values)
            key_row = {key: row[json_keys[indexes[key]]] for key in keys}
            _register(tx, table, key_row, inserted_at)
    tx.execute(
        "INSERT INTO setting VALUES ('demoDataLoaded', 'true', ?) ON CONFLICT (key) "
        "DO UPDATE SET value_json='true', updated_at=excluded.updated_at",
        [inserted_at],
    )
    _register(tx, "setting", {"key": "demoDataLoaded"}, inserted_at)


def _value(table: str, key: str, value: Any) -> Any:
    if table == "risk_run" and key in ("paramsJson", "resultJson", "instrumentIds"):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return value


def _register(tx: SqlExecutor, table: str, values: dict[str, Any], inserted_at: datetime) -> None:
    tx.execute("INSERT INTO demo_row VALUES (?, ?, ?)", [table, pk_json(values), inserted_at])


def delete_registered(tx: SqlExecutor, cleared_at: datetime) -> int:
    tx.execute("SELECT table_name, pk_json FROM demo_row")
    rows = tx.fetchall()
    order = {table: index for index, table in enumerate(DELETE_ORDER)}
    ordered = sorted(rows, key=lambda row: order.get(cast(str, row[0]), len(order)))
    removed = 0
    for table, raw in ordered:
        name = cast(str, table)
        if name == "setting":
            continue
        if name not in SCHEMA_BY_TABLE:
            raise InternalError(detail=f"demo: unknown registry table {name}")
        _columns, keys, _json_keys = SCHEMA_BY_TABLE[name][1:]
        try:
            values = json.loads(cast(str, raw))
        except (TypeError, ValueError) as exc:
            raise InternalError(detail="demo: invalid registry row") from exc
        if not isinstance(values, dict) or set(values) != set(keys):
            raise InternalError(detail="demo: registry key mismatch")
        clauses = " AND ".join(f"{key}=?" for key in keys)
        tx.execute(f"DELETE FROM {name} WHERE {clauses}", [values[key] for key in keys])
        removed += 1
    tx.execute(
        "UPDATE setting SET value_json='false', updated_at=? WHERE key='demoDataLoaded'",
        [cleared_at],
    )
    tx.execute("DELETE FROM demo_row")
    return removed


def registry_count(tx: SqlExecutor) -> int:
    tx.execute("SELECT count(*) FROM demo_row")
    row = tx.fetchone()
    return 0 if row is None else cast(int, row[0])


def residual_tables(tx: SqlExecutor) -> tuple[str, ...]:
    tx.execute(
        "SELECT 'instrument' WHERE EXISTS (SELECT 1 FROM instrument WHERE source='demo') "
        "UNION ALL SELECT 'event_doc' WHERE EXISTS "
        "(SELECT 1 FROM event_doc WHERE source='demo') "
        "UNION ALL SELECT 'price_daily' WHERE EXISTS "
        "(SELECT 1 FROM price_daily WHERE source='demo') "
        "UNION ALL SELECT 'paper_account' WHERE EXISTS "
        "(SELECT 1 FROM paper_account WHERE is_demo)"
    )
    return tuple(sorted(cast(str, row[0]) for row in tx.fetchall()))


def residual_rows(tx: SqlExecutor) -> int:
    tx.execute(
        "SELECT (SELECT count(*) FROM instrument WHERE source='demo') + "
        "(SELECT count(*) FROM event_doc WHERE source='demo') + "
        "(SELECT count(*) FROM price_daily WHERE source='demo') + "
        "(SELECT count(*) FROM paper_account WHERE is_demo)"
    )
    row = tx.fetchone()
    return 0 if row is None else cast(int, row[0])
