from __future__ import annotations

import logging
import math
from datetime import date, datetime
from decimal import Decimal
from typing import cast

from sentinel.errors import InternalError, UserError
from sentinel.ids import new_id
from sentinel.storage.db import SqlExecutor, WriteTx

from .models import (
    EstimateView,
    FillView,
    InstrumentView,
    LedgerTotals,
    OrderRow,
    PaperAccountView,
    PaperOrderView,
    PortfolioView,
    PositionRow,
    PositionView,
    RejectReason,
    isolated_decimal,
    money,
)

_logger = logging.getLogger(__name__)
ACCOUNT_COLUMNS = (
    "account_id, name, base_currency, initial_cash, start_date, clock_date, created_at"
)
ORDER_COLUMNS = ", ".join(OrderRow.model_fields)
ENTRY_TYPES = frozenset({"deposit", "buy", "sell", "fee", "reserve", "release"})


class Ledger:
    @isolated_decimal
    def totals(self, tx: SqlExecutor, account_id: str) -> LedgerTotals:
        tx.execute(
            "SELECT COALESCE(SUM(CASE WHEN entry_type IN ('deposit','buy','sell','fee') "
            "THEN amount END),0), COALESCE(-SUM(CASE WHEN entry_type IN ('reserve','release') "
            "THEN amount END),0) FROM cash_ledger WHERE account_id=?",
            [account_id],
        )
        row = tx.fetchone()
        assert row is not None
        cash, reserved = money(cast(Decimal, row[0])), money(cast(Decimal, row[1]))
        return LedgerTotals(cash=cash, reserved=reserved, available=money(cash - reserved))

    def append(
        self,
        tx: WriteTx,
        account_id: str,
        day: date,
        entry_type: str,
        amount: Decimal,
        ref_id: str | None,
        now: datetime,
    ) -> None:
        if entry_type not in ENTRY_TYPES:
            raise InternalError(reason="INVALID_LEDGER_ENTRY")
        tx.execute(
            "INSERT INTO cash_ledger VALUES (?, ?, ?, ?, ?, ?, ?)",
            [new_id(), account_id, day, entry_type, money(amount), ref_id, now],
        )

    def account(self, tx: SqlExecutor, account_id: str, *, active: bool = True) -> PaperAccountView:
        tx.execute(
            f"SELECT {ACCOUNT_COLUMNS}, archived_at FROM paper_account WHERE account_id=?",
            [account_id],
        )
        row = tx.fetchone()
        if row is None or (active and row[-1] is not None):
            raise UserError("NOT_FOUND", field="accountId")
        return PaperAccountView.model_validate(
            dict(zip(PaperAccountView.model_fields, row[:-1], strict=True))
        )

    def instrument(self, tx: SqlExecutor, instrument_id: str) -> InstrumentView:
        tx.execute(
            "SELECT instrument_id, market, symbol, name, name_zh, exchange, currency, is_active "
            "FROM instrument WHERE instrument_id=?",
            [instrument_id],
        )
        row = tx.fetchone()
        if row is None:
            raise UserError("NOT_FOUND", field="instrumentId")
        return InstrumentView.model_validate(
            dict(zip(InstrumentView.model_fields, row, strict=True))
        )

    def order(self, tx: SqlExecutor, order_id: str) -> OrderRow:
        tx.execute(f"SELECT {ORDER_COLUMNS} FROM paper_order WHERE order_id=?", [order_id])
        row = tx.fetchone()
        if row is None:
            raise UserError("NOT_FOUND", field="orderId")
        return self.order_row(row)

    @staticmethod
    def order_row(row: tuple[object, ...]) -> OrderRow:
        return OrderRow.model_validate(dict(zip(OrderRow.model_fields, row, strict=True)))

    def position(self, tx: SqlExecutor, account_id: str, instrument_id: str) -> PositionRow | None:
        tx.execute(
            "SELECT * FROM position WHERE account_id=? AND instrument_id=?",
            [account_id, instrument_id],
        )
        row = tx.fetchone()
        return (
            None
            if row is None
            else PositionRow.model_validate(dict(zip(PositionRow.model_fields, row, strict=True)))
        )

    def position_quantity(self, tx: SqlExecutor, account_id: str, instrument_id: str) -> int:
        row = self.position(tx, account_id, instrument_id)
        return row.quantity if row else 0

    def pending_sell_quantity(self, tx: SqlExecutor, account_id: str, instrument_id: str) -> int:
        tx.execute(
            "SELECT COALESCE(SUM(quantity),0) FROM paper_order WHERE account_id=? "
            "AND instrument_id=? AND side='sell' AND status='pending'",
            [account_id, instrument_id],
        )
        row = tx.fetchone()
        assert row is not None
        return cast(int, row[0])

    def pending_count(self, tx: SqlExecutor, account_id: str) -> int:
        tx.execute(
            "SELECT COUNT(*) FROM paper_order WHERE account_id=? AND status='pending'", [account_id]
        )
        row = tx.fetchone()
        assert row is not None
        return cast(int, row[0])

    @staticmethod
    def _price_value(value: object) -> Decimal | None:
        if value is None:
            return None
        if not isinstance(value, (float, int, Decimal)) or isinstance(value, bool):
            raise InternalError(reason="INVALID_PRICE")
        if not math.isfinite(value) or value < 0:
            raise InternalError(reason="INVALID_PRICE")
        return Decimal(str(value)) if value > 0 else None

    def open_on(self, tx: SqlExecutor, instrument_id: str, day: date) -> Decimal | None:
        tx.execute(
            "SELECT open FROM price_daily WHERE instrument_id=? AND trade_date=?",
            [instrument_id, day],
        )
        row = tx.fetchone()
        return self._price_value(row[0]) if row else None

    def close_on(self, tx: SqlExecutor, instrument_id: str, day: date) -> Decimal | None:
        tx.execute(
            "SELECT close FROM price_daily WHERE instrument_id=? AND trade_date=?",
            [instrument_id, day],
        )
        row = tx.fetchone()
        return self._price_value(row[0]) if row else None

    def close_on_or_before(
        self, tx: SqlExecutor, instrument_id: str, day: date
    ) -> tuple[date, Decimal] | None:
        tx.execute(
            "SELECT trade_date, close FROM price_daily WHERE instrument_id=? AND trade_date<=? "
            "AND close IS NOT NULL AND close<>0 ORDER BY trade_date DESC LIMIT 1",
            [instrument_id, day],
        )
        row = tx.fetchone()
        if row is None:
            return None
        close = self._price_value(row[1])
        assert close is not None
        return cast(date, row[0]), close

    def has_prices_on(self, tx: SqlExecutor, account_id: str, day: date) -> bool:
        # 必须有目标日行情；未来某日的 MAX 日期不能证明目标日可推进。
        tx.execute(
            "SELECT COUNT(*) FROM price_daily WHERE trade_date=? AND instrument_id IN ("
            "SELECT instrument_id FROM position WHERE account_id=? AND quantity>0 UNION "
            "SELECT instrument_id FROM paper_order WHERE account_id=?)",
            [day, account_id, account_id],
        )
        row = tx.fetchone()
        assert row is not None
        return cast(int, row[0]) > 0

    @isolated_decimal
    def order_view(self, tx: SqlExecutor, order: OrderRow) -> PaperOrderView:
        tx.execute(
            "SELECT fill_id, filled_on, price, quantity, amount, fee FROM fill WHERE order_id=? "
            "ORDER BY filled_on, fill_id",
            [order.order_id],
        )
        fills = [
            FillView.model_validate(dict(zip(FillView.model_fields, r, strict=True)))
            for r in tx.fetchall()
        ]
        estimate = None
        if order.estimate_price is not None:
            # 原 reserve 只追加，成交/取消后仍可恢复当时费用，不依赖当前配置或行情。
            tx.execute(
                "SELECT -amount FROM cash_ledger WHERE ref_id=? AND entry_type='reserve'",
                [order.order_id],
            )
            reserved = tx.fetchone()
            if reserved is not None:
                amount = money(order.estimate_price * order.quantity)
                estimate = EstimateView(
                    price=order.estimate_price,
                    amount=amount,
                    fee=money(cast(Decimal, reserved[0]) - amount),
                )
        return PaperOrderView(
            order_id=order.order_id,
            account_id=order.account_id,
            instrument=self.instrument(tx, order.instrument_id),
            side=order.side,
            quantity=order.quantity,
            order_type="market_open",
            status=order.status,
            reject_reason=None
            if order.reject_code is None
            else RejectReason(code=order.reject_code, message=order.reject_message or ""),
            created_clock_date=order.created_clock_date,
            reserved_cash=order.reserved_cash,
            idempotency_key=order.idempotency_key,
            fills=fills,
            estimate=estimate,
        )

    @isolated_decimal
    def portfolio(self, tx: SqlExecutor, account_id: str) -> PortfolioView:
        account = self.account(tx, account_id)
        totals = self.totals(tx, account_id)
        tx.execute(
            "SELECT * FROM position WHERE account_id=? AND quantity>0 ORDER BY instrument_id",
            [account_id],
        )
        positions = [
            PositionRow.model_validate(dict(zip(PositionRow.model_fields, r, strict=True)))
            for r in tx.fetchall()
        ]
        views: list[PositionView] = []
        for pos in positions:
            bar = self.close_on_or_before(tx, pos.instrument_id, account.clock_date)
            if bar is None:
                raise UserError(
                    "DATA_INSUFFICIENT",
                    reason="POSITION_PRICE_MISSING",
                    params={"instrumentId": pos.instrument_id},
                )
            day, close = bar
            if day < account.clock_date:
                _logger.warning(
                    "paper.valuation.stale price_date=%s clock_date=%s", day, account.clock_date
                )
            value, cost = money(close * pos.quantity), money(pos.avg_cost * pos.quantity)
            pnl = money(value - cost)
            views.append(
                PositionView(
                    instrument=self.instrument(tx, pos.instrument_id),
                    quantity=pos.quantity,
                    sellable_quantity=pos.quantity,
                    avg_cost=pos.avg_cost,
                    last_close=float(close),
                    market_value=value,
                    unrealized_pnl=pnl,
                    unrealized_pnl_pct=float(pnl / cost) if cost else 0.0,
                )
            )
        equity = money(totals.cash + sum((p.market_value for p in views), Decimal(0)))
        return PortfolioView(
            account=account,
            cash=totals.cash,
            reserved_cash=totals.reserved,
            available_cash=totals.available,
            positions=views,
            equity=equity,
            as_of=account.clock_date,
            pending_orders=self.pending_count(tx, account_id),
        )

    @isolated_decimal
    def check_invariants(self, tx: SqlExecutor, account_id: str) -> list[str]:
        failures: list[str] = []
        totals = self.totals(tx, account_id)
        if totals.cash < 0:
            failures.append("negative_cash")
        if totals.available < 0:
            failures.append("negative_available_cash")
        checks = {
            "order_account_missing": (
                "SELECT 1 FROM paper_order o WHERE o.account_id=? AND NOT EXISTS "
                "(SELECT 1 FROM paper_account a WHERE a.account_id=o.account_id)"
            ),
            "negative_position": "SELECT 1 FROM position WHERE account_id=? AND quantity<0",
            "fill_without_order": (
                "SELECT 1 FROM fill f LEFT JOIN paper_order o USING(order_id) "
                "WHERE (o.account_id=? OR o.order_id IS NULL) "
                "AND (o.order_id IS NULL OR o.status<>'filled')"
            ),
            "filled_order_without_fill": (
                "SELECT 1 FROM paper_order o WHERE o.account_id=? AND o.status='filled' "
                "AND (SELECT COUNT(*) FROM fill f WHERE f.order_id=o.order_id)<>1"
            ),
            "position_mismatch": (
                "WITH net AS (SELECT o.instrument_id, SUM(CASE WHEN o.side='buy' THEN "
                "f.quantity ELSE -f.quantity END) qty FROM fill f JOIN paper_order o "
                "USING(order_id) WHERE o.account_id=? GROUP BY o.instrument_id) "
                "SELECT 1 FROM net FULL JOIN (SELECT * FROM position WHERE account_id=?) p "
                "USING(instrument_id) WHERE COALESCE(qty,0)<>COALESCE(p.quantity,0)"
            ),
            "equity_mismatch": (
                "SELECT 1 FROM equity_snapshot WHERE account_id=? AND equity<>cash+positions_value"
            ),
            "reserved_mismatch": (
                "SELECT 1 FROM paper_order WHERE account_id=? AND ((status='pending' "
                "AND side='buy' AND (reserved_cash IS NULL OR reserved_cash<0)) "
                "OR ((status<>'pending' OR side='sell') AND reserved_cash IS NOT NULL))"
            ),
            "reserve_reference_mismatch": (
                "WITH net AS (SELECT ref_id, -SUM(amount) reserved FROM cash_ledger "
                "WHERE account_id=? AND entry_type IN ('reserve','release') GROUP BY ref_id) "
                "SELECT 1 FROM net LEFT JOIN paper_order o ON o.order_id=net.ref_id "
                "WHERE o.order_id IS NULL OR o.account_id<>? OR net.reserved<> "
                "CASE WHEN o.status='pending' AND o.side='buy' THEN o.reserved_cash ELSE 0 END"
            ),
            "fill_ledger_mismatch": (
                "SELECT 1 FROM fill f JOIN paper_order o USING(order_id) WHERE o.account_id=? "
                "AND ((SELECT COUNT(*) FROM cash_ledger l WHERE l.ref_id=f.fill_id "
                "AND l.account_id=o.account_id AND l.entry_type=o.side "
                "AND l.entry_date=f.filled_on "
                "AND l.amount=CASE WHEN o.side='buy' THEN -f.amount ELSE f.amount END)<>1 "
                "OR (SELECT COUNT(*) FROM cash_ledger l WHERE l.ref_id=f.fill_id "
                "AND l.account_id=o.account_id AND l.entry_type='fee' "
                "AND l.entry_date=f.filled_on AND l.amount=-f.fee)<>1)"
            ),
        }
        for name, sql in checks.items():
            tx.execute(sql, [account_id] * sql.count("?"))
            if tx.fetchone() is not None:
                failures.append(name)
        tx.execute(
            "SELECT COALESCE(SUM(reserved_cash),0) FROM paper_order "
            "WHERE account_id=? AND side='buy' AND status='pending'",
            [account_id],
        )
        row = tx.fetchone()
        assert row is not None
        if (
            totals.reserved < 0 or totals.reserved != row[0]
        ) and "reserved_mismatch" not in failures:
            failures.append("reserved_mismatch")
        tx.execute(
            "SELECT f.price, f.quantity, f.amount, o.quantity FROM fill f JOIN paper_order o "
            "USING(order_id) WHERE o.account_id=?",
            [account_id],
        )
        for p, qty, amount, ordered in tx.fetchall():
            if money(cast(Decimal, p) * cast(int, qty)) != amount or qty != ordered:
                failures.append("fill_amount_mismatch")
                break
        tx.execute(
            "SELECT snapshot_date, cash, positions_value, equity FROM equity_snapshot "
            "WHERE account_id=? ORDER BY snapshot_date DESC LIMIT 1",
            [account_id],
        )
        snapshot = tx.fetchone()
        account = self.account(tx, account_id, active=False)
        if snapshot and snapshot[0] == account.clock_date:
            portfolio = self.portfolio(tx, account_id)
            values = money(sum((p.market_value for p in portfolio.positions), Decimal(0)))
            if (
                tuple(snapshot[1:]) != (totals.cash, values, portfolio.equity)
                and "equity_mismatch" not in failures
            ):
                failures.append("equity_mismatch")
        return failures

    def assert_invariants(self, tx: SqlExecutor, account_id: str) -> None:
        violations = self.check_invariants(tx, account_id)
        if violations:
            _logger.error("paper.integrity.failed violations=%s", ",".join(violations))
            raise InternalError(reason="LEDGER_INVARIANT_FAILED", params={"violations": violations})
