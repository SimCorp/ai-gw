"""baseline schema

Captures the schema that previously existed as the union of:
- infra/postgres/init.sql  (the legacy db-migrate compose step)
- Base.metadata.create_all() at admin startup
- _EXTRA_DDL block in services/admin/app/main.py

ORM-mapped tables (teams, projects, api_keys, policies, model_pricing,
team_members, audit_log, model_registry, mcp_*, plugins, plugin_team_overrides,
areas, area_policies) AND raw-SQL tables (developers, sessions, cost_records,
developer_activity_log, developer_output_events, org_settings, admin_users,
ai_insights, guardrails, guardrail_hits) are all created here so a single
`alembic upgrade head` against an empty DB produces the exact runtime schema.

Seed data for model_pricing, model_registry, plugins, and org_settings is
included; ON CONFLICT DO NOTHING keeps it idempotent. The default admin
account, default Engineering team, and guardrail seeds remain in the admin
service's lifespan (runtime concerns, not schema).

Revision ID: 0001
Revises:
Create Date: 2026-05-11
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto"')

    # ------------------------------------------------------------------
    # Core identity: areas -> teams -> projects -> developers -> api_keys
    # ------------------------------------------------------------------
    op.execute("""
        CREATE TABLE IF NOT EXISTS areas (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name TEXT NOT NULL,
            slug TEXT NOT NULL UNIQUE,
            description TEXT,
            color TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS teams (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name TEXT NOT NULL,
            slug TEXT NOT NULL UNIQUE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            monthly_budget_usd NUMERIC(14,8),
            budget_alert_pct FLOAT NOT NULL DEFAULT 0.8,
            budget_action TEXT NOT NULL DEFAULT 'alert',
            area_id UUID REFERENCES areas(id) ON DELETE SET NULL
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_teams_area_id ON teams(area_id)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS projects (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            team_id UUID NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            slug TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (team_id, slug)
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS developers (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            email VARCHAR(255) NOT NULL UNIQUE,
            display_name VARCHAR(255),
            password_hash TEXT NOT NULL,
            status VARCHAR(50) NOT NULL DEFAULT 'pending',
            email_verified_at TIMESTAMPTZ,
            team_id UUID REFERENCES teams(id) ON DELETE SET NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_developers_email  ON developers(email)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_developers_status ON developers(status)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_developers_team   ON developers(team_id)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS api_keys (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            team_id UUID NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
            project_id UUID REFERENCES projects(id) ON DELETE SET NULL,
            name TEXT NOT NULL,
            key_hash TEXT NOT NULL UNIQUE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            revoked_at TIMESTAMPTZ,
            developer_id UUID REFERENCES developers(id) ON DELETE SET NULL,
            last_used_at TIMESTAMPTZ,
            monthly_budget_usd NUMERIC(14,8)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_api_keys_developer ON api_keys(developer_id)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS team_members (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            team_id UUID NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
            user_id TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'member' CHECK (role IN ('admin', 'member')),
            developer_id UUID REFERENCES developers(id) ON DELETE CASCADE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (team_id, user_id)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS team_members_team_id_idx ON team_members (team_id)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_team_members_developer_id ON team_members(developer_id)"
    )

    # ------------------------------------------------------------------
    # Policies (per-team-project) and area-level policies
    # ------------------------------------------------------------------
    op.execute("""
        CREATE TABLE IF NOT EXISTS policies (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            team_id UUID NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
            project_id UUID REFERENCES projects(id) ON DELETE CASCADE,
            cache_ttl_seconds INT NOT NULL DEFAULT 3600,
            cache_similarity_threshold FLOAT NOT NULL DEFAULT 0.95,
            cache_opt_out BOOLEAN NOT NULL DEFAULT FALSE,
            embedding_model TEXT NOT NULL DEFAULT 'text-embedding-3-small',
            rate_limit_rpm INT NOT NULL DEFAULT 1000,
            allowed_models TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (team_id, project_id)
        )
    """)
    # Partial unique indexes so ON CONFLICT works when project_id is NULL
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS policies_team_null_proj_uidx ON policies (team_id) WHERE project_id IS NULL"
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS policies_team_proj_uidx ON policies (team_id, project_id) WHERE project_id IS NOT NULL"
    )

    op.execute("""
        CREATE TABLE IF NOT EXISTS area_policies (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            area_id UUID NOT NULL REFERENCES areas(id) ON DELETE CASCADE,
            cache_ttl_seconds INT NOT NULL DEFAULT 3600,
            cache_similarity_threshold FLOAT NOT NULL DEFAULT 0.95,
            cache_opt_out BOOLEAN NOT NULL DEFAULT FALSE,
            embedding_model TEXT NOT NULL DEFAULT 'text-embedding-3-small',
            rate_limit_rpm INT NOT NULL DEFAULT 1000,
            allowed_models TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (area_id)
        )
    """)

    # ------------------------------------------------------------------
    # Cost records & telemetry
    # ------------------------------------------------------------------
    op.execute("""
        CREATE TABLE IF NOT EXISTS cost_records (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            team_id UUID NOT NULL REFERENCES teams(id),
            project_id UUID REFERENCES projects(id),
            model TEXT NOT NULL,
            tokens_input INT NOT NULL DEFAULT 0,
            tokens_output INT NOT NULL DEFAULT 0,
            cost_usd NUMERIC(10,8) NOT NULL DEFAULT 0,
            cache_hit BOOLEAN NOT NULL DEFAULT FALSE,
            latency_ms INT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            api_key_id UUID REFERENCES api_keys(id) ON DELETE SET NULL,
            developer_id UUID REFERENCES developers(id) ON DELETE SET NULL,
            session_trace_id TEXT,
            tool_invocation_count INT NOT NULL DEFAULT 0,
            retry_count INT NOT NULL DEFAULT 0,
            request_error_type TEXT,
            cache_namespace TEXT,
            repo TEXT,
            session_purpose TEXT
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS cost_records_team_id_created_at_idx ON cost_records (team_id, created_at DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_cost_records_api_key_id ON cost_records(api_key_id, created_at DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_cost_records_developer_id ON cost_records(developer_id, created_at DESC)"
    )

    op.execute("""
        CREATE TABLE IF NOT EXISTS developer_activity_log (
            developer_id UUID NOT NULL REFERENCES developers(id) ON DELETE CASCADE,
            date DATE NOT NULL,
            request_count INT NOT NULL DEFAULT 0,
            tokens_input BIGINT NOT NULL DEFAULT 0,
            tokens_output BIGINT NOT NULL DEFAULT 0,
            cost_usd NUMERIC(12,6) NOT NULL DEFAULT 0,
            cache_hits INT NOT NULL DEFAULT 0,
            tool_invocations INT NOT NULL DEFAULT 0,
            error_count INT NOT NULL DEFAULT 0,
            PRIMARY KEY (developer_id, date)
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_dev_activity_developer_date ON developer_activity_log(developer_id, date DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_dev_activity_date ON developer_activity_log(date DESC)"
    )

    op.execute("""
        CREATE TABLE IF NOT EXISTS developer_output_events (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            developer_id UUID REFERENCES developers(id) ON DELETE SET NULL,
            repo TEXT NOT NULL,
            event_type TEXT NOT NULL,
            github_user TEXT,
            commit_count INT NOT NULL DEFAULT 0,
            lines_added INT NOT NULL DEFAULT 0,
            lines_removed INT NOT NULL DEFAULT 0,
            pr_number INT,
            occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            raw JSONB
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_dev_output_developer ON developer_output_events(developer_id, occurred_at DESC)"
    )

    op.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            session_trace_id TEXT PRIMARY KEY,
            developer_id UUID REFERENCES developers(id) ON DELETE SET NULL,
            team_id TEXT NOT NULL,
            first_request_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            last_request_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            turn_count INT NOT NULL DEFAULT 1,
            total_tokens BIGINT NOT NULL DEFAULT 0,
            total_cost NUMERIC(12,8) NOT NULL DEFAULT 0,
            retry_count INT NOT NULL DEFAULT 0,
            error_count INT NOT NULL DEFAULT 0,
            tool_invocations INT NOT NULL DEFAULT 0,
            session_purpose TEXT,
            repo TEXT,
            primary_model TEXT,
            quality_score INT,
            avg_inter_request_s FLOAT,
            produced_commit BOOLEAN,
            dominant_intent TEXT,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_sessions_developer ON sessions(developer_id, first_request_at DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_sessions_team ON sessions(team_id, first_request_at DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_sessions_first_request ON sessions(first_request_at DESC)"
    )

    # ------------------------------------------------------------------
    # Audit log
    # ------------------------------------------------------------------
    op.execute("""
        CREATE TABLE IF NOT EXISTS audit_log (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            actor TEXT NOT NULL DEFAULT 'unknown',
            action TEXT NOT NULL,
            resource_type TEXT NOT NULL,
            resource_id TEXT,
            details JSONB
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS audit_log_timestamp_idx ON audit_log (timestamp DESC)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS audit_log_resource_idx ON audit_log (resource_type, resource_id)"
    )

    # ------------------------------------------------------------------
    # Pricing & model registry (with seeds)
    # ------------------------------------------------------------------
    op.execute("""
        CREATE TABLE IF NOT EXISTS model_pricing (
            model_prefix TEXT PRIMARY KEY,
            price_input_per_1k  NUMERIC(12,8) NOT NULL DEFAULT 0,
            price_output_per_1k NUMERIC(12,8) NOT NULL DEFAULT 0,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("""
        INSERT INTO model_pricing (model_prefix, price_input_per_1k, price_output_per_1k) VALUES
            ('claude-opus-4-7',    0.015,    0.075),
            ('claude-sonnet-4-6',  0.003,    0.015),
            ('claude-haiku-4-5',   0.0008,   0.004),
            ('gpt-4o-mini',        0.00015,  0.0006),
            ('gpt-4o',             0.0025,   0.01),
            ('gemini-1.5-flash',   0.000075, 0.0003),
            ('gemini-1.5-pro',     0.00125,  0.005)
        ON CONFLICT (model_prefix) DO NOTHING
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS model_registry (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name TEXT NOT NULL,
            model_id TEXT NOT NULL UNIQUE,
            provider TEXT NOT NULL,
            enabled BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("""
        INSERT INTO model_registry (name, model_id, provider) VALUES
            ('Claude Opus 4.7',     'claude-opus-4-7',       'anthropic'),
            ('Claude Sonnet 4.6',   'claude-sonnet-4-6',     'anthropic'),
            ('Claude Haiku 4.5',    'claude-haiku-4-5',      'anthropic'),
            ('GPT-4o',              'gpt-4o',                'openai'),
            ('GPT-4o Mini',         'gpt-4o-mini',           'openai'),
            ('Gemini 1.5 Pro',      'gemini-1.5-pro',        'google'),
            ('Gemini 1.5 Flash',    'gemini-1.5-flash',      'google')
        ON CONFLICT (model_id) DO NOTHING
    """)

    # ------------------------------------------------------------------
    # MCP registry
    # ------------------------------------------------------------------
    op.execute("""
        CREATE TABLE IF NOT EXISTS mcp_servers (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name TEXT NOT NULL,
            description TEXT,
            url TEXT NOT NULL,
            auth_type TEXT NOT NULL DEFAULT 'none',
            auth_header TEXT,
            auth_secret TEXT,
            status TEXT NOT NULL DEFAULT 'pending',
            last_ping_at TIMESTAMPTZ,
            last_ping_ms INT,
            last_error TEXT,
            tool_count INT NOT NULL DEFAULT 0,
            enabled BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (url)
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS mcp_tools (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            server_id UUID NOT NULL REFERENCES mcp_servers(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            description TEXT,
            input_schema JSONB NOT NULL DEFAULT '{}',
            enabled BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (server_id, name)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_mcp_tools_server_id ON mcp_tools(server_id)")
    op.execute("""
        CREATE TABLE IF NOT EXISTS mcp_server_access (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            server_id UUID NOT NULL REFERENCES mcp_servers(id) ON DELETE CASCADE,
            team_id UUID NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
            granted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (server_id, team_id)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_mcp_access_team ON mcp_server_access(team_id)")

    # ------------------------------------------------------------------
    # Plugin registry (with seeds)
    # ------------------------------------------------------------------
    op.execute("""
        CREATE TABLE IF NOT EXISTS plugins (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name TEXT NOT NULL,
            slug TEXT NOT NULL UNIQUE,
            description TEXT,
            version TEXT NOT NULL DEFAULT '0.1.0',
            author TEXT NOT NULL DEFAULT 'community',
            category TEXT NOT NULL DEFAULT 'tool',
            scopes TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
            homepage_url TEXT,
            icon_url TEXT,
            enabled BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS plugin_team_overrides (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            plugin_id UUID NOT NULL REFERENCES plugins(id) ON DELETE CASCADE,
            team_id UUID NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
            enabled BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (plugin_id, team_id)
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_plugin_team_overrides_team ON plugin_team_overrides(team_id)"
    )
    op.execute("""
        INSERT INTO plugins (name, slug, description, version, author, category, scopes) VALUES
            ('Web Search',       'web-search',       'Search the web using Brave or SerpAPI',                   '1.2.0', 'first-party', 'tool',        ARRAY['internet']),
            ('Code Interpreter', 'code-interpreter', 'Execute Python code in a sandboxed environment',          '2.0.1', 'first-party', 'tool',        ARRAY['compute']),
            ('File Reader',      'file-reader',      'Parse and extract text from PDF, DOCX, and CSV files',    '1.0.3', 'first-party', 'data',        ARRAY['files']),
            ('GitHub',           'github',           'Read repos, issues, PRs and create comments via GitHub',  '1.5.2', 'first-party', 'integration', ARRAY['github']),
            ('Slack',            'slack',            'Send messages and read channel history',                  '1.1.0', 'first-party', 'integration', ARRAY['slack']),
            ('SQL Query',        'sql-query',        'Run read-only SQL queries against configured datasources','0.9.0', 'first-party', 'data',        ARRAY['database']),
            ('PII Detector',     'pii-detector',     'Scan text for personally identifiable information',       '1.0.0', 'first-party', 'security',    ARRAY[]::TEXT[]),
            ('Jira',             'jira',             'Create and update Jira issues from agent workflows',      '1.0.0', 'community',   'integration', ARRAY['jira']),
            ('Confluence',       'confluence',       'Read Confluence pages and spaces',                        '1.0.0', 'community',   'integration', ARRAY['confluence'])
        ON CONFLICT (slug) DO NOTHING
    """)

    # ------------------------------------------------------------------
    # Admin users & org-level settings
    # ------------------------------------------------------------------
    op.execute("""
        CREATE TABLE IF NOT EXISTS admin_users (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            email VARCHAR(255) NOT NULL UNIQUE,
            display_name VARCHAR(255),
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'admin' CHECK (role IN ('superadmin', 'admin', 'viewer')),
            last_login_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_admin_users_email ON admin_users(email)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS org_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("""
        INSERT INTO org_settings (key, value) VALUES
            ('monthly_budget_usd', '0'),
            ('budget_alert_pct', '0.8'),
            ('budget_action', 'alert'),
            ('notification_webhook_url', ''),
            ('semantic_similarity_threshold', '0.85')
        ON CONFLICT (key) DO NOTHING
    """)

    # ------------------------------------------------------------------
    # AI insights (optimization worker output)
    # ------------------------------------------------------------------
    op.execute("""
        CREATE TABLE IF NOT EXISTS ai_insights (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            generated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            category TEXT NOT NULL,
            severity TEXT NOT NULL,
            title TEXT NOT NULL,
            description TEXT NOT NULL,
            action TEXT,
            team_id UUID REFERENCES teams(id) ON DELETE CASCADE,
            team_name TEXT,
            developer_id UUID REFERENCES developers(id) ON DELETE CASCADE,
            dismissed BOOLEAN NOT NULL DEFAULT FALSE,
            auto_applied BOOLEAN NOT NULL DEFAULT FALSE,
            source TEXT NOT NULL DEFAULT 'optimization_worker'
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_ai_insights_generated_at ON ai_insights(generated_at DESC)"
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_ai_insights_team_id ON ai_insights(team_id)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_ai_insights_developer_id ON ai_insights(developer_id)"
    )

    # ------------------------------------------------------------------
    # Guardrails
    # ------------------------------------------------------------------
    op.execute("""
        CREATE TABLE IF NOT EXISTS guardrails (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            team_id UUID REFERENCES teams(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            description TEXT,
            type TEXT NOT NULL,
            applies_to TEXT NOT NULL CHECK (applies_to IN ('input','output','both')),
            action TEXT NOT NULL CHECK (action IN ('block','flag','redact','rewrite','truncate','route')),
            severity TEXT NOT NULL DEFAULT 'high' CHECK (severity IN ('low','medium','high','critical')),
            priority INT NOT NULL DEFAULT 100,
            config JSONB NOT NULL DEFAULT '{}',
            enabled BOOLEAN NOT NULL DEFAULT TRUE,
            version INT NOT NULL DEFAULT 1,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            created_by TEXT NOT NULL DEFAULT 'system',
            updated_by TEXT NOT NULL DEFAULT 'system'
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS guardrails_priority_idx ON guardrails (priority ASC) WHERE enabled = TRUE"
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS guardrails_name_org_uidx ON guardrails (name) WHERE team_id IS NULL"
    )

    op.execute("""
        CREATE TABLE IF NOT EXISTS guardrail_hits (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            guardrail_id UUID NOT NULL REFERENCES guardrails(id) ON DELETE CASCADE,
            guardrail_version INT NOT NULL DEFAULT 1,
            guardrail_type TEXT NOT NULL,
            team_id UUID REFERENCES teams(id) ON DELETE SET NULL,
            api_key_id UUID REFERENCES api_keys(id) ON DELETE SET NULL,
            request_id TEXT,
            model TEXT,
            input_or_output TEXT NOT NULL CHECK (input_or_output IN ('input','output')),
            action_taken TEXT NOT NULL,
            severity TEXT NOT NULL,
            match_count INT NOT NULL DEFAULT 1,
            match_hash TEXT,
            redacted_excerpt TEXT,
            match_offsets JSONB,
            false_positive BOOLEAN,
            reviewed_by TEXT,
            reviewed_at TIMESTAMPTZ
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS guardrail_hits_guardrail_created_idx ON guardrail_hits (guardrail_id, created_at DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS guardrail_hits_team_created_idx ON guardrail_hits (team_id, created_at DESC)"
    )


def downgrade() -> None:
    # Drop in reverse dependency order.
    for tbl in [
        "guardrail_hits",
        "guardrails",
        "ai_insights",
        "org_settings",
        "admin_users",
        "plugin_team_overrides",
        "plugins",
        "mcp_server_access",
        "mcp_tools",
        "mcp_servers",
        "model_registry",
        "model_pricing",
        "audit_log",
        "sessions",
        "developer_output_events",
        "developer_activity_log",
        "cost_records",
        "area_policies",
        "policies",
        "team_members",
        "api_keys",
        "developers",
        "projects",
        "teams",
        "areas",
    ]:
        op.execute(f"DROP TABLE IF EXISTS {tbl} CASCADE")
    op.execute('DROP EXTENSION IF EXISTS "pgcrypto"')
