"""Small statistical helpers for honest measurements."""

from __future__ import annotations

import random
from statistics import median
from typing import Callable, Sequence

Statistic = Callable[[Sequence[float]], float]


def bootstrap_ci(
    samples: Sequence[float],
    statistic: Statistic = median,
    confidence: float = 0.95,
    resamples: int = 500,
    seed: int = 0,
) -> dict[str, float]:
    values = [float(x) for x in samples]
    if not values:
        return {"estimate": 0.0, "low": 0.0, "high": 0.0}
    rng = random.Random(seed)
    n = len(values)
    estimates = sorted(
        statistic([values[rng.randrange(n)] for _ in range(n)]) for _ in range(resamples)
    )
    tail = (1.0 - confidence) / 2.0
    low = estimates[max(0, int(tail * resamples))]
    high = estimates[min(resamples - 1, int((1.0 - tail) * resamples) - 1)]
    return {"estimate": statistic(values), "low": low, "high": high}


def bootstrap_ratio_ci(
    numerator: Sequence[float],
    denominator: Sequence[float],
    confidence: float = 0.95,
    resamples: int = 500,
    seed: int = 0,
) -> dict[str, float]:
    a = [float(x) for x in numerator]
    b = [float(x) for x in denominator]
    if not a or not b:
        return {"estimate": 0.0, "low": 0.0, "high": 0.0}
    rng = random.Random(seed)
    ratios = []
    for _ in range(resamples):
        ra = median([a[rng.randrange(len(a))] for _ in range(len(a))])
        rb = median([b[rng.randrange(len(b))] for _ in range(len(b))])
        ratios.append(ra / rb if rb else 0.0)
    ratios.sort()
    tail = (1.0 - confidence) / 2.0
    low = ratios[max(0, int(tail * resamples))]
    high = ratios[min(resamples - 1, int((1.0 - tail) * resamples) - 1)]
    return {"estimate": median(a) / median(b) if median(b) else 0.0, "low": low, "high": high}
