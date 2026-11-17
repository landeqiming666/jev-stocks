import random
from decimal import ROUND_DOWN, Decimal, Inexact, Rounded, localcontext

import numpy as np
import pytest

from sentinel.evaluation.metrics import bootstrap_f1, compute_metrics, total_usage, wilson
from sentinel.evaluation.models import PredictionRow, Usage


def row(gold, predicted, **kwargs):
    return PredictionRow(
        id="p",
        split="test",
        lang="zh",
        subsets=[],
        gold=gold,
        relation=predicted,
        status="ok",
        **kwargs,
    )


def test_confusion_matrix_matches_hand_counted_example():
    rows = [
        row("none", "none"),
        row("support", "support"),
        row("weaken", "weaken"),
        row("overturn", "overturn"),
        row("weaken", "uncertain"),
    ]
    strict = compute_metrics(rows, {"weaken", "overturn"})
    assert strict.matrix == [[1, 0, 0, 0, 0], [0, 1, 0, 0, 0], [0, 0, 1, 0, 1], [0, 0, 0, 1, 0]]
    assert (strict.tp, strict.fp, strict.fn, strict.tn) == (2, 0, 1, 2)
    assert strict.precision == 1
    assert strict.recall == pytest.approx(2 / 3)
    assert strict.f1 == 0.8
    assert strict.positive_count == 3
    assert compute_metrics(rows, {"weaken", "overturn", "uncertain"}).f1 == 1


def test_wilson_interval_for_zero_success():
    assert wilson(0, 10) == pytest.approx((0, 0.2775327998628892))
    assert wilson(0, 0) is None
    assert wilson(10, 10) == pytest.approx((0.7224672001371107, 1))


def test_bootstrap_matches_independent_resampling():
    pairs = [(True, True), (True, False), (False, True), (False, False), (True, True)]
    rng = random.Random(20261102)
    scores = []
    for _ in range(1000):
        selected = [pairs[rng.randrange(5)] for _ in range(5)]
        tp = sum(a and b for a, b in selected)
        fp = sum(not a and b for a, b in selected)
        fn = sum(a and not b for a, b in selected)
        scores.append(2 * tp / (2 * tp + fp + fn) if tp + fp + fn else 0)
    expected = tuple(np.quantile(scores, [0.025, 0.975]))
    assert bootstrap_f1(pairs) == expected
    assert bootstrap_f1(pairs) == bootstrap_f1(pairs)
    assert bootstrap_f1([]) is None


def test_failed_prediction_is_not_counted_as_none():
    rows = [
        row("none", "none"),
        PredictionRow(
            id="failed",
            split="test",
            lang="en",
            subsets=[],
            gold="weaken",
            status="failed",
            error="MODEL_ERROR",
        ),
    ]
    metrics = compute_metrics(rows, {"weaken", "overturn"})
    assert metrics.n == 1
    assert sum(map(sum, metrics.matrix)) == 1
    assert metrics.f1 == 0
    assert not total_usage(rows).complete


def test_wilson_for_nonzero_success_matches_independent_formula():
    import math

    lower, upper = wilson(2, 3)
    z = 1.959963984540054
    denominator = 1 + z * z / 3
    midpoint = (2 / 3 + z * z / 6) / denominator
    halfwidth = z * math.sqrt((2 / 3) * (1 / 3) / 3 + z * z / 36) / denominator
    assert (lower, upper) == pytest.approx((midpoint - halfwidth, midpoint + halfwidth))


def test_usage_cost_sum_isolated_from_caller_decimal_context():
    rows = [
        row("none", "none", usage=Usage(cost_usd=Decimal(value)))
        for value in ("123456789012345678901234567890.123456", ".000001", ".000004")
    ]
    with localcontext() as ctx:
        ctx.prec, ctx.rounding, ctx.Emax, ctx.Emin, ctx.clamp = 1, ROUND_DOWN, 6, -6, 1
        ctx.traps[Inexact] = ctx.traps[Rounded] = True
        ctx.flags[Inexact] = True
        before = (repr(ctx), dict(ctx.flags), dict(ctx.traps))
        usage = total_usage(rows)
        assert usage.cost_usd == Decimal("123456789012345678901234567890.123461")
        assert usage.complete
        assert (repr(ctx), dict(ctx.flags), dict(ctx.traps)) == before


@pytest.mark.parametrize("status", ["failed", "not_run"])
def test_non_successful_usage_never_claims_complete(status):
    stopped = row("none", "none", usage=Usage(cost_usd=Decimal(".000001")))
    stopped.status = status
    assert total_usage([stopped]).cost_usd == Decimal(".000001")
    assert not total_usage([stopped]).complete
