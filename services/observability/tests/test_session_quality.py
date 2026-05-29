"""Unit tests for _session_quality_score in observability postgres worker."""

from app.workers.postgres import _session_quality_score


def test_baseline_score_is_3():
    """Neutral conditions (mid-range rates, normal turn count, moderate timing) produce score 3."""
    # 10 turns, 2 retries (20%), 2 errors (20%), 60s — all in neutral bands → no adjustments
    assert _session_quality_score(10, 2, 2, 60.0) == 3


def test_low_retry_and_error_rates_add_two():
    """<10% retry + <10% error each add 1 → max bonus = 5."""
    score = _session_quality_score(10, 0, 0, 60.0)
    assert score == 5


def test_high_retry_rate_subtracts_one():
    score = _session_quality_score(10, 5, 0, 60.0)  # retry_rate = 0.5
    # -1 retry, +1 error(0), 0 turn bonus → 3
    assert score == 3


def test_high_error_rate_subtracts_one():
    score = _session_quality_score(10, 0, 5, 60.0)  # error_rate = 0.5
    # +1 retry, -1 error, 0 turn bonus → 3
    assert score == 3


def test_single_turn_subtracts_one():
    score = _session_quality_score(1, 0, 0, None)
    # +1 retry, +1 error, -1 single turn → 4
    assert score == 4


def test_many_turns_subtracts_one():
    score = _session_quality_score(25, 0, 0, 60.0)
    # +1 retry, +1 error, -1 many turns → 4
    assert score == 4


def test_long_inter_request_adds_one():
    score = _session_quality_score(5, 0, 0, 180.0)  # > 120s
    # +1 retry, +1 error, +1 timing → 5 (capped)
    assert score == 5


def test_rapid_fire_with_many_turns_subtracts_one():
    score = _session_quality_score(10, 0, 0, 5.0)  # <10s + >3 turns
    # +1 retry, +1 error, -1 rapid → 4
    assert score == 4


def test_rapid_fire_single_turn_no_penalty():
    """Rapid-fire only penalizes when turn_count > 3."""
    score = _session_quality_score(1, 0, 0, 5.0)
    # +1 retry, +1 error, -1 single turn, no rapid penalty → 4
    assert score == 4


def test_none_inter_request_no_timing_bonus():
    score = _session_quality_score(5, 0, 0, None)
    # +1 retry, +1 error, no timing → 5
    assert score == 5


def test_minimum_score_is_1():
    score = _session_quality_score(25, 10, 10, 5.0)  # all penalties
    # -1 retry, -1 error, -1 turns, -1 rapid → 3 - 4 = -1 → clamped to 1
    assert score == 1


def test_maximum_score_is_5():
    score = _session_quality_score(5, 0, 0, 180.0)
    assert score == 5


def test_normal_retry_rate_no_adjustment():
    """10-30% retry rate → no change."""
    score = _session_quality_score(10, 2, 0, 60.0)  # retry_rate = 0.2
    # 0 retry adj, +1 error, 0 turn → 4
    assert score == 4


def test_boundary_retry_rate_exactly_10pct():
    """Exactly 10% → not < 0.1 → no bonus."""
    score = _session_quality_score(10, 1, 0, 60.0)  # retry_rate = 0.1
    # 0 retry adj, +1 error → 4
    assert score == 4


def test_boundary_retry_rate_exactly_30pct():
    """Exactly 30% → not > 0.3 → no penalty."""
    score = _session_quality_score(10, 3, 0, 60.0)  # retry_rate = 0.3
    # 0 retry adj, +1 error → 4
    assert score == 4
