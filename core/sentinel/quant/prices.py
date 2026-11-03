from __future__ import annotations

import math
from calendar import monthrange
from collections.abc import Mapping, Sequence
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Context, Decimal, localcontext
from typing import Protocol

import numpy as np

from sentinel.errors import UserError
from sentinel.messages.risk import text

from .models import (
    ExcludedAsset,
    HoldingPoint,
    PriceBasis,
    PricePoint,
    RiskDataInsufficient,
    RiskInput,
    WindowLabel,
)

WINDOW_MONTHS = {"6M": 6, "1Y": 12, "3Y": 36}


class TradingDays(Protocol):
    def is_trading_day(self, day: date) -> bool: ...
    def prev_trading_day(self, day: date) -> date: ...


def calendar_start(endpoint: date, window: WindowLabel) -> date:
    if window not in WINDOW_MONTHS:
        raise UserError("INVALID_ARGUMENT", field="window")
    absolute_month = endpoint.year * 12 + endpoint.month - 1 - WINDOW_MONTHS[window]
    year, month = divmod(absolute_month, 12)
    month += 1
    return date(year, month, min(endpoint.day, monthrange(year, month)[1]))


def _valid(value: float | None) -> bool:
    return value is not None and math.isfinite(value) and value > 0


def build_risk_input(
    holdings: Sequence[HoldingPoint],
    prices: Mapping[str, Sequence[PricePoint]],
    window: WindowLabel,
    min_observations: int = 60,
    *,
    calendar: TradingDays,
    as_of: date,
) -> RiskInput:
    if window not in WINDOW_MONTHS or type(min_observations) is not int or min_observations < 2:
        raise UserError(
            "INVALID_ARGUMENT",
            field="window" if window not in WINDOW_MONTHS else "min_observations",
        )
    participating: list[HoldingPoint] = []
    by_id: dict[str, dict[date, PricePoint]] = {}
    excluded: list[ExcludedAsset] = []
    for holding in sorted(holdings, key=lambda item: (item.symbol, item.instrument_id)):
        if holding.instrument_id in by_id:
            raise UserError("INVALID_ARGUMENT", field="holdings", reason="DUPLICATE_INSTRUMENT")
        if isinstance(holding.quantity, bool) or not isinstance(holding.quantity, (Decimal, int)):
            raise UserError("INVALID_ARGUMENT", field="quantity")
        quantity = Decimal(holding.quantity)
        if not quantity.is_finite() or quantity < 0:
            raise UserError("INVALID_ARGUMENT", field="quantity")
        rows: dict[date, PricePoint] = {}
        for point in prices.get(holding.instrument_id, ()):
            if point.trade_date > as_of or not calendar.is_trading_day(point.trade_date):
                continue
            if point.trade_date in rows:
                raise UserError("INVALID_ARGUMENT", field="prices", reason="DUPLICATE_DATE")
            rows[point.trade_date] = point
        by_id[holding.instrument_id] = rows
        reason = "risk.watch_only" if quantity == 0 else None
        if quantity > 0 and not any(_valid(point.close) for point in rows.values()):
            reason = "risk.no_baseline"
        if reason:
            excluded.append(
                ExcludedAsset(
                    instrument_id=holding.instrument_id, symbol=holding.symbol, reason=text(reason)
                )
            )
        else:
            participating.append(holding)
    if not participating:
        raise RiskDataInsufficient(0, min_observations, no_holdings=True)

    # 最新日的最小值只是上界；内洞时退到真实共同估值日，不能因此删掉持仓权重。
    valuation_dates = set.intersection(
        *(
            {day for day, point in by_id[h.instrument_id].items() if _valid(point.close)}
            for h in participating
        )
    )
    if not valuation_dates:
        raise RiskDataInsufficient(0, min_observations)
    endpoint = max(valuation_dates)
    start = calendar_start(endpoint, window)
    baseline_start = calendar.prev_trading_day(start)
    days: list[date] = []
    day = start
    while day <= endpoint:
        if calendar.is_trading_day(day):
            days.append(day)
        day += timedelta(days=1)
    adjusted = all(
        point.adj_close is not None
        for holding in participating
        for point in by_id[holding.instrument_id].values()
        if baseline_start <= point.trade_date <= endpoint
    )
    basis: PriceBasis = "adj_close" if adjusted else "close"
    warnings = [] if adjusted else [text("risk.unadjusted")]
    valid_returns: list[dict[date, float]] = []
    for holding in participating:
        rows = by_id[holding.instrument_id]
        returns: dict[date, float] = {}
        for day in days:
            previous = rows.get(calendar.prev_trading_day(day))
            current = rows.get(day)
            if previous is None or current is None or previous.source != current.source:
                continue
            left, right = getattr(previous, basis), getattr(current, basis)
            if not _valid(left) or not _valid(right):
                continue
            assert left is not None and right is not None
            value = right / left - 1
            if math.isfinite(value):
                returns[day] = value
        valid_returns.append(returns)
    common = sorted(set.intersection(*(set(rows) for rows in valid_returns)))
    if len(common) < min_observations:
        limiting = min(
            range(len(participating)),
            key=lambda i: (len(valid_returns[i]), participating[i].symbol),
        )
        raise RiskDataInsufficient(
            len(common), min_observations, symbol=participating[limiting].symbol
        )
    closes = np.array(
        [by_id[h.instrument_id][endpoint].close for h in participating], dtype=np.float64
    )
    # 小数持仓与市值不按数量上限截断；只在输出权重时转换为 float。
    with localcontext(Context(prec=60, rounding=ROUND_HALF_UP)):
        values = [
            Decimal(h.quantity) * Decimal(str(close))
            for h, close in zip(participating, closes, strict=True)
        ]
        total = sum(values)
        weights = np.array([float(value / total) for value in values], dtype=np.float64)
    latest_closed = as_of
    if not calendar.is_trading_day(latest_closed):
        latest_closed = calendar.prev_trading_day(latest_closed)
    stale_cutoff = latest_closed
    for _ in range(3):
        stale_cutoff = calendar.prev_trading_day(stale_cutoff)
    # 最小最新日作为窗口终点时，“比终点更旧”不可能，改以注入时钟的已收盘日检查。
    for holding in participating:
        latest = max(
            day for day, point in by_id[holding.instrument_id].items() if _valid(point.close)
        )
        if latest < stale_cutoff:
            warnings.append(text("risk.stale", {"symbol": holding.symbol}))
    if window == "3Y" and common[0] > days[0]:
        warnings.append(text("risk.short_history", {"start": common[0].isoformat()}))
    return RiskInput(
        symbols=[h.symbol for h in participating],
        instrument_ids=[h.instrument_id for h in participating],
        returns=np.array(
            [[rows[day] for rows in valid_returns] for day in common], dtype=np.float64
        ),
        weights=weights,
        endpoint_closes=closes,
        window_observations=len(common),
        periods_per_year=252,
        price_basis=basis,
        as_of=endpoint,
        from_date=common[0],
        window_label=window,
        min_observations=min_observations,
        return_dates=common,
        warnings=warnings,
        excluded=sorted(excluded, key=lambda item: (item.symbol, item.instrument_id)),
    )
