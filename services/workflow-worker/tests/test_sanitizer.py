"""Tests for sanitizer.py — @mention redaction, HTML escaping, size limits."""
import pytest


def test_sanitize_string_redacts_at_mentions():
    from app.sanitizer import sanitize_string

    result = sanitize_string("Hello @alice, meet @bob_123")
    assert "@alice" not in result
    assert "@bob_123" not in result
    assert result.count("(mention redacted)") == 2


def test_sanitize_string_escapes_html_angle_brackets():
    from app.sanitizer import sanitize_string

    result = sanitize_string("check <script>alert('xss')</script>")
    assert "<script>" not in result
    assert "&lt;script&gt;" in result
    assert "&lt;/script&gt;" in result


def test_sanitize_string_truncates_over_50k():
    from app.sanitizer import sanitize_string

    long_str = "x" * 60_000
    result = sanitize_string(long_str)
    assert "[truncated]" in result
    # Result must not grow beyond the truncation cap plus the suffix
    assert len(result) <= 50_000 + len(" [truncated]")


def test_sanitize_string_no_change_for_clean_input():
    from app.sanitizer import sanitize_string

    clean = "Hello world, this is fine."
    assert sanitize_string(clean) == clean


def test_sanitize_string_exactly_at_limit_not_truncated():
    from app.sanitizer import sanitize_string

    at_limit = "y" * 50_000
    result = sanitize_string(at_limit)
    assert "[truncated]" not in result
    assert len(result) == 50_000


def test_sanitize_inputs_redacts_nested_strings():
    from app.sanitizer import sanitize_inputs

    result = sanitize_inputs({"message": "ping @devteam", "count": 42})
    assert "(mention redacted)" in result["message"]
    assert result["count"] == 42


def test_sanitize_inputs_key_limit_stops_at_100():
    from app.sanitizer import sanitize_inputs

    many_keys = {f"k{i}": f"v{i}" for i in range(150)}
    result = sanitize_inputs(many_keys)
    # _MAX_KEYS_TOTAL = 100 — excess keys are dropped
    assert len(result) < 150
    assert len(result) <= 100


def test_sanitize_inputs_oversized_drops_nested_objects():
    from app.sanitizer import sanitize_inputs

    # Build an input that exceeds 1 MB after sanitization.
    # 25 strings × 50 000 chars ≈ 1.25 MB serialized.
    inputs: dict = {f"content_{i}": "x" * 50_000 for i in range(25)}
    inputs["count"] = 42
    inputs["flag"] = True
    inputs["nested"] = {"a": "should be dropped"}
    inputs["items"] = [1, 2, 3]

    result = sanitize_inputs(inputs)

    # Scalars are kept by the fallback
    assert result.get("count") == 42
    assert result.get("flag") is True
    # Complex types (dict, list) are dropped by the fallback
    assert not isinstance(result.get("nested"), dict)
    assert not isinstance(result.get("items"), list)
