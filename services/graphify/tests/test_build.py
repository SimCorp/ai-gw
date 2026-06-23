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


def test_extract_cmd_offline_without_key(monkeypatch):
    # No gateway key → code-only offline extraction: must NOT force --backend openai
    # (which hard-fails "requires OPENAI_API_KEY") and must not set OPENAI_* env.
    from app import builder

    monkeypatch.setattr(builder.settings, "graphify_gateway_key", "")
    args, env = builder._extract_cmd("six")
    assert "--backend" not in args
    assert "OPENAI_API_KEY" not in env


def test_extract_cmd_scrubs_inherited_provider_keys(monkeypatch):
    # Stack .env provider keys must NOT leak into the build env, else graphify
    # auto-routes to a direct provider (governance hole + failure).
    from app import builder

    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-leak")
    monkeypatch.setenv("GEMINI_API_KEY", "gm-leak")
    monkeypatch.setattr(builder.settings, "graphify_gateway_key", "")
    _, env = builder._extract_cmd("six")
    assert "ANTHROPIC_API_KEY" not in env
    assert "GEMINI_API_KEY" not in env


def test_extract_cmd_uses_gateway_when_key_set(monkeypatch):
    from app import builder

    # Even with a stray inherited OpenAI key, the gateway values win and the
    # inherited one is scrubbed first.
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-leak")
    monkeypatch.setattr(builder.settings, "graphify_gateway_key", "sk-test")
    monkeypatch.setattr(builder.settings, "graphify_openai_base_url", "http://cache:8002/v1")
    args, env = builder._extract_cmd("six")
    assert args[-2:] == ["--backend", "openai"]
    assert env["OPENAI_API_KEY"] == "sk-test"
    assert env["OPENAI_BASE_URL"] == "http://cache:8002/v1"
    assert "ANTHROPIC_API_KEY" not in env


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
    # Point graphify_out_dir at tmp_path so the realpath containment check passes.
    from app.config import settings as _s

    monkeypatch.setattr(_s, "graphify_out_dir", str(tmp_path))

    result = query.stats("ims", top_n=2)
    assert result["nodes"] == 3
    assert result["edges"] == 2
    # A is the most-connected node (god node).
    assert result["god_nodes"][0]["node"] == "A"
    assert result["god_nodes"][0]["degree"] == 2
