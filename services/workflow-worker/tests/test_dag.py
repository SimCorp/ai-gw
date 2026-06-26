"""Tests for dag.py — condition evaluation, loop control, graph traversal."""


def test_evaluate_condition_none_is_unconditional():
    from app.dag import evaluate_condition

    assert evaluate_condition(None, {}) is True


def test_evaluate_condition_empty_string_is_unconditional():
    from app.dag import evaluate_condition

    assert evaluate_condition("", {}) is True


def test_evaluate_condition_equality_string():
    from app.dag import evaluate_condition

    assert evaluate_condition('status == "success"', {"status": "success"}) is True
    assert evaluate_condition('status == "success"', {"status": "failure"}) is False


def test_evaluate_condition_numeric_comparisons():
    from app.dag import evaluate_condition

    assert evaluate_condition("score > 0.8", {"score": 0.9}) is True
    assert evaluate_condition("score > 0.8", {"score": 0.5}) is False
    assert evaluate_condition("score >= 1.0", {"score": 1.0}) is True
    assert evaluate_condition("count != 0", {"count": 0}) is False
    assert evaluate_condition("count != 0", {"count": 5}) is True
    assert evaluate_condition("n < 10", {"n": 9}) is True
    assert evaluate_condition("n <= 10", {"n": 10}) is True


def test_evaluate_condition_outputs_prefix_stripped():
    from app.dag import evaluate_condition

    # "outputs." prefix is optional — both forms must work identically
    assert evaluate_condition('outputs.status == "ok"', {"status": "ok"}) is True
    assert evaluate_condition('status == "ok"', {"status": "ok"}) is True


def test_evaluate_condition_fallback_path_truthiness():
    from app.dag import evaluate_condition

    # Unparseable condition → treat value at that key as truthy/falsy
    assert evaluate_condition("my_field", {"my_field": "truthy"}) is True
    assert evaluate_condition("my_field", {"my_field": None}) is False
    assert evaluate_condition("missing_field", {"other": "val"}) is False


def test_should_loop_off_by_one_boundary():
    from app.dag import should_loop

    spec = {"loop": {"enabled": True, "max_iterations": 10}}
    # Iteration 9 is the last allowed (max-1); must NOT loop further
    assert should_loop(spec, {"_loop_continue": True}, 9) is False
    # Iteration 8 is within bounds; loops when signal present
    assert should_loop(spec, {"_loop_continue": True}, 8) is True
    # No continue signal → no loop regardless of iteration count
    assert should_loop(spec, {"_loop_continue": False}, 8) is False


def test_should_loop_disabled():
    from app.dag import should_loop

    spec = {"loop": {"enabled": False}}
    assert should_loop(spec, {"_loop_continue": True}, 0) is False


def test_should_loop_no_spec():
    from app.dag import should_loop

    assert should_loop({}, {"_loop_continue": True}, 0) is False


def test_successors_returns_direct_children():
    from app.dag import successors

    dag = {
        "nodes": [{"id": "a"}, {"id": "b"}, {"id": "c"}],
        "edges": [
            {"from": "a", "to": "b"},
            {"from": "a", "to": "c"},
            {"from": "b", "to": "c"},
        ],
    }
    assert set(successors(dag, "a")) == {"b", "c"}
    assert set(successors(dag, "b")) == {"c"}
    assert successors(dag, "c") == []


def test_is_terminal_no_outgoing_edges():
    from app.dag import is_terminal

    dag = {
        "nodes": [{"id": "a"}, {"id": "b"}],
        "edges": [{"from": "a", "to": "b"}],
    }
    assert is_terminal(dag, "b") is True
    assert is_terminal(dag, "a") is False
