#!/usr/bin/env bash
set -euo pipefail

# One-shot setup script for a fresh Ubuntu 24.04 VM.
# Installs Docker, authenticates to GHCR, clones the repo, and starts the
# ai-gw stack via docker compose.

# ── 1. Install Docker Engine + Compose plugin ─────────────────────────────────
echo "==> Installing Docker Engine..."
apt-get update -y
apt-get install -y ca-certificates curl gnupg lsb-release

install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
  | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
chmod a+r /etc/apt/keyrings/docker.gpg

echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
  https://download.docker.com/linux/ubuntu \
  $(lsb_release -cs) stable" \
  > /etc/apt/sources.list.d/docker.list

apt-get update -y
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# ── 2. Add current user to docker group ──────────────────────────────────────
CURRENT_USER="${SUDO_USER:-$(whoami)}"
echo "==> Adding ${CURRENT_USER} to docker group..."
usermod -aG docker "${CURRENT_USER}"

# ── 3. Authenticate to GHCR ──────────────────────────────────────────────────
if [[ -z "${GHCR_PAT:-}" ]]; then
  read -rsp "Enter GitHub PAT for GHCR (ghcr.io): " GHCR_PAT
  echo
fi

GHCR_USER="${GHCR_USER:-${CURRENT_USER}}"
echo "==> Logging in to ghcr.io as ${GHCR_USER}..."
echo "${GHCR_PAT}" | docker login ghcr.io -u "${GHCR_USER}" --password-stdin

# ── 4. Clone the repo ─────────────────────────────────────────────────────────
REPO_DIR="/opt/aigw"
if [[ -d "${REPO_DIR}" ]]; then
  echo "==> ${REPO_DIR} already exists; skipping clone."
else
  echo "==> Cloning SimCorp/ai-gw to ${REPO_DIR}..."
  git clone https://github.com/SimCorp/ai-gw.git "${REPO_DIR}"
fi

# ── 5. Copy .env.example → .env ───────────────────────────────────────────────
if [[ ! -f "${REPO_DIR}/.env" ]]; then
  cp "${REPO_DIR}/.env.example" "${REPO_DIR}/.env"
  echo ""
  echo "==> IMPORTANT: Edit ${REPO_DIR}/.env and fill in all required secrets before proceeding."
  echo "    Minimum required: ANTHROPIC_API_KEY or OPENAI_API_KEY, LITELLM_MASTER_KEY,"
  echo "    INTERNAL_API_KEY, SCANNER_WORKER_SECRET."
  echo ""
  read -rp "Press Enter once you have edited ${REPO_DIR}/.env to continue..."
else
  echo "==> ${REPO_DIR}/.env already exists; skipping copy."
fi

# ── 6. Pull images ────────────────────────────────────────────────────────────
echo "==> Pulling images (IMAGE_TAG=${IMAGE_TAG:-latest})..."
IMAGE_TAG="${IMAGE_TAG:-latest}" docker compose \
  -f "${REPO_DIR}/infra/docker-compose.yml" \
  --project-directory "${REPO_DIR}" \
  pull

# ── 7. Start services ─────────────────────────────────────────────────────────
echo "==> Starting services..."
IMAGE_TAG="${IMAGE_TAG:-latest}" docker compose \
  -f "${REPO_DIR}/infra/docker-compose.yml" \
  --project-directory "${REPO_DIR}" \
  up -d

# ── 8. Print access URL ───────────────────────────────────────────────────────
HOST_IP=$(hostname -I | awk '{print $1}')
echo ""
echo "============================================================"
echo " AI Gateway running at http://${HOST_IP}:8080"
echo "============================================================"
echo ""

# ── GitHub Actions self-hosted runner setup ───────────────────────────────────
#
# Run these commands to register the VM as a GitHub Actions runner with
# label 'vnet-aigw-dev' so CI can deploy directly to this machine.
#
# 1. Go to: https://github.com/SimCorp/ai-gw/settings/actions/runners/new
# 2. Copy the runner token shown there
# 3. Run:
#
#   mkdir -p /opt/actions-runner && cd /opt/actions-runner
#   curl -sL https://github.com/actions/runner/releases/download/v2.317.0/actions-runner-linux-x64-2.317.0.tar.gz | tar xz
#   ./config.sh --url https://github.com/SimCorp/ai-gw --token <TOKEN> --labels vnet-aigw-dev --unattended
#   sudo ./svc.sh install && sudo ./svc.sh start
