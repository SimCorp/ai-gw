#!/usr/bin/env python3
"""Internal end-to-end verification for the AI Gateway (run from inside the VNet).

Designed to be piped to a container that has BOTH database access and internal
network reach — i.e. the admin container:

    cat scripts/verify_internal_access.py | az containerapp exec \
        -n ca-admin-dev-sdc -g rg-aigw-dev-sdc --command "python3 -"

It proves, through the Caddy front-door (ca-gateway-<env>-sdc), that:
  1. Browser access  — GET /portal/ returns 200 (developer portal renders).
  2. Agent access    — an sk-* key drives /v1/chat/completions to a 200 Claude
                       completion, and the identical 2nd call is served from the
                       semantic/exact cache (x-cache: hit).

The test sk-* key + its team are minted directly in the DB (no Entra / login
dependency), mirroring how a service account would be provisioned, then revoked
at the end so nothing is left behind.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import secrets
import sys
import urllib.error
import urllib.request

sys.path.insert(0, "/app")

from app.db import async_session_maker  # noqa: E402
from sqlalchemy import text  # noqa: E402

ENV = os.environ.get("ENV_SUFFIX", "dev-sdc").replace("dev-sdc", "dev")
GW = os.environ.get("GATEWAY_URL", "http://ca-gateway-dev-sdc")

_fail = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global _fail
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""), flush=True)
    if not ok:
        _fail += 1


def http(method: str, url: str, headers: dict | None = None, body: dict | None = None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers=dict(headers or {}))
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, {k.lower(): v for k, v in r.headers.items()}, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, {k.lower(): v for k, v in e.headers.items()}, e.read().decode()
    except Exception as e:  # noqa: BLE001
        return 0, {}, f"{type(e).__name__}: {e}"


async def mint_key() -> tuple[str, str]:
    raw = "sk-" + secrets.token_urlsafe(32)
    key_hash = hashlib.sha256(raw.encode()).hexdigest()
    async with async_session_maker() as s:
        # auth validates an inference key purely by key_hash + revoked_at IS NULL
        # (services/auth/app/validators/api_key.py); node_id/team is optional, so
        # this stays decoupled from the org-node model. node_id defaults to NULL.
        await s.execute(
            text(
                "INSERT INTO api_keys (name, key_hash, scopes) "
                "VALUES ('verify-key', :h, ARRAY['ai-gw:inference:*'])"
            ),
            {"h": key_hash},
        )
        await s.commit()
    return raw, key_hash


async def revoke_key(key_hash: str) -> None:
    async with async_session_maker() as s:
        await s.execute(
            text("UPDATE api_keys SET revoked_at = NOW() WHERE key_hash = :h"), {"h": key_hash}
        )
        await s.commit()


async def main() -> int:
    # Browser access through the front-door.
    sc, _, _ = http("GET", f"{GW}/portal/")
    check("browser: GET /portal/ -> 200", sc == 200, f"status {sc}")

    # Mint a real sk-* key and drive the agent inference path twice.
    raw, key_hash = await mint_key()
    check("agent: sk-* key minted", raw.startswith("sk-"), raw[:6] + "…")
    hdr = {"Authorization": f"Bearer {raw}"}
    payload = {
        "model": "claude-haiku-4-5",
        "messages": [{"role": "user", "content": "Reply with the single word: pong."}],
        "max_tokens": 16,
    }
    try:
        s1, _, b1 = http("POST", f"{GW}/v1/chat/completions", hdr, payload)
        check("agent: inference #1 -> 200", s1 == 200, f"status {s1} {b1[:160]}")
        s2, h2, _ = http("POST", f"{GW}/v1/chat/completions", hdr, payload)
        check("agent: inference #2 -> 200", s2 == 200, f"status {s2}")
        xc = h2.get("x-cache", "")
        check("agent: cache hit on identical 2nd call", "hit" in xc.lower(), f"x-cache={xc!r}")
    finally:
        await revoke_key(key_hash)
        print("  (verify-key revoked)", flush=True)

    print("\n" + ("INTERNAL VERIFICATION PASSED" if _fail == 0 else f"FAILED: {_fail} check(s)"))
    return 1 if _fail else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
