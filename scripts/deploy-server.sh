#!/usr/bin/env bash
# Sync working-tree source to the production box and rebuild.
#
# /opt/rhapto is NOT a git checkout — there is no .git there and no remote. Code arrives by file
# sync, which is why the runbook's `git fetch` / `git checkout` steps cannot work. This script is
# the actual mechanism.
#
# Usage:
#   scripts/deploy-server.sh                      # deploy origin/main, rebuild web only
#   scripts/deploy-server.sh api worker web       # deploy origin/main, rebuild named services
#   RHAPTO_REF=some-branch scripts/deploy-server.sh   # deploy a different committed ref
#
# Deploys origin/main by DEFAULT, not your checked-out branch: what reaches production should not
# depend on which branch you happen to be on. Uncommitted edits are never deployed.
# Never syncs .env or profile/ — those live only on the server.
set -euo pipefail

HOST="${RHAPTO_HOST:-root@64.225.30.51}"
DEST="${RHAPTO_DEST:-/opt/rhapto}"
# What gets deployed is an explicit ref, NOT whatever branch happens to be checked out. Deploying
# `HEAD` once meant a feature branch with an unapplied migration was one keystroke from production
# because a rebase had left that branch checked out.
REF="${RHAPTO_REF:-origin/main}"
SERVICES=("${@:-web}")

cd "$(git rev-parse --show-toplevel)"

git rev-parse --verify "${REF}^{commit}" >/dev/null 2>&1 || {
  echo "FATAL: '${REF}' is not a commit. Run 'git fetch origin' first, or set RHAPTO_REF." >&2
  exit 1
}

echo "==> Deploying ref: ${REF} = $(git rev-parse --short=9 "$REF") $(git log -1 --format=%s "$REF")"
echo "    services: ${SERVICES[*]}"
# git archive reads the committed tree, so uncommitted edits are never deployed -- say so rather than
# warning about a danger that does not exist. What DOES matter is deploying a ref you did not mean to.
if [[ -n "$(git status --porcelain --untracked-files=no)" ]]; then
  echo "    note: you have uncommitted changes; they are NOT included (a committed ref is deployed)."
fi
if [[ "$(git rev-parse HEAD)" != "$(git rev-parse "$REF")" ]]; then
  echo "    note: this differs from your checked-out HEAD ($(git rev-parse --abbrev-ref HEAD))."
fi
read -r -p "    Deploy this to ${HOST}:${DEST}? [y/N] " reply
[[ "$reply" == "y" || "$reply" == "Y" ]] || { echo "aborted"; exit 1; }

echo "==> Backing up the files about to be replaced"
BACKUP="/root/rhapto-predeploy-$(date -u +%Y%m%dT%H%M%SZ)"
ssh "$HOST" "cp -a '$DEST' '$BACKUP' && echo '    backup: $BACKUP'"

echo "==> Syncing tracked source (excluding .env, profile/, .git)"
# git archive gives exactly the tracked tree at REF — no working-tree edits, no build output, no
# gitignored data, and in particular no profile/ even if it exists locally.
git archive --format=tar "$REF" | ssh "$HOST" "cd '$DEST' && tar -xf - --exclude='.env' --exclude='profile/*'"

echo "==> Rebuilding: ${SERVICES[*]}"
ssh "$HOST" "cd '$DEST' && docker compose build ${SERVICES[*]} && docker compose up -d ${SERVICES[*]}"

echo "==> Verifying"
ssh "$HOST" "cd '$DEST' && docker compose ps --format '{{.Service}} {{.State}}' && head -2 LICENSE"

cat <<'DONE'

==> Done. Check https://rhapto.augaster.com in a browser.
    Roll back with:  ssh HOST "rm -rf /opt/rhapto && mv BACKUP /opt/rhapto && cd /opt/rhapto && docker compose up -d --build"
    (the backup path is printed above)
DONE
