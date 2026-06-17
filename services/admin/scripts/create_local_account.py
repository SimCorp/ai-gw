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
import os
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


async def run(
    email: str,
    password: str,
    name: str,
    role: str,
    group: str,
    node_path: str,
    *,
    reactivate: bool = False,
    force: bool = False,
) -> None:
    email = email.lower().strip()
    group_id = _local_group_id(group)

    async with async_session_maker() as session:
        # 1. ensure user (bcrypt, active)
        existing = (
            await session.execute(
                text("SELECT id, status FROM users WHERE email = :email"),
                {"email": email},
            )
        ).first()
        if existing:
            user_id = str(existing[0])
            cur_status = existing[1]
            # Guard against account takeover: an existing account with no local-group
            # membership is likely SSO/Entra-managed — refuse to overwrite its
            # password unless explicitly forced.
            is_local = (
                await session.execute(
                    text(
                        "SELECT 1 FROM local_group_members WHERE user_id = CAST(:id AS uuid) LIMIT 1"
                    ),
                    {"id": user_id},
                )
            ).first() is not None
            if not is_local and not force:
                raise SystemExit(
                    f"Refusing to overwrite existing non-local account {email!r} "
                    "(no local-group membership — likely SSO-managed). Re-run with "
                    "--force to take it over as a local account."
                )
            # Don't silently reactivate a suspended/offboarded account.
            if cur_status != "active" and not reactivate:
                raise SystemExit(
                    f"Account {email!r} has status {cur_status!r}; re-run with "
                    "--reactivate to set it active."
                )
            new_status = "active" if (reactivate or cur_status == "active") else cur_status
            await session.execute(
                text("""
                    UPDATE users
                    SET password_hash = :h, hash_type = 'bcrypt', status = :st,
                        display_name = COALESCE(NULLIF(:dn, ''), display_name), updated_at = NOW()
                    WHERE id = CAST(:id AS uuid)
                """),
                {"h": _hash_bcrypt(password), "dn": name, "id": user_id, "st": new_status},
            )
            print(f"  user exists, updated: {email} ({user_id}) status={new_status}")
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
    # Avoid passing the password in argv (visible in ps/exec logs). Prefer the
    # LOCAL_ACCOUNT_PASSWORD env var or --password-stdin.
    p.add_argument("--password", default=None)
    p.add_argument("--password-stdin", action="store_true", help="read the password from stdin")
    p.add_argument("--name", default="")
    p.add_argument("--role", default="platform_admin")
    p.add_argument("--group", default="platform-admins")
    p.add_argument("--node-path", default="/")
    p.add_argument(
        "--reactivate", action="store_true", help="allow activating a non-active account"
    )
    p.add_argument("--force", action="store_true", help="allow taking over a non-local account")
    args = p.parse_args()

    password = args.password or os.environ.get("LOCAL_ACCOUNT_PASSWORD")
    if args.password_stdin:
        password = sys.stdin.readline().rstrip("\n")
    if not password:
        p.error("provide a password via LOCAL_ACCOUNT_PASSWORD, --password-stdin, or --password")

    asyncio.run(
        run(
            args.email,
            password,
            args.name,
            args.role,
            args.group,
            args.node_path,
            reactivate=args.reactivate,
            force=args.force,
        )
    )


if __name__ == "__main__":
    main()
