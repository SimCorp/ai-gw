#!/usr/bin/env bash
#
# Run the browser E2E quality walkthrough against a deployed environment.
#
# Logs into the dev + admin portals and walks every route, asserting no
# client-side crashes and no failed backend calls, then clicks every
# non-destructive button. This is a QUALITY / smoke test — NOT a CI merge gate.
#
# Run from an in-VNet host (e.g. AZWESU0005) that can reach the target over ZPA
# and has `pass` available. Credentials come from `pass`; nothing is written to
# disk in plaintext.
#
# Usage:
#   scripts/e2e-quality.sh [-- <playwright args>]
#   scripts/e2e-quality.sh --project dev-portal
#   E2E_BASE_URL=https://aigw-test.lab.cloud.scdom.net scripts/e2e-quality.sh
#
# Env overrides:
#   E2E_BASE_URL       Target gateway (default: https://dev.aigw.scdom.net)
#   DEV_PASS_ENTRY     pass entry for the dev portal account  (default: aigw/dev-portal)
#   ADMIN_PASS_ENTRY   pass entry for the admin portal account (default: aigw/admin-portal)
#
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
E2E_DIR="$REPO_ROOT/e2e"

export E2E_BASE_URL="${E2E_BASE_URL:-https://dev.aigw.scdom.net}"
DEV_PASS_ENTRY="${DEV_PASS_ENTRY:-aigw/dev-portal}"
ADMIN_PASS_ENTRY="${ADMIN_PASS_ENTRY:-aigw/admin-portal}"

command -v pass >/dev/null || { echo "error: 'pass' not found on this host" >&2; exit 1; }
command -v pnpm >/dev/null || { echo "error: 'pnpm' not found on this host" >&2; exit 1; }

# pass entry format: line 1 = password, then `login: <email>` metadata.
creds_from_pass() {  # $1 = entry; prints "EMAIL\tPASSWORD"
  local entry="$1" pw email
  pw="$(pass show "$entry" | head -1)"
  email="$(pass show "$entry" | sed -n 's/^login:[[:space:]]*//p' | head -1)"
  [ -n "$pw" ] && [ -n "$email" ] || { echo "error: $entry must have a password (line 1) + 'login:' email" >&2; exit 1; }
  printf '%s\t%s' "$email" "$pw"
}

IFS=$'\t' read -r E2E_DEV_EMAIL E2E_DEV_PW < <(creds_from_pass "$DEV_PASS_ENTRY")
IFS=$'\t' read -r E2E_ADMIN_EMAIL E2E_ADMIN_PW < <(creds_from_pass "$ADMIN_PASS_ENTRY")
export E2E_DEV_EMAIL E2E_DEV_PW E2E_ADMIN_EMAIL E2E_ADMIN_PW

cd "$E2E_DIR"
if [ ! -d node_modules ]; then
  echo "==> Installing e2e deps (standalone — ignoring the repo workspace)"
  pnpm install --ignore-workspace
  pnpm exec playwright install chromium
fi

echo "==> Walking $E2E_BASE_URL (dev + admin portals)"
exec pnpm exec playwright test "$@"
