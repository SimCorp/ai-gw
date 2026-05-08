CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE TABLE IF NOT EXISTS teams (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    slug TEXT NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS projects (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    team_id UUID NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    slug TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (team_id, slug)
);

CREATE TABLE IF NOT EXISTS api_keys (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    team_id UUID NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    project_id UUID REFERENCES projects(id) ON DELETE SET NULL,
    name TEXT NOT NULL,
    key_hash TEXT NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    revoked_at TIMESTAMPTZ
);

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
);

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
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS cost_records_team_id_created_at_idx ON cost_records (team_id, created_at DESC);

CREATE TABLE IF NOT EXISTS model_pricing (
    model_prefix TEXT PRIMARY KEY,
    price_input_per_1k  NUMERIC(12,8) NOT NULL DEFAULT 0,
    price_output_per_1k NUMERIC(12,8) NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO model_pricing (model_prefix, price_input_per_1k, price_output_per_1k) VALUES
    ('claude-opus-4-7',    0.015,    0.075),
    ('claude-sonnet-4-6',  0.003,    0.015),
    ('claude-haiku-4-5',   0.0008,   0.004),
    ('gpt-4o-mini',        0.00015,  0.0006),
    ('gpt-4o',             0.0025,   0.01),
    ('gemini-1.5-flash',   0.000075, 0.0003),
    ('gemini-1.5-pro',     0.00125,  0.005)
ON CONFLICT (model_prefix) DO NOTHING;

CREATE TABLE IF NOT EXISTS team_members (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    team_id UUID NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    user_id TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'member' CHECK (role IN ('admin', 'member')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (team_id, user_id)
);

CREATE INDEX IF NOT EXISTS team_members_team_id_idx ON team_members (team_id);

CREATE TABLE IF NOT EXISTS audit_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    actor TEXT NOT NULL DEFAULT 'unknown',
    action TEXT NOT NULL,
    resource_type TEXT NOT NULL,
    resource_id TEXT,
    details JSONB
);

CREATE INDEX IF NOT EXISTS audit_log_timestamp_idx ON audit_log (timestamp DESC);
CREATE INDEX IF NOT EXISTS audit_log_resource_idx ON audit_log (resource_type, resource_id);

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
);

CREATE INDEX IF NOT EXISTS idx_developers_email  ON developers(email);
CREATE INDEX IF NOT EXISTS idx_developers_status ON developers(status);
CREATE INDEX IF NOT EXISTS idx_developers_team   ON developers(team_id);

ALTER TABLE api_keys ADD COLUMN IF NOT EXISTS developer_id UUID REFERENCES developers(id) ON DELETE SET NULL;
ALTER TABLE api_keys ADD COLUMN IF NOT EXISTS last_used_at TIMESTAMPTZ;
CREATE INDEX IF NOT EXISTS idx_api_keys_developer ON api_keys(developer_id);

-- Budget fields on teams
ALTER TABLE teams ADD COLUMN IF NOT EXISTS monthly_budget_usd NUMERIC(12,4);
ALTER TABLE teams ADD COLUMN IF NOT EXISTS budget_alert_pct FLOAT NOT NULL DEFAULT 0.8;
ALTER TABLE teams ADD COLUMN IF NOT EXISTS budget_action TEXT NOT NULL DEFAULT 'alert';

-- Per-key budget cap
ALTER TABLE api_keys ADD COLUMN IF NOT EXISTS monthly_budget_usd NUMERIC(12,4);

-- Track which key was used on each cost record (for per-key spend rollup)
ALTER TABLE cost_records ADD COLUMN IF NOT EXISTS api_key_id UUID REFERENCES api_keys(id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS idx_cost_records_api_key_id ON cost_records(api_key_id, created_at DESC);

-- Link team_members to developers
ALTER TABLE team_members ADD COLUMN IF NOT EXISTS developer_id UUID REFERENCES developers(id) ON DELETE CASCADE;
CREATE INDEX IF NOT EXISTS idx_team_members_developer_id ON team_members(developer_id);

-- Org-level global budget ceiling
CREATE TABLE IF NOT EXISTS org_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
INSERT INTO org_settings (key, value) VALUES
    ('monthly_budget_usd', '0'),
    ('budget_alert_pct', '0.8'),
    ('budget_action', 'alert')
ON CONFLICT (key) DO NOTHING;

CREATE TABLE IF NOT EXISTS model_registry (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    model_id TEXT NOT NULL UNIQUE,
    provider TEXT NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO model_registry (name, model_id, provider) VALUES
    ('Claude Opus 4.7',     'claude-opus-4-7',       'anthropic'),
    ('Claude Sonnet 4.6',   'claude-sonnet-4-6',     'anthropic'),
    ('Claude Haiku 4.5',    'claude-haiku-4-5',      'anthropic'),
    ('GPT-4o',              'gpt-4o',                'openai'),
    ('GPT-4o Mini',         'gpt-4o-mini',           'openai'),
    ('Gemini 1.5 Pro',      'gemini-1.5-pro',        'google'),
    ('Gemini 1.5 Flash',    'gemini-1.5-flash',      'google')
ON CONFLICT (model_id) DO NOTHING;

-- MCP Server Registry
CREATE TABLE IF NOT EXISTS mcp_servers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    description TEXT,
    url TEXT NOT NULL,
    auth_type TEXT NOT NULL DEFAULT 'none', -- none | bearer | api_key
    auth_header TEXT,                        -- header name when auth_type = api_key
    auth_secret TEXT,                        -- stored secret (bearer token or api key value)
    status TEXT NOT NULL DEFAULT 'pending',  -- pending | active | error | disabled
    last_ping_at TIMESTAMPTZ,
    last_ping_ms INT,
    last_error TEXT,
    tool_count INT NOT NULL DEFAULT 0,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (url)
);

CREATE TABLE IF NOT EXISTS mcp_tools (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    server_id UUID NOT NULL REFERENCES mcp_servers(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    description TEXT,
    input_schema JSONB NOT NULL DEFAULT '{}',
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (server_id, name)
);

CREATE INDEX IF NOT EXISTS idx_mcp_tools_server_id ON mcp_tools(server_id);

CREATE TABLE IF NOT EXISTS mcp_server_access (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    server_id UUID NOT NULL REFERENCES mcp_servers(id) ON DELETE CASCADE,
    team_id UUID NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    granted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (server_id, team_id)
);

CREATE INDEX IF NOT EXISTS idx_mcp_access_team ON mcp_server_access(team_id);

-- Plugin Registry
CREATE TABLE IF NOT EXISTS plugins (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    slug TEXT NOT NULL UNIQUE,
    description TEXT,
    version TEXT NOT NULL DEFAULT '0.1.0',
    author TEXT NOT NULL DEFAULT 'community',
    category TEXT NOT NULL DEFAULT 'tool',   -- tool | integration | data | security | workflow
    scopes TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    homepage_url TEXT,
    icon_url TEXT,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS plugin_team_overrides (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    plugin_id UUID NOT NULL REFERENCES plugins(id) ON DELETE CASCADE,
    team_id UUID NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (plugin_id, team_id)
);

CREATE INDEX IF NOT EXISTS idx_plugin_team_overrides_team ON plugin_team_overrides(team_id);

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
ON CONFLICT (slug) DO NOTHING;

-- ============================================================
-- Admin portal users (separate from developer portal users)
-- ============================================================
CREATE TABLE IF NOT EXISTS admin_users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) NOT NULL UNIQUE,
    display_name VARCHAR(255),
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'admin' CHECK (role IN ('superadmin', 'admin', 'viewer')),
    last_login_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_admin_users_email ON admin_users(email);

-- Seed a default admin (password: Admin1234! — must be changed)
-- bcrypt hash of "Admin1234!" with 12 rounds
INSERT INTO admin_users (email, display_name, password_hash, role) VALUES
    ('admin@simcorp.com', 'Default Admin', '$2b$12$GwGtCW6GNoGJlD5lhF8xLeZPEZO8W5eDXr6TO7u3zm3SiHe1uZK3S', 'superadmin')
ON CONFLICT (email) DO NOTHING;
