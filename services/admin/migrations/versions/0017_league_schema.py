# services/admin/migrations/versions/0017_league_schema.py
"""League schema — seasons, challenges, submissions, scores, leaderboard, store, points

Revision ID: 0017
Revises: 0016
"""
from alembic import op
from typing import Sequence, Union

revision = "0017"
down_revision = "0016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    op.execute("""
        CREATE TABLE IF NOT EXISTS league_seasons (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name            TEXT NOT NULL,
            status          TEXT NOT NULL DEFAULT 'upcoming'
                            CHECK (status IN ('upcoming', 'active', 'closed')),
            starts_at       TIMESTAMPTZ NOT NULL,
            ends_at         TIMESTAMPTZ NOT NULL CHECK (ends_at > starts_at),
            scoring_weights JSONB NOT NULL DEFAULT '{"quality":0.35,"robustness":0.20,"token_efficiency":0.15,"speed":0.10,"cost_efficiency":0.10,"improvement_rate":0.05,"creativity":0.05}',
            season_multiplier NUMERIC(4,2) NOT NULL DEFAULT 1.0,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS league_challenges (
            id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            season_id            UUID NOT NULL REFERENCES league_seasons(id) ON DELETE CASCADE,
            title                TEXT NOT NULL,
            goal                 TEXT NOT NULL,
            training_inputs      JSONB NOT NULL DEFAULT '[]',
            hidden_test_suite    JSONB NOT NULL DEFAULT '[]',
            allowed_models       TEXT[] NOT NULL DEFAULT ARRAY['claude-sonnet-4-6'],
            max_tokens_budget    INT NOT NULL DEFAULT 4096 CHECK (max_tokens_budget > 0),
            max_league_attempts  INT NOT NULL DEFAULT 3 CHECK (max_league_attempts > 0),
            scores_revealed_at   TIMESTAMPTZ,
            status               TEXT NOT NULL DEFAULT 'draft'
                                 CHECK (status IN ('draft', 'active', 'closed')),
            proposed_by          UUID REFERENCES users(id) ON DELETE SET NULL,
            created_at           TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_league_challenges_season ON league_challenges(season_id)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS league_submissions (
            id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            challenge_id     UUID NOT NULL REFERENCES league_challenges(id) ON DELETE CASCADE,
            engineer_id      UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            mode             TEXT NOT NULL CHECK (mode IN ('training', 'league')),
            system_prompt    TEXT NOT NULL,
            tool_config      JSONB NOT NULL DEFAULT '[]',
            attempt_number   INT NOT NULL DEFAULT 1,
            run_results      JSONB,
            prompt_hash      TEXT NOT NULL,
            submitted_at     TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_league_submissions_challenge ON league_submissions(challenge_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_league_submissions_engineer ON league_submissions(engineer_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_league_submissions_challenge_engineer ON league_submissions(challenge_id, engineer_id)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS league_scores (
            id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            submission_id     UUID NOT NULL REFERENCES league_submissions(id) ON DELETE CASCADE,
            quality           NUMERIC(5,2) NOT NULL DEFAULT 0,
            robustness        NUMERIC(5,2) NOT NULL DEFAULT 0,
            token_efficiency  NUMERIC(5,2) NOT NULL DEFAULT 0,
            speed             NUMERIC(5,2) NOT NULL DEFAULT 0,
            cost_efficiency   NUMERIC(5,2) NOT NULL DEFAULT 0,
            improvement_rate  NUMERIC(5,2) NOT NULL DEFAULT 50,
            creativity        NUMERIC(5,2) NOT NULL DEFAULT 50,
            composite         NUMERIC(7,2) NOT NULL DEFAULT 0
        )
    """)
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_league_scores_submission ON league_scores(submission_id)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS league_leaderboard (
            season_id         UUID NOT NULL REFERENCES league_seasons(id) ON DELETE CASCADE,
            engineer_id       UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            composite_score   NUMERIC(7,2) NOT NULL DEFAULT 0,
            rank              INT,
            points_earned     INT NOT NULL DEFAULT 0,
            updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (season_id, engineer_id)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_league_leaderboard_season_score ON league_leaderboard(season_id, composite_score DESC)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS league_points_ledger (
            id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            engineer_id   UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            delta         INT NOT NULL,
            reason        TEXT NOT NULL CHECK (reason IN (
                              'league_submission_reward',
                              'training_xp_reward',
                              'store_purchase',
                              'admin_grant',
                              'season_exclusive_grant'
                          )),
            ref_id        UUID,
            created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_league_points_engineer ON league_points_ledger(engineer_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_league_points_engineer_time ON league_points_ledger(engineer_id, created_at DESC)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS league_store_items (
            id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name                  TEXT NOT NULL,
            type                  TEXT NOT NULL CHECK (type IN ('badge', 'card_border', 'avatar_frame', 'title')),
            point_cost            INT NOT NULL DEFAULT 0 CHECK (point_cost >= 0),
            asset_url             TEXT NOT NULL DEFAULT '',
            exclusive_season_id   UUID REFERENCES league_seasons(id) ON DELETE SET NULL,
            exclusive_top_n       INT,
            active                BOOLEAN NOT NULL DEFAULT TRUE,
            created_at            TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS league_purchases (
            id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            engineer_id   UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            item_id       UUID NOT NULL REFERENCES league_store_items(id) ON DELETE CASCADE,
            points_spent  INT NOT NULL DEFAULT 0,
            purchased_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (engineer_id, item_id)
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS league_challenge_proposals (
            id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            proposed_by    UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            title          TEXT NOT NULL,
            goal           TEXT NOT NULL,
            notes          TEXT NOT NULL DEFAULT '',
            status         TEXT NOT NULL DEFAULT 'proposed'
                           CHECK (status IN ('proposed', 'approved', 'rejected')),
            reviewed_by    UUID REFERENCES users(id) ON DELETE SET NULL,
            reviewer_notes TEXT NOT NULL DEFAULT '',
            created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)


def downgrade():
    for tbl in [
        "league_challenge_proposals",
        "league_purchases",
        "league_store_items",
        "league_points_ledger",
        "league_leaderboard",
        "league_scores",
        "league_submissions",
        "league_challenges",
        "league_seasons",
    ]:
        op.execute(f"DROP TABLE IF EXISTS {tbl} CASCADE")
