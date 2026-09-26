"""Fail if any organisation name from the real profile appears in the repository.

Two scopes, because scanning only one of them is what let a real leak sit in a public repo for
weeks while this check reported success:

    python scripts/check-no-personal-data.py              # git-tracked files in the working tree
    python scripts/check-no-personal-data.py --history     # every object in git history

The working-tree scan is the pre-commit check. The history scan is the pre-publish check, and it is
the one that matters before a repository is made public or a branch is pushed for the first time:
correcting a file does not correct the commit that introduced it. On 2026-09-25 this repository was
public with an employer name in an old blob AND two employer names, with employment dates, in a
reachable commit message. The working-tree check was green throughout, because it had no reason not
to be -- the working tree was clean. Commit messages in particular are easy to forget: they are not
files, no linter reads them, and they cannot be fixed without rewriting history.

Runs as a no-op when profile/ is absent (for example in CI).
"""

from __future__ import annotations

import pathlib
import subprocess
import sys

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
MIN_LEN = 4


def needles() -> set[str]:
    """Organisation names from the real profile. Never printed in full by the history scan."""
    blocks_path = ROOT / "profile" / "blocks.yaml"
    if not blocks_path.exists():
        return set()
    data = yaml.safe_load(blocks_path.read_text(encoding="utf-8")) or {}
    return {
        str(b["org"]).strip()
        for b in data.get("blocks", [])
        if b.get("org") and len(str(b["org"]).strip()) >= MIN_LEN
    }


def scan_working_tree(orgs: set[str]) -> list[str]:
    tracked = subprocess.run(
        ["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout.split("\n")
    hits = []
    for rel in filter(None, tracked):
        path = ROOT / rel
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore").lower()
        hits.extend(f"{rel} contains org name from profile/: {n!r}" for n in orgs if n.lower() in text)
    return hits


def scan_history(orgs: set[str]) -> list[str]:
    """Every blob, commit message and path name in the object database.

    Reports WHERE a name was found, never the name itself: this scan is the one likely to be run
    with its output pasted into an issue or a terminal someone is sharing.
    """
    lowered = {n.lower().encode() for n in orgs}

    paths_by_sha: dict[str, set[str]] = {}
    listing = subprocess.run(
        ["git", "rev-list", "--objects", "--all"], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout
    for line in listing.splitlines():
        parts = line.split(" ", 1)
        if len(parts) == 2 and parts[1]:
            paths_by_sha.setdefault(parts[0], set()).add(parts[1])

    catalogue = subprocess.run(
        ["git", "cat-file", "--batch-all-objects", "--batch-check=%(objectname) %(objecttype)"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout

    hits: list[str] = []
    proc = subprocess.Popen(
        ["git", "cat-file", "--batch"], cwd=ROOT, stdin=subprocess.PIPE, stdout=subprocess.PIPE
    )
    assert proc.stdin and proc.stdout
    for line in catalogue.splitlines():
        if not line.strip():
            continue
        sha, otype = line.split()
        if otype not in ("blob", "commit", "tag"):
            continue
        proc.stdin.write(f"{sha}\n".encode())
        proc.stdin.flush()
        header = proc.stdout.readline().decode().split()
        if len(header) < 3:
            continue
        body = proc.stdout.read(int(header[2]) + 1)[:-1].lower()
        if any(n in body for n in lowered):
            where = ", ".join(sorted(paths_by_sha.get(sha, set()))) or f"{otype} {sha[:12]}"
            hits.append(f"{otype} {sha[:12]} ({where}) contains an org name from profile/")
    proc.stdin.close()
    proc.wait()

    for sha, paths in paths_by_sha.items():
        for path in paths:
            if any(n in path.lower().encode() for n in lowered):
                hits.append(f"path name {path!r} contains an org name from profile/")

    return hits


def main() -> int:
    history = "--history" in sys.argv[1:]
    orgs = needles()
    if not orgs:
        print("profile/blocks.yaml absent; nothing to check")
        return 0

    hits = scan_history(orgs) if history else scan_working_tree(orgs)
    scope = "git history" if history else "tracked files"
    for hit in hits:
        print(f"LEAK: {hit}", file=sys.stderr)
    if hits:
        print(
            f"\n{len(hits)} leak(s) in {scope}."
            + (
                "\nA history leak cannot be fixed by editing a file -- it needs a history rewrite."
                if history
                else ""
            ),
            file=sys.stderr,
        )
        return 1
    print(f"clean: no org name from profile/ in {scope} ({len(orgs)} names checked)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
