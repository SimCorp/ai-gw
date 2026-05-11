"""Canvas designer API tests — verifies the workflow designer backend is
wired correctly and a workflow created via the API renders valid DAG JSON.

Run (from repo root):
  DEV_BYPASS_AUTH=true pytest services/workflow-worker/tests/test_canvas_e2e.py -v

Prerequisites: same as test_acceptance.py (docker stack up, echo-agent image built).
"""
from __future__ import annotations

import uuid

import httpx
import pytest

ADMIN = "http://localhost:8005"
HEADERS: dict[str, str] = {}  # no token needed in DEV_BYPASS_AUTH mode


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
    r = httpx.post(
        f"{ADMIN}/agents",
        headers=HEADERS,
        timeout=10,
        json={"slug": slug, "name": slug, "image": image, "category": "test"},
    )
    r.raise_for_status()
    return r.json()["id"]


@pytest.fixture(scope="module")
def team_id() -> str:
    return _team_id()


@pytest.fixture(scope="module")
def echo_agent_id() -> str:
    return _register_agent("echo-agent", "ai-gateway-echo-agent:dev")


# ---------------------------------------------------------------------------
# Test 1: create workflow + version, verify DAG round-trip
# ---------------------------------------------------------------------------

def test_canvas_create_workflow(team_id, echo_agent_id):
    """POST a workflow, POST a version with a 2-node DAG including a conditional
    edge, GET the version back and verify the DAG round-trips correctly."""

    # Create workflow
    wf = _post("/workflows", {
        "slug": f"canvas-{uuid.uuid4().hex[:8]}",
        "name": "Canvas Test Workflow",
        "team_id": team_id,
    })
    wf_id = wf["id"]
    assert wf_id, "Expected workflow id in response"

    dag = {
        "entry_node": "n1",
        "nodes": [
            {"id": "n1", "agent_slug": "echo-agent"},
            {"id": "n2", "agent_slug": "echo-agent"},
        ],
        "edges": [
            {
                "from": "n1",
                "to": "n2",
                "condition": "outputs.status == 'success'",
            }
        ],
    }

    # Post version
    version = _post(f"/workflows/{wf_id}/versions", {
        "dag": dag,
        "created_by": str(uuid.uuid4()),
    })
    version_id = version.get("id") or version.get("version_id")
    assert version_id, "Expected version id in response"

    # GET version back and verify DAG round-trips
    fetched = _get(f"/workflows/{wf_id}/versions/{version_id}")
    fetched_dag = fetched.get("dag") or fetched.get("version", {}).get("dag") or fetched

    # Normalise: some endpoints wrap under "version"
    if "version" in fetched and isinstance(fetched["version"], dict):
        fetched_dag = fetched["version"].get("dag", fetched_dag)

    assert fetched_dag["entry_node"] == "n1", (
        f"entry_node mismatch: {fetched_dag.get('entry_node')}"
    )

    node_ids = {n["id"] for n in fetched_dag["nodes"]}
    assert node_ids == {"n1", "n2"}, f"Node ids mismatch: {node_ids}"

    edges = fetched_dag["edges"]
    assert len(edges) == 1, f"Expected 1 edge, got {len(edges)}"
    edge = edges[0]
    assert edge["from"] == "n1"
    assert edge["to"] == "n2"
    assert "condition" in edge, "Conditional edge should preserve condition field"
    assert edge["condition"] == "outputs.status == 'success'"


# ---------------------------------------------------------------------------
# Test 2: conditional edge routes to n2 when n1 outputs status=success
# ---------------------------------------------------------------------------

def test_canvas_conditional_edge_dag(team_id, echo_agent_id):
    """Submit a run where n1 produces {'status': 'success'} and a conditional
    edge leads to n2.  Verify n2 runs (echo-agent returns success)."""
    import time

    wf = _post("/workflows", {
        "slug": f"cond-{uuid.uuid4().hex[:8]}",
        "name": "Conditional Edge Test",
        "team_id": team_id,
    })
    wf_id = wf["id"]

    _post(f"/workflows/{wf_id}/versions", {
        "dag": {
            "entry_node": "n1",
            "nodes": [
                {"id": "n1", "agent_slug": "echo-agent"},
                {"id": "n2", "agent_slug": "echo-agent"},
            ],
            "edges": [
                {
                    "from": "n1",
                    "to": "n2",
                    "condition": "outputs.status == 'success'",
                }
            ],
        },
        "created_by": str(uuid.uuid4()),
    })

    run = _post("/runs", {
        "workflow_id": wf_id,
        "inputs": {"status": "success"},
        "team_id": team_id,
        "triggered_by": str(uuid.uuid4()),
        "triggered_by_kind": "user",
    })
    run_id = run["id"]

    # Wait for completion (up to 120s)
    deadline = time.time() + 120
    result = None
    while time.time() < deadline:
        result = _get(f"/runs/{run_id}")
        status = result["run"]["status"]
        if status in ("succeeded", "failed", "cancelled"):
            break
        time.sleep(2)

    assert result is not None
    assert result["run"]["status"] == "succeeded", (
        f"Expected succeeded, got {result['run']['status']}"
    )

    # Verify n2 ran (conditional edge was evaluated true and n2 was executed)
    node_statuses = {n["node_id"]: n["status"] for n in result["nodes"]}
    assert "n2" in node_statuses, (
        f"n2 not found in node statuses: {node_statuses}"
    )
    assert node_statuses["n2"] == "succeeded", (
        f"n2 did not succeed: {node_statuses['n2']}"
    )


# ---------------------------------------------------------------------------
# Test 3: loop node with max_iterations=2 terminates when agent returns
#         {"_loop_continue": false}
# ---------------------------------------------------------------------------

def test_canvas_loop_node(team_id, echo_agent_id):
    """Submit a workflow where n1 is a loop node with max_iterations=2.
    The echo-agent always returns {"_loop_continue": false} so the loop
    runs once and terminates.  Verify run succeeds."""
    import time

    wf = _post("/workflows", {
        "slug": f"loop-{uuid.uuid4().hex[:8]}",
        "name": "Loop Node Test",
        "team_id": team_id,
    })
    wf_id = wf["id"]

    _post(f"/workflows/{wf_id}/versions", {
        "dag": {
            "entry_node": "n1",
            "nodes": [
                {
                    "id": "n1",
                    "agent_slug": "echo-agent",
                    "loop": True,
                    "max_iterations": 2,
                }
            ],
            "edges": [],
        },
        "created_by": str(uuid.uuid4()),
    })

    run = _post("/runs", {
        "workflow_id": wf_id,
        "inputs": {"_loop_continue": False},
        "team_id": team_id,
        "triggered_by": str(uuid.uuid4()),
        "triggered_by_kind": "user",
    })
    run_id = run["id"]

    # Wait for completion
    deadline = time.time() + 120
    result = None
    while time.time() < deadline:
        result = _get(f"/runs/{run_id}")
        status = result["run"]["status"]
        if status in ("succeeded", "failed", "cancelled"):
            break
        time.sleep(2)

    assert result is not None
    assert result["run"]["status"] == "succeeded", (
        f"Loop run did not succeed: {result['run']['status']}"
    )

    # Verify the loop node itself shows as succeeded
    node_statuses = {n["node_id"]: n["status"] for n in result["nodes"]}
    assert node_statuses.get("n1") == "succeeded", (
        f"Loop node n1 status: {node_statuses.get('n1')}"
    )


# ---------------------------------------------------------------------------
# Smoke test: Awesome Copilot catalog endpoints
# ---------------------------------------------------------------------------

def test_awesome_copilot_catalog():
    """Basic smoke test: catalog items endpoint returns data and meta is sane."""
    items = _get("/mcp/copilot-catalog/items?limit=5")["items"]
    assert len(items) > 0, "Expected at least one catalog item"

    meta = _get("/mcp/copilot-catalog/meta")
    assert meta["count"] > 0, f"Catalog meta count should be > 0, got: {meta['count']}"
