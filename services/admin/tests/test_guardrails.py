"""Tests for /guardrails endpoints."""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _guardrail_row(guardrail_id=None, team_id=None):
    _id = guardrail_id or uuid.uuid4()
    row = MagicMock()
    data = {
        "id": _id,
        "name": "PII Detector",
        "description": "Blocks PII",
        "type": "pii_detector",
        "applies_to": "input",
        "action": "block",
        "severity": "critical",
        "priority": 10,
        "config": {},
        "enabled": True,
        "version": 1,
        "created_at": None,
        "updated_at": None,
        "created_by": "system",
        "updated_by": "system",
        "team_id": team_id,
        "hits_24h": 0,
        "blocks_24h": 0,
    }
    row.__getitem__ = lambda self, k: data[k]
    row.keys = lambda: data.keys()
    # dict(row) pattern used by guardrails router
    row.__iter__ = lambda self: iter(data.keys())
    # Support dict(row) by making it behave like a mapping
    row.items = lambda: data.items()
    return row


def _mappings_all(rows):
    result = MagicMock()
    result.mappings.return_value.all.return_value = rows
    return result


def _mappings_first(row):
    result = MagicMock()
    result.mappings.return_value.first.return_value = row
    return result


def _summary_row():
    row = MagicMock()
    data = {
        "active_count": 5,
        "input_count": 3,
        "output_count": 1,
        "both_count": 1,
        "hits_24h": 10,
        "blocked_24h": 3,
    }
    row.__getitem__ = lambda self, k: data[k]
    row.keys = lambda: data.keys()
    row.items = lambda: data.items()
    return row


def _hit_row():
    row = MagicMock()
    _id = uuid.uuid4()
    data = {
        "id": _id,
        "created_at": None,
        "guardrail_type": "pii_detector",
        "input_or_output": "input",
        "action_taken": "block",
        "severity": "critical",
        "match_count": 1,
        "redacted_excerpt": None,
        "request_id": None,
        "model": None,
        "team_name": "Engineering",
    }
    row.__getitem__ = lambda self, k: data[k]
    row.keys = lambda: data.keys()
    row.items = lambda: data.items()
    return row


# ---------------------------------------------------------------------------
# GET /guardrails
# ---------------------------------------------------------------------------

async def test_list_guardrails_no_filter(client, mock_session):
    row = _guardrail_row()
    mock_session.execute.return_value = _mappings_all([row])

    resp = await client.get("/guardrails")

    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, list)
    assert len(body) == 1


async def test_list_guardrails_with_team_filter(client, mock_session):
    team_id = str(uuid.uuid4())
    row = _guardrail_row(team_id=uuid.UUID(team_id))
    mock_session.execute.return_value = _mappings_all([row])

    resp = await client.get(f"/guardrails?team_id={team_id}")

    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, list)


# ---------------------------------------------------------------------------
# GET /guardrails/summary
# ---------------------------------------------------------------------------

async def test_guardrails_summary_returns_200(client, mock_session):
    summary = _summary_row()
    result = MagicMock()
    result.mappings.return_value.first.return_value = summary
    mock_session.execute.return_value = result

    resp = await client.get("/guardrails/summary")

    assert resp.status_code == 200
    body = resp.json()
    assert "active_count" in body
    assert "hits_24h" in body


# ---------------------------------------------------------------------------
# GET /guardrails/hits
# ---------------------------------------------------------------------------

async def test_recent_hits_returns_200(client, mock_session):
    hit = _hit_row()
    mock_session.execute.return_value = _mappings_all([hit])

    resp = await client.get("/guardrails/hits")

    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, list)


# ---------------------------------------------------------------------------
# POST /guardrails
# ---------------------------------------------------------------------------

async def test_create_guardrail_returns_201(client, mock_session):
    new_row = _guardrail_row()
    mock_session.execute.return_value = _mappings_first(new_row)

    resp = await client.post(
        "/guardrails",
        json={
            "name": "Test Guard",
            "type": "pii_detector",
            "applies_to": "input",
            "action": "block",
            "severity": "high",
            "priority": 50,
            "config": {},
        },
    )

    assert resp.status_code == 201


# ---------------------------------------------------------------------------
# PATCH /guardrails/{id}
# ---------------------------------------------------------------------------

async def test_patch_guardrail_updates_enabled(client, mock_session):
    guardrail_id = str(uuid.uuid4())
    row = _guardrail_row(uuid.UUID(guardrail_id))
    mock_session.execute.return_value = _mappings_first(row)

    resp = await client.patch(
        f"/guardrails/{guardrail_id}",
        json={"enabled": False},
    )

    assert resp.status_code == 200


async def test_patch_guardrail_no_fields_returns_400(client, mock_session):
    guardrail_id = str(uuid.uuid4())

    resp = await client.patch(f"/guardrails/{guardrail_id}", json={})

    assert resp.status_code == 400


async def test_patch_guardrail_not_found_returns_404(client, mock_session):
    guardrail_id = str(uuid.uuid4())
    mock_session.execute.return_value = _mappings_first(None)

    resp = await client.patch(
        f"/guardrails/{guardrail_id}",
        json={"enabled": True},
    )

    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# DELETE /guardrails/{id}
# ---------------------------------------------------------------------------

async def test_delete_guardrail_found_returns_204(client, mock_session):
    guardrail_id = str(uuid.uuid4())
    # delete_guardrail uses result.first() directly (not mappings)
    delete_result = MagicMock()
    delete_result.first.return_value = (uuid.UUID(guardrail_id),)
    mock_session.execute.return_value = delete_result

    resp = await client.delete(f"/guardrails/{guardrail_id}")

    assert resp.status_code == 204


async def test_delete_guardrail_not_found_returns_404(client, mock_session):
    guardrail_id = str(uuid.uuid4())
    delete_result = MagicMock()
    delete_result.first.return_value = None
    mock_session.execute.return_value = delete_result

    resp = await client.delete(f"/guardrails/{guardrail_id}")

    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /guardrails/hits
# ---------------------------------------------------------------------------

async def test_record_hit_returns_201(client, mock_session):
    guardrail_id = str(uuid.uuid4())
    hit_id = uuid.uuid4()

    hit_result = MagicMock()
    hit_result.mappings.return_value.first.return_value = {"id": hit_id}
    mock_session.execute.return_value = hit_result

    resp = await client.post(
        "/guardrails/hits",
        json={
            "guardrail_id": guardrail_id,
            "guardrail_type": "pii_detector",
            "input_or_output": "input",
            "action_taken": "block",
            "severity": "critical",
            "match_count": 1,
        },
    )

    assert resp.status_code == 201
    body = resp.json()
    assert "id" in body
