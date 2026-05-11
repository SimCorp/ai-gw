"""DAG evaluator — v0.1 supports linear successor scheduling.

The DAG JSON shape (v0.1):
    {
      "entry_node": "n1",
      "nodes": [{"id": "n1", "agent_slug": "echo-agent"}, ...],
      "edges": [{"from": "n1", "to": "n2"}, ...]
    }

In v0.1, edges have no conditions; branches/loops live in v0.5.
"""
from __future__ import annotations

from typing import Any


def successors(dag: dict[str, Any], node_id: str) -> list[str]:
    """Direct successors of node_id (no condition evaluation in v0.1)."""
    return [e["to"] for e in dag.get("edges", []) if e.get("from") == node_id]


def predecessors(dag: dict[str, Any], node_id: str) -> list[str]:
    return [e["from"] for e in dag.get("edges", []) if e.get("to") == node_id]


def node(dag: dict[str, Any], node_id: str) -> dict[str, Any] | None:
    for n in dag.get("nodes", []):
        if n.get("id") == node_id:
            return n
    return None


def ready_successors(dag: dict[str, Any], finished_node: str, run_nodes_state: dict[str, str]) -> list[str]:
    """Given a node that just finished, return successor nodes whose predecessors
    are all 'succeeded'. run_nodes_state maps node_id -> status string.
    """
    out = []
    for succ in successors(dag, finished_node):
        preds = predecessors(dag, succ)
        if all(run_nodes_state.get(p) == "succeeded" for p in preds):
            out.append(succ)
    return out


def is_terminal(dag: dict[str, Any], node_id: str) -> bool:
    """True if node has no outgoing edges."""
    return not successors(dag, node_id)
