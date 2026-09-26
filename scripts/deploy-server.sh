#!/usr/bin/env bash
# Sync working-tree source to the production box and rebuild.
#
# /opt/rhapto is NOT a git checkout — there is no .git there and no remote. Code arrives by file
# sync, which is why the runbook's `git fetch` / `git checkout` steps cannot work. This script is
# the actual mechanism.
#
# Usage:
#   scripts/deploy-server.sh                      # sync + rebuild web only (fast, UI/copy changes)
#   scripts/deploy-server.sh api worker web       # sync + rebuild named services
#
# Never syncs .env or profile/ — those live only on the server.
set -euo pipefail

HOST="${RHAPTO_HOST:-root@64.225.30.51}"
DEST="${RHAPTO_DEST:-/opt/rhapto}"
SERVICES=("${@:-web}")

cd "$(git rev-parse --show-toplevel)"

if [[ -n "$(git status --porcelain --untracked-files=no)" ]]; then
  echo "WARNING: working tree has uncommitted changes — you are about to deploy them." >&2
  git status --short --untracked-files=no >&2
  read -r -p "Continue? [y/N] " reply
  [[ "$reply" == "y" || "$reply" == "Y" ]] || exit 1
fi

echo "==> Backing up the files about to be replaced"
BACKUP="/root/rhapto-predeploy-$(date -u +%Y%m%dT%H%M%SZ)"
ssh "$HOST" "cp -a '$DEST' '$BACKUP' && echo '    backup: $BACKUP'"

echo "==> Syncing tracked source (excluding .env, profile/, .git)"
# git archive gives exactly the tracked tree at HEAD — no build output, no gitignored data.
git archive --format=tar HEAD | ssh "$HOST" "cd '$DEST' && tar -xf - --exclude='.env' --exclude='profile/*'"

echo "==> Rebuilding: ${SERVICES[*]}"
ssh "$HOST" "cd '$DEST' && docker compose build ${SERVICES[*]} && docker compose up -d ${SERVICES[*]}"

echo "==> Verifying"
ssh "$HOST" "cd '$DEST' && docker compose ps --format '{{.Service}} {{.State}}' && head -2 LICENSE"

cat <<'DONE'

==> Done. Check https://rhapto.augaster.com in a browser.
    Roll back with:  ssh HOST "rm -rf /opt/rhapto && mv BACKUP /opt/rhapto && cd /opt/rhapto && docker compose up -d --build"
    (the backup path is printed above)
DONE
