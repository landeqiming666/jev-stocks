import math
import random
from collections import Counter
from collections.abc import Sequence
from decimal import Decimal

import numpy as np

from .models import EvalSample, Gold, MetricPair, Metrics, PredictionRow, Usage

BOOTSTRAP_SEED = 20261102
BOOTSTRAP_N = 1000
POSITIVE_CLASSES = {"weaken", "overturn"}
GOLD_CLASSES: tuple[Gold, ...] = ("none", "support", "weaken", "overturn")
PREDICTED_CLASSES = (*GOLD_CLASSES, "uncertain")


def wilson(success: int, total: int) -> tuple[float, float] | None:
    if type(success) is not int or type(total) is not int or not 0 <= success <= total:
        raise ValueError("invalid Wilson counts")
    if not total:
        return None
    z = 1.959963984540054
    p, z2 = success / total, z * z
    center = (p + z2 / (2 * total)) / (1 + z2 / total)
    margin = z * math.sqrt(p * (1 - p) / total + z2 / (4 * total * total)) / (1 + z2 / total)
    return max(0.0, center - margin), min(1.0, center + margin)


def bootstrap_f1(pairs: Sequence[tuple[bool, bool]]) -> tuple[float, float] | None:
    if not pairs:
        return None
    rng = random.Random(BOOTSTRAP_SEED)
    values = []
    for _ in range(BOOTSTRAP_N):
        selected = [pairs[rng.randrange(len(pairs))] for _ in pairs]
        tp = sum(a and b for a, b in selected)
        fp = sum(not a and b for a, b in selected)
        fn = sum(a and not b for a, b in selected)
        values.append(2 * tp / (2 * tp + fp + fn) if tp + fp + fn else 0.0)
    quantiles = np.quantile(values, [0.025, 0.975])
    return float(quantiles[0]), float(quantiles[1])


def compute_metrics(rows: Sequence[PredictionRow], positives: set[str]) -> Metrics:
    if positives not in (POSITIVE_CLASSES, POSITIVE_CLASSES | {"uncertain"}):
        raise ValueError("unknown positive classes")
    valid = [r for r in rows if r.status == "ok"]
    if any(r.relation not in PREDICTED_CLASSES for r in valid):
        raise ValueError("successful prediction missing relation")
    pairs = [(r.gold in POSITIVE_CLASSES, r.relation in positives) for r in valid]
    tp = sum(a and b for a, b in pairs)
    fp = sum(not a and b for a, b in pairs)
    fn = sum(a and not b for a, b in pairs)
    tn = sum(not a and not b for a, b in pairs)
    matrix = [
        [sum(r.gold == g and r.relation == p for r in valid) for p in PREDICTED_CLASSES]
        for g in GOLD_CLASSES
    ]
    return Metrics(
        n=len(valid),
        positive_count=tp + fn,
        tp=tp,
        fp=fp,
        fn=fn,
        tn=tn,
        precision=tp / (tp + fp) if tp + fp else None,
        recall=tp / (tp + fn) if tp + fn else None,
        f1=2 * tp / (2 * tp + fp + fn) if tp + fp + fn else (0.0 if valid else None),
        precision_ci=wilson(tp, tp + fp),
        recall_ci=wilson(tp, tp + fn),
        f1_ci=bootstrap_f1(pairs),
        matrix=matrix,
    )


def metric_pair(rows: Sequence[PredictionRow]) -> MetricPair:
    return MetricPair(
        strict=compute_metrics(rows, POSITIVE_CLASSES),
        lenient=compute_metrics(rows, POSITIVE_CLASSES | {"uncertain"}),
    )


def total_usage(rows: Sequence[PredictionRow]) -> Usage:
    return Usage(
        calls=sum(r.usage.calls for r in rows),
        input_tokens=sum(r.usage.input_tokens for r in rows),
        output_tokens=sum(r.usage.output_tokens for r in rows),
        latency_ms=sum(r.usage.latency_ms for r in rows),
        cost_usd=sum((r.usage.cost_usd for r in rows), Decimal("0.000000")),
        estimated=any(r.usage.estimated for r in rows),
        complete=all(r.usage.complete for r in rows),
    )


def cohen_kappa(samples: Sequence[EvalSample], ids: Sequence[str]) -> float | None:
    pairs = [
        tuple(next(a.relation for a in s.annotators if a.id == i) for i in ids) for s in samples
    ]
    if not pairs:
        return None
    n = len(pairs)
    left, right = Counter(p[0] for p in pairs), Counter(p[1] for p in pairs)
    expected = sum(left[c] * right[c] for c in GOLD_CLASSES) / (n * n)
    observed = sum(a == b for a, b in pairs) / n
    return (observed - expected) / (1 - expected) if expected < 1 else None
