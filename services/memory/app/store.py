"""Database operations for Memory Palace.

All functions enforce ``developer_id`` isolation — every query filters by the
caller's developer_id so no cross-developer data leaks are possible.

Embeddings are passed as Python list[float] and cast to the pgvector ``vector``
type using a string literal cast (``$1::vector``) to avoid requiring the
``pgvector`` Python package.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any

import asyncpg

# ── Helpers ────────────────────────────────────────────────────────────────────


def _emb_to_str(embedding: list[float]) -> str:
    """Encode a float list as pgvector literal '[x,y,...]'."""
    return "[" + ",".join(map(str, embedding)) + "]"


def _row(record: asyncpg.Record | None) -> dict | None:
    if record is None:
        return None
    return dict(record)


def _rows(records: list[asyncpg.Record]) -> list[dict]:
    return [dict(r) for r in records]


# ── Drawers ────────────────────────────────────────────────────────────────────


async def add_drawer(
    pool: asyncpg.Pool,
    developer_id: str,
    wing: str,
    room: str,
    content: str,
    summary: str | None,
    tags: list[str],
    source: str | None,
    embedding: list[float],
) -> dict:
    row = await pool.fetchrow(
        """
        INSERT INTO memory_drawers
            (developer_id, wing, room, content, summary, tags, source, embedding)
        VALUES
            ($1::uuid, $2, $3, $4, $5, $6, $7, $8::vector)
        RETURNING *
        """,
        developer_id,
        wing,
        room,
        content,
        summary,
        tags,
        source,
        _emb_to_str(embedding),
    )
    return _row(row)


async def get_drawer(
    pool: asyncpg.Pool,
    developer_id: str,
    drawer_id: str,
) -> dict | None:
    row = await pool.fetchrow(
        "SELECT * FROM memory_drawers WHERE id = $1::uuid AND developer_id = $2::uuid",
        drawer_id,
        developer_id,
    )
    return _row(row)


async def update_drawer(
    pool: asyncpg.Pool,
    developer_id: str,
    drawer_id: str,
    **fields: Any,
) -> dict | None:
    allowed = {"wing", "room", "content", "summary", "tags", "source", "embedding"}
    updates = {k: v for k, v in fields.items() if k in allowed and v is not None}
    if not updates:
        return await get_drawer(pool, developer_id, drawer_id)

    set_clauses = []
    values: list[Any] = []
    idx = 1
    for key, val in updates.items():
        if key == "embedding":
            set_clauses.append(f"{key} = ${idx}::vector")
            values.append(_emb_to_str(val))
        else:
            set_clauses.append(f"{key} = ${idx}")
            values.append(val)
        idx += 1

    set_clauses.append("updated_at = NOW()")
    values.extend([drawer_id, developer_id])

    sql = (
        f"UPDATE memory_drawers SET {', '.join(set_clauses)} "
        f"WHERE id = ${idx}::uuid AND developer_id = ${idx + 1}::uuid "
        f"RETURNING *"
    )
    row = await pool.fetchrow(sql, *values)
    return _row(row)


async def delete_drawer(
    pool: asyncpg.Pool,
    developer_id: str,
    drawer_id: str,
) -> bool:
    result = await pool.execute(
        "DELETE FROM memory_drawers WHERE id = $1::uuid AND developer_id = $2::uuid",
        drawer_id,
        developer_id,
    )
    return result.split()[-1] != "0"


async def list_drawers(
    pool: asyncpg.Pool,
    developer_id: str,
    wing: str | None = None,
    room: str | None = None,
    limit: int = 20,
) -> list[dict]:
    if wing and room:
        rows = await pool.fetch(
            "SELECT * FROM memory_drawers WHERE developer_id = $1::uuid AND wing = $2 AND room = $3 "
            "ORDER BY created_at DESC LIMIT $4",
            developer_id,
            wing,
            room,
            limit,
        )
    elif wing:
        rows = await pool.fetch(
            "SELECT * FROM memory_drawers WHERE developer_id = $1::uuid AND wing = $2 "
            "ORDER BY created_at DESC LIMIT $3",
            developer_id,
            wing,
            limit,
        )
    else:
        rows = await pool.fetch(
            "SELECT * FROM memory_drawers WHERE developer_id = $1::uuid "
            "ORDER BY created_at DESC LIMIT $2",
            developer_id,
            limit,
        )
    return _rows(rows)


async def search_drawers(
    pool: asyncpg.Pool,
    developer_id: str,
    embedding: list[float],
    limit: int = 10,
    threshold: float = 0.7,
) -> list[dict]:
    rows = await pool.fetch(
        """
        SELECT *, 1 - (embedding <=> $1::vector) AS similarity
        FROM memory_drawers
        WHERE developer_id = $2::uuid
          AND 1 - (embedding <=> $1::vector) >= $3
        ORDER BY embedding <=> $1::vector
        LIMIT $4
        """,
        _emb_to_str(embedding),
        developer_id,
        threshold,
        limit,
    )
    return _rows(rows)


async def check_duplicate(
    pool: asyncpg.Pool,
    developer_id: str,
    embedding: list[float],
    threshold: float = 0.95,
) -> dict | None:
    row = await pool.fetchrow(
        """
        SELECT *, 1 - (embedding <=> $1::vector) AS similarity
        FROM memory_drawers
        WHERE developer_id = $2::uuid
          AND 1 - (embedding <=> $1::vector) >= $3
        ORDER BY embedding <=> $1::vector
        LIMIT 1
        """,
        _emb_to_str(embedding),
        developer_id,
        threshold,
    )
    return _row(row)


# ── Knowledge Graph ────────────────────────────────────────────────────────────


async def kg_add_node(
    pool: asyncpg.Pool,
    developer_id: str,
    name: str,
    entity_type: str,
    attributes: dict,
) -> dict:
    row = await pool.fetchrow(
        """
        INSERT INTO memory_kg_nodes (developer_id, name, entity_type, attributes)
        VALUES ($1::uuid, $2, $3, $4::jsonb)
        RETURNING *
        """,
        developer_id,
        name,
        entity_type,
        json.dumps(attributes),
    )
    return _row(row)


async def kg_add_edge(
    pool: asyncpg.Pool,
    developer_id: str,
    from_id: str,
    to_id: str,
    relation: str,
    attributes: dict,
) -> dict:
    row = await pool.fetchrow(
        """
        INSERT INTO memory_kg_edges (developer_id, from_id, to_id, relation, attributes)
        VALUES ($1::uuid, $2::uuid, $3::uuid, $4, $5::jsonb)
        RETURNING *
        """,
        developer_id,
        from_id,
        to_id,
        relation,
        json.dumps(attributes),
    )
    return _row(row)


async def kg_query(
    pool: asyncpg.Pool,
    developer_id: str,
    name: str | None = None,
    entity_type: str | None = None,
    limit: int = 20,
) -> list[dict]:
    if name and entity_type:
        rows = await pool.fetch(
            "SELECT * FROM memory_kg_nodes WHERE developer_id = $1::uuid AND name ILIKE $2 "
            "AND entity_type = $3 AND valid_to IS NULL ORDER BY created_at DESC LIMIT $4",
            developer_id,
            f"%{name}%",
            entity_type,
            limit,
        )
    elif name:
        rows = await pool.fetch(
            "SELECT * FROM memory_kg_nodes WHERE developer_id = $1::uuid AND name ILIKE $2 "
            "AND valid_to IS NULL ORDER BY created_at DESC LIMIT $3",
            developer_id,
            f"%{name}%",
            limit,
        )
    elif entity_type:
        rows = await pool.fetch(
            "SELECT * FROM memory_kg_nodes WHERE developer_id = $1::uuid AND entity_type = $2 "
            "AND valid_to IS NULL ORDER BY created_at DESC LIMIT $3",
            developer_id,
            entity_type,
            limit,
        )
    else:
        rows = await pool.fetch(
            "SELECT * FROM memory_kg_nodes WHERE developer_id = $1::uuid "
            "AND valid_to IS NULL ORDER BY created_at DESC LIMIT $2",
            developer_id,
            limit,
        )
    return _rows(rows)


async def kg_invalidate(
    pool: asyncpg.Pool,
    developer_id: str,
    node_id: str,
) -> bool:
    result = await pool.execute(
        "UPDATE memory_kg_nodes SET valid_to = NOW() "
        "WHERE id = $1::uuid AND developer_id = $2::uuid AND valid_to IS NULL",
        node_id,
        developer_id,
    )
    return result.split()[-1] != "0"


async def kg_stats(
    pool: asyncpg.Pool,
    developer_id: str,
) -> dict:
    node_rows = await pool.fetch(
        "SELECT entity_type, COUNT(*) AS count FROM memory_kg_nodes "
        "WHERE developer_id = $1::uuid AND valid_to IS NULL GROUP BY entity_type",
        developer_id,
    )
    edge_rows = await pool.fetch(
        "SELECT relation, COUNT(*) AS count FROM memory_kg_edges "
        "WHERE developer_id = $1::uuid GROUP BY relation",
        developer_id,
    )
    total_nodes = sum(r["count"] for r in node_rows)
    total_edges = sum(r["count"] for r in edge_rows)
    return {
        "total_nodes": total_nodes,
        "total_edges": total_edges,
        "nodes_by_type": {r["entity_type"]: r["count"] for r in node_rows},
        "edges_by_relation": {r["relation"]: r["count"] for r in edge_rows},
    }


async def kg_timeline(
    pool: asyncpg.Pool,
    developer_id: str,
    since: datetime | None = None,
    until: datetime | None = None,
) -> list[dict]:
    since_ts = since or datetime.min
    until_ts = until or datetime.max
    rows = await pool.fetch(
        "SELECT * FROM memory_kg_nodes WHERE developer_id = $1::uuid "
        "AND created_at >= $2 AND created_at <= $3 ORDER BY created_at ASC",
        developer_id,
        since_ts,
        until_ts,
    )
    return _rows(rows)


# ── Diary ──────────────────────────────────────────────────────────────────────


async def diary_read(
    pool: asyncpg.Pool,
    developer_id: str,
    date_filter: date | None = None,
    limit: int = 7,
) -> list[dict]:
    if date_filter:
        rows = await pool.fetch(
            "SELECT * FROM memory_diary WHERE developer_id = $1::uuid AND date = $2 "
            "ORDER BY date DESC LIMIT $3",
            developer_id,
            date_filter,
            limit,
        )
    else:
        rows = await pool.fetch(
            "SELECT * FROM memory_diary WHERE developer_id = $1::uuid ORDER BY date DESC LIMIT $2",
            developer_id,
            limit,
        )
    return _rows(rows)


async def diary_write(
    pool: asyncpg.Pool,
    developer_id: str,
    entry_date: date,
    entry: str,
) -> dict:
    row = await pool.fetchrow(
        """
        INSERT INTO memory_diary (developer_id, date, entry)
        VALUES ($1::uuid, $2, $3)
        ON CONFLICT (developer_id, date) DO UPDATE SET entry = EXCLUDED.entry, updated_at = NOW()
        RETURNING *
        """,
        developer_id,
        entry_date,
        entry,
    )
    return _row(row)


# ── Tunnels ────────────────────────────────────────────────────────────────────


async def create_tunnel(
    pool: asyncpg.Pool,
    developer_id: str,
    from_wing: str,
    to_wing: str,
    label: str | None,
    bidirectional: bool,
) -> dict:
    row = await pool.fetchrow(
        """
        INSERT INTO memory_tunnels (developer_id, from_wing, to_wing, label, bidirectional)
        VALUES ($1::uuid, $2, $3, $4, $5)
        RETURNING *
        """,
        developer_id,
        from_wing,
        to_wing,
        label,
        bidirectional,
    )
    return _row(row)


async def delete_tunnel(
    pool: asyncpg.Pool,
    developer_id: str,
    tunnel_id: str,
) -> bool:
    result = await pool.execute(
        "DELETE FROM memory_tunnels WHERE id = $1::uuid AND developer_id = $2::uuid",
        tunnel_id,
        developer_id,
    )
    return result.split()[-1] != "0"


async def list_tunnels(
    pool: asyncpg.Pool,
    developer_id: str,
) -> list[dict]:
    rows = await pool.fetch(
        "SELECT * FROM memory_tunnels WHERE developer_id = $1::uuid ORDER BY created_at DESC",
        developer_id,
    )
    return _rows(rows)


async def find_tunnels(
    pool: asyncpg.Pool,
    developer_id: str,
    from_wing: str,
) -> list[dict]:
    rows = await pool.fetch(
        "SELECT * FROM memory_tunnels WHERE developer_id = $1::uuid "
        "AND (from_wing = $2 OR (bidirectional = TRUE AND to_wing = $2))",
        developer_id,
        from_wing,
    )
    return _rows(rows)


# ── Stats ──────────────────────────────────────────────────────────────────────


async def palace_stats(
    pool: asyncpg.Pool,
    developer_id: str,
) -> dict:
    drawer_count = await pool.fetchval(
        "SELECT COUNT(*) FROM memory_drawers WHERE developer_id = $1::uuid",
        developer_id,
    )
    kg_node_count = await pool.fetchval(
        "SELECT COUNT(*) FROM memory_kg_nodes WHERE developer_id = $1::uuid AND valid_to IS NULL",
        developer_id,
    )
    kg_edge_count = await pool.fetchval(
        "SELECT COUNT(*) FROM memory_kg_edges WHERE developer_id = $1::uuid",
        developer_id,
    )
    diary_count = await pool.fetchval(
        "SELECT COUNT(*) FROM memory_diary WHERE developer_id = $1::uuid",
        developer_id,
    )
    tunnel_count = await pool.fetchval(
        "SELECT COUNT(*) FROM memory_tunnels WHERE developer_id = $1::uuid",
        developer_id,
    )
    wing_rows = await pool.fetch(
        "SELECT wing, COUNT(*) AS count FROM memory_drawers WHERE developer_id = $1::uuid GROUP BY wing",
        developer_id,
    )
    return {
        "drawers": drawer_count,
        "kg_nodes": kg_node_count,
        "kg_edges": kg_edge_count,
        "diary_entries": diary_count,
        "tunnels": tunnel_count,
        "drawers_by_wing": {r["wing"]: r["count"] for r in wing_rows},
    }
