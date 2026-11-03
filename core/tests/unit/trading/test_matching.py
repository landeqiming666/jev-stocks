from dataclasses import replace
from datetime import timedelta
from decimal import Decimal

import pytest
from test_account import START, account, intent, rows, set_price
from test_account import service as service

from sentinel.errors import InternalError
from sentinel.storage.db import WriteTx


def test_buy_fill_updates_avg_cost_with_fee(service):
    service.rules = replace(service.rules, slippage_bps=Decimal("0"), commission_min=Decimal("1"))
    a = account(service, "100000")
    service.place_order(intent(a, "first", qty=100))
    set_price(service, START + timedelta(days=1), opening=49.9, closing=50)
    first = service.advance(a.account_id).portfolio
    assert first.positions[0].avg_cost == Decimal("49.910000")
    service.place_order(intent(a, "second", qty=50))
    set_price(service, START + timedelta(days=2), opening=52)
    second = service.advance(a.account_id).portfolio
    assert second.positions[0].quantity == 150
    assert second.positions[0].avg_cost == Decimal("50.613333")


def test_sell_fill_keeps_avg_cost(service):
    service.rules = replace(service.rules, commission_min=Decimal("1"))
    a = account(service, "100000")
    service.place_order(intent(a, "buy", qty=100))
    set_price(service, START + timedelta(days=1), opening=51.1)
    first = service.advance(a.account_id).portfolio
    assert first.positions[0].avg_cost == Decimal("51.135550")
    service.place_order(intent(a, "first-sell", qty=40, side="sell"))
    before = service.advance(a.account_id).portfolio
    assert before.positions[0].quantity == 60
    service.place_order(intent(a, "second-sell", qty=40, side="sell"))
    after = service.advance(a.account_id).portfolio
    assert after.positions[0].quantity == 20
    assert after.positions[0].avg_cost == before.positions[0].avg_cost


def test_fill_failure_rolls_back_reserve_and_position(service, monkeypatch):
    a = account(service)
    service.place_order(intent(a))
    before = service.portfolio(a.account_id)
    original = WriteTx.execute

    def fail(tx, sql, params=None):
        if sql.startswith("INSERT INTO fill"):
            raise RuntimeError("synthetic fill failure")
        return original(tx, sql, params)

    monkeypatch.setattr(WriteTx, "execute", fail)
    with pytest.raises(InternalError):
        service.advance(a.account_id)
    assert service.portfolio(a.account_id) == before
    assert service.list_orders(a.account_id).items[0].status == "pending"
    assert not rows(service, "SELECT * FROM position")
    assert not rows(service, "SELECT * FROM cash_ledger WHERE entry_type='release'")


def test_full_book_example_with_synthetic_regulatory_fees(service):
    service.rules = replace(
        service.rules,
        commission_per_share=Decimal("0.005"),
        commission_min=Decimal("1"),
        sec_fee_per_million=Decimal("27.80"),
        taf_per_share=Decimal("0.000166"),
        taf_max_per_trade=Decimal("8.30"),
    )
    a = account(service)
    set_price(service, START, closing=51)
    service.place_order(intent(a, "buy", qty=100))
    set_price(service, START + timedelta(days=1), opening=51.1, closing=52)
    first = service.advance(a.account_id)
    assert first.portfolio.cash == Decimal("4886.4450")
    assert first.filled[0].fills[0].fee == Decimal("1.0000")
    service.place_order(intent(a, "sell", qty=40, side="sell"))
    set_price(service, START + timedelta(days=2), opening=53, closing=54)
    second = service.advance(a.account_id)
    assert second.filled[0].fills[0].fee == Decimal("1.0700")
    assert second.portfolio.cash == Decimal("7004.3150")
    assert second.portfolio.equity == Decimal("10244.3150")
    assert second.portfolio.positions[0].avg_cost == Decimal("51.135550")
