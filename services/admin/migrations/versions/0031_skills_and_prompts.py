"""Add skills and prompt_templates tables"""

from alembic import op

revision = "0031"
down_revision = "0030"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE IF NOT EXISTS skills (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name            TEXT NOT NULL,
            slug            TEXT NOT NULL UNIQUE,
            version         TEXT NOT NULL DEFAULT 'v1.0',
            model           TEXT NOT NULL DEFAULT 'claude-sonnet-4-6',
            description     TEXT NOT NULL DEFAULT '',
            system_prompt   TEXT NOT NULL DEFAULT '',
            tools           TEXT[] NOT NULL DEFAULT '{}',
            tags            TEXT[] NOT NULL DEFAULT '{}',
            visibility      TEXT NOT NULL DEFAULT 'team' CHECK (visibility IN ('draft','team','org')),
            team_id         UUID REFERENCES organization_nodes(id) ON DELETE SET NULL,
            author          TEXT NOT NULL DEFAULT '',
            uses_total      INT NOT NULL DEFAULT 0,
            stars_avg       NUMERIC(3,1) NOT NULL DEFAULT 0,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_skills_team_id ON skills(team_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_skills_visibility ON skills(visibility)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS prompt_templates (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            title           TEXT NOT NULL,
            slug            TEXT NOT NULL UNIQUE,
            version         TEXT NOT NULL DEFAULT 'v1.0',
            description     TEXT NOT NULL DEFAULT '',
            content         TEXT NOT NULL DEFAULT '',
            author          TEXT NOT NULL DEFAULT '',
            team_id         UUID REFERENCES organization_nodes(id) ON DELETE SET NULL,
            model           TEXT,
            tags            TEXT[] NOT NULL DEFAULT '{}',
            visibility      TEXT NOT NULL DEFAULT 'team' CHECK (visibility IN ('draft','team','org')),
            uses_total      INT NOT NULL DEFAULT 0,
            stars_avg       NUMERIC(3,1) NOT NULL DEFAULT 0,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_prompts_team_id ON prompt_templates(team_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_prompts_visibility ON prompt_templates(visibility)")

    # Seed a handful of example skills and prompts so the UI is not empty on first run
    op.execute("""
        INSERT INTO skills (name, slug, version, model, description, system_prompt, tools, tags, visibility, author, uses_total, stars_avg)
        VALUES
        ('PR reviewer · Python', 'pr-reviewer-python', 'v5.1', 'claude-sonnet-4-6',
         'Reviews PRs against the SimCorp Python style guide. Flags type-hint gaps, missing tests, and risky deps. Posts inline comments via the github-mcp tool.',
         'You are a senior Python engineer performing a PR review against the SimCorp Python style guide. For each issue found, output: file, line, rule_id, severity (block/warn/nit), suggested_fix. Be concise and constructive.',
         ARRAY['github-mcp'], ARRAY['code-review','python'], 'org', 'platform-engineering', 284, 4.7),
        ('Filing summarizer', 'filing-summarizer', 'v2.0', 'claude-haiku-4-5-20251001',
         'Summarises 10-K, 10-Q and EU prospectus filings into a 6-bullet brief with citations.',
         'You summarise regulatory filings. Produce exactly 6 bullets: company, period, key financials (3 bullets), risks, outlook. Cite PDF page anchors.',
         ARRAY['filings-mcp'], ARRAY['finance','summarisation'], 'org', 'research', 192, 4.6),
        ('SQL → narrative', 'sql-to-narrative', 'v2.7', 'claude-haiku-4-5-20251001',
         'Takes a SQL result set and writes a 2-paragraph narrative explaining what changed week-over-week.',
         'You receive a SQL result set as JSON. Write a 2-paragraph narrative explaining the data. Flag the three biggest movers automatically. Audience: non-technical stakeholders.',
         ARRAY[]::TEXT[], ARRAY['sql','reporting'], 'org', 'data-insights', 318, 4.7)
        ON CONFLICT (slug) DO NOTHING
    """)

    op.execute("""
        INSERT INTO prompt_templates (title, slug, version, description, content, author, model, tags, visibility, uses_total, stars_avg)
        VALUES
        ('PR review · Python style', 'pr-review-python', 'v3', 'Reviews a unified diff for style guide violations. Returns structured JSON.',
         'You are a senior reviewer. For each violation in the diff, return JSON with: file, line, rule_id, severity (block/warn/nit), suggested_fix. Focus on: type hints, docstrings, test coverage, risky deps.',
         'p.fontaine', 'claude-sonnet-4-6', ARRAY['code-review','python'], 'org', 142, 4.8),
        ('Incident postmortem draft', 'incident-postmortem', 'v4', 'Turns an incident timeline into a one-page postmortem draft. Tone: calm, factual, no blame.',
         'You write postmortem drafts. Audience: engineering. Tone: calm, factual, no blame. Lead with impact and root cause. Sections: Summary, Timeline, Root Cause, Contributing Factors, Action Items (with owners).',
         'p.fontaine', 'claude-sonnet-4-6', ARRAY['incidents','operations'], 'org', 62, 4.7),
        ('Support ticket classifier', 'support-classifier', 'v2.1', 'Classifies inbound support tickets into categories with confidence scores.',
         'Classify this customer message into exactly one of: account_access, billing, data_quality, integration, performance, feature_request, bug, training_request, other. Return JSON: {category, confidence, reasoning}.',
         'a.silva', 'claude-haiku-4-5-20251001', ARRAY['support','classification'], 'org', 1820, 4.9),
        ('SQL → natural language', 'sql-natural-language', 'v1', 'Explain a SQL query in plain English for a non-SQL teammate.',
         'Given this SQL, write a 3-paragraph explanation that a backend engineer who does not use SQL daily could understand. Highlight joins, filters, and windowing. Keep it under 200 words.',
         'l.gunnarsson', NULL, ARRAY['sql','documentation'], 'org', 92, 4.6)
        ON CONFLICT (slug) DO NOTHING
    """)


def downgrade():
    op.execute("DROP TABLE IF EXISTS prompt_templates")
    op.execute("DROP TABLE IF EXISTS skills")
