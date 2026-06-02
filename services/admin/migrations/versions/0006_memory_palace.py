"""memory palace schema

Adds 5 tables for the Memory Palace service: drawers, KG nodes/edges, diary,
and tunnels. Enables the pgvector extension for ANN search.

Revision ID: 0006
Revises: 0005
Create Date: 2026-05-12
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # pgvector extension — required for the vector column type and <=> operator
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # ── memory_drawers ─────────────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS memory_drawers (
            id           UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            developer_id UUID        NOT NULL REFERENCES developers(id) ON DELETE CASCADE,
            wing         TEXT        NOT NULL DEFAULT 'default',
            room         TEXT        NOT NULL DEFAULT 'default',
            content      TEXT        NOT NULL,
            summary      TEXT,
            tags         TEXT[]      NOT NULL DEFAULT '{}',
            source       TEXT,
            embedding    vector(1536),
            created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_memory_drawers_developer ON memory_drawers(developer_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_memory_drawers_wing "
        "ON memory_drawers(developer_id, wing, room)"
    )
    # HNSW works on empty tables, unlike IVFFlat which requires rows to train
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_memory_drawers_embedding "
        "ON memory_drawers USING hnsw (embedding vector_cosine_ops)"
    )

    # ── memory_kg_nodes ────────────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS memory_kg_nodes (
            id           UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            developer_id UUID        NOT NULL REFERENCES developers(id) ON DELETE CASCADE,
            name         TEXT        NOT NULL,
            entity_type  TEXT        NOT NULL DEFAULT 'entity',
            attributes   JSONB       NOT NULL DEFAULT '{}',
            created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            valid_to     TIMESTAMPTZ
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_memory_kg_nodes_developer ON memory_kg_nodes(developer_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_memory_kg_nodes_name ON memory_kg_nodes(developer_id, name)"
    )

    # ── memory_kg_edges ────────────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS memory_kg_edges (
            id           UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            developer_id UUID        NOT NULL REFERENCES developers(id) ON DELETE CASCADE,
            from_id      UUID        NOT NULL REFERENCES memory_kg_nodes(id) ON DELETE CASCADE,
            to_id        UUID        NOT NULL REFERENCES memory_kg_nodes(id) ON DELETE CASCADE,
            relation     TEXT        NOT NULL DEFAULT 'related',
            attributes   JSONB       NOT NULL DEFAULT '{}',
            created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_memory_kg_edges_developer ON memory_kg_edges(developer_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_memory_kg_edges_from "
        "ON memory_kg_edges(developer_id, from_id)"
    )

    # ── memory_diary ───────────────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS memory_diary (
            id           UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            developer_id UUID        NOT NULL REFERENCES developers(id) ON DELETE CASCADE,
            date         DATE        NOT NULL,
            entry        TEXT        NOT NULL,
            created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (developer_id, date)
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_memory_diary_developer "
        "ON memory_diary(developer_id, date DESC)"
    )

    # ── memory_tunnels ─────────────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS memory_tunnels (
            id            UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            developer_id  UUID        NOT NULL REFERENCES developers(id) ON DELETE CASCADE,
            from_wing     TEXT        NOT NULL,
            to_wing       TEXT        NOT NULL,
            label         TEXT,
            bidirectional BOOLEAN     NOT NULL DEFAULT FALSE,
            created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_memory_tunnels_developer ON memory_tunnels(developer_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_memory_tunnels_from_wing "
        "ON memory_tunnels(developer_id, from_wing)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS memory_tunnels")
    op.execute("DROP TABLE IF EXISTS memory_diary")
    op.execute("DROP TABLE IF EXISTS memory_kg_edges")
    op.execute("DROP TABLE IF EXISTS memory_kg_nodes")
    op.execute("DROP TABLE IF EXISTS memory_drawers")
    # Do NOT drop the vector extension — other services may depend on it
