CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE TABLE teams (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    slug TEXT NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE projects (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    team_id UUID NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    slug TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (team_id, slug)
);

CREATE TABLE api_keys (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    team_id UUID NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    project_id UUID REFERENCES projects(id) ON DELETE SET NULL,
    name TEXT NOT NULL,
    key_hash TEXT NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    revoked_at TIMESTAMPTZ
);

CREATE TABLE policies (
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

CREATE TABLE cost_records (
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

CREATE INDEX ON cost_records (team_id, created_at DESC);

CREATE TABLE model_pricing (
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
    ('gemini-1.5-pro',     0.00125,  0.005);

-- Team membership with roles
CREATE TABLE team_members (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    team_id UUID NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    user_id TEXT NOT NULL,  -- Entra OID or similar identity
    role TEXT NOT NULL DEFAULT 'member' CHECK (role IN ('admin', 'member')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (team_id, user_id)
);

CREATE INDEX ON team_members (team_id);

-- Audit log for all admin mutations
CREATE TABLE audit_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    actor TEXT NOT NULL DEFAULT 'unknown',
    action TEXT NOT NULL,
    resource_type TEXT NOT NULL,
    resource_id TEXT,
    details JSONB
);

CREATE INDEX ON audit_log (timestamp DESC);
CREATE INDEX ON audit_log (resource_type, resource_id);

-- Global model registry — superset of all available models
CREATE TABLE model_registry (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,           -- display name
    model_id TEXT NOT NULL UNIQUE, -- LiteLLM identifier
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
    ('Gemini 1.5 Flash',    'gemini-1.5-flash',      'google');
