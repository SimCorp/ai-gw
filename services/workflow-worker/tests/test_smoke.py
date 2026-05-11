"""v0.1 smoke test — end-to-end against the running compose stack.

Prerequisites:
  - `docker compose -f infra/docker-compose.yml up -d` (services healthy)
  - `docker build agents/echo-agent -t ai-gateway-echo-agent:dev`
  - DEV_BYPASS_AUTH=true OR set ADMIN_TOKEN env var

Run:
  pytest services/workflow-worker/tests/test_smoke.py -v
"""
from __future__ import annotations

import json
import os
import time
import uuid

import httpx
import pytest

ADMIN = os.getenv("ADMIN_URL", "http://localhost:8005")
ADMIN_HEADERS = {"X-Admin-Token": os.environ["ADMIN_TOKEN"]} if os.getenv("ADMIN_TOKEN") else {}


def _post(path: str, body: dict) -> dict:
    r = httpx.post(f"{ADMIN}{path}", json=body, headers=ADMIN_HEADERS, timeout=10)
    r.raise_for_status()
    return r.json()


def _get(path: str) -> dict:
    r = httpx.get(f"{ADMIN}{path}", headers=ADMIN_HEADERS, timeout=10)
    r.raise_for_status()
    return r.json()


def _get_team_id() -> str:
    """The compose stack seeds a default 'Engineering' team in dev mode."""
    return ""  # supplied via env or fetched via /teams; smoke test uses /teams listing


def test_3node_linear_chain():
    # Register the echo agent
    _post("/agents", {
        "slug": "echo-agent",
        "name": "Echo Agent",
        "image": "ai-gateway-echo-agent:dev",
        "manifest": {},
        "category": "utility",
        "managed": True,
    })

    # Find a team to scope the workflow to
    teams = _get("/teams")
    # /teams returns a plain list
    team_id = (teams[0] if isinstance(teams, list) else teams["teams"][0])["id"]

    # Create a workflow
    wf = _post("/workflows", {
        "slug": f"smoke-{uuid.uuid4().hex[:6]}",
        "name": "Smoke Workflow",
        "team_id": team_id,
    })

    # Define a 3-node linear DAG
    dag = {
        "entry_node": "n1",
        "nodes": [
            {"id": "n1", "agent_slug": "echo-agent"},
            {"id": "n2", "agent_slug": "echo-agent"},
            {"id": "n3", "agent_slug": "echo-agent"},
        ],
        "edges": [
            {"from": "n1", "to": "n2"},
            {"from": "n2", "to": "n3"},
        ],
    }
    _post(f"/workflows/{wf['id']}/versions", {
        "dag": dag,
        "created_by": str(uuid.uuid4()),
    })

    # Submit a run
    submit = _post("/runs", {
        "workflow_id": wf["id"],
        "inputs": {"greeting": "hello"},
        "team_id": team_id,
        "triggered_by": str(uuid.uuid4()),
        "triggered_by_kind": "user",
    })
    run_id = submit["id"]

    # Poll until terminal
    deadline = time.time() + 120
    while time.time() < deadline:
        run = _get(f"/runs/{run_id}")
        status = run["run"]["status"]
        if status in ("succeeded", "failed", "cancelled"):
            break
        time.sleep(2)

    assert status == "succeeded", f"run did not succeed; got {status}; run={json.dumps(run, default=str)}"
    # All three nodes should be succeeded
    statuses = {n["node_id"]: n["status"] for n in run["nodes"]}
    assert statuses.get("n1") == "succeeded"
    assert statuses.get("n2") == "succeeded"
    assert statuses.get("n3") == "succeeded"
