from __future__ import annotations

import math
from datetime import date, datetime
from typing import Literal, cast

from sentinel.clock import to_iso
from sentinel.errors import InternalError
from sentinel.markets.instruments.models import Instrument
from sentinel.storage import SqlExecutor

from .models import (
    HoldingRow,
    HoldingView,
    InstrumentView,
    ThesisRow,
    ThesisVersionView,
    ThesisView,
)
from .validation import market_value

_HOLDING_COLUMNS = [
    "holding_id",
    "instrument_id",
    "quantity",
    "avg_cost",
    "note",
    "created_at",
    "updated_at",
    "archived_at",
]
_THESIS_COLUMNS = [
    "thesis_id",
    "instrument_id",
    "status",
    "current_version",
    "created_at",
    "updated_at",
    "archived_at",
]
_INSTRUMENT_COLUMNS = [
    "instrument_id",
    "market",
    "symbol",
    "exchange",
    "name",
    "name_zh",
    "currency",
    "cik",
    "is_active",
]


def _dict(columns: list[str], row: tuple[object, ...]) -> dict[str, object]:
    return dict(zip(columns, row, strict=True))


def _tables(tx: SqlExecutor) -> set[str]:
    tx.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_schema = current_schema()"
    )
    return {cast(str, row[0]) for row in tx.fetchall()}


class PortfolioRepository:
    def get_instrument(self, tx: SqlExecutor, instrument_id: str) -> Instrument | None:
        tx.execute(
            "SELECT " + ", ".join(_INSTRUMENT_COLUMNS) + " FROM instrument WHERE instrument_id = ?",
            [instrument_id],
        )
        row = tx.fetchone()
        return (
            None
            if row is None
            else Instrument(
                *cast(tuple[str, str, str, str, str, str | None, str, str | None, bool], row)
            )
        )

    def get_holding(self, tx: SqlExecutor, instrument_id: str) -> HoldingRow | None:
        tx.execute("SELECT * FROM holding WHERE instrument_id = ?", [instrument_id])
        row = tx.fetchone()
        return None if row is None else HoldingRow.model_validate(_dict(_HOLDING_COLUMNS, row))

    def get_thesis(self, tx: SqlExecutor, thesis_id: str) -> ThesisRow | None:
        tx.execute("SELECT * FROM thesis WHERE thesis_id = ?", [thesis_id])
        row = tx.fetchone()
        return None if row is None else ThesisRow.model_validate(_dict(_THESIS_COLUMNS, row))

    def count_active(self, tx: SqlExecutor, instrument_id: str) -> int:
        tx.execute(
            "SELECT count(*) FROM thesis WHERE instrument_id = ? AND status = 'active'",
            [instrument_id],
        )
        row = tx.fetchone()
        assert row is not None
        return cast(int, row[0])

    def insert_version(
        self,
        tx: SqlExecutor,
        thesis_id: str,
        version: int,
        statement: str,
        kill_condition: str | None,
        content_hash: str,
        moment: datetime,
    ) -> None:
        tx.execute(
            "INSERT INTO thesis_version VALUES (?, ?, ?, ?, ?, ?)",
            [thesis_id, version, statement, kill_condition, content_hash, moment],
        )

    def current_hash(self, tx: SqlExecutor, thesis: ThesisRow) -> str:
        tx.execute(
            "SELECT content_hash FROM thesis_version WHERE thesis_id = ? AND version = ?",
            [thesis.thesis_id, thesis.current_version],
        )
        row = tx.fetchone()
        if row is None:
            raise InternalError(detail="current thesis version is missing")
        return cast(str, row[0])

    def list_holdings(self, tx: SqlExecutor, instrument_id: str | None = None) -> list[HoldingView]:
        tables = _tables(tx)
        price_join = ""
        price_columns = "NULL AS last_close, NULL AS last_close_date, NULL AS day_change_pct"
        if "price_daily" in tables:
            price_join = """
            LEFT JOIN (
              SELECT instrument_id, trade_date, close,
                     LAG(close) OVER (PARTITION BY instrument_id ORDER BY trade_date) AS prev_close,
                     ROW_NUMBER() OVER (PARTITION BY instrument_id ORDER BY trade_date DESC) AS rn
              FROM price_daily
            ) lp ON lp.instrument_id = h.instrument_id AND lp.rn = 1
            """
            price_columns = (
                "lp.close, lp.trade_date, "
                "CASE WHEN lp.prev_close > 0 THEN lp.close / lp.prev_close - 1 END"
            )
        pending_cte = ""
        pending_join = ""
        pending_columns = "0 AS pending_count, 0 AS uncertain_count"
        if {"decision", "v_last_action"} <= tables:
            pending_cte = """
            WITH ranked AS (
              SELECT d.decision_id, t.instrument_id, d.relation,
                     ROW_NUMBER() OVER (
                       PARTITION BY d.thesis_id, d.event_id
                       ORDER BY CASE d.relation
                                  WHEN 'overturn' THEN 0 WHEN 'weaken' THEN 1 ELSE 2 END,
                                d.headline DESC, p.seq ASC, d.decision_id ASC
                     ) AS rk
              FROM decision d
              LEFT JOIN event_passage p ON p.passage_id = d.passage_id
              JOIN thesis t ON t.thesis_id = d.thesis_id AND t.status = 'active'
                            AND t.archived_at IS NULL
              WHERE d.relation IN ('overturn', 'weaken', 'uncertain')
            ), pending AS (
              SELECT r.instrument_id,
                     count(*) FILTER (WHERE r.relation IN ('overturn', 'weaken')) AS pending_count,
                     count(*) FILTER (WHERE r.relation = 'uncertain') AS uncertain_count
              FROM ranked r
              JOIN decision d ON d.decision_id = r.decision_id
              JOIN thesis t ON t.thesis_id = d.thesis_id
              JOIN thesis_version tv ON tv.thesis_id = d.thesis_id
                                     AND tv.version = d.thesis_version
              JOIN event_passage p ON p.passage_id = d.passage_id AND p.event_id = d.event_id
              JOIN event_doc e ON e.event_id = d.event_id AND e.instrument_id = d.instrument_id
              LEFT JOIN event_file f ON f.event_id = p.event_id AND f.seq = p.file_seq
              LEFT JOIN v_last_action la ON la.decision_id = r.decision_id
              WHERE r.rk = 1 AND (la.action IS NULL OR la.action = 'reopen')
                AND d.instrument_id = t.instrument_id AND d.content_status = e.content_status
                AND d.thesis_version >= 1 AND t.current_version >= 1
                AND length(trim(tv.statement)) BETWEEN 1 AND 500
                AND (tv.kill_condition IS NULL OR length(tv.kill_condition) <= 300)
                AND isfinite(d.headline) AND d.headline BETWEEN 0 AND 1
                AND isfinite(d.p_relevant) AND d.p_relevant BETWEEN 0 AND 1
                AND isfinite(d.p_against) AND d.p_against BETWEEN 0 AND 1
                AND isfinite(d.p_contradicts) AND d.p_contradicts BETWEEN 0 AND 1
                AND isfinite(d.p_supports) AND d.p_supports BETWEEN 0 AND 1
                AND (d.p_kill_met IS NULL OR
                     (isfinite(d.p_kill_met) AND d.p_kill_met BETWEEN 0 AND 1))
                AND length(trim(p.text)) > 0
                AND (
                  (d.evidence_kind = 'title' AND p.file_seq = -1
                   AND d.content_status = 'title_only' AND p.text = e.title
                   AND d.evidence_start IS NULL AND d.evidence_end IS NULL)
                  OR
                  (p.file_seq >= 0 AND d.content_status = 'full_text'
                   AND f.text_status = 'extracted' AND length(trim(f.text)) > 0
                   AND length(trim(f.doc_type)) > 0
                   AND (
                     (d.evidence_kind = 'passage'
                      AND d.evidence_start IS NULL AND d.evidence_end IS NULL)
                     OR
                     (d.evidence_kind = 'sentence' AND d.evidence_start >= 0
                      AND d.evidence_end > d.evidence_start
                      AND d.evidence_end <= length(p.text)
                      AND length(trim(substr(p.text, d.evidence_start + 1,
                                               d.evidence_end - d.evidence_start))) > 0)
                   ))
                )
              GROUP BY r.instrument_id
            )
            """
            pending_join = "LEFT JOIN pending pend ON pend.instrument_id = h.instrument_id"
            pending_columns = "coalesce(pend.pending_count, 0), coalesce(pend.uncertain_count, 0)"
        tx.execute(
            pending_cte + "SELECT h.*, i.instrument_id, i.market, i.symbol, i.exchange, i.name, "
            "i.name_zh, i.currency, i.cik, i.is_active, " + price_columns + ", "
            "(SELECT count(*) FROM thesis t "
            "WHERE t.instrument_id = h.instrument_id AND t.status = 'active' "
            "AND t.archived_at IS NULL), "
            + pending_columns
            + " FROM holding h JOIN instrument i ON i.instrument_id = h.instrument_id "
            + price_join
            + pending_join
            + " WHERE h.archived_at IS NULL AND (? IS NULL OR h.instrument_id = ?) "
            "ORDER BY (h.quantity > 0) DESC, i.symbol",
            [instrument_id, instrument_id],
        )
        views = []
        for row in tx.fetchall():
            holding = HoldingRow.model_validate(_dict(_HOLDING_COLUMNS, row[:8]))
            instrument = InstrumentView.model_validate(
                {
                    key: value
                    for key, value in _dict(_INSTRUMENT_COLUMNS, row[8:17]).items()
                    if key != "cik"
                }
            )
            close, trade_date, change, count, pending, uncertain = row[17:]
            last_close = cast(float | None, close)
            if last_close is not None and (not math.isfinite(last_close) or last_close < 0):
                raise InternalError(detail="invalid latest holding price")
            status: Literal["unguarded", "attention", "guarded"] = (
                "unguarded" if count == 0 else "attention" if cast(int, pending) > 0 else "guarded"
            )
            views.append(
                HoldingView(
                    holding_id=holding.holding_id,
                    instrument=instrument,
                    quantity=holding.quantity,
                    avg_cost=holding.avg_cost,
                    note=holding.note,
                    last_close=last_close,
                    last_close_date=None
                    if trade_date is None
                    else cast(date, trade_date).isoformat(),
                    day_change_pct=cast(float | None, change),
                    market_value=None
                    if last_close is None
                    else market_value(holding.quantity, last_close),
                    thesis_count=cast(int, count),
                    pending_count=cast(int, pending),
                    uncertain_count=cast(int, uncertain),
                    status=status,
                )
            )
        return views

    def list_theses(
        self,
        tx: SqlExecutor,
        instrument_id: str | None = None,
        status: str | None = None,
        thesis_id: str | None = None,
    ) -> list[ThesisView]:
        tables = _tables(tx)
        decision_join = ""
        decision_columns = "NULL, NULL, NULL, NULL, NULL"
        if {"decision", "event_doc"} <= tables:
            decision_join = """
            LEFT JOIN (
              SELECT d.thesis_id, d.decision_id, d.relation, d.headline, d.created_at, e.title,
                     ROW_NUMBER() OVER (
                       PARTITION BY d.thesis_id ORDER BY d.created_at DESC, d.decision_id DESC
                     ) AS rn
              FROM decision d JOIN event_doc e ON e.event_id = d.event_id
            ) ld ON ld.thesis_id = t.thesis_id AND ld.rn = 1
            """
            decision_columns = "ld.decision_id, ld.relation, ld.headline, ld.created_at, ld.title"
        tx.execute(
            "SELECT t.thesis_id, t.instrument_id, t.current_version, "
            "(SELECT count(*) FROM thesis_version v WHERE v.thesis_id = t.thesis_id), "
            "v.statement, v.kill_condition, t.status, t.created_at, t.updated_at, "
            + decision_columns
            + " FROM thesis t LEFT JOIN thesis_version v "
            "ON v.thesis_id = t.thesis_id AND v.version = t.current_version "
            + decision_join
            + " WHERE (? IS NULL OR t.instrument_id = ?) AND (? IS NULL OR t.status = ?) "
            "AND (? IS NULL OR t.thesis_id = ?) ORDER BY t.created_at, t.thesis_id",
            [instrument_id, instrument_id, status, status, thesis_id, thesis_id],
        )
        views = []
        for row in tx.fetchall():
            if row[4] is None:
                raise InternalError(detail="current thesis version is missing")
            fields = _dict(
                [
                    "thesis_id",
                    "instrument_id",
                    "version",
                    "version_count",
                    "statement",
                    "kill_condition",
                    "status",
                    "created_at",
                    "updated_at",
                ],
                row[:9],
            )
            fields["created_at"] = to_iso(cast(datetime, row[7]))
            fields["updated_at"] = to_iso(cast(datetime, row[8]))
            fields["last_decision"] = (
                None
                if row[9] is None
                else {
                    "decision_id": row[9],
                    "relation": row[10],
                    "headline": row[11],
                    "created_at": to_iso(cast(datetime, row[12])),
                    "event_title": row[13],
                }
            )
            views.append(ThesisView.model_validate(fields))
        return views

    def thesis_view(self, tx: SqlExecutor, thesis_id: str) -> ThesisView:
        views = self.list_theses(tx, thesis_id=thesis_id)
        if not views:
            raise InternalError(detail="written thesis is missing")
        return views[0]

    def list_versions(self, tx: SqlExecutor, thesis_id: str) -> list[ThesisVersionView]:
        tx.execute(
            "SELECT version, statement, kill_condition, created_at FROM thesis_version "
            "WHERE thesis_id = ? ORDER BY version DESC",
            [thesis_id],
        )
        return [
            ThesisVersionView.model_validate(
                {
                    "version": row[0],
                    "statement": row[1],
                    "kill_condition": row[2],
                    "created_at": to_iso(cast(datetime, row[3])),
                }
            )
            for row in tx.fetchall()
        ]
