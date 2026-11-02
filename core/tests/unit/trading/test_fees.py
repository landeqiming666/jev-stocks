from dataclasses import asdict, replace
from decimal import ROUND_DOWN, Decimal, Inexact, localcontext

import pytest

from sentinel.errors import InternalError, UserError
from sentinel.trading.fees import FeeBreakdown, FeeConfig, calculate_fees, match_at_open
from sentinel.trading.rules import MarketRules, OrderIntent

D = Decimal


def sample_rules() -> MarketRules:
    return replace(
        MarketRules(),
        commission_per_share=D("0.005"),
        commission_min=D("1.00"),
        sec_fee_per_million=D("27.80"),
        taf_per_share=D("0.000166"),
        taf_max_per_trade=D("8.30"),
        sec_source="test-only:08-section-5.2",
        taf_source="test-only:08-section-5.2",
    )


def order(side: str = "buy", quantity: int = 100) -> OrderIntent:
    return OrderIntent("acct-1", "us:ZZAR", side, quantity, "market_open", "key-1")


def test_buy_fees_use_commission_minimum() -> None:
    fee = calculate_fees("buy", 100, D("5112.5550"), FeeConfig.from_rules(sample_rules()))
    assert str(fee.commission) == "1.00"
    assert str(fee.sec) == "0.00"
    assert str(fee.taf) == "0.00"
    assert str(fee.total) == "1.00"
    assert asdict(fee)["total"] == D("1.00")
    assert str(FeeBreakdown(D(1), D(0), D(0)).commission) == "1.00"


def test_sell_fee_samples_b_and_e() -> None:
    cfg = FeeConfig.from_rules(sample_rules())
    fee = calculate_fees("sell", 100, D("5107.4450"), cfg)
    assert fee.sec == D("0.15") and fee.taf == D("0.02") and fee.total == D("1.17")
    fee = calculate_fees("sell", 60000, D("599700.0000"), cfg)
    assert fee.commission == D("300.00")
    assert fee.sec == D("16.68") and fee.taf == D("8.30") and fee.total == D("324.98")


def test_no_open_price_fifth_day_boundary() -> None:
    rules = MarketRules()
    pending = match_at_open(order(), None, 3, D("2841.4200"), D(0), 0, rules)
    assert pending.kind == "pending" and pending.reject is None
    rejected = match_at_open(order(), None, 4, D("2841.4200"), D(0), 0, rules)
    assert rejected.kind == "rejected"
    assert rejected.reject_code == "NO_PRICE_AT_FILL"
    assert rejected.reject is not None and rejected.reject.data["n"] == 5


def test_buy_fill_rejects_on_gap_up_cash_shortfall() -> None:
    result = match_at_open(
        order(), D("28.55"), 0, D("2841.4200"), D("2857.4274"), 0, sample_rules()
    )
    assert result.kind == "rejected"
    assert result.reject_code == "INSUFFICIENT_CASH_AT_FILL"
    assert result.reject is not None
    assert result.reject.data["required"] == "2857.4275"
    assert result.reject.data["available"] == "2857.4274"
    assert result.price is None and result.amount is None and result.fee is None


def test_sell_fill_preserves_positive_amount() -> None:
    result = match_at_open(order("sell", 5000), D("20.00"), 0, D(0), D(0), 5000, sample_rules())
    assert result.kind == "filled"
    assert str(result.price) == "19.990000"
    assert str(result.amount) == "99950.0000"
    assert str(result.fee) == "28.6100"


@pytest.mark.parametrize(
    "side,quantity,open_price,price,amount,fee",
    [
        ("buy", 100, "51.10", "51.125550", "5112.5550", "1.0000"),
        ("sell", 100, "51.10", "51.074450", "5107.4450", "1.1700"),
        ("buy", 1000, "28.55", "28.564275", "28564.2750", "5.0000"),
        ("sell", 5000, "20.00", "19.990000", "99950.0000", "28.6100"),
        ("sell", 60000, "10.00", "9.995000", "599700.0000", "324.9800"),
    ],
)
def test_all_document_fill_samples(
    side: str, quantity: int, open_price: str, price: str, amount: str, fee: str
) -> None:
    result = match_at_open(
        order(side, quantity), D(open_price), 0, D(0), D("1000000"), quantity, sample_rules()
    )
    assert result.kind == "filled" and result.reject is None
    assert str(result.price) == price and str(result.amount) == amount and str(result.fee) == fee
    assert result.fees is not None and result.fees.total == D(fee)


def test_commission_cap_applies_after_minimum_and_rounds_half_up() -> None:
    cfg = replace(FeeConfig.from_rules(sample_rules()), commission_max_pct=D("0.1"))
    assert calculate_fees("buy", 100, D("100"), cfg).commission == D("0.10")
    assert calculate_fees("buy", 100, D("105"), cfg).commission == D("0.11")
    assert calculate_fees("buy", 100, D("1005"), cfg).commission == D("1.00")
    assert calculate_fees("buy", 100, D(0), cfg).commission == D("0.00")
    cfg = replace(cfg, commission_max_pct=D(0))
    assert calculate_fees("buy", 201, D("10000"), cfg).commission == D("1.01")


def test_regulatory_fees_round_up_even_when_below_half_cent() -> None:
    cfg = FeeConfig(
        sec_fee_per_million=D("1"), taf_per_share=D("0.000001"), taf_max_per_trade=D("8.30")
    )
    fee = calculate_fees("sell", 1, D("1.0000"), cfg)
    assert fee.sec == D("0.01") and fee.taf == D("0.01") and fee.total == D("0.02")
    fee = calculate_fees("sell", 10000, D("10000.0000"), cfg)
    assert fee.sec == D("0.01") and fee.taf == D("0.01")


def test_buy_fill_accepts_exact_cash_without_double_release() -> None:
    rules = sample_rules()
    result = match_at_open(order(), D("28.55"), 0, D("2841.4200"), D("2857.4275"), 0, rules)
    assert result.kind == "filled" and str(result.fee) == "1.0000"
    short = match_at_open(order(), D("28.55"), 0, D("999999"), D("2857.4274"), 0, rules)
    assert short.reject_code == "INSUFFICIENT_CASH_AT_FILL"


def test_sell_fill_rejects_position_shortfall_and_no_price_has_priority() -> None:
    result = match_at_open(order("sell"), D("20"), 0, D(0), D(0), 99, sample_rules())
    assert result.kind == "rejected" and result.reject_code == "INSUFFICIENT_POSITION_AT_FILL"
    assert result.reject is not None and result.reject.data["held"] == 99
    assert result.reject.data["requested"] == 100
    result = match_at_open(order("sell"), None, 4, D(0), D(0), 0, sample_rules())
    assert result.reject_code == "NO_PRICE_AT_FILL"


@pytest.mark.parametrize(
    "waited,kind",
    [
        (0, "pending"),
        (1, "pending"),
        (2, "pending"),
        (3, "pending"),
        (4, "rejected"),
        (5, "rejected"),
    ],
)
def test_missing_or_zero_open_counts_trading_days(waited: int, kind: str) -> None:
    for price in (None, D(0)):
        result = match_at_open(order(), price, waited, D(0), D(0), 0, MarketRules())
        assert result.kind == kind and result.waited_days == waited + 1
    result = match_at_open(order(), D("1"), waited, D(0), D("1000"), 0, MarketRules())
    assert result.kind == "filled"


@pytest.mark.parametrize(
    "bad", [1.0, True, "1", D("NaN"), D("sNaN"), D("Infinity"), D("-Infinity"), D("-1")]
)
def test_fee_and_fill_reject_invalid_decimal_inputs(bad: Decimal) -> None:
    cfg = FeeConfig()
    with pytest.raises(UserError) as error:
        calculate_fees("buy", 100, bad, cfg)
    assert error.value.field == "amount"
    for field in ("open_price", "reserved_cash", "available_cash_after_release"):
        arguments = {
            "open_price": D("1"),
            "reserved_cash": D(0),
            "available_cash_after_release": D("1000"),
        }
        arguments[field] = bad
        with pytest.raises(UserError) as error:
            match_at_open(order(), waited_days=0, held=0, rules=MarketRules(), **arguments)
        assert error.value.field == field


@pytest.mark.parametrize("bad", [True, 0, -1, 100.0, D(100), 1000001])
def test_fee_and_fill_reject_invalid_order_quantity(bad: int) -> None:
    with pytest.raises(UserError) as error:
        calculate_fees("buy", bad, D("1"), FeeConfig())
    assert error.value.field == "quantity"
    with pytest.raises(UserError) as error:
        match_at_open(order(quantity=bad), D("1"), 0, D(0), D("1000"), 0, MarketRules())
    assert error.value.field == "quantity"


@pytest.mark.parametrize("bad", [True, -1, 1.0, D(1)])
def test_fill_rejects_invalid_wait_and_position_counts(bad: int) -> None:
    with pytest.raises(UserError) as error:
        match_at_open(order(), D("1"), bad, D(0), D("1000"), 0, MarketRules())
    assert error.value.field == "waited_days"
    with pytest.raises(UserError) as error:
        match_at_open(order(), D("1"), 0, D(0), D("1000"), bad, MarketRules())
    assert error.value.field == "held"


@pytest.mark.parametrize(
    "field",
    [
        "commission_per_share",
        "commission_min",
        "commission_max_pct",
        "sec_fee_per_million",
        "taf_per_share",
        "taf_max_per_trade",
    ],
)
@pytest.mark.parametrize("bad", [1.0, True, D("NaN"), D("sNaN"), D("Infinity"), D("-1")])
def test_fee_config_rejects_invalid_decimals(field: str, bad: Decimal) -> None:
    with pytest.raises(InternalError) as error:
        replace(FeeConfig(), **{field: bad})
    assert error.value.field == field


def test_fee_config_requires_valid_taf_cap_and_verification_metadata() -> None:
    with pytest.raises(InternalError):
        FeeConfig(taf_per_share=D("0.000166"))
    with pytest.raises(InternalError):
        FeeConfig(sec_verified=True)
    cfg = FeeConfig.from_rules(sample_rules())
    assert not cfg.sec_verified and not cfg.taf_verified
    assert cfg.sec_source.startswith("test-only:")


def test_fee_and_fill_do_not_depend_on_decimal_context() -> None:
    rules = sample_rules()
    with localcontext() as ctx:
        ctx.prec = 2
        ctx.rounding = ROUND_DOWN
        ctx.traps[Inexact] = True
        fee = calculate_fees("sell", 100, D("5107.4450"), rules.fee_config)
        result = match_at_open(order("sell"), D("51.10"), 0, D(0), D(0), 100, rules)
        total = fee.total
    assert total == D("1.17") and str(result.amount) == "5107.4450"


def test_sell_slippage_is_downward_and_uses_half_up() -> None:
    rules = replace(MarketRules(), slippage_bps=D(0))
    result = match_at_open(order("sell", 1), D("1.2345675"), 0, D(0), D(0), 1, rules)
    assert str(result.price) == "1.234568" and str(result.amount) == "1.2346"


def test_amounts_require_four_decimal_places() -> None:
    with pytest.raises(UserError) as error:
        calculate_fees("buy", 100, D("100.00001"), FeeConfig())
    assert error.value.field == "amount"
    for field in ("reserved_cash", "available_cash_after_release"):
        arguments = {"reserved_cash": D(0), "available_cash_after_release": D("1000")}
        arguments[field] = D("100.00001")
        with pytest.raises(UserError) as error:
            match_at_open(order(), D(1), 0, held=0, rules=MarketRules(), **arguments)
        assert error.value.field == field


@pytest.mark.parametrize("side", ["short", "BUY", None, [], True])
def test_fee_side_type_is_checked(side: str) -> None:
    with pytest.raises(UserError) as error:
        calculate_fees(side, 100, D("100"), FeeConfig())
    assert error.value.field == "side"


def test_sub_quantum_open_price_reports_input_field() -> None:
    with pytest.raises(UserError) as error:
        match_at_open(order(), D("0.0000001"), 0, D(0), D("1000"), 0, MarketRules())
    assert error.value.field == "open_price"


@pytest.mark.parametrize("bad", [1.0, D("NaN"), D("-1"), D("0.001")])
def test_fee_breakdown_rejects_invalid_cent_values(bad: Decimal) -> None:
    with pytest.raises(UserError) as error:
        FeeBreakdown(bad, D("0.00"), D("0.00"))
    assert error.value.field == "commission"
