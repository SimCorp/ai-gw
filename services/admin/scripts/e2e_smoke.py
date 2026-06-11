#!/usr/bin/env python3
"""End-to-end smoke test for the deployed AI Gateway.

Validates the testable surface that does NOT depend on the pending Entra
app-registration — run it from inside the VNet (the jumpbox `ca-toolbox-*`
or a VNet-connected self-hosted runner), since the ACA environment is
`internal: true`.

What it checks (each failure exits non-zero):
  1. Service health — auth, cache, admin.
  2. Local-account login (UNMANAGED identity) → returns a session token and a
     `platform_admin` role. This is the headline of the mixed-identity work:
     it proves a local account can authenticate AND authorize via local-group
     role_assignments, with zero Entra dependency.
  3. (optional) Inference through the gateway with an `sk-*` key, twice, and a
     cache hit on the second identical call. Runs only if AIGW_TEST_API_KEY is
     set (issue one in the admin portal / via a service account first).

Each service is addressed by its ACA internal DNS name — there is no unified
path-router in the Azure deployment. Override any base via env.

Env:
  ADMIN_BASE            default http://ca-admin-dev-sdc   (serves /auth/* + /admin/*)
  CACHE_BASE            default http://ca-cache-dev-sdc   (serves /v1/chat/completions)
  AUTH_BASE             default http://ca-auth-dev-sdc
  AIGW_E2E_ADMIN_EMAIL      local admin to log in as (seed via create_local_account.py)
  AIGW_E2E_ADMIN_PASSWORD
  AIGW_TEST_API_KEY     optional sk-* key for the inference check
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

ADMIN_BASE = os.environ.get("ADMIN_BASE", "http://ca-admin-dev-sdc").rstrip("/")
CACHE_BASE = os.environ.get("CACHE_BASE", "http://ca-cache-dev-sdc").rstrip("/")
AUTH_BASE = os.environ.get("AUTH_BASE", "http://ca-auth-dev-sdc").rstrip("/")

_failures: list[str] = []


def _check(name: str, ok: bool, detail: str = "") -> bool:
    mark = "PASS" if ok else "FAIL"
    print(f"[{mark}] {name}" + (f" — {detail}" if detail else ""))
    if not ok:
        _failures.append(name)
    return ok


def _request(method: str, url: str, *, headers: dict | None = None, body: dict | None = None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers=headers or {})
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode()
            payload = json.loads(raw) if raw else {}
            return resp.status, dict(resp.headers), payload
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            payload = json.loads(raw)
        except ValueError:
            payload = {"raw": raw}
        return e.code, dict(e.headers), payload


def main() -> int:
    # 1. Health
    for name, base in (("auth", AUTH_BASE), ("cache", CACHE_BASE), ("admin", ADMIN_BASE)):
        status, _, _ = _request("GET", f"{base}/health")
        _check(f"health: {name}", status == 200, f"status {status}")

    # 2. Local-account login + platform_admin role
    email = os.environ.get("AIGW_E2E_ADMIN_EMAIL")
    password = os.environ.get("AIGW_E2E_ADMIN_PASSWORD")
    if not (email and password):
        _check("login: credentials provided", False, "set AIGW_E2E_ADMIN_EMAIL/PASSWORD")
        return _summary()

    status, _, payload = _request(
        "POST", f"{ADMIN_BASE}/auth/login", body={"email": email, "password": password}
    )
    token = payload.get("token")
    _check("login: 200 + token", status == 200 and bool(token), f"status {status}")
    roles = [r.get("role") for r in (payload.get("user", {}).get("roles") or [])]
    _check(
        "login: local account has platform_admin (unmanaged-identity authz)",
        "platform_admin" in roles,
        f"roles={roles}",
    )

    # 3. Optional inference + cache hit
    api_key = os.environ.get("AIGW_TEST_API_KEY")
    if not api_key:
        print("[SKIP] inference — set AIGW_TEST_API_KEY to exercise the inference path")
        return _summary()

    body = {
        "model": "claude-haiku-4-5",
        "messages": [{"role": "user", "content": "Reply with the single word: pong."}],
    }
    hdr = {"Authorization": f"Bearer {api_key}"}
    s1, h1, _ = _request("POST", f"{CACHE_BASE}/v1/chat/completions", headers=hdr, body=body)
    _check("inference: first call 200", s1 == 200, f"status {s1}")
    s2, h2, _ = _request("POST", f"{CACHE_BASE}/v1/chat/completions", headers=hdr, body=body)
    _check("inference: second call 200", s2 == 200, f"status {s2}")
    cache_state = (h2.get("x-cache") or h2.get("X-Cache") or "").lower()
    _check(
        "inference: cache hit on identical 2nd call",
        "hit" in cache_state,
        f"x-cache={cache_state!r}",
    )
    return _summary()


def _summary() -> int:
    if _failures:
        print(f"\nE2E FAILED: {len(_failures)} check(s) failed: {', '.join(_failures)}")
        return 1
    print("\nE2E PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
