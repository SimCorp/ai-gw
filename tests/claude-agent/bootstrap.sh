#!/usr/bin/env bash
set -euo pipefail

# ── 1. Require ANTHROPIC_API_KEY ─────────────────────────────────────────────
: "${ANTHROPIC_API_KEY:?ANTHROPIC_API_KEY is not set. Export a gateway sk- key before launching.}"

# ── 2. Verify connectivity to the SimCorp AI Gateway ─────────────────────────
GATEWAY_CACHE_URL="${GATEWAY_CACHE_URL:-http://cache:8002}"

echo "Checking gateway connectivity at ${GATEWAY_CACHE_URL}/health ..."
HTTP_STATUS=$(curl -fsS -o /dev/null -w "%{http_code}" \
    --max-time 10 \
    --retry 3 \
    --retry-delay 2 \
    "${GATEWAY_CACHE_URL}/health" 2>&1) || {
    echo "ERROR: Cannot reach gateway at ${GATEWAY_CACHE_URL}/health (got: ${HTTP_STATUS:-no response})"
    echo "Make sure the gateway stack is running: docker compose up --wait"
    exit 1
}

echo "Gateway health check: HTTP ${HTTP_STATUS} OK"

# ── 3. Probe the models endpoint (best-effort; non-fatal) ─────────────────────
MODELS_URL="${GATEWAY_CACHE_URL}/v1/models"
MODEL_COUNT=$(curl -fsS --max-time 5 "${MODELS_URL}" 2>/dev/null \
    | grep -o '"id"' | wc -l) || MODEL_COUNT="?"

echo "Gateway connected. Models available: ${MODEL_COUNT}"

# ── 4. Print banner ───────────────────────────────────────────────────────────
echo ""
echo "┌─────────────────────────────────────────────────────────┐"
echo "│  SimCorp AI Gateway — Claude Agent                     │"
echo "│                                                         │"
echo "│  ANTHROPIC_BASE_URL : ${ANTHROPIC_BASE_URL:-http://cache:8002/anthropic}"
echo "│  Gateway health     : OK (HTTP ${HTTP_STATUS})"
echo "│  Models available   : ${MODEL_COUNT}"
echo "│                                                         │"
echo "│  Starting Claude agent (using SimCorp AI Gateway)...   │"
echo "└─────────────────────────────────────────────────────────┘"
echo ""

# ── 5. Hand off to Claude Code ────────────────────────────────────────────────
# Pass all arguments through; no args drops into the interactive REPL.
exec claude "$@"
