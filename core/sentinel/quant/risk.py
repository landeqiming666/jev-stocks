from __future__ import annotations

import math
from typing import cast

import numpy as np

from sentinel.errors import UserError
from sentinel.messages.risk import text

from .models import (
    Correlation,
    FloatArray,
    Loading,
    RiskDataInsufficient,
    RiskInput,
    RiskResult,
    RiskWindow,
    SVDResult,
    TopWeight,
)

PERIODS_PER_YEAR = 252
MIN_OBSERVATIONS = 60
SHRINKAGE_ALPHA = 0.1
SINGULARITY_RATIO = 1e-12
MAX_EXPLAINED_COMPONENTS = 5


def _center(returns: FloatArray) -> FloatArray:
    centered = returns - returns.mean(axis=0)
    # 恒定的非二进制小数也必须精确零方差，不能让均值舍入制造伪波动。
    centered[:, np.all(returns == returns[0], axis=0)] = 0.0
    return centered


def sample_covariance(returns: FloatArray) -> FloatArray:
    centered = _center(returns)
    return centered.T @ centered / (len(returns) - 1)


def shrink_covariance(covariance: FloatArray, alpha: float = SHRINKAGE_ALPHA) -> FloatArray:
    n = len(covariance)
    return cast(
        FloatArray, (1 - alpha) * covariance + alpha * (np.trace(covariance) / n) * np.eye(n)
    )


def _condition(covariance: FloatArray, ratio: float) -> float | None:
    eigenvalues = np.linalg.eigvalsh(covariance)
    smallest, largest = float(eigenvalues[0]), float(eigenvalues[-1])
    if not math.isfinite(largest) or smallest <= ratio * largest:
        return None
    value = largest / smallest
    return max(1.0, value) if math.isfinite(value) else None


def _validate(data: RiskInput) -> None:
    if type(data.min_observations) is not int or data.min_observations < 2:
        raise UserError("INVALID_ARGUMENT", field="min_observations")
    arrays = (data.returns, data.weights, data.endpoint_closes)
    if any(
        not isinstance(array, np.ndarray)
        or array.dtype != np.float64
        or not np.isfinite(array).all()
        for array in arrays
    ):
        raise UserError("INVALID_ARGUMENT", field="returns", reason="NONFINITE_OR_NON_FLOAT64")
    n = len(data.symbols)
    if data.returns.ndim != 2 or data.returns.shape[1] != n:
        raise UserError("INVALID_ARGUMENT", field="returns")
    observations = len(data.returns)
    if n == 0 or observations < data.min_observations:
        raise RiskDataInsufficient(observations, data.min_observations, no_holdings=n == 0)
    if (
        data.weights.shape != (n,)
        or data.endpoint_closes.shape != (n,)
        or len(data.instrument_ids) != n
        or len(set(data.instrument_ids)) != n
        or len(set(data.symbols)) != n
        or data.symbols != sorted(data.symbols)
        or data.window_observations != observations
        or (
            data.return_dates
            and (
                len(data.return_dates) != observations
                or data.return_dates != sorted(set(data.return_dates))
            )
        )
        or np.any(data.weights < 0)
        or np.any(data.endpoint_closes <= 0)
        or not math.isclose(float(data.weights.sum()), 1.0, rel_tol=0, abs_tol=1e-12)
        or np.any(data.returns < -1)
        or data.price_basis not in ("close", "adj_close")
        or data.window_label not in ("6M", "1Y", "3Y")
        or data.from_date > data.as_of
    ):
        raise UserError("INVALID_ARGUMENT", field="riskInput")


def _svd(centered: FloatArray, covariance: FloatArray, symbols: list[str]) -> SVDResult:
    standard_deviations = np.sqrt(np.diag(covariance))
    active = np.flatnonzero(standard_deviations > 0)
    if not len(active):
        return SVDResult(explained=[], loadings=[])
    standardized = centered[:, active] / standard_deviations[active]
    _, singular, vt = np.linalg.svd(standardized, full_matrices=False)
    squares = singular**2
    explained = squares / squares.sum()
    values = vt[0].copy()
    # 列已按 symbol 排序；精确并列取首列，符号严格以实际最大绝对值为准。
    pivot = int(np.argmax(np.abs(values)))
    if values[pivot] < 0:
        values *= -1
    order = sorted(
        range(len(active)),
        key=lambda i: (-round(abs(float(values[i])), 12), symbols[int(active[i])]),
    )
    parts = [float(value) for value in explained[:MAX_EXPLAINED_COMPONENTS]]
    if sum(parts) > 1.0:
        parts[-1] = max(0.0, 1.0 - sum(parts[:-1]))
    return SVDResult(
        explained=parts,
        loadings=[
            Loading(symbol=symbols[int(active[i])], value=float(np.clip(values[i], -1, 1)))
            for i in order[:MAX_EXPLAINED_COMPONENTS]
        ],
    )


def _drawdown(portfolio: FloatArray) -> float:
    # 对数净值避免长窗口或极端有限收益使 cumprod 溢出；首次亏损也计入 V0 峰值。
    if np.any(portfolio <= -1):
        return 1.0
    log_values = np.concatenate(([0.0], np.cumsum(np.log1p(portfolio))))
    log_peaks = np.maximum.accumulate(log_values)
    return float(np.max(-np.expm1(log_values - log_peaks)))


def _finite_parameter(value: object, field: str) -> float:
    # bool 与自定义 __float__ 均不能成为数值配置，避免隐式转换执行调用方代码。
    if type(value) not in (int, float):
        raise UserError("INVALID_ARGUMENT", field=field)
    try:
        number = float(cast(int | float, value))
    except OverflowError as exc:
        raise UserError("INVALID_ARGUMENT", field=field) from exc
    if not math.isfinite(number):
        raise UserError("INVALID_ARGUMENT", field=field)
    return number


def compute_risk(
    data: RiskInput,
    *,
    shrinkage_alpha: float = SHRINKAGE_ALPHA,
    singularity_ratio: float = SINGULARITY_RATIO,
) -> RiskResult:
    _validate(data)
    shrinkage_alpha = _finite_parameter(shrinkage_alpha, "shrinkage_alpha")
    singularity_ratio = _finite_parameter(singularity_ratio, "singularity_ratio")
    if not 0 <= shrinkage_alpha <= 1:
        raise UserError("INVALID_ARGUMENT", field="shrinkage_alpha")
    if not 0 < singularity_ratio < 1:
        raise UserError("INVALID_ARGUMENT", field="singularity_ratio")
    try:
        with np.errstate(over="raise", invalid="raise", divide="raise"):
            covariance = sample_covariance(data.returns)
            shrunk = shrink_covariance(covariance, shrinkage_alpha)
            raw_condition = _condition(covariance, singularity_ratio)
            shrunk_condition = _condition(shrunk, singularity_ratio)
            variance = float(data.weights @ covariance @ data.weights)
            annualized = math.sqrt(PERIODS_PER_YEAR * max(0.0, variance))
            portfolio = data.returns @ data.weights
            drawdown = _drawdown(portfolio)
            effective = max(1.0, 1 / float(data.weights @ data.weights))
            svd = _svd(_center(data.returns), covariance, data.symbols)
    except (FloatingPointError, np.linalg.LinAlgError, OverflowError) as exc:
        raise UserError("INVALID_ARGUMENT", field="returns", reason="NUMERICAL_OVERFLOW") from exc
    if not all(math.isfinite(value) for value in (annualized, drawdown, effective)):
        raise UserError("INVALID_ARGUMENT", field="returns", reason="NONFINITE_RESULT")
    n = len(data.symbols)
    standard_deviations = np.sqrt(np.diag(covariance))
    matrix: list[list[float | None]] = []
    for i in range(n):
        row: list[float | None] = []
        for j in range(n):
            value: float | None = None
            if i == j:
                value = 1.0
            elif standard_deviations[i] > 0 and standard_deviations[j] > 0:
                correlation = float(
                    covariance[i, j] / standard_deviations[i] / standard_deviations[j]
                )
                value = float(np.clip(correlation, -1, 1)) if math.isfinite(correlation) else None
            row.append(value)
        matrix.append(row)
    warnings = []
    if data.price_basis == "close":
        warnings.append(text("risk.unadjusted"))
    if raw_condition is None or shrunk_condition is None:
        warnings.append(text("risk.singular"))
    if n == 1:
        warnings.append(text("risk.single"))
    warnings.extend(data.warnings)
    if np.all(standard_deviations == 0):
        warnings.append(text("risk.zero_variance"))
    elif np.any(standard_deviations == 0):
        warnings.append(text("risk.partial_zero_variance"))
    order = sorted(range(n), key=lambda i: (-float(data.weights[i]), data.symbols[i]))
    return RiskResult(
        as_of=data.as_of,
        window=RiskWindow(
            label=data.window_label,
            from_date=data.from_date,
            to=data.as_of,
            observations=data.window_observations,
        ),
        annualized_vol=annualized,
        max_drawdown=drawdown,
        effective_holdings=effective,
        top_weights=[
            TopWeight(
                instrument_id=data.instrument_ids[i],
                symbol=data.symbols[i],
                weight=float(data.weights[i]),
            )
            for i in order[:3]
        ],
        correlation=Correlation(
            instrument_ids=list(data.instrument_ids), symbols=list(data.symbols), matrix=matrix
        ),
        svd=svd,
        condition_number_raw=raw_condition,
        condition_number_shrunk=shrunk_condition,
        warnings=list(dict.fromkeys(warnings)),
        excluded=list(data.excluded),
    )
