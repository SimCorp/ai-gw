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


import uuid


async def test_list_agents_filters(client, insert_agent):
    team_a = uuid.uuid4()
    await insert_agent("a1", category="research", capabilities=["web"], managed=True)
    await insert_agent("a2", category="ops", capabilities=["web", "shell"], managed=False)
    await insert_agent("a3", category="research", capabilities=["shell"], managed=True)

    # Seed one with a team_id via direct SQL (insert_agent has no team param).
    async with client.pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO agent_identities (slug, name, capabilities, team_id) "
            "VALUES ($1, $1, $2, $3)",
            "a4",
            [],
            team_a,
        )

    # capability filter (ANY)
    by_cap = await client.get("/agents", params={"capability": "shell"})
    assert {a["slug"] for a in by_cap.json()} == {"a2", "a3"}

    # category filter
    by_cat = await client.get("/agents", params={"category": "research"})
    assert {a["slug"] for a in by_cat.json()} == {"a1", "a3"}

    # managed filter
    by_managed = await client.get("/agents", params={"managed": "true"})
    assert {a["slug"] for a in by_managed.json()} == {"a1", "a3"}

    # team_id filter
    by_team = await client.get("/agents", params={"team_id": str(team_a)})
    assert {a["slug"] for a in by_team.json()} == {"a4"}

    # no filter → all four
    all_agents = await client.get("/agents")
    assert {a["slug"] for a in all_agents.json()} == {"a1", "a2", "a3", "a4"}
