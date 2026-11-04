from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import cast

from sentinel import clock as system_clock
from sentinel.errors import InternalError, SentinelError, UserError
from sentinel.ids import new_id
from sentinel.markets.prices.calendar import next_trading_day
from sentinel.storage.db import Database, WriteTx

from .ledger import ACCOUNT_COLUMNS, ORDER_COLUMNS, Ledger
from .matching import OrderRejectedError, execute_order, rejection_message
from .models import (
    MAX_MONEY,
    MAX_POSITION_QUANTITY,
    AdvanceResult,
    OrderRow,
    PaperAccountView,
    PaperOrderPage,
    PaperOrderView,
    PortfolioView,
    RejectCode,
    isolated_decimal,
    money,
    price,
)
from .rules import (
    MONEY_QUANTUM,
    MarketRules,
    MarketSnapshot,
    OrderIntent,
    precheck,
    request_hash,
    validate_parameters,
)

MAX_ACCOUNT_NAME_CODEPOINTS = 30
INITIAL_CASH_QUANTUM = MONEY_QUANTUM
DEFAULT_ORDER_LIMIT = 50
MAX_ORDER_LIMIT = 200


class PaperService:
    def __init__(
        self,
        db: Database,
        rules: MarketRules,
        clock: Callable[[], datetime] = system_clock.now,
    ) -> None:
        self.db, self.rules, self.clock = db, rules, clock
        self.ledger = Ledger()

    @contextmanager
    def _write(self) -> Iterator[WriteTx]:
        try:
            with self.db.write() as tx:
                yield tx
        except SentinelError:
            raise
        except Exception as exc:
            raise InternalError(
                reason="PAPER_TRANSACTION_FAILED", detail=type(exc).__name__
            ) from exc

    def _now(self) -> datetime:
        now = self.clock()
        system_clock.to_iso(now)
        return now

    def list_accounts(self) -> list[PaperAccountView]:
        with self.db.read() as tx:
            tx.execute(
                f"SELECT {ACCOUNT_COLUMNS} FROM paper_account WHERE archived_at IS NULL "
                "ORDER BY created_at, account_id"
            )
            return [
                PaperAccountView.model_validate(
                    dict(zip(PaperAccountView.model_fields, r, strict=True))
                )
                for r in tx.fetchall()
            ]

    @isolated_decimal
    def create_account(
        self, name: str, initial_cash: Decimal, start_date: date
    ) -> PaperAccountView:
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= MAX_ACCOUNT_NAME_CODEPOINTS:
            raise UserError("INVALID_ARGUMENT", field="name")
        name = name.strip()
        if (
            not isinstance(initial_cash, Decimal)
            or not initial_cash.is_finite()
            or not 0 < initial_cash <= MAX_MONEY
            or cast(int, initial_cash.as_tuple().exponent) < -4
        ):
            raise UserError("INVALID_ARGUMENT", field="initialCash")
        if type(start_date) is not date or start_date == date.min or start_date == date.max:
            raise UserError("INVALID_ARGUMENT", field="startDate")
        if next_trading_day(start_date - timedelta(days=1)) != start_date:
            raise UserError("INVALID_ARGUMENT", field="startDate")
        initial_cash = money(initial_cash)
        aid, now = new_id(), self._now()
        with self._write() as tx:
            tx.execute("SELECT 1 FROM paper_account WHERE name=?", [name])
            if tx.fetchone() is not None:
                raise UserError("CONFLICT", field="name")
            tx.execute(
                "INSERT INTO paper_account(account_id, name, base_currency, initial_cash, "
                "start_date, clock_date, created_at) "
                "VALUES (?, ?, 'USD', ?, ?, ?, ?)",
                [aid, name, initial_cash, start_date, start_date, now],
            )
            self.ledger.append(tx, aid, start_date, "deposit", initial_cash, None, now)
            view = self.ledger.account(tx, aid)
        return view

    def portfolio(self, account_id: str) -> PortfolioView:
        with self.db.read() as tx:
            return self.ledger.portfolio(tx, account_id)

    @isolated_decimal
    def place_order(self, intent: OrderIntent) -> PaperOrderView:
        if not isinstance(intent, OrderIntent):
            raise UserError("INVALID_ARGUMENT", field="intent")
        reject = None
        with self._write() as tx:
            account = self.ledger.account(tx, intent.account_id)
            digest = request_hash(intent.account_id, intent)
            tx.execute(
                f"SELECT {ORDER_COLUMNS} FROM paper_order WHERE idempotency_key=?",
                [intent.idempotency_key],
            )
            stored = tx.fetchone()
            if stored is not None:
                order = self.ledger.order_row(stored)
                if order.request_hash != digest:
                    raise UserError("CONFLICT", field="idempotencyKey")
                return self.ledger.order_view(tx, order)
            instrument = self.ledger.instrument(tx, intent.instrument_id)
            if (
                not instrument.is_active
                or instrument.market != "us"
                or instrument.currency != "USD"
            ):
                raise UserError("NOT_FOUND", field="instrumentId")
            validate_parameters(
                intent, self.ledger.pending_count(tx, account.account_id), self.rules
            )
            if intent.quantity > MAX_POSITION_QUANTITY:
                raise UserError("INVALID_ARGUMENT", field="quantity")
            close = self.ledger.close_on(tx, intent.instrument_id, account.clock_date)
            totals = self.ledger.totals(tx, account.account_id)
            result = precheck(
                intent,
                MarketSnapshot(account.clock_date, close, self.rules.max_order_quantity),
                totals.available,
                self.ledger.position_quantity(tx, account.account_id, intent.instrument_id),
                self.ledger.pending_sell_quantity(tx, account.account_id, intent.instrument_id),
                self.rules,
            )
            reject, estimate = result.reject, result.estimate
            if estimate is not None:
                # 外部参数形成的估算越界必须在写订单之前拒绝。
                try:
                    price(estimate.price)
                    money(estimate.amount)
                    money(estimate.fee)
                    money(estimate.required)
                except InternalError as exc:
                    raise UserError(
                        "INVALID_ARGUMENT", field="quantity", reason="ESTIMATE_OVERFLOW"
                    ) from exc
            now, oid = self._now(), new_id()
            message = rejection_message(reject) if reject else None
            order = OrderRow(
                order_id=oid,
                account_id=account.account_id,
                instrument_id=intent.instrument_id,
                side=intent.side,
                quantity=intent.quantity,
                order_type=intent.order_type,
                status="rejected" if reject else "pending",
                reject_code=cast(RejectCode, reject.code) if reject else None,
                reject_message=message,
                created_clock_date=account.clock_date,
                estimate_price=estimate.price if estimate else None,
                reserved_cash=estimate.required if estimate else None,
                idempotency_key=intent.idempotency_key,
                request_hash=digest,
                created_at=now,
                updated_at=now,
            )
            placeholders = ",".join("?" for _ in OrderRow.model_fields)
            tx.execute(
                f"INSERT INTO paper_order({ORDER_COLUMNS}) VALUES ({placeholders})",
                list(order.model_dump().values()),
            )
            if estimate is not None:
                self.ledger.append(
                    tx,
                    account.account_id,
                    account.clock_date,
                    "reserve",
                    -estimate.required,
                    oid,
                    now,
                )
            view = self.ledger.order_view(tx, order)
        if reject:
            # 只有 COMMIT 成功后才抛错，orderId 此时可被历史查询和幂等重试读到。
            raise OrderRejectedError(reject, oid)
        return view

    def cancel_order(self, order_id: str) -> PaperOrderView:
        with self._write() as tx:
            order = self.ledger.order(tx, order_id)
            account = self.ledger.account(tx, order.account_id)
            if order.status != "pending":
                raise UserError("CONFLICT", field="orderId")
            now = self._now()
            if order.reserved_cash is not None:
                self.ledger.append(
                    tx,
                    order.account_id,
                    account.clock_date,
                    "release",
                    order.reserved_cash,
                    order.order_id,
                    now,
                )
            tx.execute(
                "UPDATE paper_order SET status='cancelled', reserved_cash=NULL, updated_at=? "
                "WHERE order_id=?",
                [now, order_id],
            )
            view = self.ledger.order_view(tx, self.ledger.order(tx, order_id))
        return view

    def list_orders(
        self,
        account_id: str,
        status: str | None = None,
        limit: int = DEFAULT_ORDER_LIMIT,
        cursor: str | None = None,
        idempotency_key: str | None = None,
    ) -> PaperOrderPage:
        if type(limit) is not int or not 1 <= limit <= MAX_ORDER_LIMIT:
            raise UserError("INVALID_ARGUMENT", field="limit")
        if status is not None and status not in ("pending", "filled", "rejected", "cancelled"):
            raise UserError("INVALID_ARGUMENT", field="status")
        if idempotency_key is not None and (
            not isinstance(idempotency_key, str) or not 1 <= len(idempotency_key) <= 64
        ):
            raise UserError("INVALID_ARGUMENT", field="idempotencyKey")
        clauses, params = ["account_id=?"], [cast(object, account_id)]
        if status is not None:
            clauses.append("status=?")
            params.append(status)
        if idempotency_key is not None:
            clauses.append("idempotency_key=?")
            params.append(idempotency_key)
        with self.db.read() as tx:
            self.ledger.account(tx, account_id)
            if cursor is not None:
                tx.execute(
                    "SELECT created_at, order_id FROM paper_order "
                    "WHERE order_id=? AND account_id=?",
                    [cursor, account_id],
                )
                row = tx.fetchone()
                if row is None:
                    raise UserError("INVALID_ARGUMENT", field="cursor")
                clauses.append("(created_at, order_id)<(?, ?)")
                params.extend(row)
            tx.execute(
                f"SELECT {ORDER_COLUMNS} FROM paper_order WHERE {' AND '.join(clauses)} "
                "ORDER BY created_at DESC, order_id DESC LIMIT ?",
                [*params, limit + 1],
            )
            orders = [self.ledger.order_row(r) for r in tx.fetchall()]
            return PaperOrderPage(
                items=[self.ledger.order_view(tx, o) for o in orders[:limit]],
                next_cursor=orders[limit - 1].order_id if len(orders) > limit else None,
            )

    @isolated_decimal
    def advance(self, account_id: str) -> AdvanceResult:
        with self._write() as tx:
            account = self.ledger.account(tx, account_id)
            next_day = next_trading_day(account.clock_date)
            if not self.ledger.has_prices_on(tx, account_id, next_day):
                raise UserError("DATA_INSUFFICIENT", params={"nextDay": next_day.isoformat()})
            try:
                return self._advance(tx, account, next_day)
            except InternalError:
                raise
            except Exception as exc:
                raise InternalError(
                    reason="PAPER_ADVANCE_FAILED", detail=type(exc).__name__
                ) from exc

    def _advance(self, tx: WriteTx, account: PaperAccountView, next_day: date) -> AdvanceResult:
        account_id = account.account_id
        self.ledger.assert_invariants(tx, account_id)
        tx.execute(
            f"SELECT {ORDER_COLUMNS} FROM paper_order WHERE account_id=? AND status='pending' "
            "ORDER BY CASE WHEN side='sell' THEN 0 ELSE 1 END, created_at, order_id",
            [account_id],
        )
        orders = [self.ledger.order_row(r) for r in tx.fetchall()]
        filled: list[PaperOrderView] = []
        rejected: list[PaperOrderView] = []
        now = self._now()
        for order in orders:
            outcome = execute_order(
                tx,
                order,
                next_day,
                self.ledger.open_on(tx, order.instrument_id, next_day),
                self.rules,
                now=now,
            )
            if outcome.kind != "pending":
                view = self.ledger.order_view(tx, self.ledger.order(tx, order.order_id))
                (filled if outcome.kind == "filled" else rejected).append(view)
        tx.execute(
            "UPDATE paper_account SET clock_date=? WHERE account_id=?", [next_day, account_id]
        )
        portfolio = self.ledger.portfolio(tx, account_id)
        values = money(sum((p.market_value for p in portfolio.positions), Decimal(0)))
        tx.execute(
            "INSERT INTO equity_snapshot VALUES (?, ?, ?, ?, ?)",
            [account_id, next_day, portfolio.cash, values, portfolio.equity],
        )
        self.ledger.assert_invariants(tx, account_id)
        result = AdvanceResult(
            clock_date=next_day,
            trading_day=True,
            filled=filled,
            rejected=rejected,
            pending_remaining=portfolio.pending_orders,
            portfolio=portfolio,
        )
        return result

    def reset(self, account_id: str, confirm_text: str) -> None:
        # 与 Database 的所有句柄共用锁，备份与删除之间不能插入未备份的订单。
        with self.db.exclusive():
            self._reset(account_id, confirm_text)

    def _reset(self, account_id: str, confirm_text: str) -> None:
        with self.db.read() as tx:
            account = self.ledger.account(tx, account_id)
        if not isinstance(confirm_text, str) or confirm_text != account.name:
            raise UserError("INVALID_ARGUMENT", field="confirmText")
        try:
            backup = self.db.backup("paper.reset")
            if not isinstance(backup, Path) or not backup.is_file() or backup.stat().st_size == 0:
                raise OSError("backup is missing or empty")
        except Exception as exc:
            raise InternalError(reason="PAPER_BACKUP_FAILED", detail=type(exc).__name__) from exc
        with self._write() as tx:
            current = self.ledger.account(tx, account_id)
            if current != account:
                raise UserError(
                    "CONFLICT", field="accountId", reason="ACCOUNT_CHANGED_DURING_BACKUP"
                )
            tx.execute(
                "DELETE FROM fill WHERE order_id IN "
                "(SELECT order_id FROM paper_order WHERE account_id=?)",
                [account_id],
            )
            for table in ("paper_order", "position", "cash_ledger", "equity_snapshot"):
                tx.execute(f"DELETE FROM {table} WHERE account_id=?", [account_id])
            tx.execute(
                "UPDATE paper_account SET clock_date=start_date WHERE account_id=?", [account_id]
            )
            self.ledger.append(
                tx,
                account_id,
                account.start_date,
                "deposit",
                account.initial_cash,
                None,
                self._now(),
            )
            self.ledger.assert_invariants(tx, account_id)
