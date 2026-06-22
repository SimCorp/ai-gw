#!/usr/bin/env bash
#
# Light per-service update for the single-host dev VM.
#
# Pulls the new image(s) for the named GATEWAY service(s) and restarts ONLY
# those (`up -d --no-deps`), leaving the static base (postgres, redis, dex,
# caddy) untouched. This is the routine way to ship a gateway change — the base
# stays static and is never recreated.
#
# For multi-service / base / compose-file changes, use `deploy-vm.sh` (full
# pull + `up -d`; still convergent, so unchanged containers aren't recreated).
#
# Run from an in-VNet host (e.g. AZWESU0005) with `pass` available. Mirrors
# deploy-vm.sh's credential handling (SSH key + GHCR token from pass).
#
# Usage:
#   scripts/update-service.sh [--tag <IMAGE_TAG>] <service> [<service> ...]
#   scripts/update-service.sh auth cache
#   scripts/update-service.sh --tag sha-abc1234 admin admin-portal
#
# Env overrides: same as deploy-vm.sh (VM_HOST, GHCR_USER, SSH_PASS_ENTRY, GHCR_PASS_ENTRY).
#
set -euo pipefail

IMAGE_TAG="latest"
if [ "${1:-}" = "--tag" ]; then
  IMAGE_TAG="${2:?--tag needs a value}"; shift 2
fi
[ "$#" -ge 1 ] || { echo "usage: $0 [--tag <tag>] <service> [<service> ...]" >&2; exit 2; }
SERVICES=("$@")

# Refuse the static base — those are not routine gateway updates.
BASE_RE='^(postgres|redis|dex|caddy|ollama|redis-master|redis-replica|redis-sentinel-[0-9]+)$'
for s in "${SERVICES[@]}"; do
  if [[ "$s" =~ $BASE_RE ]]; then
    echo "error: '$s' is a static base service — use deploy-vm.sh for base/infra changes." >&2
    exit 2
  fi
done

VM_HOST="${VM_HOST:-azureuser@10.179.231.68}"
SSH_PASS_ENTRY="${SSH_PASS_ENTRY:-ssh/dev.aigw.scdom.net}"
GHCR_PASS_ENTRY="${GHCR_PASS_ENTRY:-api/GHCR PAT aigw}"
COMPOSE="docker compose -f docker-compose.yml -f docker-compose.host.yml"

command -v pass >/dev/null || { echo "error: 'pass' not found on this host" >&2; exit 1; }
GHCR_USER="${GHCR_USER:-$(pass show "$GHCR_PASS_ENTRY" | sed -n 's/^login:[[:space:]]*//p' | head -1)}"
[ -n "$GHCR_USER" ] || { echo "error: set GHCR_USER or add a 'login:' field to $GHCR_PASS_ENTRY" >&2; exit 1; }

eval "$(ssh-agent -s)" >/dev/null
trap 'ssh-agent -k >/dev/null 2>&1 || true' EXIT
pass show "$SSH_PASS_ENTRY" | ssh-add - >/dev/null 2>&1
SSH="ssh -o IdentityAgent=$SSH_AUTH_SOCK $VM_HOST"

echo "==> Logging the VM into GHCR as $GHCR_USER"
pass show "$GHCR_PASS_ENTRY" | head -1 | $SSH "docker login ghcr.io -u '$GHCR_USER' --password-stdin"

echo "==> Running db-migrate (alembic upgrade head — no-op if already at head)"
$SSH "cd ~/ai-gw/infra && IMAGE_TAG='$IMAGE_TAG' $COMPOSE run --rm db-migrate"

echo "==> Updating ${SERVICES[*]} (IMAGE_TAG=$IMAGE_TAG) — base left untouched"
$SSH "cd ~/ai-gw/infra \
  && IMAGE_TAG='$IMAGE_TAG' $COMPOSE pull ${SERVICES[*]} \
  && IMAGE_TAG='$IMAGE_TAG' $COMPOSE up -d --no-deps ${SERVICES[*]}"

echo "==> Updated services:"
$SSH "cd ~/ai-gw/infra && $COMPOSE ps ${SERVICES[*]}"
