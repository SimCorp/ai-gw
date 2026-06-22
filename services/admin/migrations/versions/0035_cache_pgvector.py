"""Semantic cache vector store (pgvector HNSW).

Replaces the O(N) Redis key scan with an HNSW-indexed ANN search on Postgres.
The cache service now stores embeddings and responses in this table and uses
the <=> cosine-distance operator for similarity lookups.

Autovacuum note: this table has high churn (rows expire and are deleted by the
cache service's background cleanup loop). Set a tighter scale factor so dead
tuples are reclaimed promptly.

Revision ID: 0035
Revises: 0034
Create Date: 2026-06-22
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0035"
down_revision: Union[str, None] = "0034"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # pgvector was enabled by migration 0006; belt-and-suspenders.
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.execute("""
        CREATE TABLE IF NOT EXISTS cache_entries (
            id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            team_id     TEXT        NOT NULL,
            project_id  TEXT        NOT NULL,
            embedding   vector(1536) NOT NULL,
            response    JSONB       NOT NULL,
            expires_at  TIMESTAMPTZ NOT NULL,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)

    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_cache_entries_team_project "
        "ON cache_entries(team_id, project_id)"
    )
    # HNSW works on empty tables (unlike IVFFlat which needs rows to train).
    # vector_cosine_ops matches the <=> cosine-distance operator in queries.
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_cache_entries_embedding "
        "ON cache_entries USING hnsw (embedding vector_cosine_ops)"
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_cache_entries_expires ON cache_entries(expires_at)")
    # Tighten autovacuum for this high-churn table so the HNSW index stays lean.
    op.execute(
        "ALTER TABLE cache_entries SET ("
        "autovacuum_vacuum_scale_factor = 0.05, "
        "autovacuum_analyze_scale_factor = 0.05"
        ")"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS cache_entries")
