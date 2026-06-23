"""Graph query wrappers — pure-local retrieval, no LLM.

`graphify query|path|explain` read graph.json and return a token-budgeted text
subgraph (TF-IDF + rapidfuzz + networkx traversal). We shell out to the CLI per
request; the calls are fast and offline. graph_stats/god_nodes are derived
directly from graph.json (node-link format) without spawning a process.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from collections import Counter

from app.db import REPO_NAME_RE, graph_json_path

_log = logging.getLogger(__name__)

_QUERY_TIMEOUT = 60.0


class GraphNotReady(Exception):
    """No built graph.json exists for the repo yet."""


def _require_graph(repo: str) -> str:
    # Defense-in-depth choke-point: `repo` becomes part of a filesystem path, so
    # reject anything that isn't a plain repo name (blocks `..` traversal) before
    # touching disk. Covers every query/path/explain/stats caller, incl. MCP.
    if not REPO_NAME_RE.match(repo):
        raise ValueError(f"invalid repo name: {repo!r}")
    raw = graph_json_path(repo)
    # Realpath containment: verify the resolved path stays within the output volume.
    from app.config import settings as _settings

    base = os.path.realpath(_settings.graphify_out_dir)
    path = os.path.realpath(raw)
    if not path.startswith(base + os.sep):
        raise ValueError(f"invalid repo path: {repo!r}")
    if not os.path.exists(path):
        raise GraphNotReady(f"no graph built for repo '{repo}'")
    return path


async def _run_cli(*args: str) -> str:
    proc = await asyncio.create_subprocess_exec(
        "graphify",
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env={**os.environ, "GRAPHIFY_QUERY_LOG_DISABLE": "1"},
    )
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout=_QUERY_TIMEOUT)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        raise RuntimeError("graph query timed out")
    if proc.returncode != 0:
        raise RuntimeError((err or b"").decode("utf-8", "replace").strip() or "graph query failed")
    return (out or b"").decode("utf-8", "replace")


async def query(repo: str, question: str, *, budget: int = 2000, dfs: bool = False) -> str:
    graph = _require_graph(repo)
    args = ["query", question, "--graph", graph, "--budget", str(budget)]
    if dfs:
        args.append("--dfs")
    return await _run_cli(*args)


async def path(repo: str, source: str, target: str) -> str:
    graph = _require_graph(repo)
    return await _run_cli("path", source, target, "--graph", graph)


async def explain(repo: str, node: str) -> str:
    graph = _require_graph(repo)
    return await _run_cli("explain", node, "--graph", graph)


def stats(repo: str, *, top_n: int = 10) -> dict:
    """Node/edge counts + god-nodes (highest-degree hubs) parsed from graph.json."""
    path = _require_graph(repo)
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    nodes = data.get("nodes") or []
    edges = data.get("links") or data.get("edges") or []

    degree: Counter = Counter()
    for e in edges:
        src = e.get("source")
        tgt = e.get("target")
        if src is not None:
            degree[src] += 1
        if tgt is not None:
            degree[tgt] += 1

    god_nodes = [{"node": n, "degree": d} for n, d in degree.most_common(top_n)]
    return {
        "repo": repo,
        "nodes": len(nodes),
        "edges": len(edges),
        "god_nodes": god_nodes,
    }
