from datetime import date
from decimal import Decimal

import numpy as np
import pytest

from .conftest import trading_days


def test_weight_calculation_isolated_from_caller_decimal_traps_and_flags(calendar):
    from decimal import ROUND_DOWN, Inexact, Rounded, localcontext

    from sentinel.quant.models import HoldingPoint, PricePoint
    from sentinel.quant.prices import build_risk_input

    days = trading_days(calendar)
    prices = {
        name: [PricePoint(day, 100.0, 100.0) for day in days] for name in ("us:ZZAR", "us:ZZFD")
    }
    holdings = [HoldingPoint("us:ZZAR", "ZZAR", 1), HoldingPoint("us:ZZFD", "ZZFD", 2)]
    with localcontext() as context:
        context.prec = 3
        context.rounding = ROUND_DOWN
        context.traps[Inexact] = context.traps[Rounded] = True
        context.flags[Inexact] = True
        before = repr(context), dict(context.flags), dict(context.traps)
        data = build_risk_input(holdings, prices, "1Y", calendar=calendar, as_of=days[-1])
        np.testing.assert_allclose(data.weights, [1 / 3, 2 / 3])
        assert (repr(context), dict(context.flags), dict(context.traps)) == before


def test_window_and_calendar_start(calendar):
    from sentinel.quant.models import HoldingPoint, PricePoint
    from sentinel.quant.prices import build_risk_input, calendar_start

    assert calendar_start(date(2026, 8, 31), "6M") == date(2026, 2, 28)
    assert calendar_start(date(2024, 2, 29), "1Y") == date(2023, 2, 28)
    days = [day for day in trading_days(calendar, 87) if day < date(2026, 10, 28)]
    days += [date(2026, 10, 28), date(2026, 10, 29), date(2026, 10, 30)]
    prices = {
        "us:ZZAR": [PricePoint(day, 100.0 + i, 100.0 + i) for i, day in enumerate(days)],
        "us:ZZFD": [PricePoint(day, 100.0, 100.0) for day in days[:-2]],
    }
    data = build_risk_input(
        [
            HoldingPoint("us:ZZFD", "ZZFD", Decimal("0.0001")),
            HoldingPoint("us:ZZAR", "ZZAR", Decimal("0.0002")),
            HoldingPoint("us:ZZMD", "ZZMD", 0),
        ],
        prices,
        "6M",
        calendar=calendar,
        as_of=date(2026, 10, 30),
    )
    assert data.as_of == date(2026, 10, 28)
    assert data.symbols == ["ZZAR", "ZZFD"]
    assert data.weights[1] > 0
    assert data.excluded[0].symbol == "ZZMD"
    assert data.endpoint_closes[0] == 100.0 + days.index(date(2026, 10, 28))


def test_price_basis_and_common_days(calendar):
    from sentinel.quant import compute_risk
    from sentinel.quant.models import HoldingPoint, PricePoint
    from sentinel.quant.prices import build_risk_input

    days = trading_days(calendar)
    prices = {
        "us:ZZAR": [PricePoint(day, 100.0 + i, (100.0 + i) * 2) for i, day in enumerate(days)],
        "us:ZZFD": [
            PricePoint(day, 100.0 + i, None if i == 5 else 100.0)
            for i, day in enumerate(days)
            if i != 20
        ],
    }
    data = build_risk_input(
        [HoldingPoint("us:ZZAR", "ZZAR", 1), HoldingPoint("us:ZZFD", "ZZFD", 1)],
        prices,
        "1Y",
        calendar=calendar,
        as_of=days[-1],
    )
    assert data.price_basis == "close"
    assert "价格未复权" in compute_risk(data).warnings
    assert days[20] not in data.return_dates and days[21] not in data.return_dates
    assert data.window_observations == 63
    np.testing.assert_allclose(data.returns[:, 0], data.returns[:, 1])
    np.testing.assert_allclose(data.weights, [0.5, 0.5])


def test_missing_endpoint_does_not_create_multi_day_return(calendar):
    from sentinel.quant.models import HoldingPoint, PricePoint
    from sentinel.quant.prices import build_risk_input

    days = trading_days(calendar, 7)
    closes = [100.0, 110.0, 100.0, 110.0, 100.0, 110.0, 100.0]
    prices = {
        "us:ZZAR": [PricePoint(day, close, close) for day, close in zip(days, closes, strict=True)],
        "us:ZZFD": [
            PricePoint(day, close, close)
            for i, (day, close) in enumerate(zip(days, closes, strict=True))
            if i != 1
        ],
    }
    data = build_risk_input(
        [HoldingPoint("us:ZZAR", "ZZAR", 1), HoldingPoint("us:ZZFD", "ZZFD", 1)],
        prices,
        "1Y",
        4,
        calendar=calendar,
        as_of=days[-1],
    )
    assert data.return_dates == days[3:]
    np.testing.assert_allclose(data.returns[:, 1], [0.1, -1 / 11, 0.1, -1 / 11])


@pytest.mark.parametrize("bad", [None, float("nan"), float("inf"), 0.0, -100.0])
def test_invalid_price_removes_both_adjacent_returns(calendar, bad):
    from sentinel.quant import compute_risk
    from sentinel.quant.models import HoldingPoint, PricePoint
    from sentinel.quant.prices import build_risk_input

    days = trading_days(calendar)
    points = [PricePoint(day, 100.0, bad if i == 12 else 100.0) for i, day in enumerate(days)]
    data = build_risk_input(
        [HoldingPoint("us:ZZAR", "ZZAR", 1)],
        {"us:ZZAR": points},
        "1Y",
        calendar=calendar,
        as_of=days[-1],
    )
    if bad is None:
        assert data.window_observations == 65
    else:
        assert days[12] not in data.return_dates and days[13] not in data.return_dates
        assert data.window_observations == 63
    assert np.isfinite(data.returns).all()
    assert compute_risk(data).annualized_vol == 0
    assert data.price_basis == ("close" if bad is None else "adj_close")


def test_missing_valuation_day_keeps_assets_and_does_not_use_future(calendar):
    from sentinel.quant.models import HoldingPoint, PricePoint
    from sentinel.quant.prices import build_risk_input

    days = trading_days(calendar, 68)
    prices = {
        "us:ZZAR": [PricePoint(day, 200.0, 50.0) for i, day in enumerate(days) if i != 65],
        "us:ZZFD": [PricePoint(day, 100.0, 100.0) for day in days[:66]],
    }
    data = build_risk_input(
        [
            HoldingPoint("us:ZZFD", "ZZFD", Decimal("0.0002")),
            HoldingPoint("us:ZZAR", "ZZAR", Decimal("0.0001")),
        ],
        prices,
        "1Y",
        calendar=calendar,
        as_of=days[66],
    )
    assert data.as_of == days[64]
    assert data.symbols == ["ZZAR", "ZZFD"]
    assert data.excluded == []
    np.testing.assert_allclose(data.weights, [0.5, 0.5])
    np.testing.assert_allclose(data.endpoint_closes, [200.0, 100.0])
    assert data.return_dates[-1] < days[65]


def test_adj_prices_are_global_and_raw_close_values_fractional_holdings(calendar):
    from sentinel.quant.models import HoldingPoint, PricePoint
    from sentinel.quant.prices import build_risk_input

    days = trading_days(calendar)
    prices = {
        "us:ZZAR": [PricePoint(day, 400.0, 100.0 + i) for i, day in enumerate(days)],
        "us:ZZFD": [PricePoint(day, 100.0, 200.0 + i) for i, day in enumerate(days)],
    }
    holdings = [
        HoldingPoint("us:ZZAR", "ZZAR", Decimal("0.1250")),
        HoldingPoint("us:ZZFD", "ZZFD", Decimal("0.5000")),
    ]
    data = build_risk_input(holdings, prices, "1Y", calendar=calendar, as_of=days[-1])
    assert data.price_basis == "adj_close"
    np.testing.assert_allclose(data.weights, [0.5, 0.5])
    np.testing.assert_allclose(data.returns[0], [101 / 100 - 1, 201 / 200 - 1])
    prices["us:ZZFD"][10] = PricePoint(days[10], 100.0, None)
    fallback = build_risk_input(holdings, prices, "1Y", calendar=calendar, as_of=days[-1])
    assert fallback.price_basis == "close"
    np.testing.assert_allclose(fallback.returns, 0.0)


def test_holidays_and_source_changes_do_not_create_mixed_returns(calendar):
    from sentinel.quant.models import HoldingPoint, PricePoint
    from sentinel.quant.prices import build_risk_input

    days = trading_days(calendar)
    assert days[1:3] == [date(2026, 7, 2), date(2026, 7, 6)]
    points = [
        PricePoint(day, 100.0 + i, 100.0 + i, "primary" if i < 10 else "backup")
        for i, day in enumerate(days)
    ]
    points.append(PricePoint(date(2026, 7, 3), 1e9, None, "holiday"))
    points.append(PricePoint(date(2026, 12, 1), 1e9, None, "future"))
    data = build_risk_input(
        [HoldingPoint("us:ZZAR", "ZZAR", 1)],
        {"us:ZZAR": points},
        "1Y",
        calendar=calendar,
        as_of=days[-1],
    )
    assert data.price_basis == "adj_close"
    assert days[10] not in data.return_dates and days[11] in data.return_dates
    assert data.window_observations == 64
    assert data.returns[1, 0] == pytest.approx(102 / 101 - 1)


def test_three_year_short_history_and_stale_warning(calendar):
    from sentinel.quant import compute_risk
    from sentinel.quant.models import HoldingPoint, PricePoint
    from sentinel.quant.prices import build_risk_input

    days = trading_days(calendar, 71)
    prices = {"us:ZZAR": [PricePoint(day, 100.0 + i, 100.0 + i) for i, day in enumerate(days[:66])]}
    holdings = [HoldingPoint("us:ZZAR", "ZZAR", 1)]
    data = build_risk_input(holdings, prices, "3Y", calendar=calendar, as_of=days[-1])
    shorter = build_risk_input(holdings, prices, "1Y", calendar=calendar, as_of=days[-1])
    result = compute_risk(data)
    assert result.window.label == "3Y" and result.window.from_date == days[1]
    assert result.annualized_vol == compute_risk(shorter).annualized_vol
    assert "超过 3 个交易日" in result.warnings[-2]
    assert "数据不足三年" in result.warnings[-1]
    assert len(result.warnings) == len(set(result.warnings))


@pytest.mark.parametrize(
    "quantity", [0.1, True, Decimal("-1"), Decimal("NaN"), Decimal("Infinity")]
)
def test_invalid_quantity_is_rejected(calendar, quantity):
    from sentinel.errors import UserError
    from sentinel.quant.models import HoldingPoint
    from sentinel.quant.prices import build_risk_input

    with pytest.raises(UserError, match="INVALID_ARGUMENT"):
        build_risk_input(
            [HoldingPoint("us:ZZAR", "ZZAR", quantity)],
            {},
            "1Y",
            calendar=calendar,
            as_of=date(2026, 10, 30),
        )


def test_no_baseline_excluded_and_sample_threshold_is_real(calendar):
    from sentinel.errors import UserError
    from sentinel.quant.models import HoldingPoint, PricePoint
    from sentinel.quant.prices import build_risk_input

    days = trading_days(calendar, 61)
    holdings = [HoldingPoint("us:ZZAR", "ZZAR", 1), HoldingPoint("us:ZZFD", "ZZFD", 2)]
    points = [PricePoint(day, 100.0, 100.0) for day in days]
    with pytest.raises(UserError) as raised:
        build_risk_input(
            holdings, {"us:ZZAR": points[:-1]}, "1Y", calendar=calendar, as_of=days[-1]
        )
    assert raised.value.params["observations"] == 59
    data = build_risk_input(holdings, {"us:ZZAR": points}, "1Y", calendar=calendar, as_of=days[-1])
    assert data.window_observations == 60
    assert data.excluded[0].symbol == "ZZFD"
