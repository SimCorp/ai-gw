# services/league/app/scoring.py

import types
from collections.abc import Mapping

DEFAULT_WEIGHTS: types.MappingProxyType = types.MappingProxyType(
    {
        "quality": 0.35,
        "robustness": 0.20,
        "token_efficiency": 0.15,
        "speed": 0.10,
        "cost_efficiency": 0.10,
        "improvement_rate": 0.05,
        "creativity": 0.05,
    }
)


def score_quality_exact(results: list[dict]) -> float:
    """Score quality by exact string match. results = [{expected, actual}, ...]"""
    if not results:
        return 0.0
    passed = sum(1 for r in results if str(r.get("actual", "")).strip() == str(r.get("expected", "")).strip())
    return passed * 100.0 / len(results)


def score_efficiency(actual: float, median: float) -> float:
    """Score efficiency: using less than median is better. Returns 0-100.

    Formula: (median / actual) * 50, capped at 100, floored at 0.
    median=0 returns neutral 50. actual=0 treated as 1.
    """
    if median == 0:
        return 50.0
    actual = max(actual, 1)
    return min(100.0, max(0.0, (median / actual) * 50.0))


def score_robustness(passed: int, total: int) -> float:
    """Score robustness as % of edge-case test variants passed. Returns 0-100."""
    if total == 0:
        return 0.0
    return min(100.0, passed * 100.0 / total)


def score_improvement_rate(current: float, prior_best: float | None) -> float:
    """Score improvement vs personal season best. Returns 0-100.

    No prior best (first submission) → 50 (neutral).
    +50% or more improvement → 100 (cap).
    No change → 50 (neutral).
    Any regression → proportionally below 50; deep regression (≥50% drop) → 0 (floor).
    """
    if prior_best is None or prior_best == 0:
        return 50.0
    delta = (current - prior_best) / prior_best  # e.g. 0.5 = 50% improvement
    # Map: delta=0 -> 50, delta=+0.5 -> 100, delta=-0.5 -> 0
    # score = 50 + delta * 100, clamped to [0, 100]
    return min(100.0, max(0.0, 50.0 + delta * 100.0))


def compute_composite(scores: Mapping[str, float], weights: Mapping[str, float]) -> float:
    """Compute weighted composite score 0-1000.

    Raises ValueError if weights don't sum to 1.0 (+-0.01 tolerance).
    """
    weight_sum = sum(weights.values())
    if abs(weight_sum - 1.0) > 0.01:
        raise ValueError(f"weights must sum to 1.0, got {weight_sum:.4f}")
    raw = sum(scores.get(dim, 0.0) * w for dim, w in weights.items())
    return round(raw * 10.0, 2)  # scale 0-100 weighted avg -> 0-1000
