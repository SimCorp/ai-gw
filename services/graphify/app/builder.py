"""Build a knowledge graph for one repo: clone (or pull) + `graphify extract`.

Code is parsed locally (tree-sitter, no API calls); docs/PDF/images/audio/video
extraction is routed at the gateway's cache:8002/v1 via graphify's OpenAI backend.
The heavy CLI always runs out-of-process so it never blocks an event loop.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os

from app.config import settings
from app.db import graph_json_path, repo_dir, src_dir

_log = logging.getLogger(__name__)

# Cap captured subprocess output so a chatty build can't blow up memory / the
# log_tail column; we keep the tail (errors surface at the end).
_MAX_OUTPUT_BYTES = 200_000


def _auth_args() -> list[str]:
    """Per-invocation git auth header for HTTPS. Passing the PAT via
    `-c http.extraHeader` (not token-in-URL) keeps it out of the persisted
    .git/config remote, so no credential is left at rest on the shared volume.
    git does not echo the header, so it never reaches captured output."""
    token = settings.github_token
    if not token:
        return []
    cred = base64.b64encode(f"x-access-token:{token}".encode()).decode()
    return ["-c", f"http.extraHeader=Authorization: Basic {cred}"]


def _scrub(text: str) -> str:
    """Remove the PAT from any captured output before persisting it."""
    if settings.github_token:
        return text.replace(settings.github_token, "***")
    return text


async def _run(
    *args: str, cwd: str | None = None, env: dict | None = None, timeout: float = 1800.0
) -> tuple[int, str]:
    """Run a subprocess, capture combined output (tail-truncated). Returns (rc, output)."""
    proc = await asyncio.create_subprocess_exec(
        *args,
        cwd=cwd,
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    try:
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        return 124, f"timed out after {timeout}s"
    text = _scrub((out or b"").decode("utf-8", "replace"))
    return proc.returncode, text[-_MAX_OUTPUT_BYTES:]


async def _clone_or_pull(name: str, github_url: str, ref: str) -> tuple[bool, str]:
    """Clone the repo (or pull if already present). Returns (ok, log)."""
    src = src_dir(name)
    os.makedirs(repo_dir(name), exist_ok=True)

    if os.path.isdir(os.path.join(src, ".git")):
        rc, log = await _run(
            "git", "-C", src, *_auth_args(), "fetch", "--depth", "1", "origin", ref, timeout=600
        )
        if rc != 0:
            return False, log
        rc2, log2 = await _run("git", "-C", src, "checkout", "-f", "FETCH_HEAD", timeout=120)
        return rc2 == 0, log + log2

    rc, log = await _run(
        "git", *_auth_args(), "clone", "--depth", "1", "--branch", ref, github_url, src, timeout=600
    )
    return rc == 0, log


def _extract_env() -> dict:
    """Environment for `graphify extract --backend openai` — routes extraction
    LLM calls through the governed gateway entry point."""
    env = dict(os.environ)
    env["OPENAI_BASE_URL"] = settings.graphify_openai_base_url
    env["OPENAI_API_KEY"] = settings.graphify_gateway_key
    env["OPENAI_MODEL"] = settings.graphify_openai_model
    # Query logging writes to ~/.cache; disable it in the container.
    env["GRAPHIFY_QUERY_LOG_DISABLE"] = "1"
    return env


def _count_graph(name: str) -> tuple[int | None, int | None]:
    """Parse the built graph.json for node/edge counts. Defensive — graph.json
    may be a node-link object or carry top-level lists."""
    try:
        with open(graph_json_path(name), encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return None, None
    nodes = data.get("nodes")
    edges = data.get("edges") or data.get("links")
    n = len(nodes) if isinstance(nodes, list) else None
    e = len(edges) if isinstance(edges, list) else None
    return n, e


async def _head_commit(name: str) -> str | None:
    rc, out = await _run("git", "-C", src_dir(name), "rev-parse", "HEAD", timeout=30)
    return out.strip() if rc == 0 else None


async def run_build(name: str, github_url: str, ref: str) -> dict:
    """Clone + extract. Returns a dict the worker persists via db.finish_build:
    {succeeded, log_tail, error, nodes, edges, last_commit}."""
    _log.info("Build start repo=%s ref=%s url=%s", name, ref, github_url)

    ok, clone_log = await _clone_or_pull(name, github_url, ref)
    if not ok:
        return {
            "succeeded": False,
            "log_tail": clone_log,
            "error": "git clone/pull failed",
            "nodes": None,
            "edges": None,
            "last_commit": None,
        }

    # `--out <repo_dir>` makes graphify write artefacts to <repo_dir>/graphify-out/
    # (db.graph_dir) regardless of cwd, so build and query agree on the location.
    rc, extract_log = await _run(
        "graphify",
        "extract",
        src_dir(name),
        "--backend",
        "openai",
        "--out",
        repo_dir(name),
        cwd=repo_dir(name),
        env=_extract_env(),
        timeout=3600.0,
    )
    log_tail = (clone_log + "\n" + extract_log)[-_MAX_OUTPUT_BYTES:]

    if rc != 0 or not os.path.exists(graph_json_path(name)):
        return {
            "succeeded": False,
            "log_tail": log_tail,
            "error": f"graphify extract failed (rc={rc})",
            "nodes": None,
            "edges": None,
            "last_commit": None,
        }

    nodes, edges = _count_graph(name)
    commit = await _head_commit(name)
    _log.info("Build ok repo=%s nodes=%s edges=%s commit=%s", name, nodes, edges, commit)
    return {
        "succeeded": True,
        "log_tail": log_tail,
        "error": None,
        "nodes": nodes,
        "edges": edges,
        "last_commit": commit,
    }
