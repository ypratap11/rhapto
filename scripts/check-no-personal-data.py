"""Fail if any organisation name from the real profile appears in git-tracked files.

Runs as a no-op when profile/ is absent (for example in CI).
Usage: uv run --project apps/api python scripts/check-no-personal-data.py
"""

from __future__ import annotations

import pathlib
import subprocess
import sys

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
MIN_LEN = 4


def main() -> int:
    blocks_path = ROOT / "profile" / "blocks.yaml"
    if not blocks_path.exists():
        print("profile/blocks.yaml absent; nothing to check")
        return 0
    data = yaml.safe_load(blocks_path.read_text(encoding="utf-8")) or {}
    needles = {
        str(b["org"]).strip()
        for b in data.get("blocks", [])
        if b.get("org") and len(str(b["org"]).strip()) >= MIN_LEN
    }
    tracked = subprocess.run(
        ["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout.split("\n")
    hits: list[tuple[str, str]] = []
    for rel in filter(None, tracked):
        path = ROOT / rel
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore").lower()
        hits.extend((rel, n) for n in needles if n.lower() in text)
    for rel, needle in hits:
        print(f"LEAK: {rel} contains org name from profile/: {needle!r}", file=sys.stderr)
    return 1 if hits else 0


if __name__ == "__main__":
    sys.exit(main())
