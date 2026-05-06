#!/usr/bin/env bash
set -euo pipefail

# ── Write gateway env into user profile ──────────────────────────────────────
GATEWAY_CACHE_URL="${GATEWAY_CACHE_URL:-http://cache:8002}"
GATEWAY_ADMIN_URL="${GATEWAY_ADMIN_URL:-http://admin:8005}"

cat > /home/claude/.bashrc <<EOF
# SimCorp AI Gateway — sandbox environment
export ANTHROPIC_BASE_URL="${ANTHROPIC_BASE_URL:-http://cache:8002/anthropic}"
export ANTHROPIC_API_KEY="${ANTHROPIC_API_KEY:-}"
export GATEWAY_URL="${GATEWAY_CACHE_URL}"
export GATEWAY_ADMIN_URL="${GATEWAY_ADMIN_URL}"

# Helpers
alias gw-health='curl -s ${GATEWAY_CACHE_URL}/health | python3 -m json.tool'
alias gw-models='curl -s ${GATEWAY_CACHE_URL}/v1/models | python3 -m json.tool'
alias claude-check='claude --version && echo "ANTHROPIC_BASE_URL=\$ANTHROPIC_BASE_URL"'

export PS1='\[\e[32m\][claude-sandbox]\[\e[0m\] \w\$ '

cd /home/claude/workspace
EOF

chown claude:claude /home/claude/.bashrc

# ── Connectivity check (best-effort) ─────────────────────────────────────────
echo "Checking gateway at ${GATEWAY_CACHE_URL}/health ..."
HTTP_STATUS=$(curl -fsS -o /dev/null -w "%{http_code}" --max-time 10 "${GATEWAY_CACHE_URL}/health" 2>/dev/null || echo "000")
echo "Gateway health: HTTP ${HTTP_STATUS}"

# ── Print SSH banner ──────────────────────────────────────────────────────────
echo ""
echo "┌────────────────────────────────────────────────────────────┐"
echo "│  SimCorp AI Gateway — Claude Sandbox                       │"
echo "│                                                            │"
echo "│  SSH:  ssh claude@localhost -p 2222  (password: gateway)  │"
echo "│  Base: ${ANTHROPIC_BASE_URL:-http://cache:8002/anthropic}"
echo "│  Key:  ANTHROPIC_API_KEY is $([ -n "${ANTHROPIC_API_KEY:-}" ] && echo "SET" || echo "NOT SET — set before using claude")"
echo "│                                                            │"
echo "│  Once connected, run: claude                               │"
echo "└────────────────────────────────────────────────────────────┘"
echo ""

# ── Start SSH daemon in foreground ───────────────────────────────────────────
exec /usr/sbin/sshd -D -e
