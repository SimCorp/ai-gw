#!/usr/bin/env bash
#
# Deploy the AI Gateway to the single-host dev VM (vm-aigw-dev-sdc).
#
# Run from an in-VNet host (e.g. AZWESU0005) that can reach the VM over ZPA and
# has `pass` available. CI builds + pushes images to GHCR on every master push;
# this script pulls the SSH key + GHCR token from `pass`, logs the VM into GHCR,
# pulls the new images, and does a rolling restart.
#
# Usage:
#   scripts/deploy-vm.sh [IMAGE_TAG]
#
#   IMAGE_TAG   Image tag to deploy. Default: latest.
#               Pin a specific build for a controlled deploy / rollback, e.g.
#               `scripts/deploy-vm.sh sha-abc1234`.
#
# Env overrides:
#   VM_HOST     SSH target (default: azureuser@10.179.231.68)
#   GHCR_USER   GitHub username that owns the GHCR read token (default: the
#               `login` field of the `github/ghcr-pat-aigw` pass entry)
#   SSH_PASS_ENTRY   pass entry holding the VM SSH key (default: ssh/dev.aigw.scdom.net)
#   GHCR_PASS_ENTRY  pass entry holding the GHCR read:packages PAT
#                    (default: github/ghcr-pat-aigw; first line = token)
#
set -euo pipefail

IMAGE_TAG="${1:-latest}"
VM_HOST="${VM_HOST:-azureuser@10.179.231.68}"
SSH_PASS_ENTRY="${SSH_PASS_ENTRY:-ssh/dev.aigw.scdom.net}"
GHCR_PASS_ENTRY="${GHCR_PASS_ENTRY:-github/ghcr-pat-aigw}"
COMPOSE="docker compose -f docker-compose.yml -f docker-compose.host.yml"

command -v pass >/dev/null || { echo "error: 'pass' not found on this host" >&2; exit 1; }

# GHCR username: explicit override, else the `login:` field of the pass entry.
GHCR_USER="${GHCR_USER:-$(pass show "$GHCR_PASS_ENTRY" | sed -n 's/^login:[[:space:]]*//p' | head -1)}"
[ -n "$GHCR_USER" ] || { echo "error: set GHCR_USER or add a 'login:' field to $GHCR_PASS_ENTRY" >&2; exit 1; }

# Load the VM SSH key into a throwaway agent (never written to disk).
eval "$(ssh-agent -s)" >/dev/null
trap 'ssh-agent -k >/dev/null 2>&1 || true' EXIT
pass show "$SSH_PASS_ENTRY" | ssh-add - >/dev/null 2>&1
SSH="ssh -o IdentityAgent=$SSH_AUTH_SOCK $VM_HOST"

echo "==> Logging the VM into GHCR as $GHCR_USER"
pass show "$GHCR_PASS_ENTRY" | head -1 \
  | $SSH "docker login ghcr.io -u '$GHCR_USER' --password-stdin"

echo "==> Pulling source + images (IMAGE_TAG=$IMAGE_TAG) and restarting on $VM_HOST"
$SSH "cd ~/ai-gw/infra \
  && git pull origin master \
  && IMAGE_TAG='$IMAGE_TAG' $COMPOSE pull \
  && IMAGE_TAG='$IMAGE_TAG' $COMPOSE up -d"

echo "==> Done. Current status:"
$SSH "cd ~/ai-gw/infra && $COMPOSE ps"
