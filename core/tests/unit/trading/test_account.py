from __future__ import annotations

import json
import random
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_DOWN, Decimal, Inexact, localcontext
from pathlib import Path

import pytest

from sentinel.errors import InternalError, UserError
from sentinel.markets.prices.calendar import next_trading_day
from sentinel.storage.db import Database, WriteTx
from sentinel.trading.account import PaperService
from sentinel.trading.ledger import Ledger
from sentinel.trading.rules import MarketRules, OrderIntent

NOW = datetime(2026, 11, 3, 12, tzinfo=UTC)
START = date(2026, 10, 26)
RANDOM_SEQUENCE_STEPS = 200
RANDOM_SEED = 20261102
ROOT = Path(__file__).resolve().parents[4]


@pytest.fixture
def service(tmp_path, monkeypatch):
    monkeypatch.setenv("SENTINEL_CLOCK", "2026-11-03T12:00:00Z")
    db = Database(tmp_path / "paper.duckdb")
    db.open()
    db.migrate()
    with db.write() as tx:
        for symbol in ("ZZAR", "ZZFD"):
            tx.execute(
                "INSERT INTO instrument VALUES (?, 'us', ?, 'NASDAQ', ?, NULL, "
                "'USD', NULL, TRUE, 'synthetic', ?)",
                [f"us:{symbol}", symbol, symbol, NOW],
            )
            for offset in range(5):
                day = START + timedelta(days=offset)
                tx.execute(
                    "INSERT INTO price_daily VALUES (?, ?, 100, 120, 90, 100, 100, "
                    "1000, 'synthetic', ?)",
                    [f"us:{symbol}", day, NOW],
                )
    result = PaperService(db, MarketRules(), clock=lambda: NOW)
    yield result
    db.close()


def account(service, cash="10000", name="Replay"):
    return service.create_account(name, Decimal(cash), START)


def intent(a, key="key", qty=1, side="buy", instrument="us:ZZAR"):
    return OrderIntent(a.account_id, instrument, side, qty, "market_open", key)


def rows(service, sql, params=()):
    with service.db.read() as tx:
        tx.execute(sql, params)
        return tx.fetchall()


def set_price(service, day, opening=100, closing=100, instrument="us:ZZAR"):
    with service.db.write() as tx:
        tx.execute(
            "UPDATE price_daily SET open=?, close=? WHERE instrument_id=? AND trade_date=?",
            [opening, closing, instrument, day],
        )


def test_place_same_key_same_params_returns_original(service):
    a = account(service)
    first = service.place_order(intent(a))
    assert service.place_order(intent(a)) == first
    assert len(rows(service, "SELECT * FROM cash_ledger WHERE entry_type='reserve'")) == 1


def test_place_same_key_different_params_conflicts(service):
    a = account(service)
    first = service.place_order(intent(a))
    with pytest.raises(UserError, match="CONFLICT"):
        service.place_order(intent(a, qty=2))
    assert service.list_orders(a.account_id).items == [first]


def test_business_rejection_is_saved_without_reserve(service):
    a = account(service, "1")
    with pytest.raises(UserError, match="ORDER_REJECTED") as caught:
        service.place_order(intent(a))
    order = service.list_orders(a.account_id).items[0]
    assert caught.value.params["orderId"] == order.order_id
    assert order.status == "rejected"
    assert order.reject_reason.code == "INSUFFICIENT_CASH"
    assert not rows(service, "SELECT * FROM cash_ledger WHERE entry_type='reserve'")
    assert service.place_order(intent(a)) == order


def test_parameter_error_is_not_saved(service):
    a = account(service)
    with pytest.raises(UserError, match="INVALID_ARGUMENT"):
        service.place_order(intent(a, qty=0))
    assert service.list_orders(a.account_id).items == []


def test_cancel_releases_exact_reserved_amount(service):
    a = account(service)
    set_price(service, START, closing=28.4)
    order = service.place_order(intent(a, qty=100))
    assert order.reserved_cash == Decimal("2841.4200")
    cancelled = service.cancel_order(order.order_id)
    assert cancelled.status == "cancelled" and cancelled.reserved_cash is None
    p = service.portfolio(a.account_id)
    assert p.cash == p.available_cash == Decimal("10000.0000")
    assert p.reserved_cash == 0
    amounts = rows(
        service, "SELECT entry_type, amount FROM cash_ledger WHERE ref_id=?", [order.order_id]
    )
    assert sorted(amounts) == [
        ("release", Decimal("2841.4200")),
        ("reserve", Decimal("-2841.4200")),
    ]
    with pytest.raises(UserError, match="CONFLICT"):
        service.cancel_order(order.order_id)


def test_advance_uses_next_day_open_not_clock_day_close(service):
    a = account(service)
    service.place_order(intent(a))
    set_price(service, START + timedelta(days=1), opening=110)
    result = service.advance(a.account_id)
    assert result.filled[0].fills[0].price == Decimal("110.055000")
    assert result.clock_date == START + timedelta(days=1)
    assert result.portfolio.as_of == result.clock_date


def test_advance_does_not_read_future_prices(service):
    a = account(service)
    service.place_order(intent(a))
    with service.db.write() as tx:
        tx.execute("DELETE FROM price_daily WHERE trade_date=?", [START + timedelta(days=1)])
    before = service.portfolio(a.account_id)
    with pytest.raises(UserError, match="DATA_INSUFFICIENT"):
        service.advance(a.account_id)
    assert service.portfolio(a.account_id) == before
    assert not rows(service, "SELECT * FROM fill")


def test_empty_account_advances_on_target_day_us_prices(service):
    a = account(service, "10000.1234")
    entries = rows(service, "SELECT * FROM cash_ledger ORDER BY entry_id")
    next_day = START + timedelta(days=1)
    result = service.advance(a.account_id)
    assert result.clock_date == result.portfolio.as_of == next_day
    assert result.portfolio.account.clock_date == next_day
    assert result.trading_day is True
    assert result.filled == result.rejected == result.portfolio.positions == []
    assert result.pending_remaining == result.portfolio.pending_orders == 0
    assert result.portfolio.cash == result.portfolio.available_cash == a.initial_cash
    assert result.portfolio.equity == a.initial_cash
    assert result.portfolio.reserved_cash == 0
    assert service.list_orders(a.account_id).items == []
    assert not rows(service, "SELECT * FROM fill")
    assert rows(service, "SELECT * FROM cash_ledger ORDER BY entry_id") == entries
    assert rows(service, "SELECT * FROM equity_snapshot") == [
        (a.account_id, next_day, a.initial_cash, Decimal("0.0000"), a.initial_cash)
    ]
    with service.db.read() as tx:
        Ledger().assert_invariants(tx, a.account_id)


@pytest.mark.parametrize("remaining", ["none", "non_us", "future_us"])
def test_empty_account_without_target_day_us_prices_does_not_advance(service, remaining):
    a = account(service)
    next_day = START + timedelta(days=1)
    with service.db.write() as tx:
        tx.execute("DELETE FROM price_daily")
        if remaining == "non_us":
            tx.execute(
                "INSERT INTO instrument VALUES ('hk:ZZBK', 'hk', 'ZZBK', 'HKEX', "
                "'Zinc Bay Bancorp', NULL, 'HKD', NULL, TRUE, 'synthetic', ?)",
                [NOW],
            )
        if remaining != "none":
            instrument_id = "hk:ZZBK" if remaining == "non_us" else "us:ZZAR"
            day = next_day if remaining == "non_us" else next_day + timedelta(days=1)
            tx.execute(
                "INSERT INTO price_daily VALUES (?, ?, 100, 120, 90, 100, 100, "
                "1000, 'synthetic', ?)",
                [instrument_id, day, NOW],
            )
    before = service.portfolio(a.account_id)
    entries = rows(service, "SELECT * FROM cash_ledger ORDER BY entry_id")
    with pytest.raises(UserError, match="DATA_INSUFFICIENT") as caught:
        service.advance(a.account_id)
    assert caught.value.params["nextDay"] == next_day.isoformat()
    assert service.portfolio(a.account_id) == before
    assert service.list_orders(a.account_id).items == []
    assert not rows(service, "SELECT * FROM fill")
    assert not rows(service, "SELECT * FROM equity_snapshot")
    assert rows(service, "SELECT * FROM cash_ledger ORDER BY entry_id") == entries


def test_involved_account_does_not_use_unrelated_target_day_us_prices(service):
    a = account(service)
    service.place_order(intent(a))
    next_day = START + timedelta(days=1)
    with service.db.write() as tx:
        tx.execute(
            "DELETE FROM price_daily WHERE instrument_id='us:ZZAR' AND trade_date=?",
            [next_day],
        )
    assert rows(
        service, "SELECT instrument_id FROM price_daily WHERE trade_date=?", [next_day]
    ) == [("us:ZZFD",)]
    before = service.portfolio(a.account_id)
    with pytest.raises(UserError, match="DATA_INSUFFICIENT"):
        service.advance(a.account_id)
    assert service.portfolio(a.account_id) == before
    assert service.list_orders(a.account_id).items[0].status == "pending"
    assert not rows(service, "SELECT * FROM fill")
    assert not rows(service, "SELECT * FROM equity_snapshot")


def test_advance_second_order_failure_rolls_back_all(service, monkeypatch):
    a = account(service)
    for key in ("one", "two", "three"):
        service.place_order(intent(a, key))
    before = service.portfolio(a.account_id)
    entries = rows(service, "SELECT * FROM cash_ledger ORDER BY entry_id")
    original = WriteTx.execute
    fills = 0

    def fail_second(tx, sql, params=None):
        nonlocal fills
        if sql.startswith("INSERT INTO fill"):
            fills += 1
            if fills == 2:
                raise RuntimeError("synthetic failure")
        return original(tx, sql, params)

    monkeypatch.setattr(WriteTx, "execute", fail_second)
    with pytest.raises(InternalError):
        service.advance(a.account_id)
    assert fills == 2
    assert service.portfolio(a.account_id) == before
    assert rows(service, "SELECT * FROM cash_ledger ORDER BY entry_id") == entries
    assert not rows(service, "SELECT * FROM fill")
    assert not rows(service, "SELECT * FROM equity_snapshot")
    assert all(o.status == "pending" for o in service.list_orders(a.account_id).items)


def test_gap_up_shortfall_rejects_and_releases(service):
    a = account(service, "110.0549")
    service.place_order(intent(a))
    set_price(service, START + timedelta(days=1), opening=110)
    result = service.advance(a.account_id)
    assert not result.filled
    assert result.rejected[0].reject_reason.code == "INSUFFICIENT_CASH_AT_FILL"
    assert result.portfolio.reserved_cash == 0
    assert result.portfolio.cash == Decimal("110.0549")
    assert len(rows(service, "SELECT * FROM cash_ledger WHERE entry_type='release'")) == 1


def test_reset_removes_only_target_account(service):
    a, b = account(service), account(service, name="Other")
    service.place_order(intent(a, "one"))
    service.advance(a.account_id)
    service.place_order(intent(b, "two"))
    before = service.portfolio(b.account_id)
    history = service.list_orders(b.account_id)
    service.reset(a.account_id, a.name)
    assert service.portfolio(b.account_id) == before
    assert service.list_orders(b.account_id) == history
    assert service.list_orders(a.account_id).items == []
    assert service.portfolio(a.account_id).cash == a.initial_cash
    assert service.portfolio(a.account_id).account.clock_date == START
    backups = list((service.db.path.parent / "backups").glob("*paper.reset*.duckdb"))
    assert len(backups) == 1
    backup = Database(backups[0], read_only=True)
    backup.open()
    with backup.read() as tx:
        tx.execute("SELECT COUNT(*) FROM fill")
        assert tx.fetchone()[0] == 1
    backup.close()


def test_random_200_step_ledger_invariants(service, monkeypatch):
    from sentinel.ids import new_id
    from sentinel.trading import account as account_module
    from sentinel.trading import ledger as ledger_module
    from sentinel.trading import matching as matching_module

    serial = 0

    def sequential_id():
        nonlocal serial
        serial += 1
        return new_id(timestamp_ms=1_793_707_200_000, entropy=serial.to_bytes(10, "big"))

    for module in (account_module, ledger_module, matching_module):
        monkeypatch.setattr(module, "new_id", sequential_id)
    a = account(service, "1000000")
    day = START
    with service.db.write() as tx:
        for _ in range(60):
            day = next_trading_day(day)
            tx.execute(
                "INSERT INTO price_daily VALUES ('us:ZZAR', ?, 100, 120, 90, 100, 100, "
                "1000, 'synthetic', ?) ON CONFLICT DO NOTHING",
                [day, NOW],
            )
    actions = [kind for kind in ("buy", "sell", "cancel", "advance") for _ in range(50)]
    rng = random.Random(RANDOM_SEED)
    rng.shuffle(actions)
    for n, kind in enumerate(actions):
        if kind in ("buy", "sell"):
            try:
                service.place_order(intent(a, f"random-{n}", qty=rng.randint(1, 10), side=kind))
            except UserError as exc:
                assert exc.code == "ORDER_REJECTED"
        elif kind == "cancel":
            pending = service.list_orders(a.account_id, status="pending").items
            if pending:
                service.cancel_order(rng.choice(pending).order_id)
        else:
            service.advance(a.account_id)
        with service.db.read() as tx:
            Ledger().assert_invariants(tx, a.account_id)
    assert len(actions) == RANDOM_SEQUENCE_STEPS


@pytest.mark.parametrize("cash", ["0", "-1", "NaN", "Infinity", "0.00001", "100000000000000"])
def test_initial_cash_boundaries_do_not_write(service, cash):
    with pytest.raises(UserError, match="INVALID_ARGUMENT"):
        account(service, cash)
    assert service.list_accounts() == []


def test_decimal_context_is_isolated(service):
    with localcontext() as ctx:
        ctx.prec = 3
        ctx.rounding = ROUND_DOWN
        ctx.traps[Inexact] = True
        a = account(service, "10000.1234")
        service.place_order(intent(a, qty=3))
        p = service.advance(a.account_id).portfolio
        assert p.cash == Decimal("9699.9734")
        assert p.positions[0].avg_cost == Decimal("100.050000")
        assert ctx.prec == 3 and ctx.rounding == ROUND_DOWN and not any(ctx.flags.values())


@pytest.mark.parametrize("backup_kind", ["raises", "missing", "empty"])
def test_failed_backup_preserves_all_data(service, monkeypatch, tmp_path, backup_kind):
    a = account(service)
    service.place_order(intent(a))
    before = service.list_orders(a.account_id)
    path = tmp_path / "bad.duckdb"
    if backup_kind == "empty":
        path.touch()

    def failed(label):
        assert label == "paper.reset"
        if backup_kind == "raises":
            raise OSError("synthetic backup failure")
        return path

    monkeypatch.setattr(service.db, "backup", failed)
    with pytest.raises(InternalError):
        service.reset(a.account_id, a.name)
    assert service.list_orders(a.account_id) == before


def test_reset_confirm_is_exact_and_precedes_backup(service, monkeypatch):
    a = account(service)
    monkeypatch.setattr(service.db, "backup", lambda _: pytest.fail("must not backup"))
    with pytest.raises(UserError, match="INVALID_ARGUMENT"):
        service.reset(a.account_id, a.name + " ")


def test_idempotency_across_status_and_accounts(service):
    a, b = account(service), account(service, name="Other")
    order = service.place_order(intent(a))
    service.advance(a.account_id)
    retry = service.place_order(intent(a))
    assert retry.order_id == order.order_id and retry.status == "filled" and len(retry.fills) == 1
    with pytest.raises(UserError, match="CONFLICT"):
        service.place_order(intent(b))


def test_history_pagination_and_stable_estimate(service):
    a = account(service)
    for n in range(5):
        service.place_order(intent(a, f"page-{n}"))
    full = service.list_orders(a.account_id).items
    page1 = service.list_orders(a.account_id, limit=2)
    page2 = service.list_orders(a.account_id, limit=2, cursor=page1.next_cursor)
    page3 = service.list_orders(a.account_id, limit=2, cursor=page2.next_cursor)
    assert page1.items + page2.items + page3.items == full
    assert page3.next_cursor is None
    assert service.list_orders(a.account_id, idempotency_key="page-1").items == [
        next(o for o in full if o.idempotency_key == "page-1")
    ]
    set_price(service, START, closing=200)
    service.rules = replace(service.rules, commission_min=Decimal("1"))
    assert service.list_orders(a.account_id).items == full


def test_missing_open_waits_then_rejects_without_repeated_release(service):
    a = account(service)
    order = service.place_order(intent(a))
    service.rules = replace(service.rules, max_wait_trading_days=2)
    for offset in (1, 2):
        set_price(service, START + timedelta(days=offset), opening=None)
    first = service.advance(a.account_id)
    assert first.pending_remaining == 1 and first.portfolio.reserved_cash == order.reserved_cash
    assert not rows(service, "SELECT * FROM cash_ledger WHERE entry_type='release'")
    second = service.advance(a.account_id)
    assert second.rejected[0].reject_reason.code == "NO_PRICE_AT_FILL"
    assert second.portfolio.reserved_cash == 0
    assert len(rows(service, "SELECT * FROM cash_ledger WHERE entry_type='release'")) == 1


def test_rpc_all_eight_validate_real_contract_results(service):
    from jsonschema import Draft202012Validator, FormatChecker
    from referencing import Registry, Resource

    from sentinel.rpc.cancel import CancelToken
    from sentinel.rpc.dispatcher import Dispatcher, RequestContext
    from sentinel.trading.rpc import register_handlers

    dispatcher = Dispatcher()
    register_handlers(dispatcher, service)
    schemas = ROOT / "contracts"
    types = json.loads((schemas / "types.schema.json").read_text())
    registry = Registry().with_resource("types.schema.json", Resource.from_contents(types))
    assert len(json.loads((schemas / "index.json").read_text())["methods"]) == 40
    assert len(dispatcher.methods()) == 8

    def call(method, params):
        spec = dispatcher.lookup(method)
        assert spec.result_model is not None and spec.cancellable is False
        token = CancelToken()
        token.cancel()
        response = dispatcher.dispatch(spec, params, RequestContext("test", method, token, NOW))
        assert "error" not in response, response
        contract = json.loads((schemas / "methods" / f"{method}.json").read_text())
        for key, value in (("params", params), ("result", response["result"])):
            Draft202012Validator(
                contract[key], registry=registry, format_checker=FormatChecker()
            ).validate(value)
        return response["result"]

    a = call(
        "paper.createAccount",
        {"name": "RPC", "initialCash": "10000.00", "startDate": START.isoformat()},
    )
    aid = a["accountId"]
    call("paper.accounts", {})
    call("paper.portfolio", {"accountId": aid})
    order = call(
        "paper.order.place",
        {
            "accountId": aid,
            "instrumentId": "us:ZZAR",
            "side": "buy",
            "quantity": 1,
            "orderType": "market_open",
            "idempotencyKey": "rpc",
        },
    )
    call("paper.orders", {"accountId": aid})
    call("paper.order.cancel", {"orderId": order["orderId"]})
    call(
        "paper.order.place",
        {
            "accountId": aid,
            "instrumentId": "us:ZZAR",
            "side": "buy",
            "quantity": 1,
            "orderType": "market_open",
            "idempotencyKey": "rpc-fill",
        },
    )
    call("paper.advance", {"accountId": aid})
    call("paper.reset", {"accountId": aid, "confirmText": "RPC"})


@pytest.mark.parametrize(
    "method,params",
    [
        ("paper.createAccount", {"name": "RPC", "initial_cash": "1", "startDate": "2026-10-26"}),
        ("paper.createAccount", {"name": "RPC", "initialCash": 1.0, "startDate": "2026-10-26"}),
        ("paper.createAccount", {"name": "RPC", "initialCash": "1e2", "startDate": "2026-10-26"}),
        ("paper.createAccount", {"name": "RPC", "initialCash": "1", "startDate": "2026-02-30"}),
        ("paper.portfolio", {"account_id": "x"}),
        ("paper.orders", {"accountId": "x", "status": None}),
        ("paper.orders", {"accountId": "x", "limit": True}),
        ("paper.orders", {"accountId": "x", "limit": "2"}),
        ("paper.accounts", {"extra": 1}),
    ],
)
def test_rpc_rejects_non_json_contract_parameters(service, method, params):
    from sentinel.rpc.cancel import CancelToken
    from sentinel.rpc.dispatcher import Dispatcher, RequestContext
    from sentinel.trading.rpc import register_handlers

    dispatcher = Dispatcher()
    register_handlers(dispatcher, service)
    result = dispatcher.dispatch(
        dispatcher.lookup(method), params, RequestContext("bad", method, CancelToken(), NOW)
    )
    assert result["error"]["code"] == "INVALID_ARGUMENT"


def test_create_name_calendar_and_maximum_cash(service):
    from sentinel.trading.models import MAX_MONEY

    a = account(service, str(MAX_MONEY), name="  Replay  ")
    assert a.name == "Replay" and a.initial_cash == MAX_MONEY
    assert service.portfolio(a.account_id).cash == MAX_MONEY
    with pytest.raises(UserError, match="CONFLICT"):
        account(service, name="Replay")
    for name in ("", "   ", "a" * 31):
        with pytest.raises(UserError, match="INVALID_ARGUMENT"):
            account(service, name=name)
    for day in (date(2026, 10, 25), date(2026, 12, 25)):
        with pytest.raises(UserError, match="INVALID_ARGUMENT"):
            service.create_account("Wrong day", Decimal("1"), day)
    assert len(service.list_accounts()) == 1


@pytest.mark.parametrize(
    "changes",
    [
        {"quantity": True},
        {"quantity": 1.5},
        {"quantity": 1_000_001},
        {"side": "short"},
        {"order_type": "limit"},
        {"idempotency_key": ""},
        {"idempotency_key": "x" * 65},
    ],
)
def test_invalid_intent_leaves_no_history(service, changes):
    a = account(service)
    with pytest.raises(UserError, match="INVALID_ARGUMENT"):
        service.place_order(replace(intent(a), **changes))
    assert not service.list_orders(a.account_id).items


def test_retry_bypasses_new_pending_limit_and_inactive_instrument(service):
    a = account(service)
    order = service.place_order(intent(a))
    service.rules = replace(service.rules, max_pending_orders=1)
    with service.db.write() as tx:
        tx.execute("UPDATE instrument SET is_active=FALSE WHERE instrument_id='us:ZZAR'")
    retry = service.place_order(intent(a))
    assert retry.order_id == order.order_id and retry.reserved_cash == order.reserved_cash
    with pytest.raises(UserError, match="NOT_FOUND"):
        service.place_order(intent(a, "new"))


def test_rejection_reason_survives_reopen_and_wire_is_localized(service):
    a = account(service, "1")
    with pytest.raises(UserError, match="ORDER_REJECTED") as caught:
        service.place_order(intent(a, qty=10))
    wire = caught.value.to_wire("reject")
    assert "$1,000.50" in wire["message"] and "$1.00" in wire["message"]
    assert wire["data"]["required"] == "1000.5000"
    oid = wire["data"]["orderId"]
    service.db.close()
    service.db.open()
    recovered = service.place_order(intent(a, qty=10))
    assert recovered.order_id == oid and recovered.reject_reason.message == wire["message"]


def test_no_clock_date_close_is_a_saved_rejection(service):
    a = account(service)
    service.place_order(intent(a))
    service.advance(a.account_id)
    with service.db.write() as tx:
        tx.execute(
            "UPDATE price_daily SET close=NULL WHERE trade_date=?", [START + timedelta(days=1)]
        )
    with pytest.raises(UserError, match="ORDER_REJECTED") as caught:
        service.place_order(intent(a, "missing-close"))
    assert caught.value.reason == "NO_PRICE"
    assert service.place_order(intent(a, "missing-close")).status == "rejected"


def test_pending_sells_claim_shares_and_sell_before_buy(service):
    a = account(service, "200.20")
    service.place_order(intent(a, "initial"))
    service.advance(a.account_id)
    service.place_order(intent(a, "buy-next"))
    sell = service.place_order(intent(a, "sell-next", side="sell"))
    assert sell.reserved_cash is None
    with pytest.raises(UserError, match="ORDER_REJECTED") as caught:
        service.place_order(intent(a, "oversell", side="sell"))
    assert caught.value.reason == "INSUFFICIENT_POSITION"
    set_price(service, START + timedelta(days=2), opening=110)
    result = service.advance(a.account_id)
    assert [o.side for o in result.filled] == ["sell", "buy"]
    assert result.portfolio.positions[0].quantity == 1


def test_one_gap_rejects_while_other_order_fills(service):
    a = account(service, "201")
    service.place_order(intent(a, "one"))
    service.place_order(intent(a, "two"))
    set_price(service, START + timedelta(days=1), opening=110)
    result = service.advance(a.account_id)
    assert len(result.rejected) == len(result.filled) == 1
    assert result.portfolio.reserved_cash == 0
    assert result.portfolio.cash == Decimal("90.9450")


def test_missing_instrument_bar_waits_with_other_target_day_data(service):
    a = account(service)
    order = service.place_order(intent(a, "missing"))
    service.place_order(intent(a, "present", instrument="us:ZZFD"))
    with service.db.write() as tx:
        tx.execute(
            "DELETE FROM price_daily WHERE instrument_id='us:ZZAR' AND trade_date=?",
            [START + timedelta(days=1)],
        )
    result = service.advance(a.account_id)
    assert len(result.filled) == 1 and result.pending_remaining == 1
    assert result.portfolio.reserved_cash == order.reserved_cash


def test_portfolio_uses_stale_close_and_ignores_future(service, caplog):
    a = account(service)
    service.place_order(intent(a))
    service.advance(a.account_id)
    set_price(service, START + timedelta(days=2), closing=99999)
    set_price(service, START + timedelta(days=1), closing=None)
    p = service.portfolio(a.account_id)
    assert p.positions[0].last_close == 100.0
    assert p.positions[0].market_value == Decimal("100.0000")
    assert "paper.valuation.stale" in caplog.text


@pytest.mark.parametrize("stage", ["snapshot", "clock", "invariant", "sql"])
def test_advance_late_failure_preserves_every_table(service, monkeypatch, stage):
    a = account(service)
    service.place_order(intent(a))
    tables = ("paper_account", "paper_order", "cash_ledger", "position", "fill", "equity_snapshot")
    before = {t: rows(service, f"SELECT * FROM {t} ORDER BY 1") for t in tables}
    original = WriteTx.execute

    def fail(tx, sql, params=None):
        if stage == "snapshot" and sql.startswith("INSERT INTO equity_snapshot"):
            raise RuntimeError("synthetic snapshot failure")
        if stage == "clock" and sql.startswith("UPDATE paper_account SET clock_date="):
            raise ValueError("synthetic clock failure")
        if stage == "sql" and sql.startswith("INSERT INTO fill"):
            return original(tx, "INSERT INTO table_that_does_not_exist VALUES (1)")
        if stage == "invariant" and sql.startswith("INSERT INTO equity_snapshot"):
            original(tx, sql, params)
            return original(tx, "UPDATE position SET quantity=99")
        return original(tx, sql, params)

    monkeypatch.setattr(WriteTx, "execute", fail)
    with pytest.raises(InternalError):
        service.advance(a.account_id)
    assert {t: rows(service, f"SELECT * FROM {t} ORDER BY 1") for t in tables} == before


@pytest.mark.parametrize("opening", [float("nan"), float("inf"), -1, 1e13])
def test_invalid_or_unstorable_fill_price_rolls_back(service, opening):
    a = account(service, "99999999999999")
    service.place_order(intent(a))
    set_price(service, START + timedelta(days=1), opening=opening)
    before = service.portfolio(a.account_id)
    with pytest.raises(InternalError):
        service.advance(a.account_id)
    assert service.portfolio(a.account_id) == before
    assert not rows(service, "SELECT * FROM fill")


def test_equity_overflow_is_not_silently_rounded_or_committed(service):
    a = account(service, "99999999999999")
    service.place_order(intent(a))
    set_price(service, START + timedelta(days=1), closing=1000)
    with pytest.raises(InternalError):
        service.advance(a.account_id)
    assert service.portfolio(a.account_id).account.clock_date == START
    assert not rows(service, "SELECT * FROM fill")


def test_reset_delete_failure_rolls_back_and_backup_retains_history(service, monkeypatch):
    a = account(service)
    service.place_order(intent(a))
    service.advance(a.account_id)
    before = service.portfolio(a.account_id)
    original = WriteTx.execute

    def fail(tx, sql, params=None):
        if sql.startswith("DELETE FROM position"):
            raise RuntimeError("synthetic reset failure")
        return original(tx, sql, params)

    monkeypatch.setattr(WriteTx, "execute", fail)
    with pytest.raises(InternalError):
        service.reset(a.account_id, a.name)
    assert service.portfolio(a.account_id) == before
    assert service.list_orders(a.account_id).items[0].status == "filled"
    assert list((service.db.path.parent / "backups").glob("*paper.reset*.duckdb"))


def test_migration_is_verbatim_and_idempotent(service):
    text = (ROOT / "docs/04-数据模型.md").read_text()
    section = text.split("### 3.10 `010_paper.sql`", 1)[1].split("### 3.11", 1)[0]
    expected = section.split("```sql\n", 1)[1].split("```", 1)[0]
    assert (ROOT / "core/sentinel/storage/migrations/010_paper.sql").read_text() == expected
    service.db.migrate()
    assert rows(service, "SELECT COUNT(*) FROM schema_version WHERE version=10") == [(1,)]


def test_all_eight_handlers_through_ndjson_server(service):
    from io import BytesIO

    from sentinel.rpc import Dispatcher, RpcServer, ServerConfig
    from sentinel.rpc.protocol import serialize
    from sentinel.trading.rpc import register_handlers

    a = account(service)
    pending = service.place_order(intent(a, "cancel-wire"))
    calls = [
        ("paper.accounts", {}),
        (
            "paper.createAccount",
            {"name": "Wire", "initialCash": "10.00", "startDate": START.isoformat()},
        ),
        ("paper.portfolio", {"accountId": a.account_id}),
        (
            "paper.order.place",
            {
                "accountId": a.account_id,
                "instrumentId": "us:ZZAR",
                "side": "buy",
                "quantity": 1,
                "orderType": "market_open",
                "idempotencyKey": "fill-wire",
            },
        ),
        ("paper.orders", {"accountId": a.account_id}),
        ("paper.order.cancel", {"orderId": pending.order_id}),
        ("paper.advance", {"accountId": a.account_id}),
        ("paper.reset", {"accountId": a.account_id, "confirmText": a.name}),
    ]
    incoming = []
    for n, (method, params) in enumerate(calls):
        incoming.append(
            serialize({"jsonrpc": "2.0", "id": str(n), "method": method, "params": params})
        )
        incoming.append(
            serialize({"jsonrpc": "2.0", "method": "$/cancel", "params": {"id": str(n)}})
        )
    dispatcher = Dispatcher()
    register_handlers(dispatcher, service)
    output = BytesIO()
    server = RpcServer(BytesIO(b"".join(incoming)), output, dispatcher, ServerConfig(workers=1))
    server.serve_forever()
    responses = [json.loads(line) for line in output.getvalue().splitlines()]
    assert len(responses) == 8 and all("result" in r for r in responses), responses
    assert {r["id"] for r in responses} == {str(n) for n in range(8)}
    advanced = next(r["result"] for r in responses if r["id"] == "6")
    assert advanced["filled"][0]["fills"][0]["price"] == "100.050000"
    assert service.list_orders(a.account_id).items == []


def test_concurrent_same_key_across_database_handles_reserves_once(service):
    from concurrent.futures import ThreadPoolExecutor

    a = account(service)
    second_db = Database(service.db.path)
    second_db.open()
    second = PaperService(second_db, service.rules, clock=lambda: NOW)
    try:
        with ThreadPoolExecutor(max_workers=8) as pool:
            futures = [
                pool.submit((service if n % 2 else second).place_order, intent(a)) for n in range(8)
            ]
            orders = [f.result(timeout=5) for f in futures]
        assert len({o.order_id for o in orders}) == 1
        assert len(rows(service, "SELECT * FROM cash_ledger WHERE entry_type='reserve'")) == 1
        with service.db.read() as tx:
            Ledger().assert_invariants(tx, a.account_id)
    finally:
        second_db.close()


def test_reset_serializes_backup_and_delete_with_other_handles(service, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    a = account(service)
    service.place_order(intent(a, "before-backup"))
    second_db = Database(service.db.path)
    second_db.open()
    second = PaperService(second_db, service.rules, clock=lambda: NOW)
    backup_finished, release_reset, placing = Event(), Event(), Event()
    original = service.db.backup

    def paused_backup(label):
        path = original(label)
        backup_finished.set()
        assert release_reset.wait(5)
        return path

    def place_after_backup():
        placing.set()
        return second.place_order(intent(a, "after-backup"))

    monkeypatch.setattr(service.db, "backup", paused_backup)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            reset_future = pool.submit(service.reset, a.account_id, a.name)
            assert backup_finished.wait(5)
            place_future = pool.submit(place_after_backup)
            try:
                assert placing.wait(5)
                assert not place_future.done()
            finally:
                release_reset.set()
            reset_future.result(timeout=5)
            order = place_future.result(timeout=5)
        assert service.list_orders(a.account_id).items == [order]
        assert order.idempotency_key == "after-backup"
    finally:
        release_reset.set()
        second_db.close()


def test_result_model_rejects_invalid_service_output(service, monkeypatch):
    from sentinel.rpc.cancel import CancelToken
    from sentinel.rpc.dispatcher import Dispatcher, RequestContext
    from sentinel.trading.rpc import register_handlers

    dispatcher = Dispatcher()
    register_handlers(dispatcher, service)
    monkeypatch.setattr(service, "portfolio", lambda _: {"cash": 1.0})
    response = dispatcher.dispatch(
        dispatcher.lookup("paper.portfolio"),
        {"accountId": "invalid"},
        RequestContext("bad-result", "paper.portfolio", CancelToken(), NOW),
    )
    assert response["error"]["code"] == "INTERNAL"
