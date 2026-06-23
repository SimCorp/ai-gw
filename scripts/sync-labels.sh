#!/usr/bin/env bash
# Sync the labels defined in .github/labels.yml into the GitHub repo.
#
# The agentic workflows in .github/workflows/ can only apply labels that
# already exist, so run this once (and after editing labels.yml) to create or
# update them. Idempotent: `gh label create --force` updates an existing label
# in place. This script never deletes labels — prune by hand if needed.
#
# Requires: gh (authenticated), python3 with pyyaml.
# Usage: scripts/sync-labels.sh [owner/repo]   (defaults to the current repo)

set -euo pipefail

REPO="${1:-}"
LABELS_FILE="$(git rev-parse --show-toplevel)/.github/labels.yml"

repo_arg=()
[[ -n "$REPO" ]] && repo_arg=(--repo "$REPO")

python3 - "$LABELS_FILE" <<'PY' | while IFS=$'\t' read -r name color desc; do
import sys, yaml
for l in yaml.safe_load(open(sys.argv[1])):
    print(f"{l['name']}\t{l.get('color','ededed')}\t{l.get('description','')}")
PY
  echo "syncing: $name"
  gh label create "$name" --color "$color" --description "$desc" --force "${repo_arg[@]}"
done

echo "✓ Labels synced from $LABELS_FILE"
