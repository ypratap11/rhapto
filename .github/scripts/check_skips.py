"""Fail CI when pytest skipped anything it should have run.

A second, independent check next to RHAPTO_TEST_REQUIRE_SERVICES: that switch covers the two skips we
know about (Postgres, Redis); this reads what actually happened and catches any skip added later.

Usage: python check_skips.py <junit.xml>
"""

from __future__ import annotations

import sys

# stdlib parser on purpose: the only input is the JUnit file pytest wrote a step earlier in the same
# job, never outside data, and expat does not fetch external entities.
import xml.etree.ElementTree as ET

# Skips that are correct in CI: a live call to a paid API needs a key, and CI has none by design.
ALLOWED = ("test_live_gemini_accepts_every_engine_schema",)


def main(path: str) -> int:
    root = ET.parse(path).getroot()
    cases = list(root.iter("testcase"))
    if not cases:
        print(f"::error::{path} records no tests at all")
        return 1
    unexpected = []
    allowed = 0
    for case in cases:
        skipped = case.find("skipped")
        if skipped is None:
            continue
        name = case.get("name", "")
        if name.startswith(ALLOWED):
            allowed += 1
            continue
        where = f"{case.get('classname', '')}::{name}"
        unexpected.append(f"{where}: {skipped.get('message', '').strip()}")
    print(f"{len(cases)} tests, {allowed} allowed skips, {len(unexpected)} unexpected skips")
    for line in unexpected:
        print(f"::error::unexpected skip {line}")
    return 1 if unexpected else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
