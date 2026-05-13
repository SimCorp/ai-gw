"""Unified user identity: merge admin_users + developers into users with RBAC roles

All existing UUIDs are preserved so every foreign key (developer_id columns on
cost_records, sessions, developer_achievements, etc.) keeps pointing correctly.

Revision ID: 0010
Revises: 0009
Create Date: 2026-05-13
"""
from __future__ import annotations
from typing import Sequence, Union
from alembic import op

revision: str = "0010"
down_revision: Union[str, None] = "0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1. Unified users table
    # ------------------------------------------------------------------
    op.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            email               VARCHAR(255) NOT NULL UNIQUE,
            display_name        VARCHAR(255) NOT NULL DEFAULT '',
            password_hash       TEXT NOT NULL,
            hash_type           TEXT NOT NULL DEFAULT 'bcrypt'
                                    CHECK (hash_type IN ('bcrypt', 'pbkdf2')),
            status              TEXT NOT NULL DEFAULT 'active'
                                    CHECK (status IN ('active', 'pending', 'suspended')),
            must_change_password BOOLEAN NOT NULL DEFAULT FALSE,
            primary_team_id     UUID REFERENCES teams(id) ON DELETE SET NULL,
            last_login_at       TIMESTAMPTZ,
            created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_users_status ON users(status)")

    # ------------------------------------------------------------------
    # 2. Scoped roles table
    # ------------------------------------------------------------------
    op.execute("""
        CREATE TABLE IF NOT EXISTS user_roles (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            role        TEXT NOT NULL CHECK (role IN (
                            'platform_admin', 'area_owner', 'team_admin',
                            'developer', 'viewer', 'service_account')),
            scope_type  TEXT NOT NULL DEFAULT 'global'
                            CHECK (scope_type IN ('global', 'area', 'team')),
            scope_id    UUID,
            granted_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            granted_by  UUID REFERENCES users(id) ON DELETE SET NULL
        )
    """)
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_user_roles_unique
        ON user_roles (user_id, role, scope_type, COALESCE(scope_id, '00000000-0000-0000-0000-000000000000'::uuid))
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_user_roles_user ON user_roles(user_id)")

    # ------------------------------------------------------------------
    # 3. Migrate developers → users (same UUIDs — all FKs stay valid)
    # ------------------------------------------------------------------
    op.execute("""
        INSERT INTO users (id, email, display_name, password_hash, hash_type,
                           status, must_change_password, primary_team_id,
                           created_at, updated_at)
        SELECT
            d.id,
            d.email,
            COALESCE(d.display_name, ''),
            d.password_hash,
            'pbkdf2',
            COALESCE(d.status, 'active'),
            COALESCE(d.must_change_password, FALSE),
            d.team_id,
            d.created_at,
            d.updated_at
        FROM developers d
        ON CONFLICT (email) DO NOTHING
    """)
    op.execute("""
        INSERT INTO user_roles (user_id, role, scope_type)
        SELECT d.id, 'developer', 'global'
        FROM developers d
        WHERE EXISTS (SELECT 1 FROM users u WHERE u.id = d.id)
        ON CONFLICT DO NOTHING
    """)

    # ------------------------------------------------------------------
    # 4. Migrate admin_users → users
    #    Map legacy roles: superadmin → platform_admin, admin → platform_admin, viewer → viewer
    # ------------------------------------------------------------------
    op.execute("""
        INSERT INTO users (id, email, display_name, password_hash, hash_type,
                           status, must_change_password, last_login_at,
                           created_at, updated_at)
        SELECT
            a.id,
            a.email,
            COALESCE(a.display_name, ''),
            a.password_hash,
            'bcrypt',
            'active',
            COALESCE(a.must_change_password, FALSE),
            a.last_login_at,
            a.created_at,
            a.updated_at
        FROM admin_users a
        ON CONFLICT (email) DO UPDATE
            SET display_name        = EXCLUDED.display_name,
                hash_type           = EXCLUDED.hash_type,
                must_change_password = EXCLUDED.must_change_password,
                last_login_at       = EXCLUDED.last_login_at
    """)
    op.execute("""
        INSERT INTO user_roles (user_id, role, scope_type)
        SELECT
            u.id,
            CASE a.role
                WHEN 'viewer' THEN 'viewer'
                ELSE 'platform_admin'
            END,
            'global'
        FROM admin_users a
        JOIN users u ON u.email = a.email
        ON CONFLICT DO NOTHING
    """)

    # ------------------------------------------------------------------
    # 5. Add user_id FK to team_members (keep developer_id for now)
    # ------------------------------------------------------------------
    op.execute("""
        ALTER TABLE team_members
        ADD COLUMN IF NOT EXISTS user_id UUID REFERENCES users(id) ON DELETE CASCADE
    """)
    op.execute("""
        UPDATE team_members tm
        SET user_id = tm.developer_id
        WHERE tm.developer_id IS NOT NULL
          AND EXISTS (SELECT 1 FROM users u WHERE u.id = tm.developer_id)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_team_members_user_id
        ON team_members(user_id)
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE team_members DROP COLUMN IF EXISTS user_id")
    op.execute("DROP TABLE IF EXISTS user_roles")
    op.execute("DROP TABLE IF EXISTS users")
