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
# Prune options (deploy-prune.sh removes files the ref no longer ships):
#   RHAPTO_PRUNE_DRY_RUN=1   pass --dry-run to deploy-prune.sh: list what it would remove, delete nothing,
#                            and continue the deploy.
#   RHAPTO_PRUNE_FORCE=1     allow a prune that removes >20 files and >25% of the previous deploy
#                            (e.g. a rollback to an old RHAPTO_REF, or the bootstrap below).
#   RHAPTO_PRUNE_BOOTSTRAP=1 ONE-TIME, never automatic. Only if the server has no .deploy-manifest yet,
#                            upload as the "previous" manifest every path ever added in git history, so
#                            the first prune also removes files deleted long ago that are still on the
#                            server. Run it FIRST with RHAPTO_PRUNE_DRY_RUN=1 and review the list; then
#                            run for real (likely with RHAPTO_PRUNE_FORCE=1 if the guard trips). A dry
#                            run still uploads the bootstrap manifest (harmless: nothing is deleted).
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

# Which ssh binary. On Windows this matters and the failure is baffling without knowing why: Git
# Bash's /usr/bin/ssh cannot reach the Windows ssh-agent (SSH_AUTH_SOCK is unset; the agent lives
# behind a named pipe), so it offers the public key, the server ACCEPTS it, and authentication then
# fails anyway because the usable private key exists only in the agent -- reported simply as
# "Permission denied (publickey)". An interactive shell resolves ssh.exe and works, while this
# script, a non-interactive child, resolved /usr/bin/ssh and did not. Diagnosed by comparing the two
# `ssh -v` auth trails: the working one says "agent returned 1 keys", the failing one does not.
SSH="${RHAPTO_SSH:-ssh}"
if [[ -x /c/Windows/System32/OpenSSH/ssh.exe ]]; then
  SSH=/c/Windows/System32/OpenSSH/ssh.exe
fi
SERVICES=("${@:-web}")

cd "$(git rev-parse --show-toplevel)"

git rev-parse --verify "${REF}^{commit}" >/dev/null 2>&1 || {
  echo "FATAL: '${REF}' is not a commit. Run 'git fetch origin' first, or set RHAPTO_REF." >&2
  exit 1
}

# Shell scripts must reach the server with LF endings (.gitattributes: *.sh eol=lf). CRLF makes bash fail
# on `set -o pipefail\r`, which would abort the deploy after the tree was already replaced. Check the
# bytes (Git Bash grep cannot see \r) before anything is touched.
CR_BYTES="$(git archive "$REF" scripts/deploy-prune.sh | tar -xO | tr -cd '\r' | wc -c | tr -d ' ')"
[[ "$CR_BYTES" == "0" ]] || {
  echo "FATAL: scripts/deploy-prune.sh at ${REF} has ${CR_BYTES} CR byte(s) in the archive; the server's bash would reject it." >&2
  echo "       Make sure that ref contains .gitattributes (*.sh text eol=lf) and the script is committed with LF." >&2
  exit 1
}
PRUNE_FORCE="${RHAPTO_PRUNE_FORCE:-}"
PRUNE_DRY="${RHAPTO_PRUNE_DRY_RUN:-}"
PRUNE_BOOTSTRAP="${RHAPTO_PRUNE_BOOTSTRAP:-}"
for v in RHAPTO_PRUNE_FORCE RHAPTO_PRUNE_DRY_RUN RHAPTO_PRUNE_BOOTSTRAP; do
  [[ -z "${!v:-}" || "${!v}" == "1" ]] || { echo "FATAL: $v must be empty or 1" >&2; exit 1; }
done

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
"$SSH" "$HOST" "cp -a '$DEST' '$BACKUP' && echo '    backup: $BACKUP'"

echo "==> Syncing tracked source (excluding .env, profile/, .git)"
# git archive gives exactly the tracked tree at REF — no working-tree edits, no build output, no
# gitignored data, and in particular no profile/ even if it exists locally.
git archive --format=tar "$REF" | "$SSH" "$HOST" "cd '$DEST' && tar -xf - --exclude='.env' --exclude='profile/*'"

echo "==> Removing files this ref no longer ships"
# tar -x only adds and overwrites, so a file deleted in git used to stay on the server and could break
# the build (2026-10-10: a stale About.tsx). deploy-prune.sh removes exactly the files the previous
# deploy shipped and this one does not, using a manifest of tracked paths; nothing that was never
# deployed (.env, profile/, backups/) can be in a manifest, so nothing else is touched.
MANIFEST="$(mktemp)"
trap 'rm -f "$MANIFEST"' EXIT
git -c core.quotepath=off ls-tree -r --name-only "$REF" > "$MANIFEST"
LINES="$(wc -l < "$MANIFEST" | tr -d ' ')"
if [[ "$PRUNE_BOOTSTRAP" == "1" ]]; then
  # One-time: seed the "previous" manifest with every path ever added, but only if the server has none.
  if "$SSH" "$HOST" "test ! -e '$DEST/.deploy-manifest'" </dev/null; then
    BOOT="$(mktemp)"
    git -c core.quotepath=off log --all --diff-filter=A --name-only --pretty=format: | sed '/^$/d' | LC_ALL=C sort -u > "$BOOT"
    echo "    bootstrap: seeding previous manifest with $(wc -l < "$BOOT" | tr -d ' ') historical path(s)"
    "$SSH" "$HOST" "cat > '$DEST/.deploy-manifest'" < "$BOOT"
    rm -f "$BOOT"
  else
    echo "    bootstrap: server already has a .deploy-manifest; skipped"
  fi
fi
PRUNE_ARGS=""
if [[ "$PRUNE_DRY" == "1" ]]; then PRUNE_ARGS="--dry-run"; echo "    prune: DRY RUN (nothing is deleted)"; fi
"$SSH" "$HOST" "cat > '$DEST/.deploy-manifest.new'" < "$MANIFEST"
"$SSH" "$HOST" "RHAPTO_PRUNE_FORCE='$PRUNE_FORCE' bash '$DEST/scripts/deploy-prune.sh' '$DEST' '$DEST/.deploy-manifest.new' '$LINES' $PRUNE_ARGS && rm -f '$DEST/.deploy-manifest.new'" </dev/null

echo "==> Rebuilding: ${SERVICES[*]}"
"$SSH" "$HOST" "cd '$DEST' && RHAPTO_BUILD_ID='$(git rev-parse --short=9 "$REF")' docker compose build ${SERVICES[*]} && docker compose up -d ${SERVICES[*]}"

echo "==> Verifying"
"$SSH" "$HOST" "cd '$DEST' && docker compose ps --format '{{.Service}} {{.State}}' && head -2 LICENSE"

cat <<'DONE'

==> Done. Check https://rhapto.augaster.com in a browser.
    Roll back with:  ssh HOST "rm -rf /opt/rhapto && mv BACKUP /opt/rhapto && cd /opt/rhapto && docker compose up -d --build"
    (the backup path is printed above)
DONE
