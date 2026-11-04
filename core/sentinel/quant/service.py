from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Protocol, cast

from pydantic import BaseModel

from sentinel import clock as system_clock
from sentinel.errors import UserError
from sentinel.ids import new_id
from sentinel.rpc.dispatcher import Handler, RequestContext
from sentinel.storage import Database
from sentinel.storage.db import SqlExecutor

from .models import HoldingPoint, PricePoint, RiskParams, RiskResult, WindowLabel
from .prices import TradingDays, build_risk_input
from .risk import (
    MIN_OBSERVATIONS,
    PERIODS_PER_YEAR,
    SHRINKAGE_ALPHA,
    SINGULARITY_RATIO,
    compute_risk,
)

CODE_VERSION = "p06-risk-v1"


class RiskCalendar(TradingDays, Protocol):
    def latest_closed_day(self, now: datetime) -> date: ...


class HandlerRegistrar(Protocol):
    def register(
        self,
        method: str,
        handler: Handler,
        params_model: type[BaseModel],
        result_model: type[BaseModel] | None = None,
        timeout_ms: int = 30_000,
    ) -> None: ...


def _holdings(tx: SqlExecutor) -> list[HoldingPoint]:
    tx.execute(
        "SELECT h.instrument_id, i.symbol, h.quantity, i.market, i.currency "
        "FROM holding h JOIN instrument i ON h.instrument_id = i.instrument_id "
        "WHERE h.archived_at IS NULL ORDER BY i.symbol, h.instrument_id"
    )
    rows = tx.fetchall()
    if any(row[3] != "us" or row[4] != "USD" for row in rows if cast(Decimal, row[2]) > 0):
        raise UserError("INVALID_ARGUMENT", field="currency", reason="UNSUPPORTED_HOLDING")
    return [
        HoldingPoint(cast(str, row[0]), cast(str, row[1]), cast(Decimal, row[2])) for row in rows
    ]


class RiskService:
    def __init__(
        self,
        db: Database,
        *,
        calendar: RiskCalendar,
        clock: Callable[[], datetime] = system_clock.now,
    ) -> None:
        self.db = db
        self.calendar = calendar
        self.clock = clock

    def compute(self, scope: str, window: str, currency: str) -> RiskResult:
        for field, valid in (
            ("scope", scope == "holdings"),
            ("window", window in ("6M", "1Y", "3Y")),
            ("currency", currency == "USD"),
        ):
            if not valid:
                raise UserError("INVALID_ARGUMENT", field=field)
        now = self.clock()
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("clock must be timezone-aware")
        now = now.astimezone(UTC)
        cutoff = self.calendar.latest_closed_day(now)
        # 持仓与行情在同一只读快照内取完，计算期间不持数据库锁。
        with self.db.read() as tx:
            holdings = _holdings(tx)
            tx.execute(
                "SELECT p.instrument_id, p.trade_date, p.close, p.adj_close, p.source "
                "FROM price_daily p "
                "JOIN holding h ON h.instrument_id = p.instrument_id "
                "WHERE h.archived_at IS NULL AND h.quantity > 0 AND p.trade_date <= ? "
                "ORDER BY p.instrument_id, p.trade_date",
                [cutoff],
            )
            prices: dict[str, list[PricePoint]] = {}
            for instrument_id, day, close, adjusted, source in tx.fetchall():
                prices.setdefault(cast(str, instrument_id), []).append(
                    PricePoint(
                        cast(date, day),
                        cast(float | None, close),
                        cast(float | None, adjusted),
                        cast(str, source),
                    )
                )
        data = build_risk_input(
            holdings,
            prices,
            cast(WindowLabel, window),
            MIN_OBSERVATIONS,
            calendar=self.calendar,
            as_of=cutoff,
        )
        result = compute_risk(data)
        snapshot = {
            "symbols": data.symbols,
            "weights": data.weights.tolist(),
            "endpoint_closes": data.endpoint_closes.tolist(),
            "returns": data.returns.tolist(),
            "return_dates": [day.isoformat() for day in data.return_dates],
            "quantities": {
                h.instrument_id: str(h.quantity)
                for h in holdings
                if h.instrument_id in data.instrument_ids
            },
            "sources": {
                instrument_id: sorted(
                    {
                        point.source
                        for point in prices[instrument_id]
                        if data.from_date <= point.trade_date <= data.as_of
                        and point.source is not None
                    }
                )
                for instrument_id in data.instrument_ids
            },
        }
        snapshot_json = json.dumps(snapshot, allow_nan=False, sort_keys=True, separators=(",", ":"))
        params = {
            "shrinkage_alpha": SHRINKAGE_ALPHA,
            "singularity_ratio": SINGULARITY_RATIO,
            "periods_per_year": PERIODS_PER_YEAR,
            "min_observations": MIN_OBSERVATIONS,
            "price_basis": data.price_basis,
            "code_version": CODE_VERSION,
            "clock": system_clock.to_iso(now),
            "price_cutoff": cutoff.isoformat(),
            "input_sha256": hashlib.sha256(snapshot_json.encode()).hexdigest(),
            "input": snapshot,
        }
        audit_row = [
            new_id(),
            now,
            scope,
            window,
            currency,
            data.window_observations,
            json.dumps(data.instrument_ids, allow_nan=False),
            json.dumps(params, allow_nan=False),
            json.dumps(result.model_dump(mode="json", by_alias=True), allow_nan=False),
        ]
        # 仅审计插入持写锁；提交失败时不得返回计算成功。
        with self.db.write() as tx:
            tx.execute(
                "INSERT INTO risk_run VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                audit_row,
            )
        return result


def register_handlers(registrar: HandlerRegistrar, service: RiskService) -> None:
    def compute(params: BaseModel, ctx: RequestContext) -> BaseModel:
        p = cast(RiskParams, params)
        return service.compute(p.scope, p.window, p.currency)

    registrar.register("risk.compute", compute, RiskParams, RiskResult)
