"""Repo registry, build-job lifecycle, and query wiring."""


async def test_register_repo_queues_build(client):
    resp = await client.post("/repos", json={"name": "ims"})
    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "ims"
    # Default URL is built from the configured org.
    assert body["github_url"] == "https://github.com/SimCorp/ims.git"
    assert body["status"] in ("registered", "building")

    # A build was queued.
    builds = (await client.get("/repos/ims/builds")).json()["builds"]
    assert len(builds) == 1
    assert builds[0]["status"] == "queued"


async def test_register_rejects_bad_name(client):
    resp = await client.post("/repos", json={"name": "Bad Name!"})
    assert resp.status_code == 422


async def test_register_rejects_non_github_url(client):
    resp = await client.post(
        "/repos", json={"name": "ims", "github_url": "https://evil.example/x.git"}
    )
    assert resp.status_code == 422


async def test_duplicate_repo_conflicts(client):
    await client.post("/repos", json={"name": "ims"})
    resp = await client.post("/repos", json={"name": "ims"})
    assert resp.status_code == 409


async def test_list_repos(client):
    await client.post("/repos", json={"name": "ims"})
    await client.post("/repos", json={"name": "core"})
    repos = (await client.get("/repos")).json()["repos"]
    assert {r["name"] for r in repos} == {"ims", "core"}


async def test_rebuild_queues_another_build(client):
    await client.post("/repos", json={"name": "ims"})
    resp = await client.post("/repos/ims/rebuild")
    assert resp.status_code == 202
    builds = (await client.get("/repos/ims/builds")).json()["builds"]
    assert len(builds) == 2


async def test_rebuild_unknown_repo_404(client):
    assert (await client.post("/repos/nope/rebuild")).status_code == 404


async def test_delete_repo(client):
    await client.post("/repos", json={"name": "ims"})
    assert (await client.delete("/repos/ims")).status_code == 204
    assert (await client.delete("/repos/ims")).status_code == 404


async def test_query_rejects_path_traversal(client):
    # `..` must never reach a filesystem path — validated at the choke-point.
    resp = await client.get("/query", params={"repo": "../etc", "q": "x"})
    assert resp.status_code == 422


async def test_mcp_tool_rejects_path_traversal(client):
    resp = await client.post("/mcp/tools/graph_query", json={"repo": "../secret", "question": "x"})
    assert resp.status_code == 422


async def test_query_unbuilt_repo_returns_409(client, monkeypatch):

    # No graph.json on disk → GraphNotReady → 409.
    resp = await client.get("/query", params={"repo": "ims", "q": "what is X?"})
    assert resp.status_code == 409


async def test_query_returns_subgraph_text(client, monkeypatch):
    from app import query

    async def _fake_query(repo, question, *, budget=2000, dfs=False):
        return f"subgraph for {question}"

    monkeypatch.setattr(query, "query", _fake_query)
    resp = await client.get("/query", params={"repo": "ims", "q": "auth flow"})
    assert resp.status_code == 200
    assert resp.json()["result"] == "subgraph for auth flow"
