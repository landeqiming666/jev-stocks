from dataclasses import replace
from decimal import Decimal, localcontext

import numpy as np
import pytest

from .conftest import DOCUMENT_RETURNS, risk_input


def test_insufficient_and_zero_variance_is_kept():
    from sentinel.errors import UserError
    from sentinel.quant import compute_risk

    with pytest.raises(UserError) as raised:
        compute_risk(risk_input(np.zeros((59, 2)), [0.5, 0.5], min_observations=60))
    wire = raised.value.to_wire("risk-1")
    assert wire["code"] == "DATA_INSUFFICIENT"
    assert wire["data"]["observations"] == 59 and wire["data"]["required"] == 60
    assert "样本不足" in wire["message"]
    data = risk_input(np.column_stack((DOCUMENT_RETURNS[:, 0], np.zeros(4))), [0.5, 0.5])
    result = compute_risk(data)
    assert result.correlation.matrix == [[1.0, None], [None, 1.0]]
    assert result.correlation.symbols == ["ZZAR", "ZZCL"]
    assert [item.symbol for item in result.svd.loadings] == ["ZZAR"]
    assert result.condition_number_raw is None
    assert len(result.top_weights) == 2


def test_annualization_is_252_regardless_of_window_label():
    from sentinel.quant import compute_risk

    data = risk_input(np.tile(DOCUMENT_RETURNS, (63, 1)), min_observations=60)
    assert (
        compute_risk(data).annualized_vol
        == compute_risk(replace(data, window_label="3Y")).annualized_vol
    )
    # 调用者的旧年化字段也不能把 3Y 偷换成每年 84 天。
    assert (
        compute_risk(data).annualized_vol
        == compute_risk(replace(data, periods_per_year=84)).annualized_vol
    )


def test_zero_variance_asset_keeps_weight_and_portfolio_vol():
    from sentinel.quant import compute_risk

    returns = np.array([[0.01, 0.0], [-0.01, 0.0]] * 30)
    result = compute_risk(risk_input(returns, [0.5, 0.5], min_observations=60))
    assert result.effective_holdings == 2.0
    expected = 0.5 * np.sqrt(252 * (60 * 0.01**2 / 59))
    assert result.annualized_vol == pytest.approx(expected, abs=1e-12)
    assert result.max_drawdown > 0
    assert result.condition_number_shrunk == pytest.approx(19.0)


def test_document_covariance_and_correlation():
    from sentinel.quant import compute_risk
    from sentinel.quant.risk import sample_covariance

    with localcontext() as ctx:
        ctx.prec = 50
        rows = [[Decimal(str(value)) for value in row] for row in DOCUMENT_RETURNS]
        expected = [
            [float(sum(row[i] * row[j] for row in rows) / 3) for j in range(3)] for i in range(3)
        ]
    np.testing.assert_allclose(sample_covariance(DOCUMENT_RETURNS), expected, atol=1e-9, rtol=0)
    np.testing.assert_allclose(
        expected,
        [[0.0004 / 3, 0.0002, 0], [0.0002, 0.0025 / 3, 0], [0, 0, 0.0016 / 3]],
        atol=1e-9,
        rtol=0,
    )
    result = compute_risk(risk_input())
    np.testing.assert_allclose(
        result.correlation.matrix, [[1, 0.6, 0], [0.6, 1, 0], [0, 0, 1]], atol=1e-9, rtol=0
    )


def test_document_condition_numbers():
    from sentinel.quant import compute_risk

    # 解析求 2×2 块特征值，独立于 numpy 的 eigvalsh。
    with localcontext() as ctx:
        ctx.prec = 50
        a, d, b = Decimal("0.0004") / 3, Decimal("0.0025") / 3, Decimal("0.0002")
        ratios = []
        for alpha in (Decimal(0), Decimal("0.1")):
            x, y = (
                (1 - alpha) * a + alpha * Decimal("0.0005"),
                (1 - alpha) * d + alpha * Decimal("0.0005"),
            )
            off = (1 - alpha) * b
            discriminant = ((x - y) ** 2 + 4 * off**2).sqrt()
            ratios.append(float((x + y + discriminant) / (x + y - discriminant)))
    result = compute_risk(risk_input())
    assert ratios == pytest.approx([11.050128313, 6.937910721], abs=1e-9)
    assert result.condition_number_raw == pytest.approx(ratios[0], abs=1e-9)
    assert result.condition_number_shrunk == pytest.approx(ratios[1], abs=1e-9)


def test_document_vol_drawdown_and_effective_holdings():
    from sentinel.quant import compute_risk

    with localcontext() as ctx:
        ctx.prec = 50
        weights = [Decimal("0.5"), Decimal("0.3"), Decimal("0.2")]
        portfolio = [
            sum(Decimal(str(x)) * w for x, w in zip(row, weights, strict=True))
            for row in DOCUMENT_RETURNS
        ]
        variance = sum(x * x for x in portfolio) / 3
        vol = float((252 * variance).sqrt())
        value = peak = Decimal(1)
        drawdown = Decimal(0)
        for ret in portfolio:
            value *= 1 + ret
            peak = max(peak, value)
            drawdown = max(drawdown, (peak - value) / peak)
        effective = float(1 / sum(w * w for w in weights))
    assert [vol, float(drawdown), effective] == pytest.approx(
        [0.2186229631, 0.0194042931, 2.6315789474], abs=1e-9
    )
    result = compute_risk(risk_input())
    assert [result.annualized_vol, result.max_drawdown, result.effective_holdings] == pytest.approx(
        [vol, float(drawdown), effective], abs=1e-9
    )


def test_document_svd_and_sign(monkeypatch):
    from sentinel.quant import compute_risk

    original = np.linalg.svd

    def negative_first(*args, **kwargs):
        u, singular, vt = original(*args, **kwargs)
        if vt[0, np.argmax(np.abs(vt[0]))] > 0:
            vt[0] *= -1
        return u, singular, vt

    monkeypatch.setattr(np.linalg, "svd", negative_first)
    result = compute_risk(risk_input())
    assert result.svd.explained == pytest.approx(
        [0.5333333333, 0.3333333333, 0.1333333333], abs=1e-9
    )
    assert [item.symbol for item in result.svd.loadings] == ["ZZAR", "ZZCL", "ZZFD"]
    assert [item.value for item in result.svd.loadings] == pytest.approx(
        [0.7071067812, 0.7071067812, 0], abs=1e-9
    )


def test_all_constant_nonbinary_returns_have_exact_zero_variance():
    from sentinel.quant import compute_risk

    data = risk_input(np.full((60, 3), 0.1), min_observations=60)
    result = compute_risk(data)
    assert result.annualized_vol == result.max_drawdown == 0.0
    assert result.correlation.matrix == [[1.0, None, None], [None, 1.0, None], [None, None, 1.0]]
    assert result.svd.explained == result.svd.loadings == []
    assert result.condition_number_raw is result.condition_number_shrunk is None
    assert "资产无波动" in result.warnings[-1]


def test_drawdown_includes_initial_loss_and_extreme_wealth_stays_finite():
    from sentinel.quant import compute_risk

    returns = np.array([[-0.5]] + [[0.1]] * 59)
    result = compute_risk(risk_input(returns, [1.0], min_observations=60))
    assert result.max_drawdown == pytest.approx(0.5)
    wealth_overflow = compute_risk(risk_input(np.full((756, 1), 1000.0), [1.0]))
    assert wealth_overflow.max_drawdown == wealth_overflow.annualized_vol == 0.0
    total_loss = compute_risk(risk_input(np.array([[-1.0]] + [[0.0]] * 59), [1.0]))
    assert total_loss.max_drawdown == 1.0


def test_compute_is_pure_and_readonly_arrays_work():
    from sentinel.quant import compute_risk

    data = risk_input()
    snapshots = [array.copy() for array in (data.returns, data.weights, data.endpoint_closes)]
    for array in (data.returns, data.weights, data.endpoint_closes):
        array.flags.writeable = False
    first = compute_risk(data)
    assert first == compute_risk(data)
    for actual, expected in zip(
        (data.returns, data.weights, data.endpoint_closes), snapshots, strict=True
    ):
        np.testing.assert_array_equal(actual, expected)


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -float("inf")])
def test_pure_nonfinite_input_never_reaches_wire(bad):
    from sentinel.errors import UserError
    from sentinel.quant import compute_risk

    for name in ("returns", "weights", "endpoint_closes"):
        data = risk_input()
        getattr(data, name).flat[0] = bad
        with pytest.raises(UserError, match="INVALID_ARGUMENT"):
            compute_risk(data)


def test_overflowing_covariance_is_an_error_not_fake_zero():
    from sentinel.errors import UserError
    from sentinel.quant import compute_risk

    with pytest.raises(UserError) as raised:
        compute_risk(risk_input(np.array([[1e200], [0.0], [1e200], [0.0]]), [1.0]))
    assert raised.value.reason == "NUMERICAL_OVERFLOW"


@pytest.mark.parametrize(
    "patch",
    [
        {"weights": np.array([0.5, 0.3, -0.2])},
        {"weights": np.array([0.5, 0.3, 0.1])},
        {"weights": np.array([0.5, 0.3], dtype=np.float64)},
        {"returns": DOCUMENT_RETURNS.astype(np.float32)},
        {"window_observations": 6},
        {"symbols": ["ZZCL", "ZZAR", "ZZFD"]},
        {"instrument_ids": ["us:ZZAR", "us:ZZAR", "us:ZZFD"]},
    ],
)
def test_malformed_matrix_metadata_is_rejected(patch):
    from sentinel.errors import UserError
    from sentinel.quant import compute_risk

    with pytest.raises(UserError, match="INVALID_ARGUMENT"):
        compute_risk(replace(risk_input(), **patch))


def test_svd_top_five_keeps_nonzero_column_mapping():
    from sentinel.quant import compute_risk

    rng = np.random.default_rng(41)
    symbols = ["ZZAR", "ZZBK", "ZZCL", "ZZEN", "ZZFD", "ZZMD"]
    returns = rng.normal(0, 0.01, (65, 6))
    data = replace(
        risk_input(),
        symbols=symbols,
        instrument_ids=[f"us:{s}" for s in symbols],
        returns=returns,
        weights=np.full(6, 1 / 6),
        endpoint_closes=np.full(6, 100.0),
        window_observations=65,
        min_observations=60,
    )
    result = compute_risk(data)
    assert len(result.svd.explained) == 5
    assert sum(result.svd.explained) < 1.0
    returns[:, 2] = 0.0
    result = compute_risk(data)
    assert len(result.svd.explained) == len(result.svd.loadings) == 5
    assert sum(result.svd.explained) <= 1.0
    assert "ZZCL" not in [item.symbol for item in result.svd.loadings]
    assert result.correlation.symbols == symbols
    assert result.correlation.matrix[2][0] is None
    assert result.correlation.matrix[2][2] == 1.0
    assert len(result.top_weights) == 3
    assert [item.symbol for item in result.top_weights] == symbols[:3]


def test_actual_largest_loading_sign_wins_over_near_tie(monkeypatch):
    from sentinel.quant import compute_risk

    original = np.linalg.svd

    def near_tied(*args, **kwargs):
        u, singular, vt = original(*args, **kwargs)
        vt[0] = [-0.707106781186, 0.707106781187, 0.0]
        return u, singular, vt

    monkeypatch.setattr(np.linalg, "svd", near_tied)
    result = compute_risk(risk_input())
    maximum = max(result.svd.loadings, key=lambda item: abs(item.value))
    assert maximum.symbol == "ZZCL" and maximum.value > 0
