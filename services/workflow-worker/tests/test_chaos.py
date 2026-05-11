"""Chaos and load tests for the workflow execution engine.

Prerequisites (same as test_acceptance.py):
  docker compose -f infra/docker-compose.yml up -d
  docker build agents/echo-agent -t ai-gateway-echo-agent:dev

Run:
  pytest services/workflow-worker/tests/test_chaos.py -v --timeout=300
"""
from __future__ import annotations

import concurrent.futures
import subprocess
import time
import uuid

import httpx
import pytest
import redis as redis_mod

ADMIN = "http://localhost:8005"
HEADERS: dict[str, str] = {}  # no token needed in DEV_BYPASS_AUTH mode

_redis = redis_mod.Redis(host="localhost", port=6379, decode_responses=True)


# ---------------------------------------------------------------------------
# Helpers (mirrors test_acceptance.py)
# ---------------------------------------------------------------------------

def _get(path: str) -> dict:
    r = httpx.get(f"{ADMIN}{path}", headers=HEADERS, timeout=10)
    r.raise_for_status()
    return r.json()


def _post(path: str, body: dict) -> dict:
    r = httpx.post(f"{ADMIN}{path}", json=body, headers=HEADERS, timeout=10)
    r.raise_for_status()
    return r.json()


def _team_id() -> str:
    teams = httpx.get(f"{ADMIN}/teams", headers=HEADERS, timeout=10).json()
    return teams[0]["id"]


def _register_agent(slug: str, image: str) -> str:
    r = httpx.post(f"{ADMIN}/agents", headers=HEADERS, timeout=10, json={
        "slug": slug, "name": slug, "image": image, "category": "test",
    })
    r.raise_for_status()
    return r.json()["id"]


def _make_workflow(team_id: str, nodes: list[dict], edges: list[dict]) -> tuple[str, str]:
    """Create a workflow + version. Returns (workflow_id, first_node_id)."""
    wf = _post("/workflows", {
        "slug": f"test-{uuid.uuid4().hex[:6]}",
        "name": "Test Workflow",
        "team_id": team_id,
    })
    entry = nodes[0]["id"]
    _post(f"/workflows/{wf['id']}/versions", {
        "dag": {"entry_node": entry, "nodes": nodes, "edges": edges},
        "created_by": str(uuid.uuid4()),
    })
    return wf["id"], entry


def _submit_run(
    workflow_id: str,
    team_id: str,
    *,
    triggered_by_kind: str = "user",
    inputs: dict | None = None,
) -> dict:
    return _post("/runs", {
        "workflow_id": workflow_id,
        "inputs": inputs or {},
        "team_id": team_id,
        "triggered_by": str(uuid.uuid4()),
        "triggered_by_kind": triggered_by_kind,
    })


def _wait_run(run_id: str, timeout: float = 120) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            run = _get(f"/runs/{run_id}")
            if run["run"]["status"] in ("succeeded", "failed", "cancelled"):
                return run
        except (httpx.HTTPError, httpx.ConnectError):
            # Service may be temporarily unavailable during restarts
            pass
        time.sleep(2)
    raise TimeoutError(f"run {run_id} did not finish within {timeout}s")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def team_id() -> str:
    return _team_id()


@pytest.fixture(autouse=True)
def reset_rate_limit(team_id) -> None:
    """Clear the per-team run rate-limit counter before each test so tests
    don't pollute each other's quota."""
    _redis.delete(f"workflow_runs:rate:{team_id}")
    yield


@pytest.fixture(scope="session")
def echo_agent_id() -> str:
    return _register_agent("echo-agent", "ai-gateway-echo-agent:dev")


# ---------------------------------------------------------------------------
# Chaos test 1: Postgres restart mid-run
# ---------------------------------------------------------------------------

def test_db_restart_mid_run(team_id, echo_agent_id):
    """Restart postgres after first node completes; workflow should still finish."""
    nodes = [{"id": f"n{i}", "agent_slug": "echo-agent"} for i in range(1, 6)]
    edges = [{"from": f"n{i}", "to": f"n{i+1}"} for i in range(1, 5)]
    wf_id, _ = _make_workflow(team_id, nodes=nodes, edges=edges)
    run = _submit_run(wf_id, team_id)
    run_id = run["id"]

    # Wait for n1 to complete before restarting postgres
    deadline = time.time() + 60
    n1_completed = False
    while time.time() < deadline:
        try:
            r = _get(f"/runs/{run_id}")
            node_statuses = {n["node_id"]: n["status"] for n in r["nodes"]}
            if node_statuses.get("n1") == "succeeded":
                n1_completed = True
                break
            if r["run"]["status"] in ("succeeded", "failed", "cancelled"):
                # Run finished before we could inject fault — still pass if succeeded
                result = r
                assert result["run"]["status"] == "succeeded", f"Got: {result['run']['status']}"
                return
        except (httpx.HTTPError, httpx.ConnectError):
            pass
        time.sleep(1)

    if not n1_completed:
        pytest.fail("n1 did not complete within 60s; cannot inject postgres chaos")

    # Restart postgres container
    subprocess.run(
        ["docker", "restart", "ai-gateway-postgres-1"],
        check=True, capture_output=True,
    )

    # Wait for postgres to come back up (admin health depends on it)
    time.sleep(5)

    result = _wait_run(run_id, timeout=180)
    assert result["run"]["status"] == "succeeded", f"Got: {result['run']['status']}"
    finished_nodes = [n for n in result["nodes"] if n["status"] == "succeeded"]
    assert len(finished_nodes) == 5, f"Expected 5 succeeded nodes, got {len(finished_nodes)}"


# ---------------------------------------------------------------------------
# Chaos test 2: Redis restart mid-run
# ---------------------------------------------------------------------------

def test_redis_restart_mid_run(team_id, echo_agent_id):
    """Restart Redis mid-run; run should complete (fails open on Redis outage)."""
    nodes = [{"id": "n1", "agent_slug": "echo-agent"},
             {"id": "n2", "agent_slug": "echo-agent"}]
    edges = [{"from": "n1", "to": "n2"}]
    wf_id, _ = _make_workflow(team_id, nodes=nodes, edges=edges)
    run = _submit_run(wf_id, team_id)
    run_id = run["id"]

    # Wait for run to be picked up by the worker (n1 running or later)
    deadline = time.time() + 30
    while time.time() < deadline:
        try:
            r = _get(f"/runs/{run_id}")
            node_statuses = {n["node_id"]: n["status"] for n in r["nodes"]}
            if node_statuses.get("n1") in ("running", "succeeded"):
                break
            if r["run"]["status"] in ("succeeded", "failed", "cancelled"):
                break
        except (httpx.HTTPError, httpx.ConnectError):
            pass
        time.sleep(0.5)

    # Restart Redis
    subprocess.run(
        ["docker", "restart", "ai-gateway-redis-1"],
        check=True, capture_output=True,
    )

    # Reinitialise the module-level redis client after the restart
    global _redis
    time.sleep(3)
    _redis = redis_mod.Redis(host="localhost", port=6379, decode_responses=True)

    result = _wait_run(run_id, timeout=120)
    assert result["run"]["status"] == "succeeded", (
        f"Run should complete despite Redis restart; got: {result['run']['status']}"
    )


# ---------------------------------------------------------------------------
# Chaos test 3: Admin restart mid-run
# ---------------------------------------------------------------------------

def test_admin_restart_mid_run(team_id, echo_agent_id):
    """Restart admin service mid-run; worker uses Postgres directly so run completes."""
    nodes = [{"id": "n1", "agent_slug": "echo-agent"},
             {"id": "n2", "agent_slug": "echo-agent"}]
    edges = [{"from": "n1", "to": "n2"}]
    wf_id, _ = _make_workflow(team_id, nodes=nodes, edges=edges)
    run = _submit_run(wf_id, team_id)
    run_id = run["id"]

    # Wait for the worker to pick up the run
    deadline = time.time() + 30
    while time.time() < deadline:
        try:
            r = _get(f"/runs/{run_id}")
            if r["run"]["status"] != "pending":
                break
        except (httpx.HTTPError, httpx.ConnectError):
            pass
        time.sleep(0.5)

    # Restart admin service
    subprocess.run(
        ["docker", "compose", "-f", "infra/docker-compose.yml", "restart", "admin"],
        check=True, capture_output=True,
    )

    # Wait for admin to come back up before polling (use /teams — known good route)
    deadline_admin = time.time() + 30
    while time.time() < deadline_admin:
        try:
            httpx.get(f"{ADMIN}/teams", headers=HEADERS, timeout=3)
            break
        except (httpx.HTTPError, httpx.ConnectError):
            time.sleep(2)

    result = _wait_run(run_id, timeout=120)
    assert result["run"]["status"] == "succeeded", (
        f"Run should complete after admin restart; got: {result['run']['status']}"
    )


# ---------------------------------------------------------------------------
# Chaos test 4: Rate-limit key lifecycle (reset via Redis delete)
# ---------------------------------------------------------------------------

def test_rate_limit_resets_after_window(team_id, echo_agent_id):
    """Exhaust rate limit for a synthetic team, delete the Redis key, verify reset.

    Uses a separate synthetic team_id for the burn loop so the shared team_id
    quota (used by other tests) is not consumed.  The workflow itself is created
    under the real team_id; only the rate-limit team bucket differs.
    """
    import hashlib

    wf_id, _ = _make_workflow(
        team_id,
        nodes=[{"id": "n1", "agent_slug": "echo-agent"}],
        edges=[],
    )

    # Synthetic team_id — has a fresh rate-limit counter, won't conflict with others
    burn_team = "00000000-0000-0000-0000-" + hashlib.md5(b"chaos-rate-limit").hexdigest()[:12]
    rate_key = f"workflow_runs:rate:{burn_team}"
    _redis.delete(rate_key)  # ensure clean state

    # Exhaust the rate limit using the synthetic team bucket
    hit_429 = False
    for _ in range(101):
        r = httpx.post(f"{ADMIN}/runs", headers=HEADERS, timeout=10, json={
            "workflow_id": wf_id,
            "inputs": {},
            "team_id": burn_team,
            "triggered_by": str(uuid.uuid4()),
            "triggered_by_kind": "user",
        })
        if r.status_code == 429:
            hit_429 = True
            break

    assert hit_429, "Expected to hit 429 rate limit within 101 submissions"

    # Simulate TTL expiry by deleting the rate-limit key from Redis
    _redis.delete(rate_key)

    # Subsequent submission under the synthetic team should now succeed
    r = httpx.post(f"{ADMIN}/runs", headers=HEADERS, timeout=10, json={
        "workflow_id": wf_id,
        "inputs": {},
        "team_id": burn_team,
        "triggered_by": str(uuid.uuid4()),
        "triggered_by_kind": "user",
    })
    assert r.status_code in (200, 201), (
        f"Expected 200/201 after rate-limit reset; got {r.status_code}: {r.text}"
    )

    # Verify the new run completes end-to-end (use real team_id so auth passes)
    new_run = _submit_run(wf_id, team_id)
    result = _wait_run(new_run["id"], timeout=60)
    assert result["run"]["status"] == "succeeded", f"Got: {result['run']['status']}"


# ---------------------------------------------------------------------------
# Load test 5: 10 concurrent runs — no deadlock
# ---------------------------------------------------------------------------

def test_concurrent_runs_dont_deadlock(team_id, echo_agent_id):
    """Submit 10 runs simultaneously; all must complete within 120s with no deadlocks."""
    nodes = [{"id": "n1", "agent_slug": "echo-agent"},
             {"id": "n2", "agent_slug": "echo-agent"}]
    edges = [{"from": "n1", "to": "n2"}]
    wf_id, _ = _make_workflow(team_id, nodes=nodes, edges=edges)

    NUM_RUNS = 10

    def submit_and_wait() -> dict:
        run = _submit_run(wf_id, team_id)
        return _wait_run(run["id"], timeout=120)

    with concurrent.futures.ThreadPoolExecutor(max_workers=NUM_RUNS) as executor:
        futures = [executor.submit(submit_and_wait) for _ in range(NUM_RUNS)]
        results = [f.result() for f in concurrent.futures.as_completed(futures)]

    assert len(results) == NUM_RUNS, f"Expected {NUM_RUNS} results, got {len(results)}"

    failed = [r for r in results if r["run"]["status"] != "succeeded"]
    assert not failed, (
        f"{len(failed)} of {NUM_RUNS} runs did not succeed: "
        + ", ".join(r["run"]["status"] for r in failed)
    )

    # Verify each node ran exactly once per run (no duplicate processing)
    for result in results:
        node_ids = [n["node_id"] for n in result["nodes"]]
        assert len(node_ids) == len(set(node_ids)), (
            f"Duplicate node execution detected in run {result['run']['id']}"
        )
        succeeded_nodes = [n for n in result["nodes"] if n["status"] == "succeeded"]
        assert len(succeeded_nodes) == 2, (
            f"Expected 2 succeeded nodes, got {len(succeeded_nodes)} "
            f"in run {result['run']['id']}"
        )


# ---------------------------------------------------------------------------
# Load test 6: 10-node linear DAG completes in order
# ---------------------------------------------------------------------------

def test_large_dag_completes(team_id, echo_agent_id):
    """10-node linear chain completes; all nodes execute in topological order."""
    num_nodes = 10
    nodes = [{"id": f"n{i}", "agent_slug": "echo-agent"} for i in range(1, num_nodes + 1)]
    edges = [{"from": f"n{i}", "to": f"n{i+1}"} for i in range(1, num_nodes)]
    wf_id, _ = _make_workflow(team_id, nodes=nodes, edges=edges)

    run = _submit_run(wf_id, team_id, inputs={"value": "large-dag"})
    result = _wait_run(run["id"], timeout=180)

    assert result["run"]["status"] == "succeeded", f"Got: {result['run']['status']}"

    finished = [n for n in result["nodes"] if n["status"] == "succeeded"]
    assert len(finished) == num_nodes, (
        f"Expected {num_nodes} succeeded nodes, got {len(finished)}"
    )

    # Verify topological execution order via started_at timestamps
    node_map = {n["node_id"]: n for n in result["nodes"]}
    for i in range(1, num_nodes):
        parent_id = f"n{i}"
        child_id = f"n{i+1}"
        parent_node = node_map.get(parent_id)
        child_node = node_map.get(child_id)
        if (
            parent_node
            and child_node
            and parent_node.get("completed_at")
            and child_node.get("started_at")
        ):
            assert parent_node["completed_at"] <= child_node["started_at"], (
                f"Node {child_id} started before {parent_id} completed"
            )
