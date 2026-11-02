from dataclasses import replace
from datetime import date
from decimal import ROUND_DOWN, Decimal, Inexact, localcontext
from hashlib import sha256
from pathlib import Path

import pytest

from sentinel.errors import InternalError, UserError
from sentinel.trading.fees import match_at_open
from sentinel.trading.rules import (
    MarketRules,
    MarketSnapshot,
    OrderIntent,
    estimate_buy,
    load_market_rules,
    precheck,
    request_hash,
    validate_parameters,
)

D = Decimal
TOML = """
[meta]
market = "us"
currency = "USD"
[costs]
slippage_bps = "5"
commission_per_share = "0"
commission_min = "0"
commission_max_pct = "0"
[costs.sec_fee]
usd_per_million = "0"
effective_from = ""
source = ""
verified = false
[costs.finra_taf]
usd_per_share = "0"
max_per_trade = "0"
effective_from = ""
source = ""
verified = false
[limits]
max_order_quantity = 1000000
max_pending_orders = 50
max_wait_trading_days = 5
"""


def intent(**changes: object) -> OrderIntent:
    return replace(OrderIntent("acct-1", "us:ZZAR", "buy", 100, "market_open", "key-1"), **changes)


def write_config(tmp_path: Path, text: str = TOML) -> Path:
    path = tmp_path / "us.toml"
    path.write_text(text, encoding="utf-8")
    return path


def test_config_and_parameter_guards(tmp_path: Path) -> None:
    with pytest.raises(InternalError):
        load_market_rules(write_config(tmp_path, TOML.replace('market = "us"', "")))
    rules = load_market_rules(write_config(tmp_path))
    with pytest.raises(UserError) as error:
        validate_parameters(intent(quantity=0), 0, rules)
    assert error.value.field == "quantity"
    with pytest.raises(UserError) as error:
        validate_parameters(intent(), 50, rules)
    assert error.value.code == "INVALID_ARGUMENT"
    assert error.value.field == "pending_count"


def test_precheck_returns_no_price_before_cash() -> None:
    result = precheck(
        intent(), MarketSnapshot(date(2026, 10, 26), None, 1000000), D(0), 0, 0, MarketRules()
    )
    assert result.estimate is None
    assert result.reject is not None
    assert result.reject.code == "NO_PRICE"
    assert result.reject.message_key == "trading.no_price"
    assert result.reject.data["date"] == "2026-10-26"


def test_buy_estimate_matches_document_sample_a() -> None:
    rules = MarketRules()
    estimate = estimate_buy(D("28.40"), 100, rules)
    assert str(estimate.price) == "28.414200"
    assert str(estimate.amount) == "2841.4200"
    assert str(estimate.fee) == "0.0000"
    assert estimate.required == D("2841.4200")
    result = match_at_open(intent(), D("51.10"), 0, estimate.required, D("10000"), 0, rules)
    assert result.kind == "filled"
    assert str(result.price) == "51.125550"
    assert str(result.amount) == "5112.5550"


def test_request_hash_is_stable_64_hex() -> None:
    expected = "efda657dd51faa14051d5566d5de50b2684a5bd32ed59e2b196e766fa77e49d1"
    assert sha256(b"acct-1|us:ZZAR|buy|100|market_open").hexdigest() == expected
    value = request_hash("acct-1", intent())
    assert value == expected
    assert len(value) == 64 and all(char in "0123456789abcdef" for char in value)
    assert request_hash("acct-1", intent(idempotency_key="key-2")) == value
    for changes in ({"quantity": 101}, {"side": "sell"}, {"instrument_id": "us:ZZFD"}):
        assert request_hash("acct-1", intent(**changes)) != value
    assert request_hash("acct-2", intent(account_id="acct-2")) != value


@pytest.mark.parametrize(
    "changes,field",
    [
        ({"account_id": ""}, "accountId"),
        ({"account_id": 1}, "accountId"),
        ({"instrument_id": "hk:ZZAR"}, "instrumentId"),
        ({"instrument_id": "us:"}, "instrumentId"),
        ({"instrument_id": 1}, "instrumentId"),
        ({"side": "short"}, "side"),
        ({"side": []}, "side"),
        ({"order_type": "limit"}, "orderType"),
        ({"order_type": None}, "orderType"),
        ({"quantity": 0}, "quantity"),
        ({"quantity": -1}, "quantity"),
        ({"quantity": True}, "quantity"),
        ({"quantity": 100.0}, "quantity"),
        ({"quantity": D("100")}, "quantity"),
        ({"quantity": 1000001}, "quantity"),
        ({"idempotency_key": ""}, "idempotencyKey"),
        ({"idempotency_key": " "}, "idempotencyKey"),
        ({"idempotency_key": "k" * 65}, "idempotencyKey"),
        ({"idempotency_key": None}, "idempotencyKey"),
    ],
)
def test_parameter_errors_identify_field(changes: dict[str, object], field: str) -> None:
    with pytest.raises(UserError) as error:
        validate_parameters(intent(**changes), 0, MarketRules())
    assert error.value.code == "INVALID_ARGUMENT" and error.value.field == field


@pytest.mark.parametrize("pending", [-1, True, 1.0, D(1), 50, 51])
def test_pending_limit_and_type(pending: int) -> None:
    with pytest.raises(UserError) as error:
        validate_parameters(intent(), pending, MarketRules())
    assert error.value.field == "pending_count"


def test_exact_quantity_pending_and_key_limits() -> None:
    validate_parameters(intent(quantity=1000000, idempotency_key="k" * 64), 49, MarketRules())


@pytest.mark.parametrize(
    "bad", [1.0, True, "1", D("NaN"), D("sNaN"), D("Infinity"), D("-Infinity"), D("-0.0001")]
)
def test_invalid_price_and_cash_are_rejected_at_entry(bad: Decimal) -> None:
    rules = MarketRules()
    snapshot = MarketSnapshot(date(2026, 10, 26), D("28.40"), rules.max_order_quantity)
    with pytest.raises(UserError) as error:
        estimate_buy(bad, 100, rules)
    assert error.value.field == "close"
    with pytest.raises(UserError) as error:
        precheck(intent(), replace(snapshot, close=bad), D("10000"), 0, 0, rules)
    assert error.value.field == "close"
    with pytest.raises(UserError) as error:
        precheck(intent(), snapshot, bad, 0, 0, rules)
    assert error.value.field == "available_cash"


@pytest.mark.parametrize("bad", [-1, True, 1.0, D(1)])
def test_precheck_position_types_are_validated(bad: int) -> None:
    rules = MarketRules()
    snapshot = MarketSnapshot(date(2026, 10, 26), D(1), rules.max_order_quantity)
    for field in ("held", "pending_sell"):
        with pytest.raises(UserError) as error:
            precheck(
                intent(),
                snapshot,
                D("1000"),
                rules=rules,
                **{
                    "held": bad if field == "held" else 0,
                    "pending_sell": bad if field == "pending_sell" else 0,
                },
            )
        assert error.value.field == field


def test_precheck_cash_exact_equality_and_sell_reservations() -> None:
    rules = MarketRules()
    snapshot = MarketSnapshot(date(2026, 10, 26), D("28.40"), rules.max_order_quantity)
    estimate = estimate_buy(snapshot.close, 100, rules)
    result = precheck(intent(), snapshot, estimate.required, 0, 0, rules)
    assert result.estimate == estimate and result.reject is None
    result = precheck(intent(), snapshot, estimate.required - D("0.0001"), 1000, 0, rules)
    assert result.estimate is None and result.reject is not None
    assert result.reject.code == "INSUFFICIENT_CASH"
    assert result.reject.data["required"] == "2841.4200"
    assert result.reject.data["available"] == "2841.4199"
    sell = intent(side="sell")
    result = precheck(sell, snapshot, D(0), 150, 50, rules)
    assert result.estimate is None and result.reject is None
    result = precheck(sell, snapshot, D(0), 149, 50, rules)
    assert result.reject is not None and result.reject.code == "INSUFFICIENT_POSITION"
    assert result.reject.data["sellable"] == 99
    assert result.reject.data["held"] == 149 and result.reject.data["requested"] == 100
    result = precheck(sell, replace(snapshot, close=D(0)), D(0), 0, 100, rules)
    assert result.reject is not None and result.reject.code == "NO_PRICE"


@pytest.mark.parametrize(
    "old,new",
    [
        ('market = "us"', 'market = "cn"'),
        ('currency = "USD"', 'currency = "CNY"'),
        ('slippage_bps = "5"', "slippage_bps = 5.0"),
        ('slippage_bps = "5"', "slippage_bps = true"),
        ('slippage_bps = "5"', 'slippage_bps = "NaN"'),
        ('slippage_bps = "5"', 'slippage_bps = "sNaN"'),
        ('slippage_bps = "5"', 'slippage_bps = "Infinity"'),
        ('slippage_bps = "5"', 'slippage_bps = "-1"'),
        ('slippage_bps = "5"', 'slippage_bps = "10000"'),
        ('commission_per_share = "0"', 'commission_per_share = "garbage"'),
        ('commission_min = "0"', 'commission_min = "0.001"'),
        ('commission_max_pct = "0"', 'commission_max_pct = "101"'),
        ('usd_per_million = "0"', "usd_per_million = -1"),
        ('usd_per_share = "0"', 'usd_per_share = "0.000166"'),
        ('max_per_trade = "0"', 'max_per_trade = "-1"'),
        ('max_per_trade = "0"', 'max_per_trade = "8.301"'),
        ("verified = false", 'verified = "false"'),
        ("verified = false", "verified = true"),
        ('effective_from = ""', 'effective_from = "2026-02-30"'),
        ('source = ""', "source = 123"),
        ("max_order_quantity = 1000000", "max_order_quantity = true"),
        ("max_pending_orders = 50", "max_pending_orders = 0"),
        ("max_wait_trading_days = 5", "max_wait_trading_days = 5.0"),
    ],
)
def test_invalid_config_is_internal(tmp_path: Path, old: str, new: str) -> None:
    with pytest.raises(InternalError) as error:
        load_market_rules(write_config(tmp_path, TOML.replace(old, new)))
    assert error.value.code == "INTERNAL"


def test_config_decimals_are_exact_and_unverified(tmp_path: Path) -> None:
    rules = load_market_rules(
        write_config(tmp_path, TOML.replace('slippage_bps = "5"', "slippage_bps = 5"))
    )
    assert rules.slippage_bps == D(5) and isinstance(rules.slippage_bps, Decimal)
    assert rules.sec_fee_per_million == 0 and not rules.sec_verified
    assert rules.taf_per_share == 0 and not rules.taf_verified
    assert not rules.fee_config.sec_verified and not rules.fee_config.taf_verified


def test_config_missing_and_malformed_files_are_internal(tmp_path: Path) -> None:
    with pytest.raises(InternalError):
        load_market_rules(tmp_path / "missing.toml")
    with pytest.raises(InternalError):
        load_market_rules(write_config(tmp_path, "[meta\n"))
    path = write_config(tmp_path)
    path.write_bytes(b"\xff")
    with pytest.raises(InternalError):
        load_market_rules(path)


def test_estimate_uses_half_up_and_ignores_callers_decimal_context() -> None:
    rules = replace(MarketRules(), slippage_bps=D(0))
    with localcontext() as ctx:
        ctx.prec = 2
        ctx.rounding = ROUND_DOWN
        ctx.traps[Inexact] = True
        estimate = estimate_buy(D("1.2345675"), 100, rules)
    assert str(estimate.price) == "1.234568"
    assert str(estimate.amount) == "123.4568"


def test_reject_data_is_immutable_and_json_compatible() -> None:
    import json

    result = precheck(
        intent(), MarketSnapshot(date(2026, 10, 26), None, 1000000), D(0), 0, 0, MarketRules()
    )
    assert result.reject is not None
    data = dict(result.reject.data)
    assert json.loads(json.dumps(data))["reason"] == "NO_PRICE"
    data["reason"] = "changed"
    assert result.reject.data["reason"] == "NO_PRICE"


def test_hash_rejects_ambiguous_ids_and_account_mismatch() -> None:
    for account, value in [
        ("acct-1|us:ZZFD", intent()),
        ("acct-2", intent()),
        ("acct-1", intent(instrument_id="us:ZZAR|sell")),
    ]:
        with pytest.raises(UserError):
            request_hash(account, value)


def test_cash_requires_at_most_four_decimal_places() -> None:
    snapshot = MarketSnapshot(date(2026, 10, 26), D("1"), 1000000)
    with pytest.raises(UserError) as error:
        precheck(intent(), snapshot, D("1000.00001"), 0, 0, MarketRules())
    assert error.value.field == "available_cash"
    assert precheck(intent(), snapshot, D("1000.00000"), 0, 0, MarketRules()).reject is None


@pytest.mark.parametrize("bad", [None, "2026-10-26", True])
def test_snapshot_date_type_is_checked(bad: date) -> None:
    with pytest.raises(UserError) as error:
        precheck(intent(), MarketSnapshot(bad, D(1), 1000000), D("1000"), 0, 0, MarketRules())
    assert error.value.field == "clockDate"


def test_snapshot_quantity_limit_is_enforced() -> None:
    snapshot = MarketSnapshot(date(2026, 10, 26), D(1), 99)
    with pytest.raises(UserError) as error:
        precheck(intent(), snapshot, D("1000"), 0, 0, MarketRules())
    assert error.value.field == "quantity"
    for bad in (True, 0, 100.0):
        with pytest.raises(UserError) as error:
            precheck(
                intent(), replace(snapshot, max_order_quantity=bad), D("1000"), 0, 0, MarketRules()
            )
        assert error.value.field == "maxOrderQuantity"


def test_sub_quantum_price_reports_input_field() -> None:
    with pytest.raises(UserError) as error:
        estimate_buy(D("0.0000001"), 100, MarketRules())
    assert error.value.field == "close"
