from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from sentinel import clock
from sentinel.errors import InternalError, UserError
from sentinel.ids import new_id
from sentinel.markets.prices.calendar import next_trading_day
from sentinel.messages import render
from sentinel.storage.db import WriteTx

from .fees import match_at_open
from .ledger import Ledger
from .models import MAX_POSITION_QUANTITY, OrderRow, isolated_decimal, money, price
from .rules import MarketRules, OrderIntent, Reject


@dataclass(frozen=True)
class MatchOutcome:
    order_id: str
    kind: Literal["filled", "rejected", "pending"]


@isolated_decimal
def rejection_message(reject: Reject) -> str:
    params = dict(reject.data)
    for key in ("required", "available"):
        if key in params:
            params[key] = format(Decimal(str(params[key])), ",.2f")
    return render(reject.message_key, params)


class OrderRejectedError(UserError):
    def __init__(self, reject: Reject, order_id: str) -> None:
        super().__init__(
            "ORDER_REJECTED", params={**reject.data, "orderId": order_id}, reason=reject.code
        )
        self.reject = reject

    def to_wire(self, request_id: str | None = None) -> dict[str, object]:
        result = super().to_wire(request_id)
        result["message"] = rejection_message(self.reject)
        return result


def prior_wait_days(created: date, next_day: date) -> int:
    days, day = 0, next_trading_day(created)
    while day < next_day:
        days += 1
        day = next_trading_day(day)
    if day != next_day:
        raise InternalError(reason="INVALID_MATCH_DATE")
    return days


@isolated_decimal
def execute_order(
    tx: WriteTx,
    order: OrderRow,
    next_day: date,
    open_price: Decimal | None,
    rules: MarketRules,
    *,
    now: datetime | None = None,
) -> MatchOutcome:
    if order.status != "pending":
        raise InternalError(reason="ORDER_NOT_PENDING")
    now = clock.now() if now is None else now
    ledger = Ledger()
    held = ledger.position_quantity(tx, order.account_id, order.instrument_id)
    totals = ledger.totals(tx, order.account_id)
    reserved = order.reserved_cash or Decimal(0)
    waited = prior_wait_days(order.created_clock_date, next_day)
    terminal = (open_price is not None and open_price > 0) or (
        waited + 1 >= rules.max_wait_trading_days
    )
    if order.reserved_cash is not None and terminal:
        ledger.append(
            tx, order.account_id, next_day, "release", order.reserved_cash, order.order_id, now
        )
        available = ledger.totals(tx, order.account_id).available
    else:
        # 尚需等待的订单不产生 release；纯规则的无价分支不会使用这笔可用资金。
        available = money(totals.available + reserved)
    intent = OrderIntent(
        order.account_id,
        order.instrument_id,
        order.side,
        order.quantity,
        order.order_type,
        order.idempotency_key,
    )
    result = match_at_open(
        intent,
        open_price,
        waited,
        reserved,
        available,
        held,
        rules,
    )
    if result.kind == "pending":
        return MatchOutcome(order.order_id, "pending")
    if result.kind == "rejected":
        assert result.reject is not None
        tx.execute(
            "UPDATE paper_order SET status='rejected', reserved_cash=NULL, reject_code=?, "
            "reject_message=?, updated_at=? WHERE order_id=? AND status='pending'",
            [result.reject.code, rejection_message(result.reject), now, order.order_id],
        )
        return MatchOutcome(order.order_id, "rejected")
    assert result.price is not None and result.amount is not None and result.fee is not None
    fill_price, amount, fee = price(result.price), money(result.amount), money(result.fee)
    fill_id = new_id()
    existing = ledger.position(tx, order.account_id, order.instrument_id)
    old_cost = existing.avg_cost if existing else Decimal(0)
    quantity = held + order.quantity if order.side == "buy" else held - order.quantity
    if not 0 <= quantity <= MAX_POSITION_QUANTITY:
        raise InternalError(reason="POSITION_OVERFLOW")
    avg_cost = (
        price((held * old_cost + amount + fee) / quantity) if order.side == "buy" else old_cost
    )
    ledger.append(
        tx,
        order.account_id,
        next_day,
        order.side,
        -amount if order.side == "buy" else amount,
        fill_id,
        now,
    )
    ledger.append(tx, order.account_id, next_day, "fee", -fee, fill_id, now)
    tx.execute(
        "INSERT INTO position VALUES (?, ?, ?, ?, ?) ON CONFLICT(account_id, instrument_id) "
        "DO UPDATE SET quantity=excluded.quantity, avg_cost=excluded.avg_cost, "
        "updated_at=excluded.updated_at",
        [order.account_id, order.instrument_id, quantity, avg_cost, now],
    )
    tx.execute(
        "INSERT INTO fill VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            fill_id,
            order.order_id,
            next_day,
            fill_price,
            order.quantity,
            amount,
            fee,
            float(rules.slippage_bps),
            now,
        ],
    )
    tx.execute(
        "UPDATE paper_order SET status='filled', reserved_cash=NULL, updated_at=? "
        "WHERE order_id=? AND status='pending'",
        [now, order.order_id],
    )
    return MatchOutcome(order.order_id, "filled")
