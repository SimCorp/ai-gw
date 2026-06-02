"""Organization nodes — unified tree model replacing areas/units/teams

Revision ID: 0025
Revises: 0024
Create Date: 2026-05-28

This is a clean-break migration. All data in areas, units, teams,
user_roles, and entra_group_role_mappings is dropped.

Tables migrated to use node_id → organization_nodes:
  cost_records, api_keys, team_members (→ node_members), users,
  policies, access_requests

Tables that had FK to teams but are out of scope for this migration
(FK is dropped, column kept as orphaned nullable data):
  mcp_server_access, plugin_team_overrides, service_accounts,
  developers, ai_insights, guardrails, guardrail_hits,
  workflows, workflow_runs, projects
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0025"
down_revision: Union[str, None] = "0024"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ------------------------------------------------------------------ #
    # 1. Create organization_nodes                                         #
    # ------------------------------------------------------------------ #
    op.execute("""
        CREATE TABLE IF NOT EXISTS organization_nodes (
            id                     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name                   TEXT NOT NULL,
            slug                   TEXT NOT NULL,
            type                   TEXT NOT NULL DEFAULT 'team',
            parent_id              UUID REFERENCES organization_nodes(id) ON DELETE CASCADE,
            path                   TEXT NOT NULL UNIQUE,
            color                  TEXT,
            description            TEXT,
            location               TEXT,
            monthly_budget_usd     NUMERIC(12,2),
            budget_alert_threshold NUMERIC(4,2) DEFAULT 0.80,
            created_at             TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE(parent_id, slug)
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_nodes_path ON organization_nodes USING btree (path text_pattern_ops)"
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_nodes_parent_id ON organization_nodes(parent_id)")

    # ------------------------------------------------------------------ #
    # 2. Create role_assignments                                           #
    # ------------------------------------------------------------------ #
    op.execute("""
        CREATE TABLE IF NOT EXISTS role_assignments (
            id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            entra_group_id   TEXT NOT NULL,
            entra_group_name TEXT,
            role             TEXT NOT NULL CHECK (role IN (
                                 'platform_admin','area_owner','unit_lead',
                                 'team_admin','developer','viewer')),
            node_id          UUID NOT NULL REFERENCES organization_nodes(id) ON DELETE CASCADE,
            granted_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            granted_by       UUID REFERENCES users(id) ON DELETE SET NULL,
            UNIQUE(entra_group_id, role, node_id)
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_role_assignments_group ON role_assignments(entra_group_id)"
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_role_assignments_node ON role_assignments(node_id)")

    # ------------------------------------------------------------------ #
    # 3. Drop area_policies (absorbed into nodes policy model)            #
    # ------------------------------------------------------------------ #
    op.execute("DROP TABLE IF EXISTS area_policies")

    # ------------------------------------------------------------------ #
    # 4. Drop user_roles and entra_group_role_mappings                    #
    #    (replaced by role_assignments)                                   #
    # ------------------------------------------------------------------ #
    op.execute("DROP TABLE IF EXISTS user_roles CASCADE")
    op.execute("DROP TABLE IF EXISTS entra_group_role_mappings CASCADE")

    # ------------------------------------------------------------------ #
    # 5. cost_records: team_id → node_id (FK to organization_nodes)      #
    # ------------------------------------------------------------------ #
    op.execute("ALTER TABLE cost_records DROP CONSTRAINT IF EXISTS cost_records_team_id_fkey")
    op.execute("ALTER TABLE cost_records RENAME COLUMN team_id TO node_id")
    op.execute("""
        ALTER TABLE cost_records
        ADD CONSTRAINT cost_records_node_id_fkey
        FOREIGN KEY (node_id) REFERENCES organization_nodes(id)
        ON DELETE SET NULL
        NOT VALID
    """)
    op.execute("ALTER TABLE cost_records ALTER COLUMN node_id DROP NOT NULL")
    # Update index name
    op.execute("DROP INDEX IF EXISTS cost_records_team_id_created_at_idx")
    op.execute(
        "CREATE INDEX IF NOT EXISTS cost_records_node_id_created_at_idx ON cost_records(node_id, created_at DESC)"
    )

    # ------------------------------------------------------------------ #
    # 6. api_keys: team_id → node_id                                     #
    # ------------------------------------------------------------------ #
    op.execute("ALTER TABLE api_keys DROP CONSTRAINT IF EXISTS api_keys_team_id_fkey")
    op.execute("ALTER TABLE api_keys RENAME COLUMN team_id TO node_id")
    op.execute("""
        ALTER TABLE api_keys
        ADD CONSTRAINT api_keys_node_id_fkey
        FOREIGN KEY (node_id) REFERENCES organization_nodes(id)
        ON DELETE SET NULL
        NOT VALID
    """)
    op.execute("ALTER TABLE api_keys ALTER COLUMN node_id DROP NOT NULL")

    # ------------------------------------------------------------------ #
    # 7. team_members → node_members, team_id → node_id                  #
    # ------------------------------------------------------------------ #
    op.execute("ALTER TABLE team_members DROP CONSTRAINT IF EXISTS team_members_team_id_fkey")
    # Drop the unique constraint that references team_id before renaming
    op.execute(
        "ALTER TABLE team_members DROP CONSTRAINT IF EXISTS team_members_team_id_user_id_key"
    )
    op.execute("ALTER TABLE team_members RENAME COLUMN team_id TO node_id")
    op.execute("ALTER TABLE team_members RENAME TO node_members")
    op.execute("""
        ALTER TABLE node_members
        ADD CONSTRAINT node_members_node_id_fkey
        FOREIGN KEY (node_id) REFERENCES organization_nodes(id)
        ON DELETE CASCADE
        NOT VALID
    """)
    op.execute("""
        ALTER TABLE node_members
        ADD CONSTRAINT node_members_node_id_user_id_key
        UNIQUE (node_id, user_id)
    """)
    # Update index
    op.execute("DROP INDEX IF EXISTS team_members_team_id_idx")
    op.execute("CREATE INDEX IF NOT EXISTS node_members_node_id_idx ON node_members(node_id)")

    # ------------------------------------------------------------------ #
    # 8. users: primary_team_id → primary_node_id                        #
    # ------------------------------------------------------------------ #
    op.execute("ALTER TABLE users DROP CONSTRAINT IF EXISTS users_primary_team_id_fkey")
    op.execute("ALTER TABLE users RENAME COLUMN primary_team_id TO primary_node_id")
    op.execute("""
        ALTER TABLE users
        ADD CONSTRAINT users_primary_node_id_fkey
        FOREIGN KEY (primary_node_id) REFERENCES organization_nodes(id)
        ON DELETE SET NULL
        NOT VALID
    """)

    # ------------------------------------------------------------------ #
    # 9. policies: team_id → node_id                                     #
    # ------------------------------------------------------------------ #
    op.execute("ALTER TABLE policies DROP CONSTRAINT IF EXISTS policies_team_id_fkey")
    # Drop old partial unique indexes
    op.execute("DROP INDEX IF EXISTS policies_team_null_proj_uidx")
    op.execute("DROP INDEX IF EXISTS policies_team_proj_uidx")
    op.execute("ALTER TABLE policies RENAME COLUMN team_id TO node_id")
    op.execute("""
        ALTER TABLE policies
        ADD CONSTRAINT policies_node_id_fkey
        FOREIGN KEY (node_id) REFERENCES organization_nodes(id)
        ON DELETE CASCADE
        NOT VALID
    """)
    # Recreate partial unique indexes with new column name
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS policies_node_null_proj_uidx
        ON policies (node_id) WHERE project_id IS NULL
    """)
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS policies_node_proj_uidx
        ON policies (node_id, project_id) WHERE project_id IS NOT NULL
    """)

    # ------------------------------------------------------------------ #
    # 10. access_requests: drop resource_id, add node_id UUID FK         #
    # ------------------------------------------------------------------ #
    op.execute("ALTER TABLE access_requests DROP COLUMN IF EXISTS resource_id")
    op.execute("ALTER TABLE access_requests ADD COLUMN IF NOT EXISTS node_id UUID")
    op.execute("""
        ALTER TABLE access_requests
        ADD CONSTRAINT access_requests_node_id_fkey
        FOREIGN KEY (node_id) REFERENCES organization_nodes(id)
        ON DELETE SET NULL
        NOT VALID
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_access_requests_node ON access_requests(node_id)")

    # ------------------------------------------------------------------ #
    # 11. Drop FKs on out-of-scope tables so teams/areas can be dropped  #
    # ------------------------------------------------------------------ #

    # projects.team_id
    op.execute("ALTER TABLE projects DROP CONSTRAINT IF EXISTS projects_team_id_fkey")
    op.execute("ALTER TABLE projects ALTER COLUMN team_id DROP NOT NULL")

    # service_accounts.team_id
    op.execute(
        "ALTER TABLE service_accounts DROP CONSTRAINT IF EXISTS service_accounts_team_id_fkey"
    )

    # developers.team_id
    op.execute("ALTER TABLE developers DROP CONSTRAINT IF EXISTS developers_team_id_fkey")

    # ai_insights.team_id
    op.execute("ALTER TABLE ai_insights DROP CONSTRAINT IF EXISTS ai_insights_team_id_fkey")

    # guardrails.team_id
    op.execute("ALTER TABLE guardrails DROP CONSTRAINT IF EXISTS guardrails_team_id_fkey")

    # guardrail_hits.team_id
    op.execute("ALTER TABLE guardrail_hits DROP CONSTRAINT IF EXISTS guardrail_hits_team_id_fkey")

    # workflows: team_id FK and owner_team_id FK (agents)
    op.execute("ALTER TABLE workflows DROP CONSTRAINT IF EXISTS workflows_team_id_fkey")
    op.execute("ALTER TABLE agents DROP CONSTRAINT IF EXISTS agents_owner_team_id_fkey")

    # workflow_runs.team_id
    op.execute("ALTER TABLE workflow_runs DROP CONSTRAINT IF EXISTS workflow_runs_team_id_fkey")

    # mcp_server_access.team_id
    op.execute(
        "ALTER TABLE mcp_server_access DROP CONSTRAINT IF EXISTS mcp_server_access_team_id_fkey"
    )

    # plugin_team_overrides.team_id
    op.execute(
        "ALTER TABLE plugin_team_overrides DROP CONSTRAINT IF EXISTS plugin_team_overrides_team_id_fkey"
    )

    # access_grants.grantor_team_id and grantee_team_id
    op.execute(
        "ALTER TABLE access_grants DROP CONSTRAINT IF EXISTS access_grants_grantor_team_id_fkey"
    )
    op.execute(
        "ALTER TABLE access_grants DROP CONSTRAINT IF EXISTS access_grants_grantee_team_id_fkey"
    )

    # scan_jobs.team_id and scan_targets.team_id (only present on legacy DBs where
    # the scanner migration ran before this one; on a fresh chain the scanner
    # tables are created later by 0026 already using node_id, so guard the drops).
    op.execute("""
        DO $$ BEGIN
            IF to_regclass('public.scan_jobs') IS NOT NULL THEN
                ALTER TABLE scan_jobs DROP CONSTRAINT IF EXISTS scan_jobs_team_id_fkey;
            END IF;
            IF to_regclass('public.scan_targets') IS NOT NULL THEN
                ALTER TABLE scan_targets DROP CONSTRAINT IF EXISTS scan_targets_team_id_fkey;
            END IF;
        END $$;
    """)

    # teams.unit_id (teams refs units — must drop before dropping units)
    op.execute("ALTER TABLE teams DROP CONSTRAINT IF EXISTS teams_unit_id_fkey")

    # teams.area_id (teams refs areas — must drop before dropping areas)
    op.execute("ALTER TABLE teams DROP CONSTRAINT IF EXISTS teams_area_id_fkey")

    # units.parent_unit_id (self-reference added in migration 0013)
    op.execute("ALTER TABLE units DROP CONSTRAINT IF EXISTS units_parent_unit_id_fkey")

    # units.area_id
    op.execute("ALTER TABLE units DROP CONSTRAINT IF EXISTS units_area_id_fkey")

    # access_grants has two FKs to teams
    op.execute(
        "ALTER TABLE access_grants DROP CONSTRAINT IF EXISTS access_grants_grantee_team_id_fkey"
    )
    op.execute(
        "ALTER TABLE access_grants DROP CONSTRAINT IF EXISTS access_grants_grantor_team_id_fkey"
    )

    # ------------------------------------------------------------------ #
    # 12. Drop units, teams, areas (CASCADE catches any remaining FKs)   #
    # ------------------------------------------------------------------ #
    op.execute("DROP TABLE IF EXISTS units CASCADE")
    op.execute("DROP TABLE IF EXISTS teams CASCADE")
    op.execute("DROP TABLE IF EXISTS areas CASCADE")


def downgrade() -> None:
    # Downgrade not supported — this is a clean-break migration.
    # To restore, replay from 0001 against a clean database.
    raise NotImplementedError("Downgrade not supported for clean-break migration 0025")
