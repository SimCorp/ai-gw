"""Behavioral tests for the identity service (real Postgres via testcontainers)."""


async def test_health(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
