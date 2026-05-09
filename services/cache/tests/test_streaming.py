"""Unit tests for SSE parsers and intent classifier in cache router."""
import json
import pytest

from app.router import (
    _classify_intent,
    _parse_sse_usage_anthropic,
    _parse_sse_usage_openai,
)


# ---------------------------------------------------------------------------
# _parse_sse_usage_openai
# ---------------------------------------------------------------------------

def _openai_chunk(**kwargs) -> bytes:
    return (f"data: {json.dumps(kwargs)}\n\n").encode()


def _make_openai_stream(*chunks: dict, include_done: bool = True) -> bytes:
    parts = [_openai_chunk(**c) for c in chunks]
    if include_done:
        parts.append(b"data: [DONE]\n\n")
    return b"".join(parts)


def test_openai_usage_in_final_chunk():
    stream = _make_openai_stream(
        {"choices": [{"delta": {"content": "hello"}}]},
        {"choices": [{"delta": {}}], "usage": {"prompt_tokens": 42, "completion_tokens": 18}},
    )
    assert _parse_sse_usage_openai(stream) == (42, 18)


def test_openai_usage_before_done():
    """Usage chunk followed by [DONE] — must still be found scanning in reverse."""
    stream = _make_openai_stream(
        {"choices": [], "usage": {"prompt_tokens": 10, "completion_tokens": 5}},
    )
    assert _parse_sse_usage_openai(stream) == (10, 5)


def test_openai_no_usage_returns_zeros():
    stream = _make_openai_stream(
        {"choices": [{"delta": {"content": "hi"}}]},
    )
    assert _parse_sse_usage_openai(stream) == (0, 0)


def test_openai_empty_stream():
    assert _parse_sse_usage_openai(b"") == (0, 0)


def test_openai_only_done():
    assert _parse_sse_usage_openai(b"data: [DONE]\n\n") == (0, 0)


def test_openai_partial_zero_usage_ignored():
    """A chunk with usage = {prompt_tokens: 0, completion_tokens: 0} should not be returned."""
    stream = _make_openai_stream(
        {"choices": [], "usage": {"prompt_tokens": 0, "completion_tokens": 0}},
        {"choices": [], "usage": {"prompt_tokens": 7, "completion_tokens": 3}},
    )
    # Reverse scan: last non-zero usage wins
    assert _parse_sse_usage_openai(stream) == (7, 3)


def test_openai_malformed_json_skipped():
    bad = b"data: {not json}\n\ndata: [DONE]\n\n"
    assert _parse_sse_usage_openai(bad) == (0, 0)


def test_openai_usage_only_completion_tokens():
    stream = _make_openai_stream(
        {"usage": {"prompt_tokens": 0, "completion_tokens": 99}},
    )
    # completion_tokens=99 is truthy → returned
    assert _parse_sse_usage_openai(stream) == (0, 99)


# ---------------------------------------------------------------------------
# _parse_sse_usage_anthropic
# ---------------------------------------------------------------------------

def _anthropic_event(event_type: str, **payload) -> bytes:
    obj = {"type": event_type, **payload}
    return (f"data: {json.dumps(obj)}\n\n").encode()


def test_anthropic_message_start_and_delta():
    stream = (
        _anthropic_event("message_start", message={"usage": {"input_tokens": 55}})
        + _anthropic_event("content_block_start", index=0, content_block={"type": "text", "text": ""})
        + _anthropic_event("content_block_delta", index=0, delta={"type": "text_delta", "text": "hi"})
        + _anthropic_event("message_delta", usage={"output_tokens": 20})
        + _anthropic_event("message_stop")
    )
    assert _parse_sse_usage_anthropic(stream) == (55, 20)


def test_anthropic_missing_delta():
    """message_delta absent → output_tokens stays 0."""
    stream = _anthropic_event("message_start", message={"usage": {"input_tokens": 30}})
    assert _parse_sse_usage_anthropic(stream) == (30, 0)


def test_anthropic_missing_start():
    """message_start absent → input_tokens stays 0."""
    stream = _anthropic_event("message_delta", usage={"output_tokens": 10})
    assert _parse_sse_usage_anthropic(stream) == (0, 10)


def test_anthropic_empty_stream():
    assert _parse_sse_usage_anthropic(b"") == (0, 0)


def test_anthropic_malformed_json_skipped():
    bad = b"data: {bad}\n\ndata: [DONE]\n\n"
    assert _parse_sse_usage_anthropic(bad) == (0, 0)


def test_anthropic_no_usage_key_in_message_start():
    stream = _anthropic_event("message_start", message={"model": "claude-haiku-4-5"})
    assert _parse_sse_usage_anthropic(stream) == (0, 0)


def test_anthropic_multiple_deltas_last_wins():
    """If multiple message_delta events exist, last value is kept."""
    stream = (
        _anthropic_event("message_start", message={"usage": {"input_tokens": 10}})
        + _anthropic_event("message_delta", usage={"output_tokens": 5})
        + _anthropic_event("message_delta", usage={"output_tokens": 15})
    )
    assert _parse_sse_usage_anthropic(stream) == (10, 15)


# ---------------------------------------------------------------------------
# _classify_intent
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text,expected", [
    # debugging
    ("Why is this throwing a TypeError?", "debugging"),
    ("There's an exception in the traceback", "debugging"),
    ("The app will crash on startup", "debugging"),
    ("fix the broken import", "debugging"),
    # testing
    ("Write a pytest for this function", "testing"),
    ("Add a unit test with mock objects", "testing"),
    ("Check the coverage for this module", "testing"),
    # refactoring
    ("Refactor this into smaller functions", "refactoring"),
    ("Clean up this messy code", "refactoring"),
    ("Extract the validation logic", "refactoring"),
    # code_review
    ("Please review this PR diff", "code_review"),
    ("What do you think about this implementation?", "code_review"),
    ("Give me feedback on my approach", "code_review"),
    # documentation
    ("Add a docstring to this function", "documentation"),
    ("Write a README for the project", "documentation"),
    ("Explain this function to me", "documentation"),
    # code_generation
    ("Write a function that parses JSON", "code_generation"),
    ("Implement a binary search algorithm", "code_generation"),
    ("Create a FastAPI endpoint for login", "code_generation"),
    # question
    ("How do I use asyncio.gather?", "question"),
    ("What is a context manager?", "question"),
    ("Can you explain decorators?", "question"),
    # general fallback
    ("", "general"),
    ("   ", "general"),
    ("banana sandwich", "general"),
])
def test_classify_intent(text, expected):
    assert _classify_intent(text) == expected


def test_classify_intent_first_match_wins():
    """debugging is listed before testing — 'fix the test' should match debugging."""
    assert _classify_intent("fix the test") == "debugging"


def test_classify_intent_case_insensitive():
    assert _classify_intent("WRITE A FUNCTION") == "code_generation"
    assert _classify_intent("Why Is This Broken") == "debugging"
