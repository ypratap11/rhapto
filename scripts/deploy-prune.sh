#!/usr/bin/env bash
# Remove files that an earlier deploy shipped and the current deploy no longer contains.
#
# Runs ON THE SERVER, after deploy-server.sh has extracted the new tree over DEST. `tar -x` only adds
# and overwrites, so without this a file deleted in git stays on the server forever; on 2026-10-10 a
# stale About.tsx importing a removed export broke the production web build.
#
# Usage: deploy-prune.sh DEST NEW_MANIFEST EXPECTED_LINES [--dry-run]
#   DEST            the deploy directory (e.g. /opt/rhapto)
#   NEW_MANIFEST    file listing every path the new deploy shipped, one per line (git ls-tree output)
#   EXPECTED_LINES  how many lines the sender wrote; a truncated upload must not read as "all deleted"
#
# The only paths ever deleted are those listed in DEST/.deploy-manifest (written by the previous
# deploy) and missing from NEW_MANIFEST. Anything no deploy ever shipped -- .env, profile/, backups/,
# runtime data -- is never in a manifest, so it can never be deleted. As a second fence, .env and
# profile/ are refused even if a manifest somehow names them, and so is any absolute or `..` path.
# With no previous manifest (the first run) nothing is deleted; the new manifest is installed.
# If more than 20 files and over 25% of the previous deploy's files would go, it stops unless
# RHAPTO_PRUNE_FORCE=1.
set -euo pipefail

USAGE="usage: deploy-prune.sh DEST NEW_MANIFEST EXPECTED_LINES [--dry-run]"
DEST="${1:?$USAGE}"
NEW="${2:?$USAGE}"
EXPECTED="${3:?$USAGE}"
DRY_RUN="${4:-}"
OLD="$DEST/.deploy-manifest"

[[ -d "$DEST" ]] || { echo "FATAL: $DEST is not a directory" >&2; exit 1; }
[[ -s "$NEW" ]] || { echo "FATAL: new manifest $NEW is missing or empty" >&2; exit 1; }
got="$(wc -l < "$NEW" | tr -d ' ')"
[[ "$got" == "$EXPECTED" ]] || {
  echo "FATAL: new manifest has $got lines, sender wrote $EXPECTED; refusing to prune" >&2
  exit 1
}

install_manifest() {
  if [[ "$DRY_RUN" == "--dry-run" ]]; then return; fi
  cp "$NEW" "$OLD"
}

if [[ ! -f "$OLD" ]]; then
  echo "    prune: no previous manifest at $OLD; nothing removed (first run)"
  install_manifest
  exit 0
fi

stale="$(comm -23 <(LC_ALL=C sort -u "$OLD") <(LC_ALL=C sort -u "$NEW"))"
if [[ -z "$stale" ]]; then
  echo "    prune: nothing to remove"
  install_manifest
  exit 0
fi

old_count="$(LC_ALL=C sort -u "$OLD" | wc -l | tr -d ' ')"
stale_count="$(printf '%s\n' "$stale" | wc -l | tr -d ' ')"
# A normal release deletes a handful of files; losing more than 20 files AND over a quarter of the
# tree means the wrong ref or a bad manifest, not a release.
if (( stale_count > 20 && stale_count * 4 > old_count )) && [[ "${RHAPTO_PRUNE_FORCE:-}" != "1" ]]; then
  echo "FATAL: $stale_count of $old_count previously deployed files would be removed (> 25%);" \
    "refusing. Check the ref, or rerun with RHAPTO_PRUNE_FORCE=1." >&2
  exit 1
fi

removed=0
while IFS= read -r path; do
  case "$path" in
    "" | /* | ..* | */..* | .env | .env/* | profile | profile/*)
      echo "    prune: REFUSED unsafe path: $path" >&2
      continue
      ;;
  esac
  target="$DEST/$path"
  if [[ ! -e "$target" && ! -L "$target" ]]; then
    continue
  fi
  if [[ -d "$target" && ! -L "$target" ]]; then
    # Manifests list files, never directories; a directory here means the manifest is not ours.
    echo "    prune: REFUSED directory: $path" >&2
    continue
  fi
  if [[ "$DRY_RUN" == "--dry-run" ]]; then
    echo "    prune: would remove $path"
  else
    rm -f -- "$target"
    echo "    prune: removed $path"
    # Drop now-empty parent directories, stopping at DEST.
    dir="$(dirname -- "$target")"
    while [[ "$dir" != "$DEST" && "$dir" == "$DEST"/* ]] && rmdir -- "$dir" 2>/dev/null; do
      dir="$(dirname -- "$dir")"
    done
  fi
  removed=$((removed + 1))
done <<< "$stale"

echo "    prune: $removed stale file(s) $([[ "$DRY_RUN" == "--dry-run" ]] && echo "would be removed (dry run)" || echo "removed")"
install_manifest
