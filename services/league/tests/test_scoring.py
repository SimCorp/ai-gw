# services/league/tests/test_scoring.py
import pytest
from app.scoring import (
    DEFAULT_WEIGHTS,
    compute_composite,
    score_efficiency,
    score_improvement_rate,
    score_quality_exact,
    score_robustness,
)


# quality: exact match
def test_quality_exact_all_correct():
    results = [
        {"expected": "A", "actual": "A"},
        {"expected": "B", "actual": "B"},
    ]
    assert score_quality_exact(results) == pytest.approx(100.0)


def test_quality_exact_half_correct():
    results = [
        {"expected": "A", "actual": "A"},
        {"expected": "B", "actual": "C"},
    ]
    assert score_quality_exact(results) == pytest.approx(50.0)


def test_quality_exact_empty():
    assert score_quality_exact([]) == pytest.approx(0.0)


# efficiency (token, speed, cost all use same formula)
def test_efficiency_at_median():
    # using exactly the median should score 50
    assert score_efficiency(actual=100, median=100) == pytest.approx(50.0)


def test_efficiency_half_median():
    # using half the median should score 100 (capped)
    assert score_efficiency(actual=50, median=100) == pytest.approx(100.0)


def test_efficiency_double_median():
    # using double the median should score 25
    assert score_efficiency(actual=200, median=100) == pytest.approx(25.0)


def test_efficiency_zero_actual():
    # zero actual is treated as 1 to avoid division by zero
    assert score_efficiency(actual=0, median=100) == pytest.approx(100.0)


def test_efficiency_zero_median():
    # zero median falls back to 50 (neutral)
    assert score_efficiency(actual=100, median=0) == pytest.approx(50.0)


# robustness
def test_robustness_all_pass():
    assert score_robustness(passed=10, total=10) == pytest.approx(100.0)


def test_robustness_none_pass():
    assert score_robustness(passed=0, total=10) == pytest.approx(0.0)


def test_robustness_zero_total():
    assert score_robustness(passed=0, total=0) == pytest.approx(0.0)


def test_robustness_passed_exceeds_total():
    # should be capped at 100, not return 150
    assert score_robustness(passed=15, total=10) == pytest.approx(100.0)


# improvement rate
def test_improvement_rate_first_submission():
    # no prior best -> neutral score of 50
    assert score_improvement_rate(current=700.0, prior_best=None) == pytest.approx(50.0)


def test_improvement_rate_50pct_improvement():
    # 50% improvement from prior best -> score 100 (cap)
    assert score_improvement_rate(current=900.0, prior_best=600.0) == pytest.approx(100.0)


def test_improvement_rate_no_improvement():
    # same score as prior best -> score 50 (neutral)
    assert score_improvement_rate(current=600.0, prior_best=600.0) == pytest.approx(50.0)


def test_improvement_rate_regression():
    # worse than prior best -> score 0 (floor)
    assert score_improvement_rate(current=300.0, prior_best=600.0) == pytest.approx(0.0)


def test_improvement_rate_shallow_regression():
    # -5% regression → proportionally below 50 (not 0)
    result = score_improvement_rate(current=570.0, prior_best=600.0)
    assert 40.0 < result < 50.0  # somewhere in the partial-regression range


# composite
def test_composite_all_100():
    scores = {
        "quality": 100.0,
        "robustness": 100.0,
        "token_efficiency": 100.0,
        "speed": 100.0,
        "cost_efficiency": 100.0,
        "improvement_rate": 100.0,
        "creativity": 100.0,
    }
    # weights sum to 1.0 -> composite = 100 * 1000 / 100 = 1000
    assert compute_composite(scores, DEFAULT_WEIGHTS) == pytest.approx(1000.0)


def test_composite_all_zero():
    scores = {k: 0.0 for k in DEFAULT_WEIGHTS}
    assert compute_composite(scores, DEFAULT_WEIGHTS) == pytest.approx(0.0)


def test_composite_weights_must_sum_to_1():
    bad_weights = {k: 0.5 for k in DEFAULT_WEIGHTS}  # sums to 3.5
    with pytest.raises(ValueError, match="weights must sum to 1.0"):
        compute_composite({k: 50.0 for k in DEFAULT_WEIGHTS}, bad_weights)
