#!/usr/bin/env python3
"""Bootstrap a local (unmanaged-identity) account with real roles.

Creates/ensures, idempotently:
  1. a `users` row (bcrypt password, hash_type='bcrypt', status 'active');
  2. a `local_groups` row (stable id `lcl-<uuid5(name)>` per group name);
  3. a `local_group_members` row linking the user to the group;
  4. a `role_assignments` row binding the local group → the org node at
     --node-path → --role (the column entra_group_id holds the lcl-... id).

This is the break-glass / first-admin and general local-account provisioning
path. Coexists with Entra SSO. Real bcrypt, real role grants — no dev bypass.

Run locally:
    python services/admin/scripts/create_local_account.py \
        --email admin@simcorp.com --password 'Sup3rSecret!!' --name Admin

Or from the jumpbox:
    az containerapp exec -n ca-admin-... --command \
        "python /app/scripts/create_local_account.py --email ... --password ..."
"""

import argparse
import asyncio
import sys
import uuid
from pathlib import Path

# Allow "from app.xxx import ..." when run as a standalone script.
sys.path.insert(0, str(Path(__file__).parents[1]))

from app.db import async_session_maker
from app.routers.nodes import ensure_root_node
from app.routers.unified_auth import _hash_bcrypt
from sqlalchemy import text


def _local_group_id(name: str) -> str:
    """Stable, namespaced id for a local group keyed by its name."""
    return f"lcl-{uuid.uuid5(uuid.NAMESPACE_DNS, name)}"


async def _resolve_node_id(session, node_path: str) -> str:
    if node_path == "/":
        return (await ensure_root_node(session))["id"]
    row = (
        await session.execute(
            text("SELECT id FROM organization_nodes WHERE path = :path"),
            {"path": node_path},
        )
    ).first()
    if not row:
        raise SystemExit(f"No organization node found at path {node_path!r}")
    return str(row[0])


async def run(email: str, password: str, name: str, role: str, group: str, node_path: str) -> None:
    email = email.lower().strip()
    group_id = _local_group_id(group)

    async with async_session_maker() as session:
        # 1. ensure user (bcrypt, active)
        existing = (
            await session.execute(
                text("SELECT id FROM users WHERE email = :email"),
                {"email": email},
            )
        ).first()
        if existing:
            user_id = str(existing[0])
            await session.execute(
                text("""
                    UPDATE users
                    SET password_hash = :h, hash_type = 'bcrypt', status = 'active',
                        display_name = COALESCE(NULLIF(:dn, ''), display_name), updated_at = NOW()
                    WHERE id = CAST(:id AS uuid)
                """),
                {"h": _hash_bcrypt(password), "dn": name, "id": user_id},
            )
            print(f"  user exists, updated: {email} ({user_id})")
        else:
            user_id = str(uuid.uuid4())
            await session.execute(
                text("""
                    INSERT INTO users (id, email, display_name, password_hash, hash_type, status)
                    VALUES (CAST(:id AS uuid), :email, :dn, :h, 'bcrypt', 'active')
                """),
                {"id": user_id, "email": email, "dn": name, "h": _hash_bcrypt(password)},
            )
            print(f"  created user: {email} ({user_id})")

        # 2. ensure local group
        await session.execute(
            text("""
                INSERT INTO local_groups (id, name) VALUES (:id, :name)
                ON CONFLICT (id) DO NOTHING
            """),
            {"id": group_id, "name": group},
        )
        print(f"  ensured local group: {group} ({group_id})")

        # 3. ensure membership
        await session.execute(
            text("""
                INSERT INTO local_group_members (group_id, user_id)
                VALUES (:gid, CAST(:uid AS uuid))
                ON CONFLICT (group_id, user_id) DO NOTHING
            """),
            {"gid": group_id, "uid": user_id},
        )
        print("  ensured group membership")

        # 4. ensure role_assignments row binding group → node → role
        node_id = await _resolve_node_id(session, node_path)
        await session.execute(
            text("""
                INSERT INTO role_assignments (entra_group_id, entra_group_name, role, node_id)
                VALUES (:gid, :gname, :role, CAST(:nid AS uuid))
                ON CONFLICT (entra_group_id, role, node_id) DO NOTHING
            """),
            {"gid": group_id, "gname": group, "role": role, "nid": node_id},
        )
        print(f"  ensured role assignment: {group} → {node_path} → {role} (node {node_id})")

        await session.commit()
    print("Done.")


def main() -> None:
    p = argparse.ArgumentParser(description="Create/ensure a local account with roles.")
    p.add_argument("--email", required=True)
    p.add_argument("--password", required=True)
    p.add_argument("--name", default="")
    p.add_argument("--role", default="platform_admin")
    p.add_argument("--group", default="platform-admins")
    p.add_argument("--node-path", default="/")
    args = p.parse_args()
    asyncio.run(run(args.email, args.password, args.name, args.role, args.group, args.node_path))


if __name__ == "__main__":
    main()
