"""DAG evaluator — v0.5 adds conditional edges, loop nodes, and parallel fan-out.

The DAG JSON shape (v0.5):
    {
      "entry_node": "n1",
      "nodes": [
        {
          "id": "n1",
          "agent_slug": "echo-agent",
          "inputs": {},
          "loop": {"enabled": false, "max_iterations": 10}
        },
        ...
      ],
      "edges": [
        {"from": "n1", "to": "n2", "condition": null},
        {"from": "n1", "to": "n3", "condition": "outputs.status == \"success\""},
        ...
      ]
    }

Condition syntax: simple dotted path comparisons, e.g.
    outputs.status == "success"
    outputs.score > 0.8
    outputs._loop_continue == true
"""

from __future__ import annotations

import operator
import re
from typing import Any

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resolve_path(obj: Any, path: str) -> Any:
    """Walk dot-separated path into obj, returning None if any segment missing."""
    for part in path.split("."):
        if isinstance(obj, dict):
            obj = obj.get(part)
        elif hasattr(obj, part):
            obj = getattr(obj, part)
        else:
            return None
    return obj


_OPS = {
    "==": operator.eq,
    "!=": operator.ne,
    ">": operator.gt,
    ">=": operator.ge,
    "<": operator.lt,
    "<=": operator.le,
}

# Tokenize: path OP literal (string or number or bool)
_COND_RE = re.compile(r"^(?P<path>[\w.]+)\s*(?P<op>==|!=|>=|<=|>|<)\s*(?P<lit>.+)$")


def _parse_literal(raw: str) -> Any:
    raw = raw.strip()
    if raw.startswith('"') and raw.endswith('"'):
        return raw[1:-1]
    if raw.startswith("'") and raw.endswith("'"):
        return raw[1:-1]
    if raw.lower() == "true":
        return True
    if raw.lower() == "false":
        return False
    if raw.lower() == "null" or raw.lower() == "none":
        return None
    try:
        return int(raw)
    except ValueError:
        pass
    try:
        return float(raw)
    except ValueError:
        pass
    return raw


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def evaluate_condition(condition: str | None, outputs: dict) -> bool:
    """Evaluate a condition string against node outputs.

    Returns True if condition is None/empty (unconditional edge) or if the
    expression evaluates to truthy.

    Supports simple binary comparisons of the form:
        <dotted.path> <op> <literal>
    where literal is a quoted string, number, bool (true/false), or null.
    Falls back to False on parse errors.
    """
    if not condition:
        return True

    cond = condition.strip()
    # Strip leading "outputs." prefix — conditions are evaluated against the
    # outputs dict directly, so "outputs.field" and "field" are equivalent.
    if cond.startswith("outputs."):
        cond = cond[len("outputs.") :]
    m = _COND_RE.match(cond)
    if not m:
        # Non-parseable condition: treat as path truthiness check
        val = _resolve_path(outputs, cond)
        return bool(val)

    path = m.group("path")
    op_str = m.group("op")
    literal = _parse_literal(m.group("lit"))
    op_fn = _OPS.get(op_str)
    if op_fn is None:
        return False

    actual = _resolve_path(outputs, path)
    try:
        return bool(op_fn(actual, literal))
    except TypeError:
        return False


def should_loop(node_spec: dict, outputs: dict, current_iteration: int) -> bool:
    """Return True if the node should loop again.

    Conditions for looping:
    - node_spec has loop.enabled = True
    - current_iteration < loop.max_iterations - 1  (0-indexed)
    - outputs contains _loop_continue: True
    """
    loop = node_spec.get("loop") or {}
    # Handle both "loop": true and "loop": {"enabled": true, "max_iterations": N}
    if isinstance(loop, bool):
        loop = {"enabled": loop, "max_iterations": 10}
    if not loop.get("enabled", False):
        return False
    max_iter = int(loop.get("max_iterations", 10))
    if current_iteration >= max_iter - 1:
        return False
    return bool(outputs.get("_loop_continue", False))


# ---------------------------------------------------------------------------
# DAG graph traversal
# ---------------------------------------------------------------------------


def successors(dag: dict[str, Any], node_id: str) -> list[str]:
    """Direct successors of node_id (ignores conditions)."""
    return [e["to"] for e in dag.get("edges", []) if e.get("from") == node_id]


def conditional_successors(dag: dict[str, Any], node_id: str, outputs: dict) -> list[str]:
    """Successors whose conditions are satisfied by outputs."""
    result = []
    for e in dag.get("edges", []):
        if e.get("from") != node_id:
            continue
        condition = e.get("condition") or None
        if evaluate_condition(condition, outputs):
            result.append(e["to"])
    return result


def predecessors(dag: dict[str, Any], node_id: str) -> list[str]:
    return [e["from"] for e in dag.get("edges", []) if e.get("to") == node_id]


def node(dag: dict[str, Any], node_id: str) -> dict[str, Any] | None:
    for n in dag.get("nodes", []):
        if n.get("id") == node_id:
            return n
    return None


def ready_successors(
    dag: dict[str, Any],
    finished_node: str,
    run_nodes_state: dict[str, str],
    outputs: dict | None = None,
) -> list[str]:
    """Given a node that just finished, return successor nodes whose predecessors
    are all 'succeeded' AND whose edge conditions are satisfied by outputs.

    run_nodes_state maps node_id -> status string.
    outputs is the finished node's output dict (used for condition evaluation).
    """
    out_dict = outputs or {}
    out = []
    for succ in conditional_successors(dag, finished_node, out_dict):
        preds = predecessors(dag, succ)
        if all(run_nodes_state.get(p) == "succeeded" for p in preds):
            out.append(succ)
    return out


def is_terminal(dag: dict[str, Any], node_id: str) -> bool:
    """True if node has no outgoing edges."""
    return not successors(dag, node_id)
