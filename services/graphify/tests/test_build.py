"""Build-job claim/finish lifecycle and graph.json stats parsing."""

import json

from app import db, query


async def test_build_lifecycle(pool):
    repo = await db.register_repo(
        pool, name="ims", github_url="https://github.com/SimCorp/ims.git", ref="main"
    )
    await db.queue_build(pool, repo["id"])

    # Worker claims the job.
    job = await db.claim_next_build(pool, "worker-1")
    assert job is not None
    assert job["repo_name"] == "ims"
    assert job["status"] == "running"

    # Nothing left to claim.
    assert await db.claim_next_build(pool, "worker-1") is None

    # Worker records success.
    await db.finish_build(
        pool,
        build_id=job["id"],
        repo_id=job["repo_id"],
        succeeded=True,
        log_tail="ok",
        nodes=42,
        edges=99,
        last_commit="abc123",
    )

    builds = await db.list_builds(pool, repo["id"])
    assert builds[0]["status"] == "succeeded"
    assert builds[0]["nodes"] == 42

    repo_row = await db.get_repo(pool, "ims")
    assert repo_row["status"] == "ready"
    assert repo_row["last_commit"] == "abc123"


async def test_failed_build_marks_repo_failed(pool):
    repo = await db.register_repo(
        pool, name="ims", github_url="https://github.com/SimCorp/ims.git", ref="main"
    )
    await db.queue_build(pool, repo["id"])
    job = await db.claim_next_build(pool, "worker-1")
    await db.finish_build(
        pool,
        build_id=job["id"],
        repo_id=job["repo_id"],
        succeeded=False,
        log_tail="boom",
        error="git clone/pull failed",
    )
    repo_row = await db.get_repo(pool, "ims")
    assert repo_row["status"] == "failed"


def test_stats_parses_node_link_graph(tmp_path, monkeypatch):
    graph = {
        "nodes": [{"id": "A"}, {"id": "B"}, {"id": "C"}],
        "links": [
            {"source": "A", "target": "B"},
            {"source": "A", "target": "C"},
        ],
    }
    graph_file = tmp_path / "graph.json"
    graph_file.write_text(json.dumps(graph))
    monkeypatch.setattr(query, "graph_json_path", lambda repo: str(graph_file))

    result = query.stats("ims", top_n=2)
    assert result["nodes"] == 3
    assert result["edges"] == 2
    # A is the most-connected node (god node).
    assert result["god_nodes"][0]["node"] == "A"
    assert result["god_nodes"][0]["degree"] == 2
