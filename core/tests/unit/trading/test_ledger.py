from dataclasses import replace
from decimal import Decimal

import pytest

from sentinel.errors import InternalError
from sentinel.trading.ledger import Ledger
from tests.unit.trading.test_account import NOW, START, account, intent, rows
from tests.unit.trading.test_account import service as service


def entry(service, aid, kind, amount):
    with service.db.write() as tx:
        Ledger().append(tx, aid, START, kind, Decimal(amount), None, NOW)


def test_cash_is_sum_of_real_entries(service):
    a = account(service)
    for kind, amount in (("reserve", "-500"), ("buy", "-4000"), ("fee", "-1")):
        entry(service, a.account_id, kind, amount)
    with service.db.read() as tx:
        totals = Ledger().totals(tx, a.account_id)
    assert (totals.cash, totals.reserved, totals.available) == (
        Decimal("5999.0000"),
        Decimal("500.0000"),
        Decimal("5499.0000"),
    )


def test_reserved_equals_pending_buy_sum(service):
    service.rules = replace(service.rules, slippage_bps=Decimal("0"))
    a = account(service)
    for key, quantity in (("one", 10), ("two", 5)):
        service.place_order(intent(a, key, qty=quantity))
    with service.db.read() as tx:
        assert Ledger().totals(tx, a.account_id).reserved == Decimal("1500.0000")
        Ledger().assert_invariants(tx, a.account_id)
    entry(service, a.account_id, "reserve", "-0.0001")
    with service.db.read() as tx, pytest.raises(InternalError) as caught:
        Ledger().assert_invariants(tx, a.account_id)
    assert "reserved_mismatch" in caught.value.params["violations"]


def test_negative_cash_is_detected(service):
    a = account(service, "1")
    entry(service, a.account_id, "buy", "-2")
    with service.db.read() as tx:
        assert "negative_cash" in Ledger().check_invariants(tx, a.account_id)


@pytest.mark.parametrize(
    "corruption,violation",
    [
        ("UPDATE position SET quantity=-1", "negative_position"),
        ("UPDATE position SET quantity=7", "position_mismatch"),
        ("UPDATE fill SET amount=1", "fill_amount_mismatch"),
        ("UPDATE equity_snapshot SET equity=1", "equity_mismatch"),
        ("DELETE FROM fill", "filled_order_without_fill"),
        ("UPDATE paper_order SET status='pending'", "fill_without_order"),
        (
            "UPDATE cash_ledger SET ref_id='missing' WHERE entry_type='release'",
            "reserve_reference_mismatch",
        ),
        ("DELETE FROM cash_ledger WHERE entry_type='fee'", "fill_ledger_mismatch"),
    ],
)
def test_integrity_detects_corruption_without_writing(service, corruption, violation):
    a = account(service)
    service.place_order(intent(a))
    service.advance(a.account_id)
    with service.db.write() as tx:
        tx.execute(corruption)
    before = rows(service, "SELECT * FROM cash_ledger ORDER BY entry_id")
    with service.db.read() as tx:
        assert violation in Ledger().check_invariants(tx, a.account_id)
    assert rows(service, "SELECT * FROM cash_ledger ORDER BY entry_id") == before
