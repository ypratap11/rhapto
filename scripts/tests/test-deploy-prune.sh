#!/usr/bin/env bash
# Tests for scripts/deploy-prune.sh. Plain bash, no framework: run `bash scripts/tests/test-deploy-prune.sh`.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PRUNE="${PRUNE:-$HERE/../deploy-prune.sh}"  # override to run against a mutated copy
fails=0

check() { # check "description" condition...
  local desc="$1"; shift
  if "$@"; then echo "ok   - $desc"; else echo "FAIL - $desc"; fails=$((fails + 1)); fi
}

setup() {
  T="$(mktemp -d)"
  D="$T/dest"
  mkdir -p "$D/apps/web/src/about" "$D/apps/web/src/keep" "$D/profile" "$D/backups"
  echo x > "$D/apps/web/src/about/About.tsx"
  echo x > "$D/apps/web/src/keep/Keep.tsx"
  echo secret > "$D/.env"
  echo me > "$D/profile/blocks.yaml"
  echo dump > "$D/backups/backup.dump"
}
teardown() { rm -rf "$T"; }
# run_prune DEST NEW [--dry-run]: call the script with the real line count of NEW.
run_prune() { bash "$PRUNE" "$1" "$2" "$(wc -l < "$2" | tr -d ' ')" "${@:3}"; }

# 1. First run: no previous manifest -> nothing removed, manifest installed.
setup
printf 'apps/web/src/keep/Keep.tsx\n' > "$T/new"
run_prune "$D" "$T/new" >/dev/null
check "first run removes nothing" test -f "$D/apps/web/src/about/About.tsx"
check "first run installs the manifest" cmp -s "$T/new" "$D/.deploy-manifest"
teardown

# 2. A file the previous deploy shipped and the new one dropped is removed, with its empty dir.
setup
printf 'apps/web/src/about/About.tsx\napps/web/src/keep/Keep.tsx\n' > "$D/.deploy-manifest"
printf 'apps/web/src/keep/Keep.tsx\n' > "$T/new"
run_prune "$D" "$T/new" >/dev/null
check "stale file removed" test ! -e "$D/apps/web/src/about/About.tsx"
check "its empty directory removed" test ! -d "$D/apps/web/src/about"
check "kept file stays" test -f "$D/apps/web/src/keep/Keep.tsx"
check "non-empty parent stays" test -d "$D/apps/web/src"
check "manifest updated to the new one" cmp -s "$T/new" "$D/.deploy-manifest"
teardown

# 3. Files no deploy ever shipped are never touched: .env, profile/, backups/.
setup
printf 'apps/web/src/keep/Keep.tsx\n' > "$D/.deploy-manifest"
printf 'apps/web/src/keep/Keep.tsx\n' > "$T/new"
run_prune "$D" "$T/new" >/dev/null
check ".env untouched" test -f "$D/.env"
check "profile untouched" test -f "$D/profile/blocks.yaml"
check "backups untouched" test -f "$D/backups/backup.dump"
teardown

# 4. Even if an old manifest names them, .env, profile/, absolute, `..` and `.` paths are refused, and
# the victims (all inside the temp dir, never real system files) survive.
setup
echo out > "$T/outside"; echo abs > "$T/abs-victim"; echo mid > "$T/victim"
mkdir -p "$D/profile/sub"; echo p > "$D/profile/x"
printf '%s\n' '.env' 'profile/blocks.yaml' "$T/abs-victim" '../outside' 'apps/../../victim' \
  './.env' './profile/x' 'profile//x' 'apps/./web/src/keep/Keep.tsx' 'apps/web//src/keep/Keep.tsx' \
  > "$D/.deploy-manifest"
printf 'unrelated\n' > "$T/new"
out="$(run_prune "$D" "$T/new" 2>&1)"
check ".env refused" test -f "$D/.env"
check "profile refused" test -f "$D/profile/blocks.yaml"
check "parent-escape refused" test -f "$T/outside"
check "absolute path refused (victim survives)" test -f "$T/abs-victim"
check "middle .. refused (victim survives)" test -f "$T/victim"
check "./.env refused (survives)" test -f "$D/.env"
check "./profile/x refused (survives)" test -f "$D/profile/x"
check "profile dir survives" test -d "$D/profile/sub"
check "refusals are reported" grep -q "REFUSED unsafe path: .env" <<< "$out"
check "a/./b refused" grep -q "REFUSED unsafe path: apps/./web" <<< "$out"
check "a//b refused" grep -q "REFUSED unsafe path: apps/web//src" <<< "$out"
check "a/./b and a//b targets survive" test -f "$D/apps/web/src/keep/Keep.tsx"
teardown

# 4b. A symlinked parent directory that points outside DEST must not let a delete escape.
setup
mkdir -p "$T/elsewhere"; echo v > "$T/elsewhere/victim"
if ln -s "$T/elsewhere" "$D/lnk" 2>/dev/null && [[ -L "$D/lnk" ]]; then
  printf 'lnk/victim\n' > "$D/.deploy-manifest"
  printf 'unrelated\n' > "$T/new"
  out="$(run_prune "$D" "$T/new" 2>&1)"
  check "symlinked parent: file outside DEST survives" test -f "$T/elsewhere/victim"
  check "symlinked parent: refusal reported" grep -q "REFUSED unsafe path: lnk/victim" <<< "$out"
else
  echo "skip - symlinked parent (this platform cannot create symlinks)"
fi
teardown

# 4c. Empty-dir cleanup stops at DEST: DEST holds only the stale file's chain; neither DEST nor its
# parent (with a sibling file) may be removed.
setup
rm -rf "$D"; mkdir -p "$T/parent/dest/a/b"; D="$T/parent/dest"
echo sib > "$T/parent/sibling"; echo gone > "$D/a/b/stale"
printf 'a/b/stale\n' > "$D/.deploy-manifest"
printf 'unrelated\n' > "$T/new"
run_prune "$D" "$T/new" >/dev/null
check "cleanup: stale file removed" test ! -e "$D/a/b/stale"
check "cleanup: its empty chain removed" test ! -d "$D/a"
check "cleanup: DEST survives" test -d "$D"
check "cleanup: DEST's parent and sibling survive" test -f "$T/parent/sibling"
teardown

# 4d. Locale robustness: under a UTF-8 locale `sort` and `comm` can disagree on mixed-case/underscore
# paths unless the script pins LC_ALL=C. (If the locale is not installed this proves nothing; it says so.
# On Debian/Ubuntu without root: localedef -i en_US -f UTF-8 /tmp/loc/en_US.UTF-8; export LOCPATH=/tmp/loc)
setup
mkdir -p "$D/a"; : > "$D/a/B.txt"; : > "$D/a/_c.txt"; : > "$D/a/a.txt"; : > "$D/a/Z_y.txt"; : > "$D/a/keep.txt"
printf 'a/B.txt\na/_c.txt\na/a.txt\na/Z_y.txt\na/keep.txt\n' > "$D/.deploy-manifest"
printf 'a/keep.txt\n' > "$T/new"
if [[ "$(LC_ALL=en_US.UTF-8 locale charmap 2>/dev/null)" == "UTF-8" ]]; then
  LC_ALL=en_US.UTF-8 run_prune "$D" "$T/new" >/dev/null 2>&1 && rc=0 || rc=$?
  check "non-C locale: exits 0" test "$rc" = 0
  check "non-C locale: mixed-case/underscore stale files removed" test ! -e "$D/a/B.txt" -a ! -e "$D/a/_c.txt" -a ! -e "$D/a/Z_y.txt" -a ! -e "$D/a/a.txt"
  check "non-C locale: kept file stays" test -f "$D/a/keep.txt"
else
  echo "skip - en_US.UTF-8 locale not installed here"
fi
teardown

# 4e. Migrations already applied to the prod DB must never be deleted from the server, even if git dropped them.
setup
mkdir -p "$D/apps/api/alembic/versions"; echo m > "$D/apps/api/alembic/versions/0010_x.py"
printf 'apps/api/alembic/versions/0010_x.py\napps/web/src/about/About.tsx\n' > "$D/.deploy-manifest"
printf 'apps/web/src/keep/Keep.tsx\n' > "$T/new"
out="$(run_prune "$D" "$T/new" 2>&1)"
check "migration file survives" test -f "$D/apps/api/alembic/versions/0010_x.py"
check "migration refusal reported" grep -q "REFUSED unsafe path: apps/api/alembic/versions/0010_x.py" <<< "$out"
check "other stale files are still removed" test ! -e "$D/apps/web/src/about/About.tsx"
teardown

# 4f. Bootstrap: the seeded "previous" manifest is an OVERRIDE file, never written to .deploy-manifest.
# A dry run with it deletes nothing and writes no .deploy-manifest, so a following plain run deletes nothing.
setup
printf 'apps/web/src/about/About.tsx\napps/web/src/keep/Keep.tsx\n' > "$T/seed"
printf 'apps/web/src/keep/Keep.tsx\n' > "$T/new"
out="$(run_prune "$D" "$T/new" --dry-run "$T/seed" 2>&1)"
check "bootstrap dry run names the stale file" grep -q "would remove apps/web/src/about/About.tsx" <<< "$out"
check "bootstrap dry run deletes nothing" test -f "$D/apps/web/src/about/About.tsx"
check "bootstrap dry run writes no .deploy-manifest" test ! -e "$D/.deploy-manifest"
run_prune "$D" "$T/new" >/dev/null 2>&1
check "plain run after a bootstrap dry run deletes nothing" test -f "$D/apps/web/src/about/About.tsx"
check "plain run after it installs the new manifest" cmp -s "$T/new" "$D/.deploy-manifest"
teardown

# 4g. A real bootstrap run removes the historical leftovers and installs the NEW manifest as usual.
setup
printf 'apps/web/src/about/About.tsx\napps/web/src/keep/Keep.tsx\n' > "$T/seed"
printf 'apps/web/src/keep/Keep.tsx\n' > "$T/new"
run_prune "$D" "$T/new" "" "$T/seed" >/dev/null 2>&1
check "real bootstrap removes the leftover" test ! -e "$D/apps/web/src/about/About.tsx"
check "real bootstrap keeps tracked files" test -f "$D/apps/web/src/keep/Keep.tsx"
check "real bootstrap installs the NEW manifest" cmp -s "$T/new" "$D/.deploy-manifest"
teardown

# 5. A directory named in a manifest is refused, not deleted.
setup
printf 'apps/web/src/about\napps/web/src/keep/Keep.tsx\n' > "$D/.deploy-manifest"
printf 'apps/web/src/keep/Keep.tsx\n' > "$T/new"
run_prune "$D" "$T/new" >/dev/null 2>&1
check "directory refused" test -f "$D/apps/web/src/about/About.tsx"
teardown

# 6. Dry run lists but removes nothing and leaves the old manifest in place.
setup
printf 'apps/web/src/about/About.tsx\napps/web/src/keep/Keep.tsx\n' > "$D/.deploy-manifest"
cp "$D/.deploy-manifest" "$T/old-copy"
printf 'apps/web/src/keep/Keep.tsx\n' > "$T/new"
out="$(run_prune "$D" "$T/new" --dry-run)"
check "dry run keeps the file" test -f "$D/apps/web/src/about/About.tsx"
check "dry run names it" grep -q "would remove apps/web/src/about/About.tsx" <<< "$out"
check "dry run keeps the old manifest" cmp -s "$T/old-copy" "$D/.deploy-manifest"
teardown

# 7. Paths with spaces are handled.
setup
mkdir -p "$D/docs"; echo x > "$D/docs/a file.md"
printf 'docs/a file.md\napps/web/src/keep/Keep.tsx\n' > "$D/.deploy-manifest"
printf 'apps/web/src/keep/Keep.tsx\n' > "$T/new"
run_prune "$D" "$T/new" >/dev/null
check "path with a space removed" test ! -e "$D/docs/a file.md"
teardown

# 8. An empty or missing new manifest is fatal and removes nothing (a broken upload must not wipe the tree).
setup
printf 'apps/web/src/keep/Keep.tsx\n' > "$D/.deploy-manifest"
: > "$T/new"
check "empty new manifest fails" bash -c '! bash "$0" "$1" "$2" 0 >/dev/null 2>&1' "$PRUNE" "$D" "$T/new"
check "empty new manifest removes nothing" test -f "$D/apps/web/src/keep/Keep.tsx"
teardown

# 9. A truncated upload (fewer lines than the sender wrote) is fatal and removes nothing.
setup
printf 'apps/web/src/about/About.tsx\napps/web/src/keep/Keep.tsx\n' > "$D/.deploy-manifest"
printf 'apps/web/src/keep/Keep.tsx\n' > "$T/new"
check "line-count mismatch fails" bash -c '! bash "$0" "$1" "$2" 2 >/dev/null 2>&1' "$PRUNE" "$D" "$T/new"
check "line-count mismatch removes nothing" test -f "$D/apps/web/src/about/About.tsx"
teardown

# 10. Removing more than 20 files and over 25% of the previous deploy stops unless forced.
setup
: > "$D/.deploy-manifest"
for i in $(seq 1 40); do
  echo x > "$D/apps/web/src/keep/f$i.tsx"
  echo "apps/web/src/keep/f$i.tsx" >> "$D/.deploy-manifest"
done
seq 1 10 | sed 's|.*|apps/web/src/keep/f&.tsx|' > "$T/new"
check "mass removal refused" bash -c '! bash "$0" "$1" "$2" 10 >/dev/null 2>&1' "$PRUNE" "$D" "$T/new"
check "mass removal removes nothing" test -f "$D/apps/web/src/keep/f40.tsx"
RHAPTO_PRUNE_FORCE=1 run_prune "$D" "$T/new" >/dev/null
check "forced mass removal proceeds" test ! -e "$D/apps/web/src/keep/f40.tsx"
check "forced mass removal keeps the rest" test -f "$D/apps/web/src/keep/f10.tsx"
teardown

if [[ $fails -gt 0 ]]; then echo "$fails test(s) failed"; exit 1; fi
echo "all deploy-prune tests passed"
