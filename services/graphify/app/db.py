"""Postgres access for the graphify service.

Raw asyncpg (no ORM), mirroring librarian/identity. Holds the schema and the
repo-registry + build-job query helpers shared by the API (app.main) and the
build worker (app.worker), so the worker never imports the FastAPI app.

Graph artefacts (graph.json / graph.html / GRAPH_REPORT.md) live on the
graphify_out volume — only registry + job state are in Postgres.
"""

from __future__ import annotations

import os
import re

import asyncpg

from app.config import settings

# Repo names double as on-disk directory names and clone targets — keep them
# strictly filesystem/shell-safe.
REPO_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,99}$")

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS graph_repos (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name          TEXT NOT NULL UNIQUE,
    github_url    TEXT NOT NULL,
    ref           TEXT NOT NULL DEFAULT 'main',
    last_commit   TEXT,
    last_built_at TIMESTAMPTZ,
    status        TEXT NOT NULL DEFAULT 'registered',
    enabled       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS graph_builds (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    repo_id     UUID NOT NULL REFERENCES graph_repos(id) ON DELETE CASCADE,
    status      TEXT NOT NULL DEFAULT 'queued',
    claimed_by  TEXT,
    log_tail    TEXT,
    error       TEXT,
    nodes       INT,
    edges       INT,
    queued_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at  TIMESTAMPTZ,
    finished_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS graph_builds_repo_idx ON graph_builds(repo_id, queued_at DESC);
CREATE INDEX IF NOT EXISTS graph_builds_queued_idx ON graph_builds(queued_at) WHERE status = 'queued';
"""


async def bootstrap_schema(pool: asyncpg.Pool) -> None:
    async with pool.acquire() as conn:
        await conn.execute(_SCHEMA_SQL)


async def create_pool() -> asyncpg.Pool:
    # asyncpg wants postgresql:// not the SQLAlchemy postgresql+asyncpg:// form.
    db_url = settings.database_url.replace("postgresql+asyncpg://", "postgresql://")
    return await asyncpg.create_pool(db_url, min_size=2, max_size=10)


# ---------------------------------------------------------------------------
# Artefact paths — single source of truth so build + query agree on locations.
# ---------------------------------------------------------------------------


def repo_dir(name: str) -> str:
    return os.path.join(settings.graphify_out_dir, name)


def src_dir(name: str) -> str:
    return os.path.join(repo_dir(name), "src")


def graph_dir(name: str) -> str:
    # graphify writes its artefacts to `graphify-out/` relative to its cwd; we
    # run the build with cwd=repo_dir(name), so they land here.
    return os.path.join(repo_dir(name), "graphify-out")


def graph_json_path(name: str) -> str:
    return os.path.join(graph_dir(name), "graph.json")


# ---------------------------------------------------------------------------
# Repo registry
# ---------------------------------------------------------------------------


async def register_repo(
    pool: asyncpg.Pool, *, name: str, github_url: str, ref: str
) -> asyncpg.Record:
    async with pool.acquire() as conn:
        return await conn.fetchrow(
            """
            INSERT INTO graph_repos (name, github_url, ref, status)
            VALUES ($1, $2, $3, 'registered')
            RETURNING *
            """,
            name,
            github_url,
            ref,
        )


async def list_repos(pool: asyncpg.Pool) -> list[asyncpg.Record]:
    async with pool.acquire() as conn:
        return await conn.fetch("SELECT * FROM graph_repos ORDER BY name")


async def get_repo(pool: asyncpg.Pool, name: str) -> asyncpg.Record | None:
    async with pool.acquire() as conn:
        return await conn.fetchrow("SELECT * FROM graph_repos WHERE name = $1", name)


async def delete_repo(pool: asyncpg.Pool, name: str) -> bool:
    async with pool.acquire() as conn:
        result = await conn.execute("DELETE FROM graph_repos WHERE name = $1", name)
    return result != "DELETE 0"


async def set_repo_status(pool: asyncpg.Pool, repo_id, status: str) -> None:
    async with pool.acquire() as conn:
        await conn.execute("UPDATE graph_repos SET status = $2 WHERE id = $1", repo_id, status)


# ---------------------------------------------------------------------------
# Build jobs
# ---------------------------------------------------------------------------


async def queue_build(pool: asyncpg.Pool, repo_id) -> asyncpg.Record:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "INSERT INTO graph_builds (repo_id, status) VALUES ($1, 'queued') RETURNING *",
            repo_id,
        )
        await conn.execute("UPDATE graph_repos SET status = 'building' WHERE id = $1", repo_id)
    return row


async def list_builds(pool: asyncpg.Pool, repo_id, limit: int = 20) -> list[asyncpg.Record]:
    async with pool.acquire() as conn:
        return await conn.fetch(
            """
            SELECT * FROM graph_builds
            WHERE repo_id = $1
            ORDER BY queued_at DESC
            LIMIT $2
            """,
            repo_id,
            limit,
        )


async def claim_next_build(pool: asyncpg.Pool, worker_id: str) -> dict | None:
    """Atomically claim the oldest queued build, marking it running. FOR UPDATE
    SKIP LOCKED keeps this safe if we ever run more than one worker. Returns the
    fresh build row merged with the repo's name/url/ref, or None when idle."""
    async with pool.acquire() as conn:
        async with conn.transaction():
            sel = await conn.fetchrow(
                """
                SELECT id FROM graph_builds
                WHERE status = 'queued'
                ORDER BY queued_at
                FOR UPDATE SKIP LOCKED
                LIMIT 1
                """
            )
            if sel is None:
                return None
            build = await conn.fetchrow(
                """
                UPDATE graph_builds
                SET status = 'running', claimed_by = $2, started_at = NOW()
                WHERE id = $1
                RETURNING *
                """,
                sel["id"],
                worker_id,
            )
            repo = await conn.fetchrow(
                "SELECT name AS repo_name, github_url, ref FROM graph_repos WHERE id = $1",
                build["repo_id"],
            )
            return {**dict(build), **dict(repo)}


async def finish_build(
    pool: asyncpg.Pool,
    *,
    build_id,
    repo_id,
    succeeded: bool,
    log_tail: str = "",
    error: str | None = None,
    nodes: int | None = None,
    edges: int | None = None,
    last_commit: str | None = None,
) -> None:
    status = "succeeded" if succeeded else "failed"
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                """
                UPDATE graph_builds
                SET status = $2, log_tail = $3, error = $4, nodes = $5, edges = $6,
                    finished_at = NOW()
                WHERE id = $1
                """,
                build_id,
                status,
                log_tail[-8000:] if log_tail else None,
                error,
                nodes,
                edges,
            )
            if succeeded:
                await conn.execute(
                    """
                    UPDATE graph_repos
                    SET status = 'ready', last_built_at = NOW(), last_commit = $2
                    WHERE id = $1
                    """,
                    repo_id,
                    last_commit,
                )
            else:
                await conn.execute(
                    "UPDATE graph_repos SET status = 'failed' WHERE id = $1", repo_id
                )
