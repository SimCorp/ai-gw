"""Behavioral tests for the identity service (real Postgres via testcontainers)."""


async def test_health(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


async def test_resolve_ranks_exact_then_capability_then_partial_and_dedups(client, insert_agent):
    # "search" is an exact slug, a capability of another agent, and a partial
    # match of a third — verifies ordering and that no slug appears twice.
    await insert_agent("search", name="Search Bot")  # exact slug
    await insert_agent("indexer", capabilities=["search"])  # capability tag
    await insert_agent("search-helper", name="Helper")  # partial ILIKE
    await insert_agent("unrelated", name="Nothing")  # must not appear

    resp = await client.get("/resolve/search")
    assert resp.status_code == 200
    slugs = [a["slug"] for a in resp.json()]

    # Exact first, then capability, then partial. No duplicates, no 'unrelated'.
    assert slugs == ["search", "indexer", "search-helper"]


async def test_resolve_returns_empty_list_for_no_match(client):
    resp = await client.get("/resolve/ghost")
    assert resp.status_code == 200
    assert resp.json() == []
